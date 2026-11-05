# Install, all ways

[Back to README](../README.md)

You need [Ollama](https://ollama.com/download) running with one model pulled:

```bash
ollama pull qwen2.5-coder:7b
```

Then install the app with one command. It installs [uv](https://docs.astral.sh/uv/), Python and `ollama-rename`
into your user folder, no admin rights needed.

## macOS / Linux

```bash
curl -LsSf https://raw.githubusercontent.com/octrow/ollama-rename-files/main/install.sh | sh
```

## Windows (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/octrow/ollama-rename-files/main/install.ps1 | iex"
```

Prefer to read it first? Download [`install.sh`](../install.sh) or [`install.ps1`](../install.ps1), look through it, then run it.
Run it again to update; `sh install.sh --uninstall` (or `$env:INSTALL_UNINSTALL = "1"` on Windows) removes the app.

## From PyPI

Already have Python 3.10+? Install it from [PyPI](https://pypi.org/project/ollama-rename-files/):

```bash
uv tool install ollama-rename-files   # or: pipx install ollama-rename-files
```

Update with `uv tool upgrade ollama-rename-files` (`pipx upgrade ollama-rename-files`).

## Standalone build

No Python needed: download the archive for your system from the
[latest release](https://github.com/octrow/ollama-rename-files/releases/latest) (Linux x86_64 and arm64, macOS on
Apple silicon, Windows), unpack it and run `ollama-rename gui` from the unpacked folder. The builds aren't signed,
so macOS asks you to allow the app in System Settings → Privacy & Security on the first run.

## From source

```bash
git clone https://github.com/octrow/ollama-rename-files.git
cd ollama-rename-files
uv sync
uv run ollama-rename gui
```

