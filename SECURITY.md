# Security policy

**English** | [Русский](SECURITY.ru.md)

## Reporting a vulnerability

Please report privately through [GitHub security advisories](https://github.com/octrow/ollama-rename-files/security/advisories/new), not in a public issue. You'll get an answer within a week.

Supported version: the latest release.

## What the app touches

- It reads files in the folder you pick and renames them there. Originals are copied to `backup_<timestamp>/` first; a rename never overwrites an existing file.
- File contents go only to your local Ollama (`http://127.0.0.1:11434` by default, or `OLLAMA_HOST`).
- The GUI serves on `127.0.0.1` only and accepts plain file names inside the chosen folder, nothing with a path.

## Verifying a download

Release files are built by GitHub Actions and carry build provenance:

```bash
gh attestation verify ollama_rename_files-<version>-py3-none-any.whl -R octrow/ollama-rename-files
```
