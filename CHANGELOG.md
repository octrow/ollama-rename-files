# Changelog

All notable changes to this project. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versions follow [Semantic Versioning](https://semver.org/).

## [0.3.0] - unreleased

First tagged release.

### Added

- `ollama-rename` command: `ollama-rename` for the CLI, `ollama-rename gui` for the desktop window.
- One-line installers for macOS/Linux (`install.sh`) and Windows (`install.ps1`), and standalone builds for
  Linux x86_64/arm64, macOS (Apple silicon) and Windows on every release.
- GUI: preview of the exact files that will change, live old → new list as the model answers, Stop between files,
  light and dark theme.
- GUI opens in the default browser on Linux without Qt or GTK bindings instead of crashing.
- GUI serves on `127.0.0.1:5000` (`--port`, `FILE_RENAMER_PORT`), moves to the next free port if another app holds it,
  and offers to restart an already running File Renamer. `--browser` serves without a window.

### Fixed

- A rename never overwrites an existing file (adds `-1`, `-2`, ...); each original is backed up right before its rename.
- Numbered files (`new1.txt`, `new2.txt`) are grouped into one `new*.txt` pattern.
- Reasoning-model `<think>` output no longer ends up in file names.
- `--auto` requires `-d`; CLI defaults are real values instead of `None`.

### Changed

- Code moved into the `ollama_rename_files` package; `python rename_files.py` and `python app.py` are replaced by the
  `ollama-rename` command. `requirements.txt` is gone, dependencies live in `pyproject.toml`.
- MIT license.

## 0.2.0 - 2024-12-03

Untagged: the original CLI and the first pywebview GUI.

[0.3.0]: https://github.com/octrow/ollama-rename-files/releases/tag/v0.3.0
