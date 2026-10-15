import argparse
import asyncio
import contextlib
import json
import logging
import os
import signal
import socket
import sys
import threading
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path

import webview
from flask import Flask, jsonify, render_template, request
from ollama import AsyncClient
from werkzeug.serving import make_server

from rename_files import DEFAULT_MODEL, InteractiveFileRenamer, list_ollama_models

APP_ID = "ollama-rename-files"
HOST = "127.0.0.1"
DEFAULT_PORT = int(os.environ.get("FILE_RENAMER_PORT", "5000"))
PORT_SEARCH_RANGE = 50
HEALTH_TIMEOUT_S = 1.0
RESTART_TIMEOUT_S = 5.0

logger = logging.getLogger(__name__)
app = Flask(__name__)
# ponytail: single-user desktop app, one module-level "current folder" is enough
current_dir: Path | None = None


class Api:
    """Exposed to JS as window.pywebview.api."""

    def choose_directory(self) -> str | None:
        result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None


def _child(name: str | None) -> Path | None:
    """Path of an existing entry in current_dir; None for missing names or anything that isn't a bare name."""
    if not current_dir or not name or Path(name).name != name:
        return None
    path = current_dir / name
    return path if path.exists() else None


def _backup_dir(name: str | None) -> Path | None:
    """The run's backup folder, if the name points at one inside current_dir."""
    path = _child(name)
    return path if path and path.is_dir() and path.name.startswith("backup_") else None


@app.route('/')
def index():
    return render_template("index.html")


@app.get('/health')
def health():
    return jsonify({"app": APP_ID, "pid": os.getpid()})


@app.post('/set_directory')
def set_directory():
    directory = Path((request.get_json(silent=True) or {}).get('directory', '')).expanduser()
    if not directory.is_dir():
        return jsonify({"error": "That folder doesn't exist. Check the path and scan again."}), 400
    global current_dir
    current_dir = directory
    patterns = InteractiveFileRenamer(base_dir=directory).discover_file_patterns()
    return jsonify({"directory": str(directory), "patterns": patterns})


@app.get('/models')
def models():
    return jsonify(list_ollama_models())


@app.post('/preview')
def preview():
    if not current_dir:
        return jsonify({'error': 'Choose a folder first.'}), 400
    data = request.get_json(silent=True) or {}
    renamer = InteractiveFileRenamer(
        base_dir=current_dir,
        filename_prefix=data.get('prefix', ''),
        filename_extension=data.get('extension', ''),
    )
    return jsonify([p.name for p in renamer.collect_files_to_rename()])


@app.post('/rename_file')
def rename_file():
    """Rename one file. The first call of a run creates the backup folder; later calls pass its name back."""
    data = request.get_json(silent=True) or {}
    path = _child(data.get('file'))
    if not path or not path.is_file():
        return jsonify({'error': 'File not found in the chosen folder.'}), 400
    backup_dir = _backup_dir(data.get('backup_dir'))
    if data.get('backup_dir') and not backup_dir:
        return jsonify({'error': 'Backup folder is missing. Start the run again.'}), 400

    renamer = InteractiveFileRenamer(
        base_dir=current_dir,
        model_name=data.get('model') or DEFAULT_MODEL,
        backup_dir=backup_dir,
    )
    renamer.backup_dir = renamer.backup_dir or renamer.create_backup_directory()

    async def run() -> tuple[bool, str]:
        return await renamer.analyze_and_rename(AsyncClient(), path)

    ok, message = asyncio.run(run())
    return jsonify({'ok': ok, 'new_name' if ok else 'error': message, 'backup_dir': renamer.backup_dir.name})


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


def main() -> None:
    parser = argparse.ArgumentParser(description="File Renamer GUI")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Preferred port (default {DEFAULT_PORT})")
    parser.add_argument("--browser", action="store_true", help="Only serve the UI and print its link, no window")
    args = parser.parse_args()

    port = choose_port(args.port)
    if port is None:
        return
    server = make_server(HOST, port, app, threaded=True)
    url = f"http://{HOST}:{port}"
    print(f"File Renamer: {url}", flush=True)
    if args.browser:
        server.serve_forever()
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    webview.create_window('File Renamer', url, js_api=Api(), width=880, height=680, min_size=(520, 480),
                          text_select=True)
    webview.start()
    server.shutdown()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        main()
