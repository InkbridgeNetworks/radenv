"""Copyright (C) 2026 Network RADIUS SAS (legal@networkradius.com)

This software may not be redistributed in any form without the prior
written consent of Network RADIUS.

THIS SOFTWARE IS PROVIDED BY THE AUTHOR AND CONTRIBUTORS ``AS IS'' AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS
OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF
SUCH DAMAGE."""

"""A Test object to manage the multi-server tests."""

import asyncio
from functools import partial
import logging
import os
from pathlib import Path
from python_on_whales import DockerClient

from src import ExitCodes, logging_helper
from src.states.state import State
from src.listener import Listener, SocketListener, FileListener
from src.tap_logger import TAPLogger


def create_test_logger(name: str, env_name: str) -> logging.Logger:
    """
    Create a logger for the test with the specified name.

    Args:
        name (str): The name of the test.
        env_name (str): The environment name for the test.

    Returns:
        logging.Logger: Configured logger for the test.
    """
    logger = logging.getLogger("Test." + name + "." + env_name)
    main_logger = logging_helper.get_logger()
    logger.setLevel(main_logger.level)

    # Copy any handlers from the main logger to this one
    for h in main_logger.handlers:
        logger.addHandler(h)

    return logger

def create_container_logger(name: str, log_dir: Path = Path("logs")) -> logging.Logger:
    """
    Create a logger for a container

    Args:
        name (str): The name of the container.
        log_dir (Path): The directory where container log files will be located.

    Returns:
        logging.Logger: Configured logger for the container.
    """

    # Set string path for FileHandler
    container_log_file = Path(log_dir, f"{name}.log")

    # Setup logger in dedicated namespace
    logger = logging.getLogger(f"Container.{name}")
    main_logger = logging_helper.get_logger()
    logger.setLevel(main_logger.level)
    # Prevent container log lines from propagating to parent/root handlers
    # (e.g., the console), which would flood the test output.
    logger.propagate = False

    container_file_handler = logging.FileHandler(container_log_file, encoding="utf-8")
    container_file_handler.setLevel(main_logger.level)
    container_file_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(container_file_handler)

    logger.debug("Created logger for container: %s (log file: %s)", name, container_log_file)

    return logger

