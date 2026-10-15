# Ollama File Renamer

<p align="center">
  <a href="https://github.com/octrow/ollama-rename-files/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/octrow/ollama-rename-files/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/octrow/ollama-rename-files/releases/latest"><img alt="Последний релиз" src="https://img.shields.io/github/v/release/octrow/ollama-rename-files"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-blue">
  <a href="LICENSE"><img alt="Лицензия MIT" src="https://img.shields.io/github/license/octrow/ollama-rename-files"></a>
</p>

<p align="center"><img src="assets/readme/hero.svg" alt="Ollama File Renamer: new2.txt становится docs-update-backend-migration-plan.txt" width="100%"></p>

<p align="center"><a href="README.md">English</a> | <b>Русский</b></p>

Переименовывает файлы по их содержимому с помощью локальной модели Ollama. `new2.txt`
превращается в `docs-update-backend-migration-plan.txt`, `new6.txt` в `sql-create-index-orders-slow-reports.txt`. Работает в
отдельном окне или в командной строке, API-ключи не нужны, а каждый исходный файл сначала копируется в папку с бэкапом.

Пригодится всем, у кого есть папка с заметками, сниппетами и черновиками вида `Untitled`, `new`, `копия (3)`:
разработчикам, авторам текстов и тем, кто складывает быстрые заметки в одну папку-«входящие».

<p align="center"><img src="assets/readme/gui-renamed.png" alt="Окно после прогона: семь файлов new*.txt переименованы моделью qwen2.5-coder:1.5b, оригиналы в папке бэкапа" width="720"></p>

## Возможности

- Работает на вашем компьютере: содержимое файлов уходит только в ваш Ollama.
- Сначала оригиналы копируются в `backup_<timestamp>/` внутри папки, а переименование никогда не перезаписывает существующий файл (добавляется `-1`, `-2`, ...).
- В окне вы выбираете папку, видите, какие именно файлы изменятся, и смотрите, как каждая строка получает новое имя.
- Группирует папку по шаблонам (`new*.txt`, `Untitled*.md`); вы выбираете один или вводите префикс и расширение.
- Подходит любая модель, установленная в Ollama. Рассуждающие модели тоже подходят: их вывод `<think>` отбрасывается.
- CLI умеет переименовывать несколько файлов сразу (`-p 4`).

## Установка

