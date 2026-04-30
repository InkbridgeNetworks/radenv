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

"""A listener to handle incoming messages from containers."""

from abc import ABC, abstractmethod
import asyncio
from enum import Enum
import logging
from pathlib import Path
import platform

import aiofiles
import json
from watchfiles import awatch, Change

from src import logging_helper


class ListenerType(Enum):
    """
    Enum for different listener types.
    """

    SOCKET = 0
    FILE = 1
    # Add other listener types as needed


class Listener(ABC):
    """
    An abstract base class for listeners that handle incoming messages.
    """

    listener_dest: Path
    listener_fr_config: Path = None # Filename for the FreeRADIUS config to use this listener
    msg_queue: asyncio.Queue
    ready_future: asyncio.Future
    logger: logging.Logger

    def __init__(
        self,
        listener_dest: Path,
        msg_queue: asyncio.Queue,
        ready_future: asyncio.Future,
        logger: logging.Logger = logging_helper.get_logger(),
    ) -> None:
        self.listener_dest = listener_dest
        self.msg_queue = msg_queue
        self.ready_future = ready_future
        self.logger = logger
        super().__init__()

    @abstractmethod
    async def start(self) -> None:
        """
        Starts the listener.
        """
        raise NotImplementedError(
            "start method must be implemented by subclasses."
        )

    async def stop(self) -> bool:
        """
        Stops and cleans up the listener.

        Returns:
            bool: True if the listener was successfully stopped and cleaned up, False otherwise.
        """
        if self.listener_dest.exists():
            try:
                self.logger.debug(
                    "Removing listener socket at %s", self.listener_dest
                )
                self.listener_dest.unlink()
                self.logger.info(
                    "Listener: Removed logging destination %s",
                    self.listener_dest,
                )
                return True
            except OSError as e:
                self.logger.error(
                    "Listener: Failed to remove logging destination %s: %s",
                    self.listener_dest,
                    e,
                )
                return False
        self.logger.info(
            "Listener: Logging destination %s does not exist, nothing to remove",
            self.listener_dest,
        )
        return True

    def _process_message(self, message: str) -> None:
        """
        Processes a single message and puts it into the message queue.

        Args:
            message (str): The incoming message.
        """
        self.logger.debug("Processing message: %s", message)

        try:
            self.msg_queue.put_nowait(json.loads(message))
        except json.JSONDecodeError as e:
            self.logger.warning(
                "Failed to decode message as JSON: %s. Error: %s",
                message,
                e,
            )


