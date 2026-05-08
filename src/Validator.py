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

from src.check import Check
from src import logging_helper
from src.tap_logger import TAPConditionResult, TAPEvent, TAPLogger, TAPResult


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

    @staticmethod
    def _yaml_str(value: object) -> str:
        """Wrap a value in YAML single-quoted scalar, escaping interior single quotes."""
        return "'" + str(value).replace("'", "''") + "'"

    def get_results_str(self, detailed: bool = False) -> str:
        """
        Get a TAP version 14 representation of the validation results.

        Each Check maps to one TAP test point. Checks that fired but had at
        least one condition failure are 'not ok'; checks that never fired are
        skipped.  Failed conditions are described in a YAML diagnostics block.
        When detailed=True, passing conditions are included in the block too.
        """
        lines = ["TAP version 14", f"1..{len(self.__checks)}"]

        for i, (check_name, check) in enumerate(self.__checks.items(), start=1):
            passed_total = check.get_passed_total()
            failed_total = check.get_failed_total()
            failed_conditions = check.get_failed_conditions()

            if failed_total == 0 and passed_total == 0:
                lines.append(f"ok {i} - {check_name} # SKIP no events seen")
                continue

            status = "not ok" if failed_total > 0 else "ok"
            lines.append(f"{status} {i} - {check_name}")

            emit_diag = status == "not ok" or (detailed and passed_total > 0)
            if not emit_diag:
                continue

            lines.append("  ---")

            if status == "not ok":
                lines.append(
                    f"  message: {self._yaml_str(len(failed_conditions))} condition(s) failed"
                )
                lines.append("  failed_conditions:")
                for condition, events in failed_conditions.items():
                    path, rule = condition
                    passed_count = check.get_passed_counter()[condition]
                    lines.append(f"    - condition: {self._yaml_str(f'{path}: {rule}')}")
                    if passed_count > 0:
                        lines.append(f"      passed_occurrences: {passed_count}")
                    lines.append(f"      failed_occurrences: {len(events)}")
                    lines.append("      events:")
                    for event in events:
                        lines.append(f"        - expected: {self._yaml_str(event['expected'])}")
                        lines.append(f"          received: {self._yaml_str(event['received'])}")

            if detailed:
                passed_only = [
                    c for c in check.get_passed_list()
                    if c not in failed_conditions
                ]
                if passed_only:
                    lines.append("  passed_conditions:")
                    for condition in passed_only:
                        path, rule = condition
                        count = check.get_passed_counter()[condition]
                        lines.append(f"    - condition: {self._yaml_str(f'{path}: {rule}')}")
                        lines.append(f"      occurrences: {count}")

            lines.append("  ...")

        return "\n".join(lines) + "\n"

    def get_tap_results(self, detailed: bool = False) -> list[TAPResult]:
        """
        Return structured TAP results for each check, suitable for passing to TAPLogger.

        When detailed=True, passing conditions are included so TAPLogger can emit them
        in the diagnostics block.
        """
        results = []
        for check_name, check in self.__checks.items():
            passed_total = check.get_passed_total()
            failed_total = check.get_failed_total()
            failed_conditions = check.get_failed_conditions()

            if failed_total == 0 and passed_total == 0:
                results.append(TAPResult(ok=True, name=check_name, skipped=True))
                continue

            failed_conds = [
                TAPConditionResult(
                    condition=f"{path}: {rule}",
                    failed_occurrences=len(events),
                    events=[
                        TAPEvent(expected=str(e["expected"]), received=str(e["received"]))
                        for e in events
                    ],
                    passed_occurrences=check.get_passed_counter()[condition],
                )
                for condition, events in failed_conditions.items()
                for path, rule in [condition]
            ]

            passed_conds = []
            if detailed:
                passed_conds = [
                    (f"{path}: {rule}", check.get_passed_counter()[condition])
                    for condition in check.get_passed_list()
                    if condition not in failed_conditions
                    for path, rule in [condition]
                ]

            results.append(TAPResult(
                ok=failed_total == 0,
                name=check_name,
                failed_conditions=failed_conds,
                passed_conditions=passed_conds,
            ))

        return results

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
