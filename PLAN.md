# План: ollama-rename-files

Открытые баги, планы и идеи. Обновлено 2026-11-05. Закрытый пункт удаляется или получает ✅ со ссылкой на коммит.

## Баги

- [ ] MEDIUM: GUI `renameAll` читает `state.directory` на каждый файл; ответ скана/превью во время прогона подменяет папку. Не подтверждено, нужен браузер. [#20](docs/plans/2026-11-01-logic-map-fixes.md)
- [ ] MEDIUM: бэкап — полный `copy2` без проверки места, синхронно внутри async-воркера под локом; большой файл блокирует цикл. [system-design.md, Risks](docs/system-design.md) (`rename_files.py:392-396`)
- [ ] MEDIUM: таймаут 300 с без retry и без аварийного останова прогона; при зависшем демоне большой прогон стоит часами. [system-design.md, Risks](docs/system-design.md) (`rename_files.py:192`, `:355-365`)
- [x] ✅ 2026-11-05 LOW: unicode-цифра вроде `²` роняет ввод меню `ValueError`. [issue #12](https://github.com/octrow/ollama-rename-files/issues/12) (`rename_files.py:156`) Исправлено: `_choose` на `isdecimal` (`rename_files.py:265`), тест; не закоммичено.
- [ ] LOW: `Fails to decode byte 0xe2` для PDF с `qwen2.5-coder:7b`. [issue #2](https://github.com/octrow/ollama-rename-files/issues/2)
- [ ] LOW: интерактивный CLI собирает список дважды, новый файл переименуется без показа. [#21](docs/plans/2026-11-01-logic-map-fixes.md)
- [x] ✅ 2026-11-05 LOW: `--port 65535` занят → `OverflowError` вместо сообщения. [#23](docs/plans/2026-11-01-logic-map-fixes.md) (`app.py:189`) Исправлено: поиск порта ограничен `MAX_PORT` (`app.py:189`), тест, логика-карта; не закоммичено.
- [ ] LOW (вопрос): выход 0, когда упали все файлы и при Ctrl+C; нужен ли код ошибки. [#22](docs/plans/2026-11-01-logic-map-fixes.md)
- [ ] LOW (вопрос): файл со своим же именем считается «переименован». [#24](docs/plans/2026-11-01-logic-map-fixes.md)
- [ ] LOW: замок на процесс, два запуска на одной папке могут столкнуться по именам. [system-design.md, Risks](docs/system-design.md) (`rename_files.py:86`)

## Планы и фичи

- [ ] Manifest прогона (JSON в папке бэкапа: старое имя → новое) и undo/resume; триггер — запуски дольше 30 мин. [system-design.md](docs/system-design.md) (`rename_files.py:447`)
- [ ] Живой прогон на реальной Ollama: длинный файл (#4), `qwen3`/`deepseek-r1`, мелкая модель, PDF, остановленный `ollama serve`. [таблица «Живой прогон»](docs/plans/2026-11-01-logic-map-fixes.md)
- [ ] Windows exe-релиз (запрос на публикацию). [issue #1](https://github.com/octrow/ollama-rename-files/issues/1)

## Идеи

- [ ] GUI: один HTTP-вызов на файл, для 1000+ файлов медленный путь. [system-design.md, Risks](docs/system-design.md)
- [ ] Подсказка в доке: `-p` выше 1 требует `OLLAMA_NUM_PARALLEL`. [system-design.md, Risks](docs/system-design.md) (`rename_files.py:423-447`)
- [ ] Живой прогон нужен и для #15 (`clearTimeout` в браузере не проверен). [logic-map-fixes](docs/plans/2026-11-01-logic-map-fixes.md)

## Подробные планы

- [docs/plans/2026-11-01-logic-map-fixes.md](docs/plans/2026-11-01-logic-map-fixes.md): находки карты логики, порядок работы, живой прогон
- [docs/system-design.md](docs/system-design.md): ступень, расчёт нагрузки, отказы, риски (2026-11-05); сводка по всем репо: `~/dev/docs/system-design-report-2026-11-05.md`
- [docs/logic-map.md](docs/logic-map.md), [docs/logic-map.ru.md](docs/logic-map.ru.md): карта логики
