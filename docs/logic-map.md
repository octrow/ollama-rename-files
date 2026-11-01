# Logic map

How a folder of badly named files becomes the same files renamed by their content.
The map describes the code as it is today, step by step.
Each step says what it decides, where the flow branches, and which module does it.

Known gaps and fixes in progress are in `docs/plans/2026-11-01-logic-map-fixes.md`.

Rule: if you change a step or a branch, update this file and `docs/logic-map.ru.md` in the same commit.
`tests/test_logic_map.py` checks that every `Module:` line points to a real module.
The Russian mirror is `docs/logic-map.ru.md`; this file is the source of truth.

## The flow at a glance

```
folder + pattern + model
  │
  ├─ 1  Dispatch .............. CLI or GUI?
  ├─ 2  Configure ............. which folder, pattern, model, context length?
  ├─ 3  Discover patterns ..... which (prefix, extension) groups does the folder have?
  ├─ 4  Select files .......... which files will be renamed?
  ├─ 5  Backup folder ......... where do the originals go?
  ├─ 6  Read content .......... what text does the model see?
  ├─ 7  Ask the model ......... what name does Ollama suggest?
  ├─ 8  Clean the reply ....... which part of the reply is the name?
  ├─ 9  Sanitize .............. what is the safe file name?
  ├─ 10 Backup and rename ..... copy the original, rename to a free name
  └─ 11 Run loop and report ... in what order, and what the user sees
  │
renamed files + backup_<timestamp>/ + summary
```

Nothing is recursive: only files directly in the folder are discovered, selected and renamed.

## Where the flow splits by file type

No registry: the file suffix and the first bytes decide, in three places.

| Variant | Switched on by | Steps | What changes |
|---|---|---|---|
| PDF | suffix `.pdf`, any case | 6 | pypdf text layer instead of raw bytes; empty text → file fails |
| Binary or UTF-16 | a NUL byte in the first `context × 4` bytes | 6 | file fails, "only UTF-8 text and PDF files are supported" |
| Text | any other file | 6 | strict UTF-8 decode; invalid bytes → file fails with the codec error |
| Extension | `Path.suffix` of the original | 3, 4, 9 | discovery groups by lowercased last suffix; selection matches `name.lower().endswith(ext.lower())`; an empty extension means none for a picked pattern and in the CLI, any for a GUI field typed by hand; the new name keeps the original suffix, the model's extension is dropped |

Examples:
- `report.PDF` with a text layer → PDF path, renamed to `<slug>.PDF`.
- `scan.pdf` without text → fails with "PDF has no text layer (scanned image?)".
- `notes.txt` in cp1251 → fails with "'utf-8' codec can't decode byte …".

Module: `rename_files`

## Entry points

All entry points end in `InteractiveFileRenamer.analyze_and_rename` per file. They differ in defaults.

| Entry | Folder | Pattern | Model | Context (chars) | Parallel | Before renaming |
|---|---|---|---|---|---|---|
| `ollama-rename` (no `-a`) | `-d`, else asked; Enter = current directory | `--prefix`/`--ext` (other one defaults), else menu of top 5; Enter = most common | `-m`, else menu of installed; Enter = first | `-c`, else asked; Enter = 2048, up to what the model's `context_length` holds | `-p`, default 0 → 1 | file list (first 20), then `Rename N files? [y/N]`; only y/yes/д/да renames |
| `ollama-rename -a -d DIR` | `-d` (required) | `--prefix new`, `--ext .txt` | `-m`, default `qwen2.5-coder:7b` | `-c`, default 2048 | `-p`, default 0 → 1 | nothing, starts at once |
| `ollama-rename gui` | the folder of the last Scan (a typed path counts only after Scan), shown as `~/…`; sent with every request | first discovered pattern pre-selected; typing in the prefix or extension field switches to plain starts-with, empty extension = any | dropdown of installed, first selected | fixed 2048 | 1 (JS loop) | file list shown; a field edit <250 ms before Rename renames the old list; the pending preview is cancelled |

Module: `__main__`, `rename_files`, `app`

## Steps

### 1. Dispatch

Decides: CLI or GUI.
Branches:
- `argv[1] == "gui"` → `app.run(argv[2:])`; Ctrl+C is swallowed;
- anything else → `rename_files.run(argv[1:])`.
stdout is reconfigured with `errors="replace"` so legacy Windows code pages can print any file name.
Module: `__main__`

### 2. Configure

