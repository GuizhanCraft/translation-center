"""
Translation center automation script.
This script manages translation files across multiple GitHub repositories.
"""

from .config import load_repos_config, validate_config, Config


def main() -> None:
    """
    Main entry point for the script.
    This function is called when the script is executed.
    """
    try:
        # Part 1: Load configuration
        print("Loading configuration...")
        config = load_repos_config()
        validate_config(config)
        print(f"Loaded configuration with {len(config['repos'])} repositories.")
        
        # Part 2: Pull the latest source files.
        print("\nPulling translation files...")
        from .pull import pull_all_repos
        pull_all_repos(config)
        print("Pull operation completed.")
        
    except Exception as e:
        print(f"Unexpected Error: {e}")
        raise
