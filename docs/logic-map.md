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
| Extension | `Path.suffix` of the original | 3, 4, 9 | discovery groups by lowercased last suffix; selection matches `name.lower().endswith(ext.lower())`; the new name keeps the original suffix, the model's extension is dropped |

Examples:
- `report.PDF` with a text layer → PDF path, renamed to `<slug>.PDF`.
- `scan.pdf` without text → fails with "PDF has no text layer (scanned image?)".
- `notes.txt` in cp1251 → fails with "'utf-8' codec can't decode byte …".

Module: `rename_files`

## Entry points

All entry points end in `InteractiveFileRenamer.analyze_and_rename` per file. They differ in defaults.

| Entry | Folder | Pattern | Model | Context (chars) | Parallel | Before renaming |
|---|---|---|---|---|---|---|
| `ollama-rename` (no `-a`) | asked; **`-d` ignored** | menu of top 5; Enter = most common; **`--prefix`/`--ext` ignored** | menu of installed; Enter = first; **`-m` ignored** | asked; Enter = model's `context_length` from `ollama show`; **`-c` ignored** | `-p`, default 0 → 1 | config summary, no file list, no confirm |
| `ollama-rename -a -d DIR` | `-d` (required) | `--prefix new`, `--ext .txt` | `-m`, default `qwen2.5-coder:7b` | `-c`, default 2048 | `-p`, default 0 → 1 | nothing, starts at once |
| `ollama-rename gui` | typed path or Browse | first discovered pattern pre-selected, editable | dropdown of installed, first selected | fixed 2048 | 1 (JS loop) | file list shown; a prefix edit <250 ms before Rename still renames the old list |

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
- CLI without `-a` → four prompts that overwrite `-d`, `--prefix`, `--ext`, `-m`, `-c` (see Entry points);
- GUI → `POST /set_directory` stores one module-level `current_dir`, shared by every tab and read when each request arrives; prefix/extension come with each `/preview`, model with each `/rename_file`.
No Ollama: CLI prints "No Ollama models found. Using default model qwen2.5-coder:7b", context falls back to 2048; GUI disables the model dropdown and the Rename button.
Fails: CLI re-asks on invalid input; GUI answers 400 "That folder doesn't exist", but an empty path is `.` and scans the server's working directory.
Module: `rename_files`, `app`

### 3. Discover patterns

Decides: which (prefix, extension) groups the folder offers, top 5 by count.
In: folder. Out: `[((prefix, ext), count), …]`.
Prefix = the leading run of letters, or of digits, or of symbols: `new2.txt` → `new`, `2024-notes.md` → `2024`, `newsletter.txt` → `newsletter`.
Branches: files only; dot-files and names starting with `_` match nothing and are not counted.
Fails: not a folder → `ValueError("Invalid directory")`.
Module: `rename_files`

### 4. Select files

Decides: the exact list of files to rename.
Rule: `name.startswith(prefix)` (case-sensitive) and `name.lower().endswith(ext.lower())`, sorted by name.
Branches:
- empty prefix and empty extension (GUI fields cleared) → every file in the folder;
- prefix `new` also takes `newsletter.txt`, which discovery counted as a separate group;
- no matches → CLI logs "No files found to rename.", prints an all-zero summary and exits 0; GUI shows "No files match".
Fails: invalid folder → CLI logs the error and exits 1.
Module: `rename_files`

### 5. Backup folder

Decides: where originals are copied.
`backup_YYYYMMDD_HHMMSS/` inside the folder; `-1`, `-2` suffix if the name exists.
Branches:
- CLI: created once, after step 4 found ≥1 file, before any model call;
- GUI: created by the first `/rename_file` of a run; JS sends its name back with every later file; a name that is not an existing `backup_*` folder in `current_dir` → 400 "Backup folder is missing".
No Ollama: still created, stays empty.
Fails: can't create (read-only folder) → CLI traceback (only `ValueError` is caught); GUI HTML 500, every row shows a JSON parse error.
Module: `rename_files`, `app`

### 6. Read content

Decides: the text the model sees.
In: file path, limit in characters. Out: string, at most `limit` characters.
Branches: by file type (see the split table).
Empty or whitespace-only text goes to the model as is (a PDF in the same state fails).
`-c` is not validated: `-c 0` sends `""` for every file, a negative value fails every text file.
Fails: any exception (pypdf errors, decode errors, OSError) → this file fails with the message, the run continues.
Module: `rename_files`

