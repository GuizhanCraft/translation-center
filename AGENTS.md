# AGENTS.md

## 1. Overview

A unified repository that manages translations for Minecraft plugins via Crowdin. It automates syncing source translation files from GitHub repositories and importing existing translations.

## 2. Folder Structure

- `config/`: repository configuration defining plugins and file mappings.
    - `repos.yml`: YAML configuration listing GitHub repos, branches, and translation file paths to sync.
- `script/`: Python automation scripts for translation sync operations.
    - `src/script/`: core script modules.
        - `config.py`: configuration loading and validation using TypedDict.
        - `common.py`: shared utilities including language code mapping and git operations.
        - `pull_common.py`: common utilities for downloading and processing YAML files.
        - `pull_sources.py`: pulls source translation files from configured repositories.
        - `pull_translations.py`: imports existing translations from other repositories.
- `translations/`: translation files organized by plugin folder (e.g., `FastMachines/`, `GuizhanCraft/`).
    - Each folder contains language files: `en-US.yml` (source), `zh-CN.yml`, `ja.yml`, etc.
- `.github/workflows/`: GitHub Actions workflows for automated sync.
    - `sync.yml`: scheduled workflow (every 10 minutes) that runs `pull_sources` command.
- `crowdin.yml`: Crowdin integration configuration for translation management.

## 3. Core Behaviors & Patterns

**YAML Processing**: Uses `ruamel.yaml` with consistent settings: `preserve_quotes=True`, `sort_keys=False`, `width=4096`. Source files use `preserve_quotes=False` for cleaner output; imported translations use `preserve_quotes=True`.

**Content Filtering**: Lines containing skip patterns like `# DO NOT translate` or `# don't translate` are filtered out during processing.

**Data Sanitization**: `process_yaml_data()` recursively extracts only string values, converts string lists to `LiteralScalarString` multiline format, and removes non-string types (numbers, booleans, floats).

**Language Code Standardization**: Non-standard language codes are mapped to standardized forms (e.g., `zh-Hans` → `zh-CN`, `pt_BR` → `pt`, `vi-VN` → `vi`) via per-repository `language_mapping` in `repos.yml`. Each repository can define its own mapping from plugin-specific codes to Crowdin standardized codes.

**Error Handling**: Operations print warnings on individual file failures but continue processing remaining repositories/files. Repository-level errors are caught and logged without stopping the entire sync.

**Git Automation**: Changes are automatically committed with conventional commit messages (`chore: update source translation files`) and pushed to remote via `git_commit_changes()`.

**File Change Detection**: Before saving, existing files are loaded and compared to avoid unnecessary writes. Returns boolean indicating whether file was actually updated.

**SSL Configuration**: Downloads use `ssl.create_default_context()` with `check_hostname=False` and `verify_mode=CERT_NONE` for GitHub raw URLs and API requests.

## 4. Conventions

**Naming**: Use `snake_case` for functions and variables. TypedDict classes use PascalCase with `Config` suffix (e.g., `RepoConfig`, `FileConfig`).

**Type Annotations**: All functions include type hints for parameters and return values. Use `TypedDict` for structured configuration data.

**Comments**: Docstrings use triple quotes with brief description, Args/Returns sections. Inline comments explain non-obvious logic.

**String Formatting**: Use f-strings for string interpolation. Multi-line strings use triple quotes.

**Path Handling**: Use `pathlib.Path` for all file system operations. Project root is determined relative to script location via `Path(__file__).resolve().parent` traversal.

**Imports**: Group imports by standard library, third-party, then local modules. Local imports use relative syntax (e.g., `from .config import ...`).

**Function Design**: Functions are small and single-purpose. Guard clauses handle edge cases early. Return boolean flags to indicate success/change status.

## 5. Working Agreements

- Respond in user's preferred language; if unspecified, infer from codebase (keep tech terms in English, never translate code blocks)
- Create tests/lint only when explicitly requested
- Build context by reviewing related usages and patterns before editing
- Prefer simple solutions; avoid unnecessary abstraction
- Ask for clarification when requirements are ambiguous
- Minimal changes; preserve public APIs
- This project uses Python without static type checking; follow existing type hint conventions
- New functions: single-purpose, colocated with related code
- External dependencies: only when necessary, explain why
