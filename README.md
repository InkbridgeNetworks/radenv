# Overview
This tool can be used to start up a group (or groups) of docker containers and run tests against them. The tests use unix sockets to communicate with the freeradius container(s) who write to the sockets using the `linelog` module when triggers are fired.

The `data` directory is used to store files that are relevant for the containers in the tests. For example, the `data/freeradius/default` directory has files that can be mounted to the `/etc/raddb` directory of a freeradius container.

There are two important configs for the tests:
1. Environment/Compose configs
2. Test configs

## Environment/Compose Configs
The files stored in the `environments/` directory just docker compose configs that specify an environment the tests should run in.

### Important
The container(s) running FreeRADIUS will need a `linelog` config that will write to a unix socket, and a unix socket mounted to the container as follows:
```
volumes:
- ${LISTENER_DIR}/${COMPOSE_PROJECT_NAME}.sock:/path/inside/container.sock
...
```

Docker compose creates a default network for each group of containers it orchestrates. This is generated randomly from a pool of available subnets when the group of containers is created. To resolve this, there is a script that will export the test subnet to `TEST_SUBNET` in a container. This is useful for FreeRADIUS as it will let you use `ipaddr = $ENV{TEST_SUBNET}` in `clients.conf`. The script is located at `data/freeradius/env-setup.sh` and can be used by mounting it to the container in the config and running it in the entrypoint:
```
volumes:
- ${DATA_PATH}/freeradius/env-setup.sh:/tmp/env-setup.sh
...
entrypoint:
- bash
- c
- |
  apt-get update && \
  source /tmp/env-setup.sh && \
  exec /docker-entrypoint.sh "$@"
```

## Test Configs
The test can be found in the `tests/` directory. They specify the various `states` that the environment can be in, and how to `verify` them.

Example:
```
timeout: 40                                     # The overall timeout of the test
state_order: sequence                           # The order the states should be run in
states:
  state_1:                                      # A state that the environment should be put in
    description: Basic access-request test
    host:
      radius-client:                            # The host the following actions should be run on
        actions:                                # A list of actions to run on the host
        - access_request:
            target: freeradius
            secret: testing123
            username: testuser
            password: testpass
    verify:                                     # Configs for verifying the behaviour of FR in the state
      timeout: 15                               # The timeout for this state/sub-test
      triggers:
      - request_sent:                           # A trigger to watch 
          pattern:                              # A validation rule with configs/params
            reg_pattern: (\w+) request sent
```

# HOW-TO
## Setup (PyPI)
This package can be installed from our PyPI repo at https://pypi.inkbridge.io/radenv. Once installed, the following commands are available:
- `radenv` - Runs the main tool for testing
- `radenv-config` - The config builder that can render a jinja2 config to an <b>envionment</b> and <b>test</b> file.
- `radenv-setup` - Setup tool that will create the `environments/`, `tests/`, and `data/` directories.

## Setup (Source)
To use this tool, first clone the repo and run `make configure` to setup the environment and install the dependencies.

Activate the python virtual environment using `source .venv/bin/activate`.

## Docker Image
You will need to install Docker.

You now need to generate a docker image on your host by first stepping into your FreeRADIUS repo with and running `docker build -t fr-build-ubuntu22 -f scripts/docker/build/ubuntu22/Dockerfile .`. Once complete, change directories back to the repo for this tool.

Next, generate the compose and config files using `python3 -m src.config_builder example.yml.j2`.

## Example
### PyPI
To use the tool, run `radenv <ARGS>`. For example:
```
radenv -v -t tests/foo.yml
```

### Source
Run `make test-framework -- <ARGS>`. For example:
```
make test-framework -- -v -t tests/foo.yml
```

# Command Arguments
`-h`, `--help` - Show help text.

`--compose` - Path to the Docker compose file or directory containing compose files to be used for testing. Defaults to the script source folder `environments/`.

`-c`, `--config` - Path to a configuration file. This file can contain the test configs, compose configs, or both, and can be in either yaml or jinja2 format.

`-t`, `--test` - Path to the test configuration file. Defaults to the directory named `tests/`.

`-d`, `--data` - Path to the data directory.

`--filter` - Filter test logs by name. Format is a comma separated list of test names.

`-o`, `--output` - Path to output log file for test summaries. Defaults to `multi_server_test.log`.

`-s`, `--seed` - Numeric seed to use for shuffling random tests.

`--debug`, `-x` - Enable debug output.

`--verbose`, `-v` - Enable verbose logging. More "v"'s set a higher verbose level.

# Development
Development notes.

## Validation Rules
Want to help out and write more rules? Great! Here's how:

I have written the rule code to make implementing new rules very easy. Yay! To add a new rule, you first need to add a method to `src/rules/rules.py` to represent your rule. The method will need to match the signature `def <method_name>(logger: logging.Logger, string: str, **kwargs) -> bool`. For example:
```
def foo(x: str, logger: logging.Logger, string: str) -> bool:
        if string == x:
                return True
        return False
```

Then, to allow your rule to be used in the test framework, you will need to add it to the global map of known rules `RULES_MAP`:
```
RULES_MAP.update({"foo": foo, "example": foo})
```
This can be done on the next line after your rule method.

Note: You can add multiple aliases for your rule, but I would recommend adding the name of the method as a bare minimum.

## Events
New events can be added to the `src/events` directory. If there is no suitable events file for your new event, create one.

Similar to how new rules can be added, you write an event method and add it to the `EVENTS_MAP` global variable. The only requirement for the method is that it has a `logger: logging.Logger` parameter. For example:
```
def bar(x: int, source: ValidContainer, logger: logging.Logger) -> None:
        docker.execute(source, ["bash", "-c", f"echo {x}"], detach=False)

EVENTS_MAP.update({"bar": bar})
```

Note: If your event has a `source` parameter, the container the event is listed under will be passed to the event.