class Test:
    """
    A class to represent a multi-server test.
    """

    listener: Listener

    def __init__(
        self,
        name: str,
        states: list[State],
        compose_file: Path,
        timeout: float,
        listener_dest: Path,
        detail_level: int,
        loop: asyncio.AbstractEventLoop,
        logger: logging.Logger = None,
        force_build: bool = False,
        project_name: str | None = None,
        log_dir: Path = Path("logs"),
        **metadata,
    ) -> None:
        self.name = name
        self.states = states
        self.compose_file = compose_file
        self.timeout = timeout
        self.loop = loop
        self.logger = logger or create_test_logger(name, compose_file.stem)
        self.detail_level = detail_level
        self.force_build = force_build
        self.log_dir = log_dir
        self.queue: asyncio.Queue = asyncio.Queue()
        self.listener_task: asyncio.Task = None
        if project_name is None:
            project_name = self.name
        self.client = DockerClient(
            compose_files=[self.compose_file], compose_project_name=project_name
        )
        self.__ready_future: asyncio.Future = self.loop.create_future()
        match listener_dest.suffix:
            case ".sock":
                self.listener = SocketListener(
                    listener_dest, self.queue, self.__ready_future, self.logger
                )
            case ".txt":
                self.listener = FileListener(
                    listener_dest, self.queue, self.__ready_future, self.logger
                )

        # Set the environment variable for the listener config to use
        os.environ["TEST_LOGGER_CONFIG"] = str(self.listener.listener_fr_config)

        self.logging_task: asyncio.Task = None
        self.container_logging_tasks = []
        self.validation_task: asyncio.Task = None
        self.metadata = metadata

    async def __setup_test(self, log_containers: bool) -> None:
        """
        Sets up the test by initializing necessary resources.

        Args:
            log_containers (bool): When True (the default), per-container logs
                are streamed to `log_dir/<container>.log`.  The compose-up
                error path captures logs unconditionally so a failed start
                still leaves a diagnostic trail; the flag only controls the
                steady-state streaming on a healthy start.
        """
        self.logger.info("Setting up test: %s", self.name)

        self.listener_task = self.loop.create_task(self.listener.start())

        # Wait for the listener to be ready
        await self.__ready_future

        self.logger.info(
            "Listener is ready. Beginning test setup for %s.", self.name
        )

        # Build Docker Compose services only if forced or if any
        # service defines a build context.
        config = self.client.compose.config()
        buildable = [
            name for name, svc in config.services.items()
            if svc.build is not None
        ]
        if self.force_build or buildable:
            self.logger.info("Building images: %s", ", ".join(buildable) if buildable else "all")
            self.client.compose.build(buildable if buildable else None, quiet=True)

        # Start the Docker Compose services.
        #
        # Wrap the up() call so that if it fails part-way (e.g. a
        # dependency became unhealthy), we still enumerate whatever
        # containers compose DID create and capture their logs.  The
        # exit state of a crashed container is the main thing an
        # operator needs to diagnose the failure; letting the exception
        # propagate with no log files leaves them blind.
        compose_up = partial(
            self.client.compose.up,
            detach=True,
            quiet=True,
        )
        up_exc: Exception | None = None
        try:
            await self.loop.run_in_executor(None, compose_up)
        except Exception as e:
            up_exc = e
            self.logger.error("docker compose up failed: %s", e)

        # Enumerate every container compose is aware of - including
        # stopped / exited ones - so a container that crashed on
        # startup still gets its final output captured.
        containers = self.client.compose.ps(all=True)

        # Stream container logs when requested OR when compose up
        # failed (in which case we override `log_containers` so the
        # operator always has something to diagnose from).
        do_stream = log_containers or up_exc is not None

        for container in containers:
            if do_stream:
                # One log file per container, in `self.log_dir`.
                container_logger = create_container_logger(container.name, self.log_dir)

                async def stream_container_logs(container_name=container.name, container_logger=container_logger) -> None:
                    container_logger.info("Starting log stream for container: %s", container_name)
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "docker", "logs", "-f", container_name,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.STDOUT,
                        )
                        while True:
                            line = await proc.stdout.readline()
                            if not line:
                                break
                            container_logger.info(line.rstrip(b"\n").decode("utf-8", errors="backslashreplace"))
                    except Exception as e:
                        container_logger.error("Error while streaming logs for container %s: %s", container_name, e)

                task = self.loop.create_task(stream_container_logs())
                self.container_logging_tasks.append(task)

            self.logger.debug("Container %s is running.", container.name)

        # If compose up failed, propagate the error now that per-container
        # log files have been seeded with whatever `docker logs` will
        # yield.  Yield briefly first so the streaming tasks can flush
        # any already-buffered output before teardown cancels them.
        if up_exc is not None:
            await asyncio.sleep(0.5)
            raise up_exc

    async def __teardown_test(self) -> None:
        """
        Cleans up resources used by the test, such as the listener task and socket file.
        """
        self.logger.info("Cleaning up test: %s", self.name)

        if self.logging_task:
            self.logging_task.cancel()
            try:
                await self.logging_task
            except asyncio.CancelledError:
                pass

        if self.validation_task:
            self.validation_task.cancel()
            try:
                await self.validation_task
            except asyncio.CancelledError:
                pass

        # Tear down the containers
        compose_down = partial(
            self.client.compose.down,
            volumes=True,
            remove_orphans=True,
            quiet=True,
        )
        await self.loop.run_in_executor(None, compose_down)

        # Ensure all containers are stopped
        containers = self.client.compose.ps()
        if containers:
            for container in containers:
                self.logger.warning(
                    "Container %s is still running during teardown.",
                    container.name,
                )
        else:
            self.logger.debug("All containers have been stopped.")

        if self.listener_task:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass

        # Shut down the listener
        await self.listener.stop()

        self.logger.info("Cleanup complete for test: %s", self.name)

        # Clean up any container logging tasks
        for task in self.container_logging_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def run(self, log_containers: bool = True) -> int:
        """
        Runs the test by orchestrating the execution of states and managing resources.

        Args:
            log_containers (bool): Whether to stream container logs to
                per-container files under `log_dir`.  Defaults to True.
                A failed compose-up forces streaming on regardless, so
                the operator always has a diagnostic trail.

        Returns:
            int: exit code based on ExitCodes enum indicating the result of the test execution.

        Raises:
            Exception: Any unexpected exception raised during setup, execution, or teardown
                of the test is propagated to the caller.
        """
        try:
            await self.__setup_test(log_containers)

            test_task = self.loop.create_task(self.__run())
            exit_code = await asyncio.wait_for(test_task, timeout=self.timeout)
        except asyncio.TimeoutError:
            self.logger.error(
                "Test %s timed out after %.2f seconds", self.name, self.timeout
            )
            # Set exit code based on timeout error
            exit_code = ExitCodes.TIMEOUT
        finally:
            await self.__teardown_test()

        # Return exit code based on test task
        return exit_code

    async def __run(self) -> int:
        """
        Internal method to run the test states sequentially.

        Returns:
            int: exit code based on ExitCodes enum indicating the result of the test execution.
        """
        self.logger.info("Starting test: %s", self.name)
        self.logger.info("Starting test states for %s.", self.name)

        test_has_failures = []
        detailed = self.detail_level > 0

        tap_path = Path(self.log_dir, f"{self.name}.tap")
        with open(tap_path, "w", encoding="utf-8") as tap_file:
            tap = TAPLogger(tap_file)
            tap.version()
            for k, v in self.metadata.items():
                if v is not None:
                    tap.comment(f"{k}: {v}")
            tap.plan(len(self.states))

            for state in self.states:
                self.logger.debug(
                    "Processing state: %s - %s", state.name, state.description
                )

                # Register new validator for the current state
                # Clear the message queue to avoid processing old messages
                self.logger.debug("Clearing message queue for new state.")
                while not self.queue.empty():
                    try:
                        self.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                # Next, setup the state's validator
                self.logger.debug("Setting up validator for state: %s", state.name)
                if self.validation_task:
                    # Swap out the previous validation task
                    self.validation_task.cancel()
                    try:
                        await self.validation_task
                    except asyncio.CancelledError:
                        pass
                self.validation_task = self.loop.create_task(
                    state.validator.start_validating(self.queue)
                )

                # Now, enter the state
                self.logger.debug("Entering state: %s", state.name)
                await state.enter_state()

                # Wait for the state to complete
                self.logger.debug("Waiting for state completion: %s", state.name)
                await state.wait_for_completion()

                self.logger.info("State completed: %s", state.name)

                result_str = state.validator.get_results_str(detailed)
                test_state_has_failures = state.validator.has_failures()
                test_has_failures.append(test_state_has_failures)

                self.logger.info(
                    " %s%s%s",
                    f"Test.{self.name}.{self.compose_file.stem}",
                    result_str,
                    f"(State: {state.name}{f', Has Failures: {test_state_has_failures}' if test_state_has_failures else ''})",
                )

                tap.subtest(state.name, state.validator.get_tap_results(detailed), detailed)

        self.logger.info("Test completed: %s", self.name)

        return ExitCodes.VALIDATION_FAILURE if (True in test_has_failures) else ExitCodes.SUCCESS
