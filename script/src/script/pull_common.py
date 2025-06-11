#!/usr/bin/env python3
"""
Common utilities for pulling and processing translation files.
"""

from io import StringIO
import re
import ssl
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
        # Create SSL context that doesn't verify certificates
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
    skip_patterns = [
        r"#.*DO NOT translate",
        r"#.*do not translate",
        r"#.*Don't translate",
        r"#.*don't translate",
    ]

    for pattern in skip_patterns:
        if re.search(pattern, line, re.IGNORECASE):
            return True

    return False


def process_yaml_content(content: str) -> Dict[str, Any]:
    """
    Process YAML content, filter out lines with should skip comments, and only keep string values.

    Args:
        content: Raw YAML content

    Returns:
        Dict[str, Any]: Processed YAML data
    """
    # Filter out lines with should skip comments
    lines = content.split("\n")
    filtered_lines = []

    for line in lines:
        if not should_skip_line(line):
            filtered_lines.append(line)

    filtered_content = "\n".join(filtered_lines)

    # Parse the filtered YAML with order preservation
    try:
        yaml_loader = YAML()
        yaml_loader.preserve_quotes = True
        yaml_loader.width = 4096
        yaml_loader.sort_keys = False

        data = yaml_loader.load(StringIO(filtered_content))
        processed_data = process_yaml_data(data)
        return processed_data if processed_data else {}
    except Exception as e:
        print(f"Warning: Failed to parse YAML content: {e}")
        return {}


def process_yaml_data(data: Any) -> Any:
    """
    Recursively extract only string values from YAML data, convert string lists to multiline strings.
    Removes other data types (numbers, booleans, floats, etc.) and preserves all comments.

    Args:
        data: The YAML data structure

    Returns:
        Any: Processed data with string lists converted to multiline strings
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            processed_value = process_yaml_data(value)
            if processed_value is not None:
                result[key] = processed_value
        return result if result else None
    elif isinstance(data, list):
        # Skip empty lists - don't import empty list fields
        if not data:
            return None
        
        # Convert list to multiline string if all elements are strings
        if all(isinstance(item, str) for item in data):
            # Always use multiline format for string lists, even with single item
            multiline_content = "\n".join(data)
            return LiteralScalarString(multiline_content)
        else:
            # Process each item in the list and keep only strings
            processed_items = []
            for item in data:
                if isinstance(item, str):
                    processed_items.append(item)
                elif isinstance(item, (dict, list)):
                    processed_item = process_yaml_data(item)
                    if processed_item is not None:
                        processed_items.append(processed_item)
            # Convert to multiline string if we have string items
            if processed_items and all(
                isinstance(item, str) for item in processed_items
            ):
                multiline_content = "\n".join(processed_items)
                return LiteralScalarString(multiline_content)
            return processed_items if processed_items else None
    elif isinstance(data, str):
        return data
    else:
        # Skip non-string values (numbers, booleans, floats, etc.)
        return None


def create_yaml(preserve_quotes: bool = False) -> YAML:
    """
    Create a YAML processor with consistent settings.

    Args:
        preserve_quotes: Whether to preserve quotes in output

    Returns:
        YAML: Configured YAML processor
    """
    yaml_processor = YAML()
    yaml_processor.preserve_quotes = preserve_quotes
    yaml_processor.default_flow_style = False
    yaml_processor.allow_unicode = True
    yaml_processor.width = 4096
    yaml_processor.sort_keys = False  # Preserve original order
    yaml_processor.encoding = "utf-8"

    if not preserve_quotes:
        # Don't use literal block scalar style for cleaner output
        yaml_processor.default_style = None

    return yaml_processor


def save_yaml_file(
    data: Dict[str, Any], target_path: Path, preserve_quotes: bool = False
) -> bool:
    """
    Save YAML data to file with proper formatting.

    Args:
        data: The YAML data to save
        target_path: Path where to save the file
        preserve_quotes: Whether to preserve quotes in output

    Returns:
        bool: Whether the file is updated
    """
    # Create directory if it doesn't exist
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if file exists and compare content
    file_changed = True
    if target_path.exists():
        try:
            yaml_loader = YAML()
            with open(target_path, "r", encoding="utf-8") as f:
                existing_data = yaml_loader.load(f)
            file_changed = existing_data != data
        except (Exception, IOError):
            # If we can't read the existing file, assume it changed
            file_changed = True

    if file_changed:
        # Save the processed data
        yaml_dumper = create_yaml(preserve_quotes)

        with open(target_path, "w", encoding="utf-8") as f:
            yaml_dumper.dump(data, f)

        print(f"  Saved: {target_path}")
        return True
    else:
        print(f"  No changes: {target_path}")
        return False