class SocketListener(Listener):
    """
    A class to represent a listener that handles incoming messages from containers.
    """

    listener_fr_config: Path = Path("linelog_socket")

    async def __handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Handles incoming client connections and processes messages.

        Args:
            reader (asyncio.StreamReader): Reader for the incoming data.
            writer (asyncio.StreamWriter): Writer for sending responses.
        """
        self.logger.debug("Client connected.")
        try:
            while True:
                data = await reader.readuntil(b"\n")
                message = data.rstrip(b"\n")

                self._process_message(message.decode("utf-8", errors="ignore"))
        except asyncio.IncompleteReadError:
            self.logger.debug("Client disconnected.")
        finally:
            writer.close()
            await writer.wait_closed()
            self.logger.debug("Client disconnected.")

    async def start(self) -> None:
        """
        Starts the listener server.
        """
        self.logger.debug("Starting listener on %s", self.listener_dest)

        if self.listener_dest.exists():
            # The path may be a directory if compose tried to mount it as a volume before
            # we created it
            self.logger.debug(
                "Socket path %s exists as a %s, removing it.",
                self.listener_dest,
                "directory" if self.listener_dest.is_dir() else "file",
            )
            if self.listener_dest.is_dir():
                self.listener_dest.rmdir()
            else:
                self.listener_dest.unlink()

        try:
            server = await asyncio.start_unix_server(
                self.__handle_connection,
                path=self.listener_dest,
            )

            # Make sure the socket is world writable so containers can connect
            self.listener_dest.chmod(0o777)
        except PermissionError as e:
            self.logger.error("Permission error starting listener: %s", e)
            return

        self.logger.debug("Listener started, setting ready future.")

        # Notify that the server is ready
        if not self.ready_future.done():
            self.ready_future.set_result(True)

        async with server:
            self.logger.debug("Listener running.")
            await server.serve_forever()


class FileListener(Listener):
    """
    A class to represent a listener that writes incoming messages to a file.
    """

    listener_fr_config: Path = Path("linelog_file")
    listener_source: aiofiles.threadpool.text.AsyncTextIOWrapper = None

    async def start(self) -> None:
        """
        Starts the file listener.
        """
        self.logger.debug("Starting file listener on %s", self.listener_dest)

        # Remove existing file if it exists
        if self.listener_dest.exists():
            self.logger.debug(
                "Listener destination %s exists, removing it.",
                self.listener_dest,
            )

            if self.listener_dest.is_dir():
                self.listener_dest.rmdir()
            else:
                self.listener_dest.unlink()

        # "w+" creates + truncates so a reused environment doesn't
        # carry over leftover lines from the previous run.
        self.listener_source = await aiofiles.open(
            self.listener_dest, mode="w+", encoding="utf-8"
        )

        # Notify that the listener is ready
        if not self.ready_future.done():
            self.ready_future.set_result(True)

        # Wait for the file to be created and start reading from it
        try:
            self.logger.debug(
                "Starting to watch for changes in %s",
                self.listener_dest.parent,
            )
            async for changes in awatch(
                self.listener_dest.parent,
                force_polling=platform.system() == "Darwin",
            ):  # macOS requires polling
                for change in changes:
                    change_type, change_path = change

                    # Only process modifications to the log file
                    if Path(change_path) != self.listener_dest:
                        continue

                    match change_type:
                        case Change.added:
                            self.logger.debug(
                                "Detected addition of file %s",
                                self.listener_dest,
                            )
                            self.listener_source = await aiofiles.open(
                                self.listener_dest, mode="r", encoding="utf-8"
                            )
                            self.logger.debug(
                                "Opened listener source for file %s",
                                self.listener_dest,
                            )
                            # Process any lines already in the file when it's first created
                            async for line in self.listener_source:
                                message = line.strip()
                                self.logger.debug(
                                    "Received message: %s", message
                                )
                                self._process_message(message)

                            self.logger.debug(
                                "Processed all existing lines in file %s",
                                self.listener_dest,
                            )
                        case Change.deleted:
                            self.logger.debug(
                                "Detected deletion of file %s",
                                self.listener_dest,
                            )
                            if self.listener_source:
                                await self.listener_source.close()
                                self.listener_source = None
                                self.logger.debug(
                                    "Closed listener source for file %s",
                                    self.listener_dest,
                                )
                        case Change.modified:
                            self.logger.debug(
                                "Detected modification to file %s",
                                self.listener_dest,
                            )
                            if self.listener_source:
                                async for line in self.listener_source:
                                    message = line.strip()
                                    self.logger.debug(
                                        "Received message: %s", message
                                    )
                                    self._process_message(message)

                                self.logger.debug(
                                    "Processed all new lines in file %s",
                                    self.listener_dest,
                                )
                        case _:
                            pass
        except FileNotFoundError:
            self.logger.warning(
                "Listener destination %s not found or removed.",
                self.listener_dest,
            )
            return

        self.logger.debug("File listener on %s stopped.", self.listener_dest)

    async def stop(self) -> bool:
        """
        Stops and cleans up the file listener.

        Returns:
            bool: True if the listener was successfully stopped and cleaned up, False otherwise.
        """

        loop = asyncio.get_running_loop()
        if loop.is_running() and self.listener_source:
            self.logger.debug(
                "Closing listener source for file %s", self.listener_dest
            )
            await self.listener_source.close()

        # Backup the file before removing it
        if self.listener_dest.exists():
            backup_path = Path(str(self.listener_dest) + ".bak")
            self.logger.debug(
                "Backing up log file %s to %s",
                self.listener_dest,
                backup_path,
            )
            self.listener_dest.rename(backup_path)

        return await super().stop()
