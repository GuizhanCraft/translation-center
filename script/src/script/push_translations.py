#!/usr/bin/env python3
"""
Push translation files from local translations/ directory to configured GitHub repositories.
Uses GitHub Contents API to create or update files in target plugin repos.
"""

import base64
import binascii
import json
import os
import ssl
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Config, RepoConfig, FileConfig
from .pull_common import get_translations_dir


def get_remote_language_code(
    language_code: str, language_mapping: dict[str, str] | None
) -> str:
    if language_mapping is not None:
        reverse_mapping = {v: k for k, v in language_mapping.items()}
        return reverse_mapping.get(language_code, language_code)
    return language_code


def get_github_api_url(owner: str, repo: str, path: str, branch: str = "master") -> str:
    """
    Generate GitHub Contents API URL for a file.

    Args:
        owner: Repository owner
        repo: Repository name
        path: File path in the repository
        branch: Branch name

    Returns:
        str: The GitHub API URL
    """
    return f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"


def create_ssl_context() -> ssl.SSLContext:
    """
    Create an SSL context that doesn't verify certificates.
    Matches the pattern used in pull_common.py.

    Returns:
        ssl.SSLContext: Configured SSL context
    """
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    return ssl_context


def request_github_json(
    url: str,
    token: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """
    Make a GitHub API request and return response.

    Args:
        url: The API URL
        token: GitHub authentication token
        method: HTTP method (GET or PUT)
        payload: Optional JSON payload for PUT requests

    Returns:
        Tuple[int, Any]: HTTP status code and parsed JSON response (or error dict)

    Raises:
        URLError: If the request fails at network level
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "translation-center-script",
    }

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    else:
        data = None

    request = Request(url, data=data, headers=headers, method=method)
    ssl_context = create_ssl_context()

    try:
        with urlopen(request, context=ssl_context) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
            if body:
                return status, json.loads(body)
            return status, {}
    except HTTPError as e:
        status = e.code
        try:
            body = e.read().decode("utf-8")
            error_data = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_data = {"message": str(e)}
        return status, error_data


def get_existing_file_state(
    owner: str, repo: str, branch: str, file_path: str, token: str
) -> tuple[str | None, str | None]:
    """
    Check if a file exists in the remote repository and get its SHA and content.

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch name
        file_path: Path to the file in the repository
        token: GitHub authentication token

    Returns:
        Tuple[Optional[str], Optional[str]]: (sha, decoded_content) if file exists,
                                             (None, None) if file doesn't exist
    """
    url = get_github_api_url(owner, repo, file_path, branch)
    status, data = request_github_json(url, token, "GET")

    if status == 404:
        return None, None
    elif status == 200:
        sha = data.get("sha")
        content_b64 = data.get("content", "")
        try:
            decoded_content = base64.b64decode(content_b64.replace("\n", "")).decode(
                "utf-8"
            )
        except (binascii.Error, UnicodeDecodeError):
            decoded_content = None
        return sha, decoded_content
    else:
        error_msg = data.get("message", f"HTTP {status}")
        raise URLError(f"Failed to check file state: {error_msg}")


def put_file_content(
    owner: str,
    repo: str,
    branch: str,
    file_path: str,
    content: str,
    token: str,
    commit_message: str,
    sha: str | None = None,
) -> bool:
    """
    Create or update a file in the remote repository via GitHub Contents API.

    Args:
        owner: Repository owner
        repo: Repository name
        branch: Branch name
        file_path: Path to the file in the repository
        content: File content as UTF-8 string
        token: GitHub authentication token
        commit_message: Commit message
        sha: SHA of existing file (required for updates, omit for creates)

    Returns:
        bool: True if successful, False otherwise
    """
    url = get_github_api_url(owner, repo, file_path, branch)
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")

    payload: dict[str, str] = {
        "message": commit_message,
        "content": content_b64,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    status, data = request_github_json(url, token, "PUT", payload)

    if status in (200, 201):
        print(f"    Successfully pushed: {file_path}")
        return True
    elif status == 409:
        print(f"    Warning: Conflict pushing {file_path} (file may have changed)")
        return False
    else:
        error_msg = data.get("message", f"HTTP {status}")
        print(f"    Error pushing {file_path}: {error_msg}")
        return False


def get_translation_files(folder: Path) -> list[Path]:
    """
    Get all translation YAML files in a folder, excluding source files.

    Args:
        folder: Path to the translations folder

    Returns:
        list[Path]: Sorted list of translation file paths
    """
    if not folder.exists():
        return []

    files = []
    for yml_file in folder.glob("*.yml"):
        if yml_file.stem not in ("en-US", "en"):
            files.append(yml_file)

    return sorted(files)


def push_file(
    repo_config: RepoConfig,
    file_config: FileConfig,
    translations_dir: Path,
    token: str,
) -> list[str]:
    """
    Push translation files for a single file configuration entry.

    Args:
        repo_config: Repository configuration
        file_config: File configuration
        translations_dir: Base translations directory
        token: GitHub authentication token

    Returns:
        list[str]: List of successfully pushed file paths
    """
    pushed_files = []
    folder = translations_dir / repo_config["folder"]
    translation_files = get_translation_files(folder)

    if not translation_files:
        print(f"  No translation files found in {folder}")
        return pushed_files

    print(f"  Found {len(translation_files)} translation files to push")

    language_mapping = repo_config.get("language_mapping")

    for local_file in translation_files:
        local_lang_code = local_file.stem
        remote_lang_code = get_remote_language_code(local_lang_code, language_mapping)

        try:
            remote_path = file_config["target"].format(lang=remote_lang_code)
        except KeyError as e:
            print(
                f"    Error: Invalid target template for {local_file.name}: missing {e}"
            )
            continue

        print(f"  Processing: {local_file.name} -> {remote_path}")

        try:
            local_content = local_file.read_text(encoding="utf-8")
            sha, remote_content = get_existing_file_state(
                repo_config["owner"],
                repo_config["repo"],
                repo_config["branch"],
                remote_path,
                token,
            )

            if remote_content is not None and remote_content == local_content:
                print(f"    No changes: {remote_path}")
                continue

            if sha:
                commit_message = f"chore(i18n): update {remote_path}"
            else:
                commit_message = f"chore(i18n): add {remote_path}"

            if put_file_content(
                repo_config["owner"],
                repo_config["repo"],
                repo_config["branch"],
                remote_path,
                local_content,
                token,
                commit_message,
                sha,
            ):
                pushed_files.append(
                    str(local_file.relative_to(translations_dir.parent))
                )

        except Exception as e:
            print(f"    Error processing {local_file.name}: {e}")
            continue

    return pushed_files


def push_repo(repo_config: RepoConfig, translations_dir: Path, token: str) -> list[str]:
    """
    Push all translation files for a repository.

    Args:
        repo_config: Repository configuration
        translations_dir: Base translations directory
        token: GitHub authentication token

    Returns:
        list[str]: List of successfully pushed file paths
    """
    print(
        f"Processing repository: {repo_config['owner']}/{repo_config['repo']}:{repo_config['branch']}"
    )

    pushed_files = []

    for file_config in repo_config["files"]:
        try:
            files = push_file(repo_config, file_config, translations_dir, token)
            pushed_files.extend(files)
        except Exception as e:
            print(f"  Error processing file config: {e}")
            continue

    return pushed_files


def push_translations(config: Config) -> None:
    """
    Push translation files from local translations/ directory to all configured repositories.

    Args:
        config: The configuration containing all repositories
    """
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("Error: BOT_TOKEN environment variable is required")
        print(
            "Please set BOT_TOKEN with a GitHub token that has write access to target repositories"
        )
        return

    translations_dir = get_translations_dir()
    all_pushed_files = []

    print(f"Pushing translation files from: {translations_dir}")
    print("=" * 60)

    for repo_config in config["repos"]:
        try:
            pushed_files = push_repo(repo_config, translations_dir, token)
            all_pushed_files.extend(pushed_files)
            if pushed_files:
                print(
                    f"  Pushed {len(pushed_files)} files from {repo_config['owner']}/{repo_config['repo']}"
                )
        except Exception as e:
            print(
                f"Error processing repository {repo_config['owner']}/{repo_config['repo']}: {e}"
            )
            continue
        print()

    print("=" * 60)
    print(f"Push completed!")
    print(f"Total repositories processed: {len(config['repos'])}")
    print(f"Total files pushed: {len(all_pushed_files)}")

    if all_pushed_files:
        print("\nPushed files:")
        for file_path in all_pushed_files:
            print(f"  - {file_path}")
