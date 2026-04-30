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
Validator object
"""

import asyncio
import logging

from termcolor import colored

from src.check import Check
from src import logging_helper


class Validator:
    """
    Validator class that will take care of all of the trigger validation
    """

    def __init__(
        self,
        checks: list[Check],
        state_completed: asyncio.Future,
        logger: logging.Logger = logging_helper.get_logger(),
    ) -> None:
        self.__checks = {check.name: check for check in checks}
        self.__state_completed = state_completed
        self.__logger = logger

    def get_results_str(self, detailed: bool = False) -> str:
        """
        Get a string representation of the validation results.

        Args:
            detailed (bool, optional): Whether to include matched rules in the output.
                Defaults to False.

        Returns:
            str: A string representation of the results.
        """
        # TODO: This should be reworked to output TAP format
        header = "Validation Results"
        detailed_tag = " (Detailed)" if detailed else ""
        header += detailed_tag + "\n"
        result_str = "\n"
        result_str += "-" * (len(header) - 1) + "\n"
        result_str += header
        result_str += "-" * (len(header) - 1) + "\n"

        passes: dict = {
            check.name: check.get_passed_list()
            for check in self.__checks.values()
        }
        fails: dict = {
            check.name: check.get_failed_conditions()
            for check in self.__checks.values()
        }

        for check_name, check in self.__checks.items():
            # Determine the overall color for the check based on its pass/fail status
            if check.get_passed_total() > 0 and check.get_failed_total() == 0:
                key_color = "green"
            elif (
                check.get_failed_total() > 0 and check.get_passed_total() == 0
            ):
                key_color = "red"
            elif check.get_failed_total() > 0 and check.get_passed_total() > 0:
                key_color = "yellow"
            else:
                key_color = "white"

            result_str += f"{colored(check_name, key_color)}:\n"

            for condition in check.validations:
                if (
                    condition in passes[check_name]
                    and condition not in fails[check_name]
                ):
                    # This condition always passed
                    key_color = "green"
                elif (
                    condition in fails[check_name]
                    and condition not in passes[check_name]
                ):
                    # This condition always failed
                    key_color = "red"
                elif (
                    condition in fails[check_name]
                    and condition in passes[check_name]
                ):
                    # This condition had mixed results
                    key_color = "yellow"
                else:
                    # This condition was never evaluated
                    key_color = "white"

                if detailed:
                    result_str += f"{' ' * 4}{colored(f'{condition[0]}: {condition[1]}', key_color)}\n"
                elif key_color != "green":
                    result_str += f"{' ' * 4}{colored(f'{condition[0]}: {condition[1]}', key_color)}\n"

                if condition in fails[check_name]:
                    result_str += f"{' ' * 8}{colored(f'Received {len(fails[check_name][condition])} event(s):', key_color)}\n"
                    for event in fails[check_name][condition]:
                        # Avoid nested single quotes in f-string
                        expected = event["expected"]
                        received = event["received"]
                        result = event["result"]
                        event_str = f'Expected: "{expected}", Received: "{received}", Result: {result}'
                        result_str += (
                            f"{' ' * 12}{colored(event_str, key_color)}\n"
                        )
                elif (
                    condition not in passes[check_name]
                    and condition not in fails[check_name]
                ):
                    result_str += (
                        f"{' ' * 8}{colored('<no events seen>', key_color)}\n"
                    )

        result_str += "-" * (len(header) - 1) + "\n"

        return result_str

    def has_failures(self) -> bool:
        """
        Returns True if any validation failures have been recorded.
        """
        for _, check in self.__checks.items():
            if check.get_failed_total() > 0:
                return True

        return False

    def validate(self, data: str) -> None:
        """
        Validates a given json-formatted string against the rules.

        Args:
            data (str): The json-formatted string to validate.
        """
        self.__logger.debug("Validating data: %s", data)
        for check_name, check in self.__checks.items():
            if check.qualify(data):
                self.__logger.debug("Check qualified: %s", check_name)
                check.validate(data)
            else:
                self.__logger.debug("Check did not qualify: %s", check_name)

    async def start_validating(self, msg_queue: asyncio.Queue) -> None:
        """
        Start validating events from the msg_queue.

        Args:
            msg_queue (asyncio.Queue): The msg_queue to get messages from.
        """
        while not self.__state_completed.done():
            try:
                msg = await asyncio.wait_for(msg_queue.get(), timeout=None)
                self.__logger.debug(
                    "Validating message: %s",
                    msg,
                )
                self.validate(msg)
            except asyncio.TimeoutError:
                continue

        self.__logger.debug("Validator finished processing messages.")
