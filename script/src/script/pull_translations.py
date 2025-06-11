#!/usr/bin/env python3
"""
Import existing translation files from other repositories.
This module handles downloading and importing translation files that already exist
in other repositories, allowing for bulk import of translations.
"""

from pathlib import Path
from typing import Dict, Any, Set, List
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from .config import Config, RepoConfig
from .pull_common import (
    get_translations_dir,
    get_github_raw_url,
    download_file_content,
    process_yaml_content,
    save_yaml_file,
)
from .common import get_mapped_language_code


def get_github_api_url(owner: str, repo: str, path: str, branch: str = "master") -> str:
    """
    Generate GitHub API URL for directory contents.

    Args:
        owner: Repository owner
        repo: Repository name
        path: Directory path
        branch: Branch name

    Returns:
        str: The GitHub API URL
    """
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"


def download_json_content(url: str) -> Any:
    """
    Download and parse JSON content from URL.

    Args:
        url: The URL to download from

    Returns:
        Any: Parsed JSON data

    Raises:
        URLError: If the download fails
    """
    try:
        import ssl
        import json

        # Create SSL context that doesn't verify certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        with urlopen(url, context=ssl_context) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, HTTPError) as e:
        raise URLError(f"Failed to download {url}: {e}")


def scan_language_files(owner: str, repo: str, branch: str, lang_dir: str) -> Set[str]:
    """
    Scan all language files in a repository directory.

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch name
        lang_dir: Language directory path

    Returns:
        Set[str]: Set of language file names
    """
    try:
        api_url = get_github_api_url(owner, repo, lang_dir, branch)
        contents = download_json_content(api_url)

        language_files = set()
        for item in contents:
            if item["type"] == "file" and item["name"].endswith(".yml"):
                language_files.add(item["name"])

        return language_files
    except Exception as e:
        print(f"  Warning: Could not list files in {lang_dir}: {e}")
        return set()


def pull_file(
    owner: str, repo: str, branch: str, file_path: str, target_dir: Path, file_name: str
) -> bool:
    """
    Pull a single language file.

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch name
        file_path: Source file path in repository
        target_dir: Target directory
        file_name: Target file name

    Returns:
        bool: True if file was successfully imported
    """
    try:
        url = get_github_raw_url(owner, repo, branch, file_path)
        content = download_file_content(url)

        # Process YAML content with full processing pipeline
        data = process_yaml_content(content)
        if not data:
            print(f"    Warning: No translatable content found in {file_name}")
            return False

        # Save to target location (preserve quotes for imported translations)
        target_path = target_dir / file_name
        return save_yaml_file(data, target_path, preserve_quotes=True)

    except Exception as e:
        print(f"    Error importing {file_name}: {e}")
        return False


def pull_repo(repo_config: RepoConfig, translations_dir: Path) -> List[str]:
    """
    Pull all existing translation files from a repository.

    Args:
        repo_config: Repository configuration
        translations_dir: Base translations directory

    Returns:
        List[str]: List of imported file paths
    """
    print(
        f"Importing existing translations from: {repo_config['owner']}/{repo_config['repo']}"
    )

    imported_files = []

    for file_config in repo_config["files"]:
        source_path = file_config["source"]
        target_pattern = file_config["target"]

        # Extract directory from source path
        lang_dir = str(Path(source_path).parent)

        print(f"  Scanning directory: {lang_dir}")

        # Get all language files in the directory
        language_files = scan_language_files(
            repo_config["owner"], repo_config["repo"], repo_config["branch"], lang_dir
        )

        if not language_files:
            print(f"    No language files found")
            continue

        # Filter out the source file (en-US.yml)
        source_file_name = Path(source_path).name
        language_files.discard(source_file_name)

        print(f"    Found {len(language_files)} translation files")

        # Import each language file
        target_dir = translations_dir / repo_config["folder"]

        for lang_file in language_files:
            # Extract language code from filename
            lang_code = Path(lang_file).stem
            
            # Get mapped language code for standardization
            mapped_lang_code = get_mapped_language_code(lang_code)
            mapped_file_name = f"{mapped_lang_code}.yml"

            # Build source file path
            source_file_path = f"{lang_dir}/{lang_file}"

            # Import the file with mapped filename
            if pull_file(
                repo_config["owner"],
                repo_config["repo"],
                repo_config["branch"],
                source_file_path,
                target_dir,
                mapped_file_name,
            ):
                relative_path = target_dir / mapped_file_name
                imported_files.append(
                    str(relative_path.relative_to(translations_dir.parent))
                )

    return imported_files


def pull_translations(config: Config) -> None:
    """
    Pull existing translation files from all configured repositories.

    Args:
        config: The configuration containing all repositories
    """
    translations_dir = get_translations_dir()
    all_imported_files = []

    for repo_config in config["repos"]:
        try:
            imported_files = pull_repo(repo_config, translations_dir)
            all_imported_files.extend(imported_files)
            print(
                f"  Imported {len(imported_files)} files from {repo_config['owner']}/{repo_config['repo']}:{repo_config['branch']}"
            )
        except Exception as e:
            print(
                f"Error processing repository {repo_config['owner']}/{repo_config['repo']}:{repo_config['branch']}: {e}"
            )
            continue
        print()

    print("=" * 60)
    print(f"Import completed!")
    print(f"Total repositories processed: {len(config['repos'])}")
    print(f"Total files imported: {len(all_imported_files)}")

    if all_imported_files:
        print("\nImported files:")
        for file_path in all_imported_files:
            print(f"  - {file_path}")
