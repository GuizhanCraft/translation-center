#!/usr/bin/env python3
"""
Push translation files from local translations/ directory to configured GitHub repositories.
Clones each target repository, applies all translation changes in a single commit, and pushes.
Skips archived repositories and empty translation files.
"""

import json
import os
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .config import Config, FileConfig, RepoConfig
from .pull_common import get_translations_dir


def get_remote_language_code(
    language_code: str, language_mapping: dict[str, str] | None
) -> str:
    if language_mapping is not None:
        reverse_mapping = {v: k for k, v in language_mapping.items()}
        return reverse_mapping.get(language_code, language_code)
    return language_code


def create_ssl_context() -> ssl.SSLContext:
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
    headers = {
        "Authorization": f"Bearer {token}",
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


def is_repo_archived(owner: str, repo: str, token: str) -> bool:
    url = f"https://api.github.com/repos/{owner}/{repo}"
    status, data = request_github_json(url, token)
    if status == 200:
        return bool(data.get("archived", False))
    error_msg = data.get("message", f"HTTP {status}")
    print(f"  Warning: Failed to check repository status: {error_msg}")
    return False


def run_git_command(
    args: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def clone_repo(owner: str, repo: str, branch: str, token: str, temp_dir: Path) -> Path:
    clone_url = f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"
    repo_dir = temp_dir / repo
    run_git_command(
        ["clone", "--depth", "1", "--branch", branch, clone_url, str(repo_dir)],
        cwd=temp_dir,
    )
    return repo_dir


def get_translation_files(folder: Path) -> list[Path]:
    if not folder.exists():
        return []

    files = []
    for yml_file in folder.glob("*.yml"):
        if yml_file.stem not in ("en-US", "en"):
            files.append(yml_file)

    return sorted(files)


def collect_changes_for_file_config(
    repo_config: RepoConfig, file_config: FileConfig, translations_dir: Path
) -> list[tuple[Path, str]]:
    changes: list[tuple[Path, str]] = []
    folder = translations_dir / repo_config["folder"]
    translation_files = get_translation_files(folder)
    language_mapping = repo_config.get("language_mapping")

    for local_file in translation_files:
        local_content = local_file.read_text(encoding="utf-8")

        if not local_content.strip():
            print(f"  Skipping empty file: {local_file.name}")
            continue

        local_lang_code = local_file.stem
        remote_lang_code = get_remote_language_code(local_lang_code, language_mapping)

        try:
            remote_path = file_config["target"].format(lang=remote_lang_code)
        except KeyError as e:
            print(
                f"    Error: Invalid target template for {local_file.name}: missing {e}"
            )
            continue

        changes.append((local_file, remote_path))

    return changes


def push_repo(repo_config: RepoConfig, translations_dir: Path, token: str) -> list[str]:
    owner = repo_config["owner"]
    repo = repo_config["repo"]
    branch = repo_config["branch"]

    print(f"Processing repository: {owner}/{repo}:{branch}")

    if is_repo_archived(owner, repo, token):
        print(f"  Skipping archived repository: {owner}/{repo}")
        return []

    pushed_files: list[str] = []
    temp_dir = Path(tempfile.mkdtemp(prefix=f"push_{repo}_"))

    try:
        all_changes: list[tuple[Path, str]] = []
        for file_config in repo_config["files"]:
            changes = collect_changes_for_file_config(
                repo_config, file_config, translations_dir
            )
            all_changes.extend(changes)

        if not all_changes:
            print("  No translation files to push")
            return pushed_files

        print(f"  Found {len(all_changes)} translation files to push")

        repo_dir = clone_repo(owner, repo, branch, token, temp_dir)

        files_changed = False
        for local_file, remote_path in all_changes:
            target_path = repo_dir / remote_path
            target_path.parent.mkdir(parents=True, exist_ok=True)

            existing_content = ""
            if target_path.exists():
                existing_content = target_path.read_text(encoding="utf-8")

            new_content = local_file.read_text(encoding="utf-8")

            if existing_content == new_content:
                print(f"    No changes: {remote_path}")
                continue

            target_path.write_text(new_content, encoding="utf-8")
            files_changed = True
            pushed_files.append(str(local_file.relative_to(translations_dir.parent)))
            print(f"    Updated: {remote_path}")

        if not files_changed:
            print("  All files are up to date")
            return pushed_files

        run_git_command(["add", "."], cwd=repo_dir)
        run_git_command(["commit", "-m", "chore(i18n): update translations"], cwd=repo_dir)
        run_git_command(["push", "origin", branch], cwd=repo_dir)
        print(f"  Pushed {len(pushed_files)} files in a single commit")

    except subprocess.CalledProcessError as e:
        print(f"  Git operation failed: {e}")
        if e.stderr:
            print(f"    stderr: {e.stderr.strip()}")
    except Exception as e:
        print(f"  Error processing repository: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return pushed_files


def push_translations(config: Config) -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        print("Error: BOT_TOKEN environment variable is required")
        print(
            "Please set BOT_TOKEN with a GitHub token that has write access to target repositories"
        )
        return

    translations_dir = get_translations_dir()
    all_pushed_files: list[str] = []

    print(f"Pushing translation files from: {translations_dir}")
    print("=" * 60)

    for repo_config in config["repos"]:
        try:
            pushed_files = push_repo(repo_config, translations_dir, token)
            all_pushed_files.extend(pushed_files)
        except Exception as e:
            print(f"Error processing repository {repo_config['owner']}/{repo_config['repo']}: {e}")
            continue
        print()

    print("=" * 60)
    print("Push completed!")
    print(f"Total repositories processed: {len(config['repos'])}")
    print(f"Total files pushed: {len(all_pushed_files)}")

    if all_pushed_files:
        print("\nPushed files:")
        for file_path in all_pushed_files:
            print(f"  - {file_path}")
