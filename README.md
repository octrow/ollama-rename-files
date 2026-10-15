# 🤖 Ollama File Renamer

Effortlessly rename files using local AI - No tokens, No API, No cost!

## ✨ What is This?

A dead-simple Python tool (CLI and desktop GUI) that uses Ollama to automatically rename your files based on their content. Perfect for developers, writers, and anyone drowning in messy file names.

## 🚀 Why Use This?

- **Free:** 100% local AI, no external services
- **Simple:** Just run `python rename_files.py -d path\to\folder`, or `python app.py` for the GUI
- **Smart:** AI understands your file content
- **Safe:** Originals copied to `backup_<timestamp>/` inside the folder; existing files are never overwritten
- **Fast:** Works with hundreds of files quickly-ish, with optional parallel processing
- **Configurable:** Interactively choose directory, file pattern, model from ollama api, and context length
- **Robust:** Error handling and comprehensive logging

## 🔧 Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) (Free, local AI)

## 💾 Installation

```bash
# Clone the repository
git clone https://github.com/octrow/ollama-rename-files.git
cd ollama-rename-files

# Install dependencies (uv preferred)
uv sync
# or: pip install -r requirements.txt

# Pull a small language model (optional, the script will prompt you to choose)
ollama pull qwen2.5-coder:7b
```

## 🖥️ Usage

### Interactive mode (prompts for directory, pattern, model)
```bash
python rename_files.py
```

### GUI mode
```bash
python app.py
```
Opens a desktop window (pywebview serving a Flask app). Browse to a folder, pick a discovered pattern or type a prefix/extension, and the window lists exactly which files will change. Choose an installed Ollama model and click **Rename N files**: each row fills in with its new name as the model answers, and **Stop** halts the run after the current file.

The UI is served at `http://127.0.0.1:5000` (change with `--port` or `FILE_RENAMER_PORT`). If that port is taken by another app, the next free port is used. If File Renamer itself is already running there, you get its link and a `Restart it? [y/N]` prompt (No by default, and always No without a terminal). `python app.py --browser` serves the UI without opening a window.

On Linux, pywebview needs a GUI backend. Either install Qt into the venv:
`uv pip install "pywebview[qt]"` (or `pip install "pywebview[qt]"`), or use the system GTK bindings (`python3-gi`).
Windows and macOS work out of the box.

### CLI mode (`-d`)
```bash
# Rename files in specific directory
python rename_files.py -d "C:\path\to\your\folder"

# Specify path, model and context length
python rename_files.py -d "your_folder" -m "qwen2.5-coder:7b" -c 500

# CLI with directory and file pattern (no prompts)
python rename_files.py -a -d "your_folder" --prefix "new" --ext ".txt"

# Parallel processing (rename 4 files at a time)
python rename_files.py -d "your_folder" -p 4
```

Here's a breakdown of all the available options:

| Option         | Short Option | Description                                                                                               |
|-----------------|-------------|-----------------------------------------------------------------------------------------------------------|
| `--auto`       | `-a`        | Run in auto mode without interactive prompts. Requires `-d`. |
| `--directory`  | `-d`        | Specify the directory containing the files to rename.                                                     |
| `--model`      | `-m`        | Ollama model to use (default `qwen2.5-coder:7b`).                                                         |
| `--context`    | `-c`        | Specify the context length (number of characters) to send to the model (default 2048).                   |
| `--prefix`     |             | File prefix to match (default `new`). Used with `--ext` to define the file pattern.                      |
| `--ext`        |             | File extension to match, including the dot (default `.txt`).                                              |
| `--parallel`  | `-p`        | Number of parallel rename operations.  0 (default) means sequential processing.                           |


## 🤔 How It Works

1. Try to run `python rename_files.py`, answer the questions!
2. Optionally, prompts for directory, file pattern (prefix and extension), and Ollama model.
3. Finds files matching the specified pattern.
4. Creates a backup directory named backup_<timestamp>.
5. Backs up each file to the backup directory.
6. Uses local Ollama AI to read file content (up to the specified context length).
7. Generates a smart, descriptive filename based on the content.
8. Renames the file, keeping its original extension and never overwriting an existing file (adds `-1`, `-2`, ... suffix).
9. Logs every action.

## 📋 Naming Convention

Creates filenames like:
- `task-fix-backend-resolve-database-connection-issue.txt`
- `doc-update-project-architecture-notes.md`

## 🛡️ What's Protected?

- Original files are backed up before renaming.
- Renames never overwrite existing files.
- Reasoning-model `<think>` output is stripped from generated names.
- Comprehensive logging
- Error-resistant design with detailed error messages.
- Works with hundreds of files, sequentially or in parallel.

## 🧪 Development

```bash
uv run pytest
uv run ruff check .
```

## 🤝 Contributing

Found a bug? Want a feature? Pull requests are welcome!