Decides: folder, prefix, extension, model, context length.
Branches:
- CLI `-a` → takes flags as they are; `-a` without `-d` → argparse error;
- CLI without `-a` → asks only what the options left out: `-d` skips the folder, `--prefix` or `--ext` the pattern, `-m` the model, `-c` the context;
- GUI → no server state: `/set_directory` checks the folder and discovers patterns; every `/preview` and `/rename_file` carries `directory`, plus prefix/extension or model.
No Ollama: CLI prints "No Ollama models found. Using default model qwen2.5-coder:7b", the context prompt has no upper limit; GUI disables the model dropdown and the Rename button.
Fails: CLI re-asks on invalid input; an invalid `-d` without `-a` → logged, exit 1 (with `--prefix`/`--ext` given, only after the model and context prompts). GUI: missing, empty or non-folder `directory` → 400. CLI with closed input (piped stdin, no `-a`) → "No input to answer the questions. Run with -a -d DIR …", exit 1.
Module: `rename_files`, `app`

### 3. Discover patterns

Decides: which (prefix, extension) groups the folder offers, top 5 by count.
In: folder. Out: `[((prefix, ext), count), …]`.
Prefix = the leading run of letters, or of digits, or of symbols: `new2.txt` → `new`, `2024-notes.md` → `2024`, `newsletter.txt` → `newsletter`.
Branches: files only; dot-files and names starting with `_` match nothing and are not counted.
Fails: not a folder → `ValueError("Invalid directory")`; unreadable → "Can't read <folder>: <reason>". CLI logs either and exits 1; GUI answers 400.
Module: `rename_files`

### 4. Select files

Decides: the exact list of files to rename.
Rule: the name starts with the prefix (case-sensitive) and `name.lower().endswith(ext.lower())`, sorted by name.
An extension without a dot gets one: `txt` → `.txt`, so `notes.mytxt` is not taken.
Whole-word prefix (picked pattern and CLI): the next character must not continue the prefix's last letter or digit run, as in step 3: `new` takes `new1.txt`, `new.txt`, `new note.txt`, not `newsletter.txt`; `2024` skips `20240101.md`.
Only letter and digit runs are checked: a symbol prefix `-` also takes `--y.txt`, which discovery counts as `--`.
Branches:
- empty extension, for a picked pattern or in the CLI (`--ext ""`, Enter at "Write your pattern") → files without an extension: the `new` (no extension) group takes `new1`, not `new4.txt`;
- GUI fields typed by hand (`as_discovered: false`) → plain starts-with, and an empty extension means any: `new` takes `newsletter.txt`; both empty → every file in the folder; the preview list shows it;
- no matches → CLI logs "No files found to rename.", prints an all-zero summary and exits 0; GUI shows "No files match".
Fails: invalid folder → CLI logs the error and exits 1.
Module: `rename_files`

### 5. Backup folder

Decides: where originals are copied.
`backup_YYYYMMDD_HHMMSS/` inside the folder; `-1`, `-2` suffix if the name exists.
Branches:
- CLI: created once, after step 4 found ≥1 file, before any model call;
- GUI: created by the first `/rename_file` of a run; JS sends its name back with every later file; a name that is not an existing `backup_*` folder in the request's folder → 400 "Backup folder is missing".
Removed when no original was copied into it: CLI when the run ends, Ctrl+C included; GUI after every file that failed or kept its own name.
No Ollama: created, then removed.
Fails: can't create (read-only folder) → "Can't create a backup folder in …": CLI logs it and exits 1 before any model call; GUI answers 400 and the row shows it.
Module: `rename_files`, `app`

### 6. Read content

Decides: the text the model sees.
In: file path, limit in characters. Out: string, at most `limit` characters.
Branches: by file type (see the split table).
Empty or whitespace-only text → this file fails with "file is empty", like a PDF without text.
`-c` must be a whole number ≥ 1; anything else is an argparse error before the run.
Fails: any exception (pypdf errors, decode errors, OSError) → this file fails with the message, the run continues.
Module: `rename_files`

### 7. Ask the model

Decides: the raw suggested name.
`AsyncClient(timeout=300).generate(model, PROMPT_TEMPLATE, think=False, options={"num_predict": 128, "num_ctx": …})`. Host from `OLLAMA_HOST`.
The prompt is fixed and tuned for software notes: `<type> - <action> - <component> - <description>.<ext>`, lowercase, ≤128 chars.
`num_ctx` = (context chars + template) / 2 chars a token + 128, rounded up to 1024, at least 4096: 2048 chars → 4096, 20000 → 11264. One value per run, so the model loads once.
Not capped by the model's trained length with `-c` or in the GUI; CJK text (~1 char a token) can still be cut.
No Ollama: every file fails with "Ollama isn't reachable. Start it with `ollama serve` …".
Fails: per file, no retry. Timeout 300 s per read, so GUI Stop can wait that long (`ollama list`/`show`: 10 s) → "Ollama didn't answer in 300 s …". 404 → "Model X isn't installed. Run `ollama pull X`."; other errors → the error text.
Module: `rename_files`

