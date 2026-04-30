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
Validation rule that allows execution of custom code blocks for validation. This is a powerful
feature that should be used with caution, as it can introduce security risks if not properly
handled. The code block should be designed to return a boolean value indicating the success or
failure of the validation.
"""

import logging

from src.rules.registry import rule


def _is_code_safe(_source: str, logger: logging.Logger) -> bool:
    """
    Check if the provided code block is safe to execute.

    Args:
        _source (str): The code block to check.
        logger (logging.Logger): Logger for debug output.
    Returns:
        bool: True if the code is safe, False otherwise.
    """
    logger.warning(
        "Code safety check is not implemented. Proceeding without checks."
    )
    return True


@rule("code", "custom_code")
def code(block: str, logger: logging.Logger, data: str) -> bool:
    """
    Execute a custom code block for validation.

    Args:
        block (str): The code block to execute.
        logger (logging.Logger): Logger for debug output.
        data (str): The string to be validated.

    Returns:
        bool: The result of the executed code block.
    """
    logger.debug("Evaluating custom code block.")
    if not _is_code_safe(block, logger):
        logger.error("Unsafe code block detected. Execution aborted.")
        return False

    logger.debug("Executing custom code block.")

    indented_block = "\n".join(f"    {line}" for line in block.splitlines())
    wrapped_code = f"def _wrapped_func():\n{indented_block}"

    local_vars = {"data": data, "logger": logger}
    try:
        exec(wrapped_code, local_vars)
        result = local_vars.get("_wrapped_func", lambda: False)()
        logger.debug("Custom code block executed with result: %s", result)
        return result
    except Exception as e:
        logger.error("Error executing custom code block: %s", e)
        return False
