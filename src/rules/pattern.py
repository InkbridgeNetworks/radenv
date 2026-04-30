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
Validation rule to check if a string matches a regex pattern.
"""

import logging
import re

from src.rules.registry import rule

@rule("pattern", "regex")
def pattern(
    reg_pattern: str | re.Pattern[str], logger: logging.Logger, data: str
) -> bool:
    """
    Check if a string matches a given regex pattern.

    Args:
        pattern (str | re.Pattern[str]): The regex pattern to match against.
        logger (logging.Logger): Logger for debug output.
        data (str): The string to be checked.

    Returns:
        bool: True if the string matches the pattern, False otherwise.
    """
    if isinstance(reg_pattern, str):
        reg_pattern = re.compile(reg_pattern)

    match = reg_pattern.match(data)
    if match:
        logger.debug("Pattern matched: %s", reg_pattern.pattern)
        return True
    logger.debug("Pattern did not match: %s", reg_pattern.pattern)
    return False
