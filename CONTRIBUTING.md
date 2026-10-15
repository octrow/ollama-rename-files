# Contributing

**English** | [Русский](CONTRIBUTING.ru.md)

Bug reports, ideas and pull requests are welcome.

## Set up

```bash
git clone https://github.com/octrow/ollama-rename-files.git
cd ollama-rename-files
uv sync
uv run ollama-rename --help
```

You need [uv](https://docs.astral.sh/uv/) and, to rename anything for real, [Ollama](https://ollama.com/download) with one model pulled.

## Before a pull request

```bash
uv run pytest
uv run ruff check .
```

Tests never call a real model: they patch `AsyncClient.generate`. Keep it that way, so CI runs without Ollama.

Optional: `uvx pre-commit install` runs the secret scan and workflow checks on every commit.

## Guidelines

- One change per pull request, with a test for new behavior.
- Commit messages: `<type>: <description>`, where type is feat, fix, refactor, docs, test, chore, ci.
- Anything that touches renaming or backups needs a test that the original file survives.
