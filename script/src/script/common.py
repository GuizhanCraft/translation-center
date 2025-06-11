#!/usr/bin/env python3
"""
Common utility functions.
"""

from pathlib import Path
import subprocess


# Language code mapping for standardization
LANGUAGE_CODE_MAPPING = {
    "zh-Hans": "zh-CN",
    "zh-Hant": "zh-TW",
}


def get_mapped_language_code(language_code: str) -> str:
    """
    Get the mapped language code based on the predefined mapping.
    
    Args:
        language_code: The original language code
        
    Returns:
        str: The mapped language code, or the original code if no mapping exists
    """
    return LANGUAGE_CODE_MAPPING.get(language_code, language_code)


def git_commit_changes(message: str) -> None:
    """
    Commit changes to git repository.

    Args:
        message: Commit message
    """
    try:
        # Add all changes
        subprocess.run(["git", "add", "."], check=True, cwd=get_project_root_dir())
        print("Added changes to git")

        # Commit changes
        subprocess.run(
            ["git", "commit", "-m", message],
            check=True,
            cwd=get_project_root_dir(),
        )
        print(f"Committed changes: {message}")

        # Push changes
        subprocess.run(["git", "push"], check=True, cwd=get_project_root_dir())
        print("Pushed changes to remote")

    except subprocess.CalledProcessError as e:
        print(f"Git operation failed: {e}")
        raise


def get_project_root_dir() -> Path:
    """
    Get the path to project's root directory.

    Returns:
        Path: The path to project's root directory.
    """
    script_dir = Path(__file__).resolve().parent.parent.parent.parent
    return script_dir
