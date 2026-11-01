import argparse
import asyncio
import contextlib
import importlib.util
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path

import webview
from flask import Flask, jsonify, render_template, request
from ollama import AsyncClient
from werkzeug.serving import make_server

from ollama_rename_files.rename_files import DEFAULT_MODEL, InteractiveFileRenamer, list_ollama_models

APP_ID = "ollama-rename-files"
HOST = "127.0.0.1"
# The API renames files anywhere on disk: only the local page may call it, not a DNS-rebinding web page
ALLOWED_HOSTS = {HOST, "localhost"}
DEFAULT_PORT = int(os.environ.get("FILE_RENAMER_PORT", "5000"))
PORT_SEARCH_RANGE = 50
HEALTH_TIMEOUT_S = 1.0
RESTART_TIMEOUT_S = 5.0

logger = logging.getLogger(__name__)
app = Flask(__name__)


class Api:
    """Exposed to JS as window.pywebview.api."""

    def choose_directory(self) -> str | None:
        result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None


def _folder(data: dict) -> Path | None:
    """The folder a request names. Every request carries it, so two tabs never act on each other's folder."""
    raw = data.get("directory")
    if not raw or not isinstance(raw, str):
        return None
    path = Path(raw).expanduser()
    return path if path.is_dir() else None


def _child(folder: Path, name: str | None) -> Path | None:
    """Path of an existing entry in folder; None for missing names or anything that isn't a bare name."""
    if not name or Path(name).name != name:
        return None
    path = folder / name
    return path if path.exists() else None


def _backup_dir(folder: Path, name: str | None) -> Path | None:
    """The run's backup folder, if the name points at one inside folder."""
    path = _child(folder, name)
    return path if path and path.is_dir() and path.name.startswith("backup_") else None


def _display_path(path: Path) -> str:
    """`~/notes` instead of the full home path, so the folder field stays readable."""
    try:
        return "~/" + path.resolve().relative_to(Path.home().resolve()).as_posix()
    except ValueError:
        return str(path)


@app.before_request
def refuse_foreign_host():
    if request.host.rsplit(":", 1)[0] not in ALLOWED_HOSTS:
        return jsonify({"error": "Forbidden host"}), 403
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"app": APP_ID, "pid": os.getpid()})


@app.post("/set_directory")
def set_directory():
    directory = _folder(request.get_json(silent=True) or {})
    if not directory:
        return jsonify({"error": "That folder doesn't exist. Check the path and scan again."}), 400
    patterns = InteractiveFileRenamer(base_dir=directory).discover_file_patterns()
    return jsonify({"directory": _display_path(directory), "patterns": patterns})


@app.get("/models")
def models():
    return jsonify(list_ollama_models())


@app.post("/preview")
def preview():
    data = request.get_json(silent=True) or {}
    folder = _folder(data)
    if not folder:
        return jsonify({"error": "Choose a folder first."}), 400
    renamer = InteractiveFileRenamer(
        base_dir=folder,
        filename_prefix=data.get("prefix", ""),
        filename_extension=data.get("extension", ""),
    )
    # a picked pattern matches like discovery counted it; a typed prefix is a plain "starts with"
    return jsonify([p.name for p in renamer.collect_files_to_rename(bool(data.get("whole_prefix", True)))])


@app.post("/rename_file")
def rename_file():
    """Rename one file. The first call of a run creates the backup folder; later calls pass its name back."""
    data = request.get_json(silent=True) or {}
    folder = _folder(data)
    if not folder:
        return jsonify({"error": "The folder is gone. Scan it again."}), 400
    path = _child(folder, data.get("file"))
    if not path or not path.is_file():
        return jsonify({"error": "File not found in the chosen folder."}), 400
    backup_dir = _backup_dir(folder, data.get("backup_dir"))
    if data.get("backup_dir") and not backup_dir:
        return jsonify({"error": "Backup folder is missing. Start the run again."}), 400

    renamer = InteractiveFileRenamer(
        base_dir=folder,
        model_name=data.get("model") or DEFAULT_MODEL,
        backup_dir=backup_dir,
    )
    if not renamer.backup_dir:
        try:
            renamer.backup_dir = renamer.create_backup_directory()
        except ValueError as e:  # read-only folder: say so, don't answer with an HTML 500
            return jsonify({"error": str(e)}), 400

    async def run() -> tuple[bool, str]:
        return await renamer.analyze_and_rename(AsyncClient(), path)

    ok, message = asyncio.run(run())
    return jsonify({"ok": ok, "new_name" if ok else "error": message, "backup_dir": renamer.backup_dir.name})


# ---------- port selection ----------


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True


def running_instance_pid(port: int) -> int | None:
    """PID of a File Renamer already serving on `port`, or None if the port belongs to something else."""
    try:
        with urllib.request.urlopen(f"http://{HOST}:{port}/health", timeout=HEALTH_TIMEOUT_S) as response:
            info = json.load(response)
    except (OSError, ValueError):
        return None
    return info.get("pid") if isinstance(info, dict) and info.get("app") == APP_ID else None


def next_free_port(start: int) -> int:
    for port in range(start, start + PORT_SEARCH_RANGE):
        if port_is_free(port):
            return port
    raise RuntimeError(f"No free port in {start}-{start + PORT_SEARCH_RANGE - 1}")


def confirm(question: str) -> bool:
    """Yes/no prompt that defaults to No, including when there's no terminal to ask."""
    if not sys.stdin.isatty():
        return False
    return input(question).strip().lower() in {"y", "yes", "д", "да"}


def stop_instance(pid: int, port: int) -> None:
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + RESTART_TIMEOUT_S
    while not port_is_free(port):
        if time.monotonic() > deadline:
            raise RuntimeError(f"File Renamer (pid {pid}) is still holding port {port}")
        time.sleep(0.1)


def choose_port(preferred: int, ask: Callable[[str], bool] = confirm) -> int | None:
    """Port to serve on, or None to keep an already running File Renamer."""
    if port_is_free(preferred):
        return preferred
    pid = running_instance_pid(preferred)
    if pid is None:
        port = next_free_port(preferred + 1)
        logger.info(f"Port {preferred} is used by another app, using {port}")
        return port
    url = f"http://{HOST}:{preferred}"
    print(f"File Renamer is already running at {url} (pid {pid}).")
    if ask("Restart it? [y/N] "):
        stop_instance(pid, preferred)
        return preferred
    print(f"Keeping the running instance. Open {url}")
    return None


def has_window_backend() -> bool:
    """pywebview needs Qt or GTK bindings on Linux; Windows and macOS ship their own."""
    return not sys.platform.startswith("linux") or any(importlib.util.find_spec(m) for m in ("qtpy", "gi"))


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ollama-rename gui", description="File Renamer desktop window")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Preferred port (default {DEFAULT_PORT})")
    parser.add_argument("--browser", action="store_true", help="Only serve the UI and print its link, no window")
    args = parser.parse_args(argv)

    port = choose_port(args.port)
    if port is None:
        return
    server = make_server(HOST, port, app, threaded=True)
    url = f"http://{HOST}:{port}"
    print(f"File Renamer: {url}", flush=True)
    if args.browser:
        server.serve_forever()
        return
    if not has_window_backend():
        print(
            "No Qt or GTK bindings for a desktop window (see README, Linux).\n"
            f"Opening {url} in your browser instead. Press Ctrl+C to stop.",
            flush=True,
        )
        webbrowser.open(url)
        server.serve_forever()
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webview.create_window(
        "File Renamer", url, js_api=Api(), width=880, height=680, min_size=(520, 480), text_select=True
    )
    webview.start()
    server.shutdown()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        run()
