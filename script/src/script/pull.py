#!/usr/bin/env python3
"""
Pull translation files from GitHub repositories.
This module handles downloading, processing, and saving translation files.
"""

import io
import re
import ssl
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from .config import Config, RepoConfig, FileConfig


def get_translations_dir() -> Path:
    """
    Get the path to the translations directory.

    Returns:
        Path: The path to the translations directory.
    """
    script_dir = Path(__file__).resolve().parent.parent.parent.parent
    return script_dir / "translations"


def get_github_raw_url(owner: str, repo: str, branch: str, file_path: str) -> str:
    """
    Generate GitHub raw file URL.

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch name
        file_path: Path to the file in the repository

    Returns:
        str: The raw GitHub URL
    """
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{file_path}"


def download_file_content(url: str) -> str:
    """
    Download file content from URL.

    Args:
        url: The URL to download from

    Returns:
        str: The file content

    Raises:
        URLError: If the download fails
    """
    try:
        # Create SSL context that doesn't verify certificates for GitHub raw content
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        with urlopen(url, context=ssl_context) as response:
            return response.read().decode("utf-8")
    except (URLError, HTTPError) as e:
        raise URLError(f"Failed to download {url}: {e}")


def should_skip_line(line: str) -> bool:
    """
    Check if a line should be skipped based on comments.

    Args:
        line: The line to check

    Returns:
        bool: True if the line should be skipped
    """
    # Check for "DO NOT translate" or similar comments
    comment_patterns = [
        r"#.*DO NOT translate",
        r"#.*do not translate",
        r"#.*Don\'t translate",
        r"#.*don\'t translate",
        r"#.*NO TRANSLATE",
        r"#.*no translate",
        r"#.*SKIP",
        r"#.*skip",
    ]

    for pattern in comment_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return True

    return False


def process_yaml_content(content: str) -> Dict[str, Any]:
    """
    Process YAML content and filter out lines with DO NOT translate comments.

    Args:
        content: Raw YAML content

    Returns:
        Dict[str, Any]: Processed YAML data with only translatable strings
    """
    lines = content.split("\n")
    filtered_lines = []

    for line in lines:
        # Skip lines with DO NOT translate comments
        if should_skip_line(line):
            continue

        # Keep the line
        filtered_lines.append(line)

    # Parse the filtered YAML with order preservation
    filtered_content = "\n".join(filtered_lines)

    try:
        # Use RoundTripLoader to preserve order and formatting
        yaml_loader = YAML()
        yaml_loader.preserve_quotes = True
        yaml_loader.width = 4096  # Prevent line wrapping

        stream = io.StringIO(filtered_content)
        data = yaml_loader.load(stream)
        return data if data is not None else {}
    except Exception as e:
        print(f"Warning: Failed to parse YAML content: {e}")
        return {}


def convert_arrays_to_multiline(data: Any, key: str = "") -> Any:
    """
    Convert string arrays to multiline strings for better Crowdin handling.

    Args:
        data: The YAML data structure
        key: Current key being processed

    Returns:
        Any: Data with arrays converted to multiline strings where appropriate
    """
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            result[k] = convert_arrays_to_multiline(v, k)
        return result
    elif isinstance(data, list):
        # Check if this is a list of strings that should be converted to multiline
        if all(isinstance(item, str) for item in data):
            # Convert array to multiline string using literal block scalar
            # This preserves line breaks and makes it easier for Crowdin to handle
            multiline_content = "\n".join(data)
            # Use ruamel.yaml's literal scalar for proper multiline representation
            return LiteralScalarString(multiline_content)
        else:
            # Process each item in the list
            result = []
            for item in data:
                processed_item = convert_arrays_to_multiline(item, key)
                result.append(processed_item)
            return result
    else:
        return data


