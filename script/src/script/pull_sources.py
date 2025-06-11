#!/usr/bin/env python3
"""
Pull source files from GitHub repositories and process them for translation.
"""

from pathlib import Path
from typing import List

from .config import Config, RepoConfig, FileConfig
from .common import git_commit_changes
from .pull_common import (
    get_translations_dir,
    get_github_raw_url,
    download_file_content,
    process_yaml_content,
    save_yaml_file,
)


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
        bool: Whether the file is updated
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

        if not data:
            print(
                f"  Warning: No translatable strings found in {file_config['source']}"
            )
            return False

        # Determine target path
        target_path = translations_dir / repo_config["folder"] / file_config["name"]

        # Save processed file
        return save_yaml_file(data, target_path, preserve_quotes=False)

    except Exception as e:
        print(f"  Error processing {file_config['source']}: {e}")
        return False


def pull_repo(repo_config: RepoConfig, translations_dir: Path) -> List[str]:
    """
    Pull source files from a repository.

    Args:
        repo_config: Repository configuration
        translations_dir: Base translations directory

    Returns:
        List[str]: List of updated file paths
    """
    print(
        f"Processing repository: {repo_config['owner']}/{repo_config['repo']}:{repo_config['branch']}"
    )

    updated_files = []

    for file_config in repo_config["files"]:
        if pull_file(repo_config, file_config, translations_dir):
            target_path = translations_dir / repo_config["folder"] / file_config["name"]
            updated_files.append(str(target_path.relative_to(translations_dir.parent)))

    return updated_files


def pull_sources(config: Config) -> None:
    """
    Pull source translation files from all configured repositories.

    Args:
        config: The configuration containing all repositories
    """
    translations_dir = get_translations_dir()
    all_updated_files = []

    print(f"Pulling source translation files to: {translations_dir}")

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
    if all_updated_files:
        git_commit_changes("chore: update source translation files")
    else:
        print("No files were updated. Skipping git commit.")

    print(f"\nCompleted pulling {len(config['repos'])} repositories.")
    print(f"Total files updated: {len(all_updated_files)}")
