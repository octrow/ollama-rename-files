# Участие в разработке

[English](CONTRIBUTING.md) | **Русский**

Баг-репорты, идеи и pull request'ы приветствуются.

## Подготовка

```bash
git clone https://github.com/octrow/ollama-rename-files.git
cd ollama-rename-files
uv sync
uv run ollama-rename --help
```

Нужен [uv](https://docs.astral.sh/uv/), а чтобы реально переименовывать файлы, ещё и [Ollama](https://ollama.com/download) со скачанной моделью.

## Перед pull request'ом

```bash
uv run pytest
uv run ruff check .
```

Тесты никогда не обращаются к настоящей модели: они подменяют `AsyncClient.generate`. Пусть так и остаётся, тогда CI работает без Ollama.

По желанию: `uvx pre-commit install` запускает поиск секретов и проверку workflow при каждом коммите.

## Правила

- Один pull request — одно изменение, у нового поведения есть тест.
- Сообщения коммитов: `<type>: <description>`, где type — feat, fix, refactor, docs, test, chore, ci.
- Если изменение касается переименования или бэкапов, нужен тест на то, что исходный файл уцелел.
