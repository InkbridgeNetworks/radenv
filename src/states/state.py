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

"""A state class to manage the state of the multi-server test environment."""

import asyncio
from collections.abc import Callable
import logging

from src import logging_helper
from src.Validator import Validator
from src.check import Check


class State:
    """
    A class to represent the state of the multi-server test environment.
    """

    validator: Validator
    _timeout_handle: asyncio.TimerHandle

    def __init__(
        self,
        name: str,
        description: str = "",
        actions: list[callable] | None = None,  # TODO: "actions" or "events"?
        checks: list[Check] | None = None,
        timeout: int = 15,
        loop: asyncio.AbstractEventLoop | None = None,
        logger: logging.Logger = logging_helper.get_logger(),
    ) -> None:
        self.name = name
        self.description = description
        self.logger = logger

        # actions is a list of callables that take no arguments and return None
        self.actions: list[Callable[[], None]] = (
            actions if actions is not None else []
        )

        self.timeout = timeout
        self._timeout_handle = None

        try:
            loop = loop or asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        self.state_completed = loop.create_future()

        self.validator = Validator(
            checks if checks is not None else [],
            self.state_completed,
            self.logger,
        )

        # When the state is marked as completed, cancel the timeout
        self.state_completed.add_done_callback(
            lambda _: (
                self._timeout_handle.cancel() if self._timeout_handle else None
            )
        )

        self.logger.debug(
            "State initialized with %d actions and timeout of %d seconds.",
            len(self.actions),
            self.timeout,
        )

    async def enter_state(self) -> None:
        """
        Enter the state and execute all actions.
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # Set up the timeout to mark the state as completed after the specified duration
        def on_timeout() -> None:
            self.logger.info("State timed out after %d seconds", self.timeout)

            if not self.state_completed.done():
                self.logger.info("Marking state as completed due to timeout.")
                self.state_completed.set_result(True)

        self._timeout_handle = loop.call_later(self.timeout, on_timeout)

        for action in self.actions:
            self.logger.debug("Executing action: %s", action.__name__)

            await loop.run_in_executor(None, action, self.logger)

    async def wait_for_completion(self) -> None:
        """
        Wait for the state to be marked as completed.
        """
        await self.state_completed
