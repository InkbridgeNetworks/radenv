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
import copy
import logging

from termcolor import colored

from src.rules.rules import SingleRuleFailure
from src import logging_helper


class MissingRuleError(Exception):
    """
    Exception raised when a rule is missing for a given attribute.
    """

    def __init__(self, attribute: str) -> None:
        super().__init__(f"No rules defined for attribute: {attribute}")
        self.attribute = attribute


class Validator:
    """
    Validator class that will take care of all of the trigger validation
    """

    def __init__(
        self,
        rules_map: dict,
        state_completed: asyncio.Future,
        logger: logging.Logger = logging_helper.get_logger(),
    ) -> None:
        self.__rules_map = rules_map
        self.__rules_tracking = copy.deepcopy(rules_map)
        self.__passed_rules = {}
        self.__failed_rules = {}

        for key in self.__rules_map.keys():
            for rule in self.__rules_map[key]:
                if rule.friendly_str.startswith(
                    "never_fire"
                ) or rule.friendly_str.startswith("fail"):
                    if key not in self.__passed_rules:
                        self.__passed_rules[key] = []
                    self.__passed_rules[key].append(rule.friendly_str)
                elif rule.friendly_str.startswith("may_"):
                    # May rules are not tracked
                    continue
                else:
                    if key not in self.__failed_rules:
                        self.__failed_rules[key] = []
                    self.__failed_rules[key].append(rule.friendly_str)

        self.__state_completed = state_completed
        self.__logger = logger

    @property
    def unmatched_rules(self) -> dict:
        """
        Get the rules that have not been matched.

        Returns:
            dict: A dictionary of unmatched rules.
        """
        return self.__rules_tracking

    def get_results_str(self, detailed: bool = False) -> str:
        """
        Get a string representation of the validation results.

        Args:
            detailed (bool, optional): Whether to include matched rules in the output.
                Defaults to False.

        Returns:
            str: A string representation of the results.
        """
        header = "Validation Results"
        detailed_tag = " (Detailed)" if detailed else ""
        header += detailed_tag + "\n"
        result_str = "\n"
        result_str += "-" * (len(header) - 1) + "\n"
        result_str += header
        result_str += "-" * (len(header) - 1) + "\n"

        total = 0
        matched = 0
        for key, value in self.__passed_rules.items():
            key_color = "green"

            if key in self.__failed_rules:
                key_color = "red"

                if len(self.__failed_rules[key]) < len(self.__rules_map[key]):
                    key_color = "yellow"

            total += len(self.__rules_map[key])
            matched += len(value)

            if detailed:
                result_str += f"{colored(key, key_color)}:\n"
                for v in value:
                    result_str += f"{' ' * 4}{colored(v, 'green')}\n"
                if key in self.__failed_rules:
                    for v in self.__failed_rules[key]:
                        result_str += f"{' ' * 4}{colored(v, 'red')}\n"
            else:
                result_str += f"{colored(key, key_color)}: {colored(f'{len(value)}/{len(self.__rules_map[key])}', key_color)}\n"

        for key, values in self.__failed_rules.items():
            if key not in self.__passed_rules:
                key_color = "red"
                total += len(self.__rules_map[key])

                result_str += f"{colored(key, key_color)}:\n"
                for v in values:
                    result_str += f"{' ' * 4}{colored(v, 'red')}\n"

        result_str += "-" * (len(header) - 1) + "\n"
        result_str += f"Matched: {colored(matched, 'green') if matched > 0 else matched} / {total} "
        result_str += f"(Failures: {colored(total - matched, 'red') if total - matched > 0 else total - matched})\n"
        result_str += "-" * (len(header) - 1) + "\n"

        return result_str

    def has_failures(self) -> bool:
        """
        Returns True if any validation failures have been recorded.
        """
        return bool(self.__failed_rules)

    def validate(self, attribute: str, value: str) -> bool:
        """
        Validates a given attribute-value pair against the rules map.

        Args:
            attribute (str): The attribute to validate.
            value (str): The value of the attribute.

        Returns:
            bool: True if the attribute-value pair is valid, False otherwise.

        Raises:
            MissingRuleError: If there are no rules defined for the given attribute.
        """
        if attribute not in self.__rules_map:
            self.__logger.debug(
                "No validation rules for attribute: %s", attribute
            )
            raise MissingRuleError(attribute)

        self.__logger.debug(
            "Validating attribute: %s, value: %s", attribute, value
        )
        self.__logger.debug("Checking rules: %s", self.__rules_map[attribute])
        for rule in self.__rules_map[attribute]:
            if hasattr(rule, "friendly_str"):
                self.__logger.debug("rule params: %s", rule.friendly_str)
                friendly_str = rule.friendly_str
            else:
                friendly_str = {}

            try:
                if rule(value):
                    if attribute not in self.__passed_rules:
                        self.__passed_rules[attribute] = []

                    if friendly_str not in self.__passed_rules[attribute]:
                        self.__passed_rules[attribute].append(friendly_str)

                    # If this is a must_fire rule, remove it from failed rules
                    if (
                        isinstance(friendly_str, str)
                        and attribute in self.__failed_rules
                        and friendly_str in self.__failed_rules[attribute]
                    ):
                        self.__failed_rules[attribute].remove(friendly_str)

                        # Clean up if no more failed rules for this attribute
                        if len(self.__failed_rules[attribute]) == 0:
                            del self.__failed_rules[attribute]

                    return True
            except SingleRuleFailure as e:
                # Add the failed rule to the failed rules list
                if attribute not in self.__failed_rules:
                    self.__failed_rules[attribute] = []
                if e not in self.__failed_rules[attribute]:
                    self.__failed_rules[attribute].append(e)
                continue

            if attribute not in self.__failed_rules:
                self.__failed_rules[attribute] = []
            if friendly_str not in self.__failed_rules[attribute]:
                self.__failed_rules[attribute].append(friendly_str)

                # Remove from passed rules if it was previously marked as passed
                if (
                    attribute in self.__passed_rules
                    and friendly_str in self.__passed_rules[attribute]
                ):
                    self.__passed_rules[attribute].remove(friendly_str)

        return False

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
                    "Validating message with trigger: %s and value: %s",
                    msg[0],
                    msg[1],
                )
                try:
                    result = self.validate(msg[0], msg[1])

                    self.__logger.debug(
                        "Message validation result: %s",
                        colored(
                            "PASSED" if result else "FAILED",
                            "green" if result else "red",
                        ),
                    )
                except MissingRuleError as e:
                    self.__logger.debug(
                        "Message validation skipped (no rules): %s", e
                    )
            except asyncio.TimeoutError:
                continue

        self.__logger.debug("Validator finished processing messages.")
