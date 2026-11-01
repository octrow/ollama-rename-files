# Changelog

All notable changes to this project. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- The desktop window renamed files in the folder scanned last, by any tab. With two tabs open (`--browser`, or the
  browser fallback on Linux), renaming in one tab changed files in the other tab's folder. Each request now names its
  folder, and an empty path is refused instead of meaning the server's working directory.
- Without `-a`, the CLI ignored `-d`, `-m`, `-c`, `--prefix` and `--ext` and asked for everything again; pressing Enter
  picked the first installed model instead of `-m`. Options you pass are no longer asked.
- The prefix `new` also renamed `news.txt` and `newsletter.txt`, which pattern discovery counts as other groups. A
  picked pattern, `--prefix` and the CLI menu now match the prefix as a whole word; a prefix typed in the desktop window
  still matches any name that starts with it.
- Empty or whitespace-only text files went to the model and got an invented name. They now fail with "file is empty",
  like a PDF without text.
- Names lost everything before the first Latin letter and after the last one: an all-Cyrillic name became
  `untitled-document-…`, `2024-q3-report` became `q3-report`. Names in any script and leading digits now stay, cut to
  255 bytes.
- A chatty reply named the file after its first line (`here-is-a-file-name.txt`). The name is now the first line that
  looks like one, with list markers, labels like `File name:` and Markdown removed; a reply without one fails the file.
- Two desktop-window requests renaming at the same moment could pick the same free name, and on Linux and macOS the
  second rename replaced the first file. Picking a name and renaming now happen under one lock for the whole process.
- A folder where the backup can't be created (read-only) crashed the CLI with a traceback and showed a JSON parse
  error on every row in the window. Both now say "Can't create a backup folder in …".
- A run where nothing was renamed (Ollama down, every file failed) left an empty `backup_<timestamp>/` folder. It is
  now removed when no original was copied into it.
- A hung Ollama blocked the run forever, and Stop in the window never took effect. Requests now time out after 300 s
  with "Ollama didn't answer in 300 s", and the model list after 10 s.
- `-c 0` and negative `-c` values were accepted and failed every file; they are now rejected. An extension without
  the dot (`--ext txt`, or `txt` in the window) matched names like `notes.mytxt`; it now means `.txt`.
- The context length was counted in characters, but Ollama's context window was left at the server's default, so a
  long prompt could be cut. Each request now sets `num_ctx` to fit the prompt (at least 4096). In the interactive CLI,
  Enter at the context prompt gives 2048 characters instead of the model's maximum in tokens.

## [0.3.4] - 2026-11-01

### Security

- The desktop window's local server answers only requests addressed to `127.0.0.1` or `localhost`. Before, a web page
  using DNS rebinding could point it at any folder, list its files and rename them.

### Fixed

- When Ollama isn't running or the model isn't pulled, each failed file says what to run (`ollama serve`,
  `ollama pull <model>`) instead of a bare connection or 404 error.

## [0.3.3] - 2026-11-01

### Changed

- PyPI lists the supported Python versions, 3.10 to 3.13, and CI tests on all four. The code is the same as 0.3.2.
- README (EN, RU): install from PyPI with `uv tool install` or `pipx install`, and a PyPI version badge.

## [0.3.2] - 2026-11-01

### Added

- Published on PyPI: `uv tool install ollama-rename-files`, `pipx install ollama-rename-files` or
  `pip install ollama-rename-files`. The code is the same as 0.3.1.
- Release notes on GitHub start with the version's section of this changelog.

## [0.3.1] - 2026-11-01

### Fixed

- PDF files are renamed by their text instead of failing with `'utf-8' codec can't decode byte 0xe2`
  ([#2](https://github.com/octrow/ollama-rename-files/issues/2)). Binary files, encrypted or broken PDFs and PDFs
  without a text layer fail with a clear reason instead of stopping the whole run.
- A backup never overwrites an earlier backup of a file with the same name in the backup directory
  ([#6](https://github.com/octrow/ollama-rename-files/issues/6)).
- A file the model names exactly as it is already named is left alone instead of getting a `-1` suffix and a needless
  backup ([#8](https://github.com/octrow/ollama-rename-files/issues/8)).

### Security

- Standalone builds ship pypdf 6.21.4 (CVE-2026-119203 to CVE-2026-119209,
  [#13](https://github.com/octrow/ollama-rename-files/issues/13)) and certifi 2026.10.19 (PYSEC-2026-4320,
  [#3](https://github.com/octrow/ollama-rename-files/issues/3)).

## [0.3.0] - 2026-10-16

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

[0.3.4]: https://github.com/octrow/ollama-rename-files/releases/tag/v0.3.4
[0.3.3]: https://github.com/octrow/ollama-rename-files/releases/tag/v0.3.3
[0.3.2]: https://github.com/octrow/ollama-rename-files/releases/tag/v0.3.2
[0.3.1]: https://github.com/octrow/ollama-rename-files/releases/tag/v0.3.1
[0.3.0]: https://github.com/octrow/ollama-rename-files/releases/tag/v0.3.0
