# Agents: start here

1. `docs/logic-map.md`: how a folder of files becomes renamed files: every step, every branch, the module behind it.
2. `docs/plans/`: work in progress; `2026-11-01-logic-map-fixes.md` lists the known logic gaps.
3. `CONTRIBUTING.md`: setup, tests, commit format.

Rules:
- Change a step or a branch → update `docs/logic-map.md` and `docs/logic-map.ru.md` in the same commit.
- `tests/test_logic_map.py` fails when a `Module:` line in the map points to a module that is gone.
- Tests never call a real model: patch `AsyncClient.generate`.
