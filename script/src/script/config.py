"""
Configuration management for the translation center script.
This module handles loading and validating configuration from config files.
"""

from pathlib import Path
from typing import List, TypedDict
from ruamel.yaml import YAML


class FileConfig(TypedDict):
    """Configuration for a translation file."""

    source: str
    name: str
    target: str


class RepoConfig(TypedDict):
    """Configuration for a GitHub repository."""

    owner: str
    repo: str
    branch: str
    folder: str
    files: List[FileConfig]


class Config(TypedDict):
    """Root configuration structure."""

    repos: List[RepoConfig]


def get_config_path() -> Path:
    """
    Get the path to the configuration directory.

    Returns:
        Path: The path to the configuration directory.
    """
    # Get the root directory of the project
    script_dir = Path(__file__).resolve().parent.parent.parent.parent
    return script_dir / "config"


def load_repos_config() -> Config:
    """
    Load the repositories configuration from the config file.

    Returns:
        Config: The parsed configuration.

    Raises:
        FileNotFoundError: If the configuration file doesn't exist.
        Exception: If the configuration file is invalid YAML.
    """
    config_path = get_config_path() / "repos.yml"

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    yaml_loader = YAML()
    yaml_loader.preserve_quotes = True
    yaml_loader.width = 4096

    with open(config_path, "r", encoding="utf-8") as file:
        data = yaml_loader.load(file)

    # Validate the configuration
    if not isinstance(data, dict) or "repos" not in data:
        raise ValueError("Invalid configuration format: 'repos' key not found")

    return data


def validate_config(config: Config) -> None:
    """
    Validate the configuration structure.

    Args:
        config: The configuration to validate.

    Raises:
        ValueError: If the configuration is invalid.
    """
    if not isinstance(config["repos"], list):
        raise ValueError("'repos' must be a list")

    for repo in config["repos"]:
        required_keys = ["owner", "repo", "branch", "folder", "files"]
        for key in required_keys:
            if key not in repo:
                raise ValueError(
                    f"Repository configuration missing required key: {key}"
                )

        if not isinstance(repo["files"], list):
            raise ValueError(f"'files' in repository {repo['repo']} must be a list")

        for file in repo["files"]:
            file_required_keys = ["source", "name", "target"]
            for key in file_required_keys:
                if key not in file:
                    raise ValueError(
                        f"File configuration in {repo['repo']} missing required key: {key}"
                    )
