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
Validation rule to check if a number is within a specified range.
"""

import logging

from src.rules.registry import rule


@rule("range", "within_range")
def within_range(
    minimum: float,
    maximum: float,
    logger: logging.Logger,
    data: str,
) -> bool:
    """
    Check if a number is within a specified range.

    Args:
        minimum (float): The minimum value of the range.
        maximum (float): The maximum value of the range.
        logger (logging.Logger): Logger for debug output.
        data (str): The number to be checked.

    Returns:
        bool: True if the number is within the range, False otherwise.
    """
    logger.debug(
        "Checking if number is within range: %f - %f", minimum, maximum
    )
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="ignore")

    logger.debug("Number to check: %s", data)

    try:
        data = float(data)
    except ValueError:
        logger.debug("Provided value is not a valid float: %s", data)
        return False

    if minimum <= data <= maximum:
        logger.debug("Number is within range: %f", data)
        return True
    logger.debug("Number is out of range: %f", data)
    return False
