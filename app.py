import asyncio
from pathlib import Path

import webview
from flask import Flask, jsonify, render_template, request

from rename_files import DEFAULT_MODEL, InteractiveFileRenamer, list_ollama_models

app = Flask(__name__)
# ponytail: single-user desktop app, one module-level "current folder" is enough
current_dir: Path | None = None


class Api:
    """Exposed to JS as window.pywebview.api."""

    def choose_directory(self) -> str | None:
        result = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        return result[0] if result else None


@app.route('/')
def index():
    return render_template("index.html")


@app.post('/set_directory')
def set_directory():
    directory = Path((request.get_json(silent=True) or {}).get('directory', '')).expanduser()
    if not directory.is_dir():
        return jsonify({"error": "Invalid directory."}), 400
    global current_dir
    current_dir = directory
    patterns = InteractiveFileRenamer(base_dir=directory).discover_file_patterns()
    return jsonify({"directory": str(directory), "patterns": patterns})


@app.get('/models')
def models():
    return jsonify(list_ollama_models())


@app.post('/rename_files')
def rename_files_route():
    if not current_dir:
        return jsonify({'error': 'Directory not set.'}), 400
    data = request.get_json(silent=True) or {}
    if not data.get('prefix') and not data.get('extension'):
        return jsonify({'error': 'Enter a prefix or an extension.'}), 400
    # fresh renamer per run: rescanning another folder mid-run can't redirect this one
    renamer = InteractiveFileRenamer(
        base_dir=current_dir,
        auto_mode=True,
        filename_prefix=data.get('prefix', ''),
        filename_extension=data.get('extension', ''),
        model_name=data.get('model') or DEFAULT_MODEL,
    )
    try:
        renamed, failed, failed_files = asyncio.run(renamer.rename_files())
    except Exception as e:
        app.logger.exception("Rename failed")
        return jsonify({'error': str(e)}), 500
    return jsonify({'renamed_count': renamed, 'failed_count': failed, 'failed_files': failed_files})


if __name__ == "__main__":
    webview.create_window('Interactive File Renamer', app, js_api=Api(), width=800, height=600, text_select=True)
    webview.start()