Нужен запущенный [Ollama](https://ollama.com/download) с одной скачанной моделью:

```bash
ollama pull qwen2.5-coder:7b
```

Дальше приложение ставится одной командой. Она установит [uv](https://docs.astral.sh/uv/), Python и `ollama-rename`
в вашу пользовательскую папку, права администратора не нужны.

### macOS / Linux

```bash
curl -LsSf https://raw.githubusercontent.com/octrow/ollama-rename-files/main/install.sh | sh
```

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/octrow/ollama-rename-files/main/install.ps1 | iex"
```

Хотите сначала прочитать скрипт? Скачайте [`install.sh`](install.sh) или [`install.ps1`](install.ps1), просмотрите и запустите.
Повторный запуск обновляет приложение, а `sh install.sh --uninstall` (или `$env:INSTALL_UNINSTALL = "1"` в Windows) удаляет его.

### Готовая сборка

Python не нужен: скачайте архив для своей системы из
[последнего релиза](https://github.com/octrow/ollama-rename-files/releases/latest) (Linux x86_64 и arm64, macOS на
Apple silicon, Windows), распакуйте и запустите `ollama-rename gui` из распакованной папки. Сборки не подписаны,
поэтому при первом запуске macOS попросит разрешить приложение в «Системные настройки» → «Конфиденциальность и безопасность».

### Из исходников

```bash
git clone https://github.com/octrow/ollama-rename-files.git
cd ollama-rename-files
uv sync
uv run ollama-rename gui
```

## Использование

### Окно приложения

```bash
ollama-rename gui
```

Укажите папку, выберите найденный шаблон или введите префикс и расширение, и окно покажет, какие именно файлы
изменятся. Выберите установленную модель и нажмите **Rename N files**: каждая строка получает новое имя по мере
ответа модели, а **Stop** останавливает прогон после текущего файла.

Окно показывает локальную страницу на `http://127.0.0.1:5000` (порт меняется через `--port` или `FILE_RENAMER_PORT`).
Если порт занят другим приложением, берётся следующий свободный. Если там уже работает сам File Renamer, вы получите
его ссылку и вопрос `Restart it? [y/N]` (по умолчанию No, а без терминала всегда No). `ollama-rename gui --browser`
только поднимает страницу, без окна.

В Linux окну нужны привязки Qt или GTK для Python. Без них `ollama-rename gui` откроет ту же страницу в браузере
по умолчанию. Для настоящего окна в клоне репозитория: `uv pip install "pywebview[qt]"` или системные привязки GTK
(`python3-gi`). В Windows и macOS всё работает сразу.

### Командная строка

```bash
# Интерактивно: спросит папку, шаблон файлов, модель и длину контекста
ollama-rename

# Папка, модель и 500 символов из каждого файла
ollama-rename -d ~/notes/inbox -m qwen2.5-coder:7b -c 500

# Без вопросов: все файлы new*.txt в папке
ollama-rename -a -d ~/notes/inbox --prefix new --ext .txt

# По четыре файла одновременно
ollama-rename -d ~/notes/inbox -p 4
```

| Параметр      | Кратко | Описание                                                                       |
|---------------|--------|--------------------------------------------------------------------------------|
| `--auto`      | `-a`   | Запуск без вопросов. Требует `-d`.                                             |
| `--directory` | `-d`   | Папка с файлами для переименования.                                            |
| `--model`     | `-m`   | Модель Ollama (по умолчанию `qwen2.5-coder:7b`).                               |
| `--context`   | `-c`   | Сколько символов каждого файла отправлять модели (по умолчанию 2048).          |
| `--prefix`    |        | Префикс имени файла (по умолчанию `new`). Вместе с `--ext` задаёт шаблон.      |
| `--ext`       |        | Расширение файла, с точкой (по умолчанию `.txt`).                              |
| `--parallel`  | `-p`   | Сколько файлов переименовывать одновременно. 0 (по умолчанию) значит по одному.|

Ollama на другой машине или порту? Задайте `OLLAMA_HOST`, например `OLLAMA_HOST=http://192.168.1.20:11434 ollama-rename`.

## Как это работает

1. Находит в папке файлы, подходящие под шаблон (префикс и расширение).
2. Создаёт в этой папке `backup_<timestamp>/` и копирует туда каждый файл перед переименованием.
3. Отправляет первые `--context` символов файла в локальную модель Ollama.
4. Чистит предложенное имя: нижний регистр, безопасные символы, не длиннее 128 символов.
5. Переименовывает файл, сохраняя исходное расширение и никогда не перезаписывая существующий файл.
6. Записывает в лог каждое действие и в конце показывает, какие файлы не удалось переименовать и почему.

Имена строятся по шаблону `<type>-<action>-<component>-<short-description>`, например:

- `task-fix-backend-resolve-database-connection-issue.txt`
- `doc-update-project-architecture-notes.md`

Промпт заточен под заметки из программных проектов: type — это task, issue, doc, snippet, review или idea. Он лежит
в `PROMPT_TEMPLATE` в [`rename_files.py`](src/ollama_rename_files/rename_files.py), если нужны другие имена.

## Чем отличается от ai-renamer

[ai-renamer](https://github.com/ozgrozer/ai-renamer) это популярный CLI на Node.js, который делает то же самое и больше:
переименовывает ещё и картинки с видео, работает с Ollama, LM Studio и OpenAI. Берите его, если переименовываете
фотографии или нужна облачная модель.

Ollama File Renamer уже: только текстовые файлы и только локальный Ollama. Зато у него есть окно с предпросмотром
файлов, которые изменятся, бэкап каждого оригинала, переименование без перезаписи и поиск шаблонов, чтобы
переименовать `new*.txt` и не задеть остальное в папке.

## Разработка

```bash
uv sync
uv run pytest
uv run ruff check .
```

Подробнее в [CONTRIBUTING.ru.md](CONTRIBUTING.ru.md). Об уязвимостях сообщайте по [SECURITY.ru.md](SECURITY.ru.md).

## Лицензия

[MIT](LICENSE)
