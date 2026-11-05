# Навыки с рынка: что добавить (2026-11-05)

Источник: `~/dev/jobs/data/corpus_roadmap.md` (11.5k вакансий, 2026-11-05) против [system-design](system-design.md) и [logic-map](logic-map.md). Берём только то, что нужно самому проекту; чего проект не требует — в «Отвергнуто». Сводка по всем репо: `~/dev/docs/skills-roadmap-report-2026-11-05.md`.

## Предложения

- [ ] **[pydantic, structured output]** Ollama `format=` + Pydantic-схема вместо чистки ответа (срезание `<think>`, ```` ``` ````, regex-санитайз в шагах 8-9); санитайз для ФС остаётся. Сначала проверить поддержку structured output у нужных моделей. Усилие M.
- [ ] **[pytest, llm-eval]** Фикстуры «входной текст → допустимое имя» + тест формата `<type> - <action> - <component> - <description>.<ext>` с mock-клиентом. Усилие S.

## Отвергнуто

- Очередь/БД: «не добавлять до манифеста» (system-design).
- Docker: локальная Ollama + GUI на localhost.
