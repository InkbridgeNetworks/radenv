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
A class to represent single check/subtest.
"""

from collections import Counter
import logging
from typing import TypeAlias

from jsonpath_ng import JSONPath, parse

from src.rule import Rule
from src.rules.registry import build_rule

Condition: TypeAlias = tuple[JSONPath, Rule]


class Check:
    """
    A class to represent single check
    """

    name: str
    qualifiers: list[Condition]
    validations: list[Condition]
    _passed_conditions: Counter
    _failed_conditions: Counter
    _failed_events: dict[Condition, list[dict]]
    logger: logging.Logger

    def __init__(
        self,
        name: str,
        qualifiers: list[Condition],
        validations: list[Condition],
        logger: logging.Logger = logging.getLogger(__name__),
    ):
        """
        Initialize the subtest with the given parameters.

        Args:
            name (str): The name of the subtest.
            qualifiers (list[Condition]): A list of conditions that must be met for the test
                to be applied.
            validations (list[Condition]): A list of conditions that must be met for the validation
                to pass.
            logger (logging.Logger): The logger for the subtest.
        """
        self.name = name
        self.qualifiers = qualifiers
        self.validations = validations
        self._passed_conditions = Counter()
        self._failed_conditions = Counter()
        self._failed_events = {}
        self.logger = logger

    def get_passed_list(self) -> list[Condition]:
        """
        Get a list of conditions that have passed at least once.

        Returns:
            list[Condition]: A list of conditions that have passed at least once.
        """
        return [
            condition
            for condition, count in self._passed_conditions.items()
            if count > 0
        ]

    def get_passed_counter(self) -> Counter:
        """
        Get a Counter of conditions that have passed.

        Returns:
            Counter: A Counter of conditions that have passed.
        """
        return self._passed_conditions

    def get_passed_total(self) -> int:
        """
        Get the total number of times this check has passed.

        Returns:
            int: The total number of times this check has passed.
        """
        # The number of times this check has passed is the number of times the last validation
        # condition has passed, since all validations must pass for the check to be considered
        # passed.
        return self._passed_conditions[self.validations[-1]]

    def get_failed_conditions(self) -> dict[Condition, list[dict]]:
        """
        Get a dictionary of conditions that have failed at least once, along with their failure
        counts.

        Returns:
            dict[Condition, list[dict]]: A dictionary of conditions that have failed at least once,
                along with a list of dictionaries representing the failed events.
        """
        return self._failed_events

    def get_failed_counter(self) -> Counter:
        """
        Get a Counter of conditions that have failed.

        Returns:
            Counter: A Counter of conditions that have failed.
        """
        return self._failed_conditions

    def get_failed_total(self) -> int:
        """
        Get the total number of failed conditions.

        Returns:
            int: The total number of failed conditions.
        """
        return self._failed_conditions.total()

    def qualify(self, data: str) -> bool:
        """
        Check if the qualifiers are met for the given data.

        Args:
            data (str): The data to check against the qualifiers.

        Returns:
            bool: True if all qualifiers are met, False otherwise.
        """
        for path, rule in self.qualifiers:
            matches = path.find(data)
            if not matches:
                self.logger.debug("Qualifier %s did not match any data", path)
                return False
            for match in matches:
                if not rule(match.value):
                    self.logger.debug(
                        "Qualifier %s failed for value: %s", path, match.value
                    )
                    return False
        return True

    def validate(self, data: str) -> None:
        """
        Check if the validations are met for the given data.

        Args:
            data (str): The data to check against the validations.
        """
        for path, rule in self.validations:
            matches = path.find(data)
            if not matches:
                self.logger.debug("Validation %s did not match any data", path)
                if not rule.default_return:
                    self._failed_conditions[(path, rule)] += 1
                    self._failed_events[
                        (path, rule)
                    ] = self._failed_events.get((path, rule), []) + [
                        {
                            "received": data,
                            "expected": (
                                rule.expected
                                if rule.expected is not None
                                else "N/A"
                            ),
                            "result": "FAIL",
                        }
                    ]
                return
            for match in matches:
                if not rule(match.value):
                    self.logger.debug(
                        "Validation %s failed for value: %s", path, match.value
                    )
                    self._failed_conditions[(path, rule)] += 1
                    self._failed_events[
                        (path, rule)
                    ] = self._failed_events.get((path, rule), []) + [
                        {
                            "received": match.value,
                            "expected": (
                                rule.expected
                                if rule.expected is not None
                                else "N/A"
                            ),
                            "result": "FAIL",
                        }
                    ]
                    return
                self.logger.debug(
                    "Validation %s passed for value: %s", path, match.value
                )
                self._passed_conditions[(path, rule)] += 1
        self.logger.debug("All validations passed for data: %s", data)

    @classmethod
    def from_config(
        cls, name: str, trigger_data: dict, logger: logging.Logger
    ) -> "Check":
        """
        Create a check instance from a configuration dictionary.

        Args:
            name (str): The name of the check.
            trigger_data (dict): The configuration data for the validation test.
            logger (logging.Logger): The logger to use for the check.

        Returns:
            Check: An instance of the Check class.
        """
        qualifiers = cls._parse_conditions(
            trigger_data.get("qualifiers", {}), logger
        )
        validations = cls._parse_conditions(
            trigger_data.get("validations", {}), logger
        )
        return cls(name, qualifiers, validations, logger)

    @staticmethod
    def _parse_conditions(
        conditions: dict, logger: logging.Logger
    ) -> list[Condition]:
        """
        Parse a dictionary of conditions into a list of Condition tuples.

        Args:
            conditions (dict): A dictionary where keys are JSONPath strings and values are rule
                configurations.
            logger (logging.Logger): The logger to use for any logging during parsing.

        Returns:
            list[Condition]: A list of Condition tuples.
        """
        parsed_conditions = []
        for path_str, condition_data in conditions.items():
            path = parse(path_str)
            if isinstance(condition_data, str):
                rule = build_rule(
                    "pattern", {"reg_pattern": condition_data}, logger
                )
                parsed_conditions.append((path, rule))
            else:
                for rule_name, params in condition_data.items():
                    rule = build_rule(rule_name, params or {}, logger)
                    parsed_conditions.append((path, rule))
        return parsed_conditions
