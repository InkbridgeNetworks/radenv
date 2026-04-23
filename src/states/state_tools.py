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
Tools to generate states for testing.
"""

import asyncio
import logging
import random
from pathlib import Path

import yaml
from src.events.event_tools import get_events
from src import logging_helper
from src.rules.rules_tools import (
    generate_rules_map,
)
from src.states.state import State


def generate_states(
    loop: asyncio.AbstractEventLoop,
    config: Path | dict,
    test_name: str,
    test_logger: logging.Logger,
    seed: int | None = None,
) -> tuple[float, list[State]]:
    """
    Generate a list of states for testing.

    Args:
        loop (asyncio.AbstractEventLoop): The event loop to use.
        config (Path | dict): Path to the configuration file or a dictionary
          containing the config.
        test_name (str): Name of the test.
        test_logger (logging.Logger): Logger for the test.
        seed (int | None): Seed for randomizing test states.

    Returns:
        timeout (float): Timeout for the test.
        states (list[State]): List of State objects created from the configuration.

    Raises:
        ValueError: If the configuration file is invalid.
    """
    try:
        # TODO: Should the test logger be used here?
        timeout, state_order, state_configs = parse_test_configs(
            config, test_name, logger=logging_helper.get_logger()
        )
    except ValueError as e:
        # TODO: Log the error to the correct logger
        raise ValueError(f"Invalid configuration file: {e}") from e

    states = []
    for state_config in state_configs:
        states.append(
            State(
                name=state_config.get("name", "Unnamed State"),
                description=state_config.get("description", ""),
                actions=state_config.get("actions", []),
                rules_map=state_config.get("rules_map", {}),
                timeout=state_config.get("timeout", 15),
                loop=loop,
                logger=test_logger,
            )
        )

    if state_order in ["random", "unordered", "shuffle"]:
        # Shuffle the states randomly
        if not seed:
            seed = random.randint(0, 2**32 - 1)

        test_logger.info("Shuffling states with seed: %d", seed)

        # Log to the file logger as well
        file_logger = logging_helper.get_file_logger()
        file_logger.info(
            "Shuffling test %s states with seed: %d", test_name, seed
        )

        random.seed(seed)
        random.shuffle(states)

    return timeout, states


def parse_test_configs(
    config: Path | dict, test_name: str, logger: logging.Logger
) -> tuple[float, str, list[dict]]:
    """
    Parse the test configuration file.

    Args:
        config (Path | dict): Path to the configuration file or a dictionary containing the config.
        test_name (str): Name of the test.

    Returns:
        float: Timeout for the test.
        str: State order for the test.
        list[dict]: List of state configurations. Each state configuration is a dictionary
            with keys:
            - name (str): Name of the state.
            - description (str): Description of the state.
            - timeout (int): Timeout for the state.
            - actions (list[callable]): List of actions to perform in the state.
            - rules_map (dict): Mapping of triggers to validation patterns.

    Raises:
        ValueError: If the configuration file is invalid.
    """

    logger.info("Parsing test configuration file: %s", config)

    # Verify the file exists
    if isinstance(config, Path) and not config.exists():
        logger.error("Configuration file does not exist: %s", config)
        return []

    known_actions = get_events()

    raw_configs = {}

    if isinstance(config, Path):
        with open(config, "r", encoding="utf-8") as f:
            raw_configs = yaml.safe_load(f)
    else:
        raw_configs = config

    timeout: float = raw_configs.get("timeout", 40.0)
    state_order: str = raw_configs.get("state_order", "sequence")
    configs = []
    for state_name, state in raw_configs.get("states", {}).items():
        state_config = {}

        state_config["name"] = state_name
        state_config["description"] = state.get("description", "")
        state_config["timeout"] = state.get("verify", {}).get("timeout", 15)

        # Parse the actions
        actions = []
        for host, host_config in state.get("host", {}).items():
            for action in host_config.get("actions", []):
                action_name = list(action.keys())[0]
                if action_name not in known_actions:
                    logger.warning("Unknown action: %s", action_name)
                    continue

                action_func = known_actions[action_name]

                # Build the action with its parameters
                def build_action(func, params, host):
                    # if the function takes a source parameter, add it
                    if "source" in func.__code__.co_varnames:
                        params["source"] = f"{test_name}-{host}-1"

                    # if the function takes a target parameter, update it
                    if "target" in func.__code__.co_varnames:
                        if "target" not in params:
                            raise ValueError(
                                f"Action {action_name} requires a target parameter."
                            )
                        # Update the target to include the full container name
                        params["target"] = f"{test_name}-{params['target']}-1"

                    # if the function takes a test_name parameter, add it
                    if "test_name" in func.__code__.co_varnames:
                        params["test_name"] = test_name

                    # If the function takes a logger parameter, set a default logger
                    if "logger" in func.__code__.co_varnames:
                        # TODO: Probably want to use the test logger here
                        return lambda logger=logging_helper.get_logger(): func(
                            **params, logger=logger
                        )
                    return lambda: func(**params)

                action_params = action.get(action_name, {})
                actions.append(build_action(action_func, action_params, host))

        # Parse the rules map
        # TODO: Handle ordered vs unordered triggers
        # TODO: Should the test logger be used here?
        rules_map = generate_rules_map(state=state, logger=logger)

        state_config["actions"] = actions
        state_config["rules_map"] = rules_map

        configs.append(state_config)
    return timeout, state_order, configs
