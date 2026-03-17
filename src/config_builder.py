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

"""config_builder.py
Configuration parser for multi-server setup
This script is used to parse configuration files
for a multi-server test, and generates two output files:
    1. `docker-compose.yml` for Docker Compose setup
    2. `test-config.yml` for test configuration
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Tuple
import jinja2
import yaml


class NoQuotedMergeDumper(yaml.SafeDumper):
    """
    Custom YAML dumper that avoids quoting merge keys (<<).
    """

    def represent_scalar(self, tag, value, style=None):
        """
        Custom representer for scalar values to handle multi-line strings as block style.
        """
        if isinstance(value, str) and "\n" in value:
            style = "|"
        return super().represent_scalar(tag, value, style)


def no_quoted_merge_key(dumper, data):
    """
    Custom representer to avoid quoting merge keys (<<).
    """
    if data == "<<":
        return dumper.represent_scalar(
            "tag:yaml.org,2002:merge", data, style=""
        )
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


# Register the custom representer
NoQuotedMergeDumper.add_representer(str, no_quoted_merge_key)


def _parse_config(config: dict) -> Tuple[dict, dict]:
    """
    Parses a configuration dictionary and separates the compose and test configurations.
    Args:
        config (dict): The configuration dictionary.
    Returns:
        Tuple[dict, dict]: A tuple containing two dictionaries:
            - 'compose_configs': A dictionary of compose configurations.
            - 'other_configs': A dictionary of other configurations.
    """
    compose_configs = {}
    other_configs = {}

    for key, value in config.items():
        if key.startswith("fixtures"):
            # Start by adding the default capabilities to the compose configs
            default_capabilities = {"cap_add": ["NET_ADMIN", "SYS_PTRACE"]}
            compose_configs["x-common-config"] = default_capabilities

            for compose_key, compose_value in value.items():
                if compose_key.startswith(tuple(["services", "hosts"])):
                    updated_services = {}
                    for service_name, service_config in compose_value.items():
                        service_config["<<"] = default_capabilities
                        updated_services[service_name] = service_config
                    compose_configs["services"] = updated_services
                else:
                    compose_configs["services"] = compose_value
        else:
            other_configs[key] = value

    return compose_configs, other_configs


def generate_configs(file_path: Path) -> None:
    """
    Generates config data for multi-server setup.

    Args:
        file_path (Path): The path to the configuration file.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the configuration file has an unsupported file type.
    """
    # If the config file does not exist, raise an error
    if not file_path.exists():
        raise FileNotFoundError(
            f"Configuration file {file_path} does not exist."
        )

    # If the config file is already rendered, just parse it
    if file_path.suffix == ".yml":
        with open(file_path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)
    elif file_path.suffix == ".j2":
        # If the config file is a Jinja2 template, render it
        template_loader = jinja2.FileSystemLoader(searchpath=file_path.parent)
        template_env = jinja2.Environment(loader=template_loader)
        template_env.globals.update(
            os=os,
        )
        template = template_env.get_template(file_path.name)
        rendered_config = template.render()
        config = yaml.safe_load(rendered_config)
    else:
        raise ValueError(
            "Unsupported file type. Only .yml and .j2 are supported."
        )

    # Parse the configuration
    return _parse_config(config)


def write_yaml_to_file(data: dict, output_path: Path) -> None:
    """
    Writes a dictionary to a YAML file.

    Args:
        data (dict): The data to write to the YAML file.
        output_path (Path): The path to the output YAML file.
    """
    with open(output_path, "w", encoding="utf-8") as file:
        yaml.dump(
            data,
            file,
            default_flow_style=False,
            sort_keys=False,
            Dumper=NoQuotedMergeDumper,
        )


def generate_config_files(
    file_path: Path,
    compose_output: Path = Path(Path.cwd(), "docker-compose.yml"),
    test_output: Path = Path(Path.cwd(), "tests", "test-config.yml"),
) -> None:
    """
    Generates configuration files for multi-server setup.

    Args:
        file_path (Path): The path to the configuration file.
        compose_output (Path, optional): The path to output the Docker Compose file.
            Defaults to 'docker-compose.yml' in the current directory.
        test_output (Path, optional): The path to output the test configs.
            Defaults to 'test-config.yml' in the current directory.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the configuration file has an unsupported file type.
    """

    compose_configs, other_configs = generate_configs(file_path)

    # Write the compose configurations to docker-compose.yml if there are any
    if compose_configs:
        write_yaml_to_file(compose_configs, compose_output)

    # Write the other configurations to test-config.yml if there are any
    if other_configs:
        write_yaml_to_file(other_configs, test_output)

def render_template_only(file_path: Path, variables_path: Path = None, include_path: list = None, output_path: Path = None, defines: dict = None) -> None:
    """
    Renders a Jinja2 template configuration file without additional parsing.

    Args:
        file_path (Path): The path to the Jinja2 template configuration file.
        variables_path (Path, optional): The path to a YAML file containing variables for rendering.
            Defaults to None.
        include_path (list, optional): Additional search paths for Jinja2 templates.
            Defaults to None.
        output_path (Path, optional): The path to output the rendered configuration file.
            defaults to the same name as the input file without the .j2 extension.
            Defaults to None.
        defines (dict, optional): Additional key=value pairs to add to template variables.
            These override any variables loaded from the vars file.
            Defaults to None.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the configuration file is not a Jinja2 template.
    """
    # If the config file does not exist, raise an error
    if not file_path.exists():
        raise FileNotFoundError(
            f"Configuration file {file_path} does not exist."
        )

    if file_path.suffix != ".j2":
        raise ValueError("Only .j2 template files are supported for auxiliary rendering.")

    # Set some variables
    config_vars = {}
    if variables_path is not None:
        # Check if the variables file exists
        if not variables_path.exists():
            # Try to file the variables file treating the path as relative to the configuration file
            potential_path = file_path.parent / variables_path
            if potential_path.exists():
                variables_path = potential_path
            else:
                # Try to find the variables treating the path as relative to the include paths
                found = False
                for path in include_path or []:
                    potential_path = Path(path, variables_path)
                    if potential_path.exists():
                        variables_path = potential_path
                        found = True
                        break
                if not found:
                    raise FileNotFoundError(
                        f"Variables file {variables_path} does not exist."
                    )
        with open(variables_path, "r", encoding="utf-8") as var_file:
            config_vars = yaml.safe_load(var_file)

    # Merge in any command-line defines (overrides vars file)
    if defines:
        config_vars.update(defines)

    # Render the Jinja2 template
    template_loader = jinja2.FileSystemLoader(searchpath=[file_path.parent] + (include_path or []))
    template_env = jinja2.Environment(loader=template_loader)
    template_env.globals.update(
        os=os,
    )
    template = template_env.get_template(file_path.name)

    try:
        rendered_config = template.render(config_vars)
    except Exception as e:
        raise ValueError(f"Error rendering {file_path}: {e}")

    # Write the rendered configuration to the output file
    if output_path is None:
        output_path = file_path.with_suffix("")

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(rendered_config)

def parse_args(args=None, prog=__package__) -> argparse.Namespace:
    """
    Parses command line arguments for the configuration parser.
    Args:
        args (list, optional): List of command line arguments. Defaults to None.
        prog (str, optional): Program name. Defaults to the package name.
    Returns:
        argparse.Namespace: Parsed command line arguments.
    """
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Generate configuration docker and test files for multi-server setup.",
    )
    parser.add_argument(
        "config_file", type=str, help="Path to the configuration file."
    )
    parser.add_argument(
        "--compose_output",
        dest="compose_output",
        type=str,
        help="Path to output the Docker Compose file.",
        default=Path(Path.cwd(), "environments", "docker-compose.yml"),
    )
    parser.add_argument(
        "--test_output",
        dest="test_output",
        type=str,
        help="Path to output the test configs.",
        default=Path(Path.cwd(), "tests", "test_configs.yml"),
    )
    parser.add_argument(
        "-d" "--data_path",
        dest="data_path",
        type=Path,
        help="Path to the data directory.",
        default=Path(
            os.getenv("DATA_PATH", str(Path(Path.cwd(), "data")))
        ),  # os.getenv wants a string, we want a Path at the end
    )
    parser.add_argument(
        "--socket-dir",
        dest="socket_dir",
        type=Path,
        help="Path to the directory to store socket files.",
        default=Path("/var/run/multi-test"),
    )
    parser.add_argument(
        "--vars-file",
        dest="variables_path",
        type=Path,
        help="Path to a YAML file containing variables for rendering.",
        default=None,
    )
    parser.add_argument(
        "--aux-file",
        dest="auxiliary",
        action="store_true",
        help="Enable auxiliary features. Enables rendering any auxiliary configurations " +
        "by just skipping other parsing logic and rendering the Jinja2 templates as-is.",
    )
    parser.add_argument(
        "--include-path",
        dest="include_path",
        help="Additional search path for Jinja2 templates.",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--output-path",
        dest="output_path",
        type=Path,
        help="Path to output the rendered configuration file. "
        "Defaults to the same name as the input file without the .j2 extension.",
        default=None,
    )
    parser.add_argument(
        "-D",
        "--define",
        dest="defines",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Define a template variable as NAME=VALUE. "
        "May be specified multiple times. Overrides variables from --vars-file.",
    )
    return parser.parse_args(args)


def interface() -> None:
    """
    Interface function to parse arguments and generate configuration files.
    """
    parsed_args = parse_args()

    # Parse -D NAME=VALUE pairs into a dict
    defines = {}
    for d in parsed_args.defines:
        if "=" not in d:
            print(f"Error: --define argument must be in NAME=VALUE format, got: {d}", file=sys.stderr)
            sys.exit(1)
        name, value = d.split("=", 1)
        defines[name] = value

    if parsed_args.auxiliary:
        try:
            render_template_only(
                Path(parsed_args.config_file),
                variables_path=parsed_args.variables_path,
                include_path=parsed_args.include_path,
                output_path=parsed_args.output_path,
                defines=defines or None,
            )
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        print("Auxiliary configuration file rendered successfully.")
        sys.exit(0)

    # Set the DATA_PATH environment variable based on the parsed argument
    if not parsed_args.data_path.exists():
        print(
            f"Data path {parsed_args.data_path} does not exist. Creating it now."
        )
        parsed_args.data_path.mkdir(parents=True, exist_ok=True)
    print(f"Setting DATA_PATH to {parsed_args.data_path}")
    os.environ["DATA_PATH"] = str(parsed_args.data_path)

    # TODO: Make the builder less dependent on global state

    if parsed_args.socket_dir:
        if not parsed_args.socket_dir.exists():
            print(
                "Socket directory %s does not exist, creating it."
                % parsed_args.socket_dir
            )
            parsed_args.socket_dir.mkdir(parents=True, exist_ok=True)

        global listener_dir
        listener_dir = parsed_args.socket_dir

    print("Using listener directory: %s" % listener_dir)
    os.environ["LISTENER_DIR"] = str(listener_dir)
    try:
        generate_config_files(
            Path(parsed_args.config_file),
            Path(parsed_args.compose_output),
            Path(parsed_args.test_output),
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print("Configuration files generated successfully.")
    sys.exit(0)


if __name__ == "__main__":
    interface()
