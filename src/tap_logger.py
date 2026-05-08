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

"""TAP version 14 formatter and data structures."""

from dataclasses import dataclass, field
from typing import IO


@dataclass
class TAPEvent:
    expected: str
    received: str


@dataclass
class TAPConditionResult:
    condition: str
    failed_occurrences: int
    events: list[TAPEvent]
    passed_occurrences: int = 0


@dataclass
class TAPResult:
    ok: bool
    name: str
    skipped: bool = False
    skip_reason: str = ""
    failed_conditions: list[TAPConditionResult] = field(default_factory=list)
    passed_conditions: list[tuple[str, int]] = field(default_factory=list)


class TAPLogger:
    """
    Writes a TAP version 14 stream to a file-like object.

    Supports nested subtests via subtest(), which indents the inner stream and
    emits a rolled-up ok/not ok line in the parent after the block closes.
    """

    def __init__(self, output: IO[str], indent: int = 0) -> None:
        self._output = output
        self._indent = indent
        self._counter = 0

    def _write(self, line: str) -> None:
        self._output.write("    " * self._indent + line + "\n")

    @staticmethod
    def _yaml_str(value: object) -> str:
        """Wrap a value as a YAML single-quoted scalar, escaping interior single quotes."""
        return "'" + str(value).replace("'", "''") + "'"

    def version(self) -> None:
        self._write("TAP version 14")

    def plan(self, n: int) -> None:
        self._write(f"1..{n}")

    def comment(self, text: str) -> None:
        for line in text.splitlines():
            self._write(f"# {line}")

    def result(self, tap_result: TAPResult, detailed: bool = False) -> None:
        """Write a single test point line, plus a YAML diagnostics block if needed."""
        self._counter += 1
        n = self._counter

        if tap_result.skipped:
            reason = tap_result.skip_reason or "no events seen"
            self._write(f"ok {n} - {tap_result.name} # SKIP {reason}")
            return

        status = "ok" if tap_result.ok else "not ok"
        self._write(f"{status} {n} - {tap_result.name}")

        emit_diag = not tap_result.ok or (detailed and tap_result.passed_conditions)
        if not emit_diag:
            return

        self._write("  ---")

        if not tap_result.ok:
            self._write(
                f"  message: {self._yaml_str(len(tap_result.failed_conditions))} condition(s) failed"
            )
            self._write("  failed_conditions:")
            for cond in tap_result.failed_conditions:
                self._write(f"    - condition: {self._yaml_str(cond.condition)}")
                if cond.passed_occurrences > 0:
                    self._write(f"      passed_occurrences: {cond.passed_occurrences}")
                self._write(f"      failed_occurrences: {cond.failed_occurrences}")
                self._write("      events:")
                for event in cond.events:
                    self._write(f"        - expected: {self._yaml_str(event.expected)}")
                    self._write(f"          received: {self._yaml_str(event.received)}")

        if detailed and tap_result.passed_conditions:
            self._write("  passed_conditions:")
            for condition_str, count in tap_result.passed_conditions:
                self._write(f"    - condition: {self._yaml_str(condition_str)}")
                self._write(f"      occurrences: {count}")

        self._write("  ...")

    def subtest(self, name: str, results: list[TAPResult], detailed: bool = False) -> bool:
        """
        Write a named subtest block then emit a rolled-up ok/not ok line in the parent.

        Returns True if every non-skipped result was ok.
        """
        self._write(f"# Subtest: {name}")
        child = TAPLogger(self._output, self._indent + 1)
        child.version()
        child.plan(len(results))
        all_ok = True
        for r in results:
            child.result(r, detailed)
            if not r.ok and not r.skipped:
                all_ok = False

        self._counter += 1
        status = "ok" if all_ok else "not ok"
        self._write(f"{status} {self._counter} - {name}")
        return all_ok
