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
Registry for validation rules. Provides a central place to register and retrieve validation rules.
"""

import logging

from src.rule import Rule

_rules: dict[str, callable] = {}
_prefixes: dict[str, callable] = {}


def rule(name, *aliases) -> callable:
    """
    Decorator to register a function as a validation rule.
    Args:
        name (str): The name of the rule.
        aliases: Additional names for the rule.

    Returns:
        callable: The decorator function.
    """

    def decorator(func):
        for key in (name, *aliases):
            _rules[key] = func
        return func

    return decorator


def prefix(name, *aliases) -> callable:
    """
    Decorator to register a function as a prefix rule.
    Args:
        name (str): The name of the prefix rule.
        aliases: Additional names for the prefix rule.

    Returns:
        callable: The decorator function.
    """

    def decorator(func):
        for key in (name, *aliases):
            _prefixes[key] = func
        return func

    return decorator


def build_rule(rule_name: str, params: dict, logger: logging.Logger) -> Rule:
    """
    Build a rule function that can be used to validate events.

    Args:
        rule_name (str): The name of the method to build the rule for.
        params (dict): The parameters for the rule.
        logger (logging.Logger): Logger for debugging.

    Returns:
        callable: A function that takes a string and returns True if the rule passes,
            False otherwise.

    Raises:
        ValueError: If the rule name is unknown.
    """

    normalized_rule_name = rule_name.lower()

    logger.debug("Building rule: %s with params: %s", rule_name, params)

    if normalized_rule_name in _rules:
        func = _rules[normalized_rule_name]

        if normalized_rule_name in ("regex", "pattern"):
            params["expected"] = params.get("expected") or params.get(
                "reg_pattern"
            )

        return Rule(func, **params, logger=logger)

    for prefix_str, transform in _prefixes.items():
        if normalized_rule_name.startswith(prefix_str):
            logger.debug(
                "Applying prefix: %s to rule: %s", prefix_str, rule_name
            )
            inner_rule = build_rule(
                normalized_rule_name[len(prefix_str) :], params, logger
            )
            return transform(inner_rule)

    raise ValueError(f"Unknown rule: {rule_name}")
