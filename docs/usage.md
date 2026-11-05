# Usage and options

[Back to README](../README.md)

## Desktop window

```bash
ollama-rename gui
```

Browse to a folder, pick a discovered pattern or type a prefix and extension, and the window lists exactly which
files will change. Choose an installed model and click **Rename N files**: each row fills in with its new name as the
model answers, and **Stop** halts the run after the current file.

The window shows a local page served at `http://127.0.0.1:5000` (change with `--port` or `FILE_RENAMER_PORT`). If that
port is taken by another app, the next free one is used. If File Renamer itself is already running there, you get its
link and a `Restart it? [y/N]` prompt (No by default, and always No without a terminal). `ollama-rename gui --browser`
serves the page without opening a window.

On Linux the window needs Qt or GTK bindings for Python. Without them `ollama-rename gui` opens the same page in
your default browser. For a native window in a source checkout: `uv pip install "pywebview[qt]"`, or install the
system GTK bindings (`python3-gi`). Windows and macOS work out of the box.

## Command line

```bash
# Interactive: asks for the folder, the file pattern, the model and the context length.
# Options you pass on the command line are not asked again. Lists the files and asks before renaming.
ollama-rename

# A folder, a model and 500 characters of each file; asks only for the file pattern
ollama-rename -d ~/notes/inbox -m qwen2.5-coder:7b -c 500

# No prompts: every new*.txt file in the folder
ollama-rename -a -d ~/notes/inbox --prefix new --ext .txt

# Four files at a time; asks for everything but the folder
ollama-rename -d ~/notes/inbox -p 4
```

| Option        | Short | Description                                                                     |
|---------------|-------|---------------------------------------------------------------------------------|
| `--auto`      | `-a`  | Run without interactive prompts. Requires `-d`.                                 |
| `--directory` | `-d`  | Folder with the files to rename.                                                |
| `--model`     | `-m`  | Ollama model to use (default `qwen2.5-coder:7b`).                               |
| `--context`   | `-c`  | How many characters of each file to send to the model (default 2048).           |
| `--prefix`    |       | File name prefix to match (default `new`): `new` takes `new1.txt` and `new.txt`, not `newsletter.txt`. Used with `--ext` as the pattern. |
| `--ext`       |       | File extension to match, with the dot (default `.txt`).                         |
| `--parallel`  | `-p`  | Files renamed at the same time. 0 (default) means one by one.                   |

Ollama on another machine or port? Set `OLLAMA_HOST`, e.g. `OLLAMA_HOST=http://192.168.1.20:11434 ollama-rename`.

## Naming pattern

Names follow the pattern `<type>-<action>-<component>-<short-description>`, for example:

- `task-fix-backend-resolve-database-connection-issue.txt`
- `doc-update-project-architecture-notes.md`

The prompt is tuned for software-project notes: type is task, issue, doc, snippet, review or idea. It lives in
`PROMPT_TEMPLATE` in [`rename_files.py`](../src/ollama_rename_files/rename_files.py) if you want other names.
