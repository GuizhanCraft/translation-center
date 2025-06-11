#!/usr/bin/env python3
"""
Translation center script package.
"""

import sys
from .config import load_repos_config, validate_config
from .pull_sources import pull_sources
from .pull_translations import pull_translations


def main() -> None:
    """
    Main entry point for the script package.
    """
    # Load configuration
    config = load_repos_config()
    validate_config(config)

    # Check command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "pull_sources":
            pull_sources(config)
        elif command == "pull_translations":
            pull_translations(config)
        elif command == "list":
            print("Configuration is valid!")
            print(f"Loaded {len(config['repos'])} repositories.")
            for repo in config["repos"]:
                print(
                    f"  - {repo['owner']}/{repo['repo']} ({len(repo['files'])} files)"
                )
        else:
            print(f"Unknown command: {command}")
            print("Available commands: pull_sources, pull_translations, list")
    else:
        print("Unknown command: ")
        print("Available commands: pull_sources, pull_translations, list")
