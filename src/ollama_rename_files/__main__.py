"""`ollama-rename` runs the CLI; `ollama-rename gui` opens the desktop window."""
import contextlib
import sys


def main() -> None:
    # legacy Windows code pages can't print every file name; replace what they can't encode
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")
    if sys.argv[1:2] == ["gui"]:
        from ollama_rename_files import app

        with contextlib.suppress(KeyboardInterrupt):
            app.run(sys.argv[2:])
    else:
        from ollama_rename_files import rename_files

        rename_files.run(sys.argv[1:])


if __name__ == "__main__":
    main()
