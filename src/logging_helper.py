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

"""
Setup logging for the application.
"""

import logging
import sys
from termcolor import colored

logger = logging.getLogger("radenv")
file_logger = logging.getLogger("file")


def setup_logging(level: int = logging.INFO) -> None:
    """
    Set up logging configuration.

    Args:
        level (int): Logging level. Defaults to logging.INFO.
    """
    # Add a log handler for the INFO level
    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(lambda record: record.levelno == logging.INFO)
    info_handler.setFormatter(logging.Formatter("%(message)s"))

    # Create a handler that will make all Warning messages yellow
    warning_handler = logging.StreamHandler(sys.stderr)
    warning_handler.setLevel(logging.WARNING)
    warning_handler.addFilter(lambda record: record.levelno == logging.WARNING)
    warning_handler.setFormatter(
        logging.Formatter(
            colored(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "yellow",
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # Create a handler that will make all Error messages red
    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.ERROR)
    error_handler.addFilter(lambda record: record.levelno >= logging.ERROR)
    error_handler.setFormatter(
        logging.Formatter(
            colored(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s", "red"
            ),
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.setLevel(level)
    logger.addHandler(info_handler)
    logger.addHandler(warning_handler)
    logger.addHandler(error_handler)

    logger.info(
        "Logging is set up with level: %s", logging.getLevelName(level)
    )


def add_debug_logging(logger_obj: logging.Logger = logger) -> None:
    """
    Add debug logging handler to the logger.

    Args:
        logger_obj (logging.Logger): The logger to add debug logging to. Defaults to the main logger.
    """
    debug_handler = logging.StreamHandler(sys.stderr)
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.addFilter(lambda record: record.levelno == logging.DEBUG)
    debug_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger_obj.setLevel(logging.DEBUG)
    logger_obj.addHandler(debug_handler)


def add_name_filter(
    names: list[str], logger_obj: logging.Logger = logger
) -> None:
    """
    Add a filter to the logger to only log messages from a specific name.

    Args:
        names (list[str]): The list of names to filter logs by.
        logger_obj (logging.Logger): The logger to add the filter to. Defaults to the main logger.
    """

    class NameFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return any(record.name.startswith(name + ".") for name in names)

    logger_obj.addFilter(NameFilter())

    # Update existing handlers to apply the new filter
    for handler in logger_obj.handlers:
        handler.addFilter(NameFilter())

    logger.debug("Added name filter for: %s", ", ".join(names))


def add_message_filter(
    substrings: list[str], logger_obj: logging.Logger = logger
) -> None:
    """
    Add a filter to the logger to only log messages containing a specific substring.

    Args:
        substrings (list[str]): The list of substrings to filter logs by.
        logger_obj (logging.Logger): The logger to add the filter to. Defaults to the main logger.
    """

    class MessageFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            return any(
                substring in record.getMessage() for substring in substrings
            )

    logger_obj.addFilter(MessageFilter())

    # Update existing handlers to apply the new filter
    for handler in logger_obj.handlers:
        handler.addFilter(MessageFilter())

    logger.debug(
        "Added message filter for substring: %s", ", ".join(substrings)
    )


def get_logger_name() -> str:
    """
    Get the name of the configured logger.

    Returns:
        str: The name of the configured logger.
    """
    return logger.name


def get_logger() -> logging.Logger:
    """
    Get the configured logger.

    Returns:
        logging.Logger: The configured logger.
    """
    return logging.getLogger(get_logger_name())


def setup_file_logging(
    file_path: str, level: int = logging.INFO, mode: str = "w"
) -> None:
    """
    Set up file logging for the logger.

    Args:
        file_path (str): The path to the log file.
        level (int): The logging level for the file. Defaults to logging.DEBUG.
        mode (str): The file mode, e.g., 'w' for write, 'a' for append. Defaults to 'w'.
    """
    file_handler = logging.FileHandler(file_path, mode)
    file_handler.setLevel(level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(message)s",
        )
    )

    file_logger.setLevel(level)
    file_logger.addHandler(file_handler)

    logger.debug(
        "File logging set up at %s with level %s",
        file_path,
        logging.getLevelName(level),
    )


def get_file_logger_name() -> str:
    """
    Get the name of the configured file logger.

    Returns:
        str: The name of the configured file logger.
    """
    return file_logger.name


def get_file_logger() -> logging.Logger:
    """
    Get the configured file logger.

    Returns:
        logging.Logger: The configured file logger.
    """
    return logging.getLogger(get_file_logger_name())