### 8. Clean the reply
Decides: which part of the reply is the name.
Drops `<think>…</think>` (or an unclosed `<think>` to the end) and lines starting with ```` ``` ````.
Per line: a `` `backticked` `` span wins; `*` and edge quotes go; a list marker (`1.`, `-`) and a short label (`File name:`) go.
Takes the first line with a `-` or an `.ext`, not ending with `:`, `!` or `?`, and at most 3 words before its first dash, lowercased.
Branches: no such line ("Sure!", a bare `readme`) → this file fails with "model returned no file name".
"Here is a name for your file - hope it helps!" is skipped; `bug fix - update - auth - token refresh.md` is taken.
Module: `rename_files`

### 9. Sanitize
Decides: the final file name.
In order: drop a trailing `.ext`; delete `` . ` ' , ; ``; replace `< > / \ | ? * : " + % ! @` with `_`; whitespace → `-`; collapse `--`; strip non-word characters and `_` from the start; cut to `128 − len(suffix)` characters and to 255 bytes with the suffix; strip them from the end.
`_` next to `-` stays: `task - fix: api` → `task-fix_-api`.
Any script and leading digits stay: `заметка - про - бэкап` → `заметка-про-бэкап`, `2024 - q3 - report` → `2024-q3-report`.
The first rule drops any trailing `.\w+`: `release-notes-v2.0` → `release-notes-v2`.
Branches: no letter left (`""`, `123`) → `untitled-document-<8 hex>`.
Appends the original suffix with its original case.
Module: `rename_files`

### 10. Backup and rename

Decides: the free target name; never overwrites.
Runs under one process-wide `threading.Lock`, so CLI workers and concurrent GUI requests can't take the same name. Two processes renaming in one folder at once still race.
Branches:
- new name == old name → success, no copy, no rename;
- else `copy2` to the backup folder (free name), then rename to a free name (`-1`, `-2`, …).
Fails: OSError → this file fails; its copy may already be in the backup folder; the original stays.
Module: `rename_files`

### 11. Run loop and report

Decides: order, concurrency, and what the user sees.
Branches:
- CLI without `-a`: lists the files and asks `Rename N files? [y/N]` first; anything but yes → "Nothing renamed.", exit 0;
- CLI: `asyncio.gather` over all files with `Semaphore(max(-p, 1))`; logs progress every 10 files; prints totals and each failed file with its reason; exit 0 even when files failed;
- GUI: JS posts one `/rename_file` per row, in order; Stop takes effect after the current file; status bar shows counts and the backup folder; patterns are re-discovered after the run, the renamed list stays on screen.
Ctrl+C in the CLI prints "Operation interrupted by user." with no summary; files done so far stay renamed.
Module: `rename_files`, `app`, `static/script.js`

### Output

Renamed files in the same folder, originals in `backup_<timestamp>/`.
CLI: "Renaming Operation Summary" with processed / renamed / failed counts and reasons.
GUI: each row shows `old → new` or the error; status line "Renamed N files, M failed. Originals are in backup_…".
Module: `rename_files`, `static/script.js`

## Side flows

### GUI server start

`ollama-rename gui [--port N] [--browser]`. Port: `--port`, else `FILE_RENAMER_PORT`, else 5000. Outside 1–65535 → argparse error.
Port busy → `GET /health`: another app → next free port within 50; a File Renamer → "Restart it? [y/N]" (No without a TTY) → SIGTERM and wait up to 5 s, or keep the old one and exit. No free port, or the old one still holds the port after 5 s → "Can't start File Renamer: …", exit 1.
`--browser` → serve only and print the link. Linux without `qtpy` or `gi` → open the default browser. Else a pywebview window; closing it shuts the server down.
Module: `app`

### GUI request guard

Every request with a Host other than `127.0.0.1` or `localhost` → 403 (DNS rebinding). The server binds 127.0.0.1 only.
`/rename_file` accepts only a bare name of an existing file in the folder the request names; anything with a path → 400.
A cross-site form POST can't send JSON, so it gets 400 and changes nothing.
Feeds: steps 2, 5, 10.
Module: `app`

### Model list

`GET /models` and the CLI menu call `ollama list`; on any error they log it and return an empty list.
Feeds: step 2.
Module: `rename_files`, `app`

## Known gaps

Short list; details and fixes are in the plan (number in brackets).
- None open.