def extract_strings_only(data: Any) -> Any:
    """
    Recursively extract only string values from YAML data.

    Args:
        data: The YAML data structure

    Returns:
        Any: Filtered data containing only strings
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            processed_value = extract_strings_only(value)
            if processed_value is not None:
                result[key] = processed_value
        return result if result else None
    elif isinstance(data, list):
        result = []
        for item in data:
            processed_item = extract_strings_only(item)
            if processed_item is not None:
                result.append(processed_item)
        return result if result else None
    elif isinstance(data, str):
        return data
    else:
        # Skip non-string values (numbers, booleans, etc.)
        return None


def save_processed_file(data: Dict[str, Any], target_path: Path) -> bool:
    """
    Save processed YAML data to file.

    Args:
        data: The processed YAML data
        target_path: Path where to save the file

    Returns:
        bool: True if file was created/updated, False if no changes
    """
    # Create directory if it doesn't exist
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if file exists and compare content
    file_changed = True
    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                existing_data = yaml.safe_load(f)
            file_changed = existing_data != data
        except (yaml.YAMLError, IOError):
            # If we can't read the existing file, assume it changed
            file_changed = True

    if file_changed:
        # Save the processed data with order preservation
        yaml_dumper = YAML()
        yaml_dumper.preserve_quotes = True
        yaml_dumper.default_flow_style = False
        yaml_dumper.allow_unicode = True
        yaml_dumper.width = 4096
        yaml_dumper.sort_keys = False  # Preserve original order
        yaml_dumper.default_style = (
            "|"  # Use literal block scalar for multiline strings
        )

        with open(target_path, "w", encoding="utf-8") as f:
            yaml_dumper.dump(data, f)

        print(f"  Saved: {target_path}")
        return True
    else:
        print(f"  No changes: {target_path}")
        return False


def pull_file(
    repo_config: RepoConfig, file_config: FileConfig, translations_dir: Path
) -> bool:
    """
    Pull and process a single file from a repository.

    Args:
        repo_config: Repository configuration
        file_config: File configuration
        translations_dir: Base translations directory

    Returns:
        bool: True if file was updated, False otherwise
    """
    # Generate GitHub raw URL
    url = get_github_raw_url(
        repo_config["owner"],
        repo_config["repo"],
        repo_config["branch"],
        file_config["source"],
    )

    print(f"  Downloading: {url}")

    try:
        # Download file content
        content = download_file_content(url)

        # Process YAML content
        data = process_yaml_content(content)

        # Extract only strings
        strings_only = extract_strings_only(data)

        if not strings_only:
            print(
                f"  Warning: No translatable strings found in {file_config['source']}"
            )
            return False

        # Convert string arrays to multiline strings for better Crowdin handling
        processed_data = convert_arrays_to_multiline(strings_only)

        # Determine target path
        target_path = translations_dir / repo_config["folder"] / file_config["name"]

        # Save processed file
        return save_processed_file(processed_data, target_path)

    except Exception as e:
        print(f"  Error processing {file_config['source']}: {e}")
        return False


def pull_repo(repo_config: RepoConfig, translations_dir: Path) -> List[str]:
    """
    Pull all files from a repository.

    Args:
        repo_config: Repository configuration
        translations_dir: Base translations directory

    Returns:
        List[str]: List of updated file paths
    """
    print(f"Processing repository: {repo_config['owner']}/{repo_config['repo']}")

    updated_files = []

    for file_config in repo_config["files"]:
        if pull_file(repo_config, file_config, translations_dir):
            target_path = translations_dir / repo_config["folder"] / file_config["name"]
            updated_files.append(str(target_path.relative_to(translations_dir.parent)))

    return updated_files


def commit_changes(updated_files: List[str]) -> None:
    """
    Commit changes to git if there are any updates.

    Args:
        updated_files: List of updated file paths
    """
    if not updated_files:
        print("No files updated, skipping git commit.")
        return

    try:
        # Get the project root directory
        script_dir = Path(__file__).resolve().parent.parent.parent.parent

        # Add updated files to git
        subprocess.run(
            ["git", "add"] + updated_files,
            cwd=script_dir,
            check=True,
            capture_output=True,
        )

        # Create commit message
        commit_message = (
            f"chore: update source translation files\n\nUpdated files:\n"
            + "\n".join(f"- {f}" for f in updated_files)
        )

        # Commit changes
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=script_dir,
            check=True,
            capture_output=True,
        )

        # Push changes
        subprocess.run(
            ["git", "push"],
            cwd=script_dir,
            check=True,
            capture_output=True,
        )

        print(f"Committed {len(updated_files)} updated files to git.")

    except subprocess.CalledProcessError as e:
        print(f"Git operation failed: {e}")
        if e.stdout:
            print(f"stdout: {e.stdout.decode()}")
        if e.stderr:
            print(f"stderr: {e.stderr.decode()}")
    except Exception as e:
        print(f"Error during git commit: {e}")


def pull_all_repos(config: Config) -> None:
    """
    Pull translation files from all configured repositories.

    Args:
        config: The configuration containing all repositories
    """
    translations_dir = get_translations_dir()
    all_updated_files = []

    print(f"Pulling translation files to: {translations_dir}")

    for repo_config in config["repos"]:
        try:
            updated_files = pull_repo(repo_config, translations_dir)
            all_updated_files.extend(updated_files)
        except Exception as e:
            print(
                f"Error processing repository {repo_config['owner']}/{repo_config['repo']}: {e}"
            )
            continue

    # Commit all changes
    commit_changes(all_updated_files)

    print(f"\nCompleted pulling {len(config['repos'])} repositories.")
    print(f"Total files updated: {len(all_updated_files)}")
