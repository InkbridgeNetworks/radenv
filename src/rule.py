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
A class to represent a validation rule.
"""

from functools import singledispatchmethod
import logging
from typing import Any, Optional


class SingleRuleFailure(Exception):
    """Exception raised when a single rule fails from a set of rules."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Rule:
    """
    Class to represent a validation rule. Provides a common interface for all validation rules,
    allowing them to be used interchangeably in the validation process.
    """

    default_return: bool
    expected: Optional[str] = None
    kwargs: dict
    logger: logging.Logger

    def __init__(
        self,
        method: callable,
        default_return: bool = True,
        expected: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the rule with the given parameters.

        Args:
            method (callable): The validation method for the rule.
            default_return (bool): The default return value for the rule.
            expected (Optional[str]): The expected value for the rule.
            logger (logging.Logger): The logger for the rule.
            kwargs: Additional parameters for the rule.
        """
        self.method = method
        self.default_return = default_return
        self.expected = expected
        self.logger = kwargs.get("logger", logging.getLogger(__name__))
        self.kwargs = kwargs

    def __call__(self, data: Any) -> bool:
        """
        Make the rule callable.

        Args:
            data (str): The string to validate.

        Returns:
            bool: The result of the validation.
        """
        return self.call_method(data)

    @singledispatchmethod
    def call_method(self, data: str) -> bool:
        """
        Make the rule callable.

        Args:
            data (str): The string to validate.

        Returns:
            bool: The result of the validation.
        """
        try:
            return (
                self.method(data=data, **self.kwargs) and self.default_return
            )
        except Exception as e:
            # Treat any exception as a validation failure and log the error
            self.logger.error("Error validating string: %s", e)
            return not self.default_return

    @call_method.register
    def _(self, data: bytes) -> bool:
        """
        Make the rule callable for bytes input.

        Args:
            data (bytes): The bytes string to validate.

        Returns:
            bool: The result of the validation.
        """
        return self.call_method(data.decode("utf-8", errors="ignore"))

    @call_method.register
    def _(self, data: dict) -> bool:
        """
        Make the rule callable for dict input.

        Args:
            data (dict): The dictionary to validate.

        Returns:
            bool: The result of the validation.
        """
        return self.call_method(str(data))

    def __str__(self) -> str:
        """
        Return a string representation of the rule.

        Returns:
            str: A string representation of the rule.
        """
        kwargs = {k: v for k, v in self.kwargs.items() if k != "logger"}
        return f"Rule(method={self.method.__name__}, default_return={self.default_return}, kwargs={kwargs})"
