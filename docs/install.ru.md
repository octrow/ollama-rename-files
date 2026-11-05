# Установка, все способы

[Назад к README](../README.ru.md)

Нужен запущенный [Ollama](https://ollama.com/download) с одной скачанной моделью:

```bash
ollama pull qwen2.5-coder:7b
```

Дальше приложение ставится одной командой. Она установит [uv](https://docs.astral.sh/uv/), Python и `ollama-rename`
в вашу пользовательскую папку, права администратора не нужны.

## macOS / Linux

```bash
curl -LsSf https://raw.githubusercontent.com/octrow/ollama-rename-files/main/install.sh | sh
```

## Windows (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/octrow/ollama-rename-files/main/install.ps1 | iex"
```

Хотите сначала прочитать скрипт? Скачайте [`install.sh`](../install.sh) или [`install.ps1`](../install.ps1), просмотрите и запустите.
Повторный запуск обновляет приложение, а `sh install.sh --uninstall` (или `$env:INSTALL_UNINSTALL = "1"` в Windows) удаляет его.

## Из PyPI

Уже есть Python 3.10+? Установите из [PyPI](https://pypi.org/project/ollama-rename-files/):

```bash
uv tool install ollama-rename-files   # или: pipx install ollama-rename-files
```

Обновление: `uv tool upgrade ollama-rename-files` (`pipx upgrade ollama-rename-files`).

## Готовая сборка

Python не нужен: скачайте архив для своей системы из
[последнего релиза](https://github.com/octrow/ollama-rename-files/releases/latest) (Linux x86_64 и arm64, macOS на
Apple silicon, Windows), распакуйте и запустите `ollama-rename gui` из распакованной папки. Сборки не подписаны,
поэтому при первом запуске macOS попросит разрешить приложение в «Системные настройки» → «Конфиденциальность и безопасность».

## Из исходников

```bash
git clone https://github.com/octrow/ollama-rename-files.git
cd ollama-rename-files
uv sync
uv run ollama-rename gui
```

