import os

import pytest

from ollama_rename_files import app as gui


def _client(tmp_path):
    (tmp_path / "new1.txt").write_text("hello")
    (tmp_path / "keep.md").write_text("x")
    client = gui.app.test_client()
    assert client.post("/set_directory", json={"directory": str(tmp_path)}).status_code == 200
    return client


def test_preview_lists_matching_files(tmp_path):
    client = _client(tmp_path)
    request = {"directory": str(tmp_path), "prefix": "new", "extension": ".txt"}
    assert client.post("/preview", json=request).json == ["new1.txt"]


def test_preview_of_a_picked_pattern_skips_longer_words(tmp_path):
    client = _client(tmp_path)
    (tmp_path / "newsletter.txt").write_text("x")
    request = {"directory": str(tmp_path), "prefix": "new", "extension": ".txt"}
    assert client.post("/preview", json={**request, "as_discovered": True}).json == ["new1.txt"]
    assert client.post("/preview", json={**request, "as_discovered": False}).json == ["new1.txt", "newsletter.txt"]


def test_each_request_uses_the_folder_it_names(tmp_path, monkeypatch):
    # two tabs: A scanned x, then B scanned y; A's rename must still happen in x
    async def fake_generate(self, model, prompt, **_kwargs):
        return {"response": "doc-hello.md"}

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", fake_generate)
    x, y = tmp_path / "x", tmp_path / "y"
    for folder in (x, y):
        folder.mkdir()
        (folder / "new1.txt").write_text("hello")
    client = gui.app.test_client()
    for folder in (x, y):
        assert client.post("/set_directory", json={"directory": str(folder)}).status_code == 200

    result = client.post("/rename_file", json={"directory": str(x), "file": "new1.txt"}).json

    assert result is not None and result["ok"] and (x / "doc-hello.txt").exists()
    assert sorted(p.name for p in y.iterdir()) == ["new1.txt"]


def test_requests_without_a_folder_are_refused(tmp_path):
    client = _client(tmp_path)
    assert client.post("/set_directory", data="directory=").status_code == 400
    assert client.post("/set_directory", json={"directory": ""}).status_code == 400
    assert client.post("/preview", json={"prefix": "new", "extension": ".txt"}).status_code == 400
    assert client.post("/rename_file", json={"file": "new1.txt"}).status_code == 400


def test_rename_file_rejects_paths_outside_folder(tmp_path):
    client = _client(tmp_path)
    for name in ("../etc/passwd", "/etc/passwd", "missing.txt"):
        assert client.post("/rename_file", json={"directory": str(tmp_path), "file": name}).status_code == 400
    bad_backup = client.post("/rename_file", json={"directory": str(tmp_path), "file": "new1.txt", "backup_dir": ".."})
    assert bad_backup.status_code == 400


def test_rename_file_renames_and_reuses_backup(tmp_path, monkeypatch):
    async def fake_generate(self, model, prompt, **_kwargs):
        return {"response": "doc-hello.md"}

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", fake_generate)
    client = _client(tmp_path)
    folder = str(tmp_path)
    first = client.post("/rename_file", json={"directory": folder, "file": "new1.txt"}).json
    assert first["ok"] and first["new_name"] == "doc-hello.txt"
    (tmp_path / "new2.txt").write_text("again")
    request = {"directory": folder, "file": "new2.txt", "backup_dir": first["backup_dir"]}
    second = client.post("/rename_file", json=request).json
    assert second["backup_dir"] == first["backup_dir"]
    assert sorted(p.name for p in (tmp_path / first["backup_dir"]).iterdir()) == ["new1.txt", "new2.txt"]


def _serve(application):
    from threading import Thread

    from werkzeug.serving import make_server

    server = make_server(gui.HOST, 0, application)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_choose_port_keeps_free_preferred_port():
    port = gui.next_free_port(20000)
    assert gui.choose_port(port) == port


def test_choose_port_skips_port_held_by_another_app():
    from flask import Flask

    other = _serve(Flask("other"))
    try:
        chosen = gui.choose_port(other.server_port, ask=lambda _: pytest.fail("must not ask"))
        assert chosen not in (None, other.server_port)
    finally:
        other.shutdown()


def test_choose_port_defaults_to_keeping_running_instance():
    ours = _serve(gui.app)
    try:
        assert gui.running_instance_pid(ours.server_port) == os.getpid()
        assert gui.choose_port(ours.server_port, ask=lambda _: False) is None
    finally:
        ours.shutdown()


def test_choose_port_restarts_running_instance_on_yes(monkeypatch):
    ours = _serve(gui.app)
    stopped = []
    monkeypatch.setattr(gui, "stop_instance", lambda pid, port: stopped.append((pid, port)))
    try:
        assert gui.choose_port(ours.server_port, ask=lambda _: True) == ours.server_port
        assert stopped == [(os.getpid(), ours.server_port)]
    finally:
        ours.shutdown()


