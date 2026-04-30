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
Prefixes can be used to modify the behavior of rules. They are applied before
the rule is evaluated and can change the default return value or the way the
rule is evaluated. This allows for more flexible and powerful rule definitions
without needing to create new rules for every variation of behavior.
"""

from src.rule import Rule
from src.rules.registry import prefix


@prefix("fail_", "not_")
def fail(rule: Rule) -> Rule:
    """
    A rule that should never pass.

    Args:
        rule (Rule): The rule to modify.

    Returns:
        Rule: The modified rule that should never pass.
    """
    rule.default_return = False
    return rule