### 7. Ask the model

Decides: the raw suggested name.
`AsyncClient().generate(model, PROMPT_TEMPLATE, think=False, options={"num_predict": 128})`. Host from `OLLAMA_HOST`.
The prompt is fixed and tuned for software notes: `<type> - <action> - <component> - <description>.<ext>`, lowercase, ≤128 chars.
No `num_ctx` is passed: the server's default context window applies, whatever the context length chosen in step 2.
No Ollama: every file fails with "Ollama isn't reachable. Start it with `ollama serve` …".
Fails: per file, no retry, no timeout (a hung Ollama blocks the run and GUI Stop). 404 → "Model X isn't installed. Run `ollama pull X`."; other errors → the error text.
Module: `rename_files`

### 8. Clean the reply

Decides: which part of the reply is the name.
Drops `<think>…</think>` (or an unclosed `<think>` to the end), lines starting with ```` ``` ````, and `` ` * " ' `` around lines; takes the first non-empty line, lowercased.
Branches: nothing left → this file fails with "model returned no file name".
A chatty first line ("here is a name:") is taken as the name.
Module: `rename_files`

### 9. Sanitize

Decides: the final file name.
In order: drop a trailing `.ext`; delete `` . ` ' , ; ``; replace `< > / \ | ? * : " + % ! @` with `_`; whitespace → `-`; collapse `--`; strip everything before the first ASCII letter; cut to `128 − len(suffix)`; strip trailing non-ASCII-alphanumerics.
The first rule drops any trailing `.\w+`: `release-notes-v2.0` → `release-notes-v2`. The last one drops a non-Latin tail: `doc - update - notes - про бэкап` → `doc-update-notes`.
Branches: nothing left (e.g. an all-Cyrillic reply) → `untitled-document-<8 hex>`.
Appends the original suffix with its original case.
Module: `rename_files`

### 10. Backup and rename

Decides: the free target name; never overwrites.
Runs under one `asyncio.Lock` per renamer so CLI workers can't take the same name. The GUI builds a renamer per request on a threaded server: two concurrent requests are not serialized.
Branches:
- new name == old name → success, no copy, no rename;
- else `copy2` to the backup folder (free name), then rename to a free name (`-1`, `-2`, …).
Fails: OSError → this file fails; its copy may already be in the backup folder; the original stays.
Module: `rename_files`

### 11. Run loop and report

Decides: order, concurrency, and what the user sees.
Branches:
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

`ollama-rename gui [--port N] [--browser]`. Port: `--port`, else `FILE_RENAMER_PORT`, else 5000.
Port busy → `GET /health`: another app → next free port within 50; a File Renamer → "Restart it? [y/N]" (No without a TTY) → SIGTERM and wait up to 5 s, or keep the old one and exit.
`--browser` → serve only and print the link. Linux without `qtpy` or `gi` → open the default browser. Else a pywebview window; closing it shuts the server down.
Module: `app`

### GUI request guard

Every request with a Host other than `127.0.0.1` or `localhost` → 403 (DNS rebinding). The server binds 127.0.0.1 only.
`/rename_file` accepts only a bare name of an existing file in `current_dir`; anything with a path → 400.
Feeds: steps 2, 5, 10.
Module: `app`

### Model list

`GET /models` and the CLI menu call `ollama list`; on any error they log it and return an empty list.
Feeds: step 2.
Module: `rename_files`, `app`

## Known gaps

Short list; details and fixes are in the plan (number in brackets).
- CLI without `-a` ignores `-d`, `-m`, `-c`, `--prefix`, `--ext` (#1).
- Prefix `new` also renames `newsletter.txt`, and the CLI renames without showing the list (#2).
- Empty text files are sent to the model and renamed to an invented name (#3).
- Context length is chosen in characters but Ollama's own context window is never set; CLI default is the model's token maximum (#4).
- GUI resolves every request against one global folder: a second tab or an empty-path POST redirects the renames (#8).
- Non-Latin text is cut from both ends: all-Cyrillic → `untitled-document-…`, `2024-q3-report` → `q3-report` (#5).
- A chatty first line of the reply becomes the file name (#6).
- Concurrent GUI requests can overwrite each other's target (#9).
- A read-only folder crashes the CLI and breaks every GUI row (#10).