def test_confirm_defaults_to_no_without_terminal(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert gui.confirm("Restart? ") is False


def test_set_directory_shows_home_as_tilde(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "inbox").mkdir()
    response = gui.app.test_client().post("/set_directory", json={"directory": "~/inbox"})
    assert response.json is not None
    assert response.json["directory"] == "~/inbox"


def test_requests_from_other_hosts_are_refused(tmp_path):
    # DNS rebinding: a web page served from evil.example resolves to 127.0.0.1 and calls the API
    client = gui.app.test_client()
    response = client.post("/set_directory", json={"directory": str(tmp_path)}, headers={"Host": "evil.example:5000"})
    assert response.status_code == 403
    assert client.get("/health", headers={"Host": "127.0.0.1:5000"}).status_code == 200


def test_rename_file_reports_an_unwritable_folder_as_json(tmp_path, monkeypatch):
    def refuse(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied", str(self))

    client = _client(tmp_path)
    monkeypatch.setattr("pathlib.Path.mkdir", refuse)
    response = client.post("/rename_file", json={"directory": str(tmp_path), "file": "new1.txt"})
    assert response.status_code == 400
    assert "Can't create a backup folder" in response.json["error"]
    assert (tmp_path / "new1.txt").exists()


def test_failed_rename_leaves_no_empty_backup_folder(tmp_path, monkeypatch):
    async def fake_generate(self, model, prompt, **_kwargs):
        raise ConnectionError("down")

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", fake_generate)
    client = _client(tmp_path)
    result = client.post("/rename_file", json={"directory": str(tmp_path), "file": "new1.txt"}).json
    assert not result["ok"] and result["backup_dir"] is None
    assert not [p for p in tmp_path.iterdir() if p.name.startswith("backup_")]


def test_preview_of_a_no_extension_chip_skips_files_with_one(tmp_path):
    for name in ("new1", "new2", "new4.txt"):
        (tmp_path / name).write_text("x")
    client = gui.app.test_client()
    request = {"directory": str(tmp_path), "prefix": "new", "extension": ""}
    assert client.post("/preview", json={**request, "as_discovered": True}).json == ["new1", "new2"]
    assert client.post("/preview", json={**request, "as_discovered": False}).json == ["new1", "new2", "new4.txt"]


def test_rename_to_the_same_name_leaves_no_empty_backup_folder(tmp_path, monkeypatch):
    async def same_name(self, model, prompt, **_kwargs):
        return {"response": "task - x"}

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", same_name)
    (tmp_path / "task-x.txt").write_text("hello")
    result = gui.app.test_client().post("/rename_file", json={"directory": str(tmp_path), "file": "task-x.txt"}).json
    assert result == {"ok": True, "new_name": "task-x.txt", "backup_dir": None}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["task-x.txt"]


def test_unreadable_folder_is_a_json_error(tmp_path, monkeypatch):
    def refuse(self):
        raise PermissionError(13, "Permission denied", str(self))

    monkeypatch.setattr("pathlib.Path.iterdir", refuse)
    client = gui.app.test_client()
    request = {"directory": str(tmp_path), "prefix": "new", "extension": ".txt"}
    for url in ("/set_directory", "/preview"):
        response = client.post(url, json=request)
        body = response.json
        assert response.status_code == 400 and body is not None and "Can't read" in body["error"]


def test_bad_port_setting_is_an_error_not_a_traceback(monkeypatch):
    monkeypatch.setattr(gui, "make_server", lambda *_args, **_kwargs: pytest.fail("must not serve"))
    monkeypatch.setenv("FILE_RENAMER_PORT", "five thousand")
    with pytest.raises(SystemExit) as stop:
        gui.run([])
    assert stop.value.code == 2
    with pytest.raises(SystemExit):
        gui.run(["--port", "99999"])


def test_no_free_port_ends_with_a_message(monkeypatch, capsys):
    def busy(_port, ask=None):
        raise RuntimeError("No free port in 5000-5049")

    monkeypatch.setattr(gui, "choose_port", busy)
    with pytest.raises(SystemExit) as stop:
        gui.run(["--port", "5000"])
    assert stop.value.code == 1
    assert "No free port" in capsys.readouterr().out


def test_next_free_port_stays_within_max_port(monkeypatch):
    probed = []
    monkeypatch.setattr(gui, "port_is_free", lambda port: probed.append(port) or False)
    with pytest.raises(RuntimeError):
        gui.next_free_port(gui.MAX_PORT)
    assert probed == [gui.MAX_PORT]
