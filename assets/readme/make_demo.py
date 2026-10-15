"""Recreate the demo folder the README screenshots are taken from: python make_demo.py <dir>."""
import shutil
import sys
from pathlib import Path

NOTES = [
    "TODO: login endpoint returns 500 when the email has uppercase letters. "
    "Normalize email to lowercase in auth/service.py before the DB lookup and add a regression test.",
    "Meeting notes 14 Oct. We agreed to move session storage from cookies to Redis. "
    "Ivan writes the migration plan, release after the load test.",
    "def retry(fn, attempts=3, delay=0.5):\n    for i in range(attempts):\n        try:\n            return fn()\n"
    "        except TimeoutError:\n            time.sleep(delay * 2 ** i)\n    raise",
    "Code review for PR #212 (payments webhook): signature check happens after JSON parsing, "
    "move it first. Missing idempotency key on retries.",
    "Idea: dark theme for the dashboard. Respect prefers-color-scheme, keep the chart palette readable on dark.",
    "Postgres: orders table scan is slow on /reports. Add index on (customer_id, created_at) and check EXPLAIN.",
    "Architecture notes: the frontend talks to the API gateway only; services never call each other directly, "
    "events go through the queue.",
]


def main(target: str) -> None:
    folder = Path(target)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    for i, text in enumerate(NOTES, 1):
        (folder / f"new{i}.txt").write_text(text + "\n")
    (folder / "README.md").write_text("Inbox of quick notes.\n")


if __name__ == "__main__":
    main(sys.argv[1])
