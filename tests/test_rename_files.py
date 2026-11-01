import asyncio

import pytest

from ollama_rename_files.rename_files import (
    InteractiveFileRenamer,
    clean_model_response,
    read_content,
    sanitize_filename,
    unique_path,
)


def test_clean_model_response_strips_think_and_fences():
    reply = "<think>hmm\nlong</think>\n```\n`Doc - Update - API - Notes.md`\n```\nextra"
    assert clean_model_response(reply) == "doc - update - api - notes.md"


def test_sanitize_filename_builds_slug_with_original_extension():
    assert sanitize_filename("doc - update - api: notes.md", ".txt") == "doc-update-api_-notes.txt"
    assert sanitize_filename("123 ...", ".txt").startswith("untitled-document-")
    assert len(sanitize_filename("a" * 500, ".txt", max_len=50)) <= 50


def test_unique_path_never_returns_existing(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "a-1.txt").write_text("x")
    assert unique_path(tmp_path / "a.txt") == tmp_path / "a-2.txt"


def test_rename_does_not_overwrite_and_backs_up(tmp_path, monkeypatch):
    for name in ("new1.txt", "new2.txt"):
        (tmp_path / name).write_text(name)
    (tmp_path / "other.md").write_text("skip me")

    async def fake_generate(self, model, prompt, **_kwargs):
        return {"response": "doc-same-name.md"}

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", fake_generate)
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True)

    renamed, failed, failed_files = asyncio.run(renamer.rename_files(parallel_count=2))

    assert (renamed, failed, failed_files) == (2, 0, [])
    contents = {(tmp_path / n).read_text() for n in ("doc-same-name.txt", "doc-same-name-1.txt")}
    assert contents == {"new1.txt", "new2.txt"}
    assert renamer.backup_dir is not None
    assert sorted(p.name for p in renamer.backup_dir.iterdir()) == ["new1.txt", "new2.txt"]
    assert (tmp_path / "other.md").exists()


def test_parse_args_defaults_are_not_none():
    from ollama_rename_files.rename_files import parse_args

    args = parse_args(["-a", "-d", "."])
    assert None not in (args.model, args.context, args.prefix, args.ext)


def test_cli_options_skip_their_prompts(tmp_path, monkeypatch):
    from ollama_rename_files.rename_files import parse_args

    monkeypatch.setattr("builtins.input", lambda _prompt="": pytest.fail("must not ask"))
    args = parse_args(["-d", str(tmp_path), "-m", "tiny:1b", "-c", "500", "--prefix", "draft", "--ext", ".md"])
    renamer = InteractiveFileRenamer(
        base_dir=args.directory,
        model_name=args.model,
        context_length=args.context,
        filename_prefix=args.prefix,
        filename_extension=args.ext,
    )
    renamer.interactive_configuration(args.given)
    assert (renamer.base_dir, renamer.model_name, renamer.context_length) == (tmp_path, "tiny:1b", 500)
    assert (renamer.filename_prefix, renamer.filename_extension) == ("draft", ".md")


def test_cli_asks_only_what_the_options_left_out(tmp_path, monkeypatch):
    from ollama_rename_files.rename_files import parse_args

    (tmp_path / "new1.txt").write_text("x")
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "")
    monkeypatch.setattr("ollama_rename_files.rename_files.list_ollama_models", lambda: ["first:1b", "second:1b"])
    monkeypatch.setattr(InteractiveFileRenamer, "_get_model_max_context", lambda self, model: 4096)
    args = parse_args(["-d", str(tmp_path), "-m", "second:1b"])
    renamer = InteractiveFileRenamer(base_dir=args.directory, model_name=args.model)

    renamer.interactive_configuration(args.given)

    assert len(prompts) == 2  # pattern and context; folder and model came from the options
    assert (renamer.base_dir, renamer.model_name, renamer.context_length) == (tmp_path, "second:1b", 4096)
    assert (renamer.filename_prefix, renamer.filename_extension) == ("new", ".txt")


def test_collect_skips_longer_words_with_the_same_start(tmp_path):
    for name in ("new.txt", "new1.txt", "new note.txt", "news.txt", "newsletter.txt", "2024.md", "20240101.md"):
        (tmp_path / name).write_text("x")
    new = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True)
    year = InteractiveFileRenamer(base_dir=tmp_path, filename_prefix="2024", filename_extension=".md")
    assert [p.name for p in new.collect_files_to_rename()] == ["new note.txt", "new.txt", "new1.txt"]
    assert [p.name for p in year.collect_files_to_rename()] == ["2024.md"]
    assert len(new.collect_files_to_rename(whole_prefix=False)) == 5


def test_clean_model_response_handles_truncated_think():
    assert clean_model_response("<think>still reasoning when cut off") == ""


def test_collect_matches_extension_case_insensitively(tmp_path):
    (tmp_path / "new1.TXT").write_text("x")
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True)
    assert [p.name for p in renamer.collect_files_to_rename()] == ["new1.TXT"]


def test_discover_groups_numbered_files_under_one_prefix(tmp_path):
    for name in ("new1.txt", "new2.txt", "new3.TXT", "other.md"):
        (tmp_path / name).write_text("x")
    patterns = InteractiveFileRenamer(base_dir=tmp_path).discover_file_patterns()
    assert patterns[0] == (("new", ".txt"), 3)


def test_discover_keeps_whole_leading_word(tmp_path):
    for name in ("Untitled.md", "Untitled 1.md"):
        (tmp_path / name).write_text("x")
    assert InteractiveFileRenamer(base_dir=tmp_path).discover_file_patterns() == [(("Untitled", ".md"), 2)]


def test_clean_model_response_ignores_fence_language_tag():
    reply = "```md\nsnippet - create - utils - retry.md\n```"
    assert clean_model_response(reply) == "snippet - create - utils - retry.md"


def test_clean_model_response_skips_chatter_around_the_name():
    assert (
        clean_model_response("Here is a file name:\n\ndoc - update - api - notes.md") == "doc - update - api - notes.md"
    )
    assert clean_model_response("**Filename:** `task-fix-api.md`") == "task-fix-api.md"
    assert (
        clean_model_response("File name: issue - fix - auth - token-expiry.md")
        == "issue - fix - auth - token-expiry.md"
    )
    assert clean_model_response("Sure! Happy to help.") == ""
    assert clean_model_response("1. snippet - create - db - index.sql") == "snippet - create - db - index.sql"
    assert clean_model_response("- doc-update-readme.md") == "doc-update-readme.md"


def test_sanitize_filename_keeps_non_latin_and_leading_digits():
    assert sanitize_filename("заметка - про - бэкап", ".txt") == "заметка-про-бэкап.txt"
    assert sanitize_filename("doc - update - notes - про бэкап", ".txt") == "doc-update-notes-про-бэкап.txt"
    assert sanitize_filename("2024 - q3 - report", ".md") == "2024-q3-report.md"
    assert sanitize_filename("-- _note_ --", ".md") == "note.md"


def test_sanitize_filename_fits_255_bytes():
    name = sanitize_filename("я" * 200, ".txt")
    assert len(name.encode()) <= 255 and name.endswith(".txt")


def test_read_content_rejects_empty_text(tmp_path):
    for name, data in (("empty.txt", b""), ("blank.txt", b"  \n\t\n")):
        (tmp_path / name).write_bytes(data)
        with pytest.raises(ValueError, match="empty"):
            read_content(tmp_path / name, 2048)


def test_sanitize_filename_drops_commas():
    name = sanitize_filename("idea - respect color-scheme, keep palette", ".txt")
    assert name == "idea-respect-color-scheme-keep-palette.txt"


def _tiny_pdf(text: str) -> bytes:
    """One-page PDF with `text` in Helvetica, valid xref offsets."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def test_read_content_extracts_pdf_text(tmp_path):
    from ollama_rename_files.rename_files import read_content

    pdf = tmp_path / "new1.pdf"
    pdf.write_bytes(_tiny_pdf("Quarterly budget report"))
    assert "Quarterly budget report" in read_content(pdf, 2048)
    assert read_content(pdf, 9) == "Quarterly"


def test_read_content_pdf_without_text_layer_fails(tmp_path):
    import pytest

    from ollama_rename_files.rename_files import read_content

    pdf = tmp_path / "new1.pdf"
    pdf.write_bytes(_tiny_pdf(""))
    with pytest.raises(ValueError, match="no text layer"):
        read_content(pdf, 2048)


def test_read_content_drops_character_cut_by_byte_limit(tmp_path):
    from ollama_rename_files.rename_files import read_content

    path = tmp_path / "new1.txt"
    path.write_text("€" * 10, encoding="utf-8")  # 3-byte chars: the 8-byte read ends mid-character
    assert read_content(path, 2) == "€€"


def test_read_content_rejects_binary(tmp_path):
    import pytest

    from ollama_rename_files.rename_files import read_content

    path = tmp_path / "new1.bin"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    with pytest.raises(ValueError, match="binary"):
        read_content(path, 2048)


def test_broken_pdf_fails_only_that_file(tmp_path, monkeypatch):
    (tmp_path / "new1.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
    (tmp_path / "new2.pdf").write_bytes(_tiny_pdf("Meeting notes"))
    prompts = []

    async def fake_generate(self, model, prompt, **_kwargs):
        prompts.append(prompt)
        return {"response": "doc-meeting-notes.md"}

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", fake_generate)
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True, filename_extension=".pdf")

    renamed, failed, failed_files = asyncio.run(renamer.rename_files())

    assert (renamed, failed) == (1, 1)
    assert failed_files[0][0] == "new1.pdf"
    assert (tmp_path / "new1.pdf").exists()
    assert (tmp_path / "doc-meeting-notes.pdf").exists()
    assert "Meeting notes" in prompts[0]


def test_backup_does_not_overwrite_existing_backup(tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "new1.txt").write_text("old backup")
    (tmp_path / "new1.txt").write_text("current")
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True, backup_dir=backup)

    ok, _ = renamer._backup_and_rename(tmp_path / "new1.txt", "doc-a.txt")

    assert ok
    assert (backup / "new1.txt").read_text() == "old backup"
    assert (backup / "new1-1.txt").read_text() == "current"


def test_rename_to_same_name_is_noop(tmp_path):
    backup = tmp_path / "backup"
    backup.mkdir()
    (tmp_path / "new-foo.txt").write_text("current")
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True, backup_dir=backup)

    ok, name = renamer._backup_and_rename(tmp_path / "new-foo.txt", "new-foo.txt")

    assert ok
    assert name == "new-foo.txt"
    assert (tmp_path / "new-foo.txt").read_text() == "current"
    assert not (tmp_path / "new-foo-1.txt").exists()
    assert list(backup.iterdir()) == []


def test_ollama_errors_say_what_to_do(tmp_path, monkeypatch):
    from ollama import ResponseError

    (tmp_path / "new1.txt").write_text("a")
    (tmp_path / "new2.txt").write_text("b")
    errors = iter([ConnectionError("Failed to connect"), ResponseError("model 'tiny:1b' not found", 404)])

    async def fake_generate(self, model, prompt, **_kwargs):
        raise next(errors)

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", fake_generate)
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True, model_name="tiny:1b")

    _, _, failed_files = asyncio.run(renamer.rename_files())

    messages = dict(failed_files)
    assert "ollama serve" in messages["new1.txt"]
    assert "ollama pull tiny:1b" in messages["new2.txt"]


def test_two_renamers_never_take_the_same_name(tmp_path, monkeypatch):
    # the GUI builds one renamer per request on a threaded server: two requests at once must not overwrite each other
    import threading
    import time

    from ollama_rename_files import rename_files

    real_unique_path = rename_files.unique_path

    def slow_unique_path(path):
        free = real_unique_path(path)
        time.sleep(0.05)  # widen the gap between picking a free name and using it
        return free

    monkeypatch.setattr(rename_files, "unique_path", slow_unique_path)
    backup = tmp_path / "backup_x"
    backup.mkdir()
    for name in ("new1.txt", "new2.txt"):
        (tmp_path / name).write_text(name)
    renamers = [InteractiveFileRenamer(base_dir=tmp_path, backup_dir=backup) for _ in range(2)]
    threads = [
        threading.Thread(target=r._backup_and_rename, args=(tmp_path / n, "doc.txt"))
        for r, n in zip(renamers, ("new1.txt", "new2.txt"), strict=True)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert {(tmp_path / n).read_text() for n in ("doc.txt", "doc-1.txt")} == {"new1.txt", "new2.txt"}


def test_unwritable_folder_stops_the_run_with_a_clear_error(tmp_path, monkeypatch):
    def refuse(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied", str(self))

    (tmp_path / "new1.txt").write_text("x")
    monkeypatch.setattr("pathlib.Path.mkdir", refuse)
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True)
    with pytest.raises(ValueError, match="Can't create a backup folder"):
        asyncio.run(renamer.rename_files())


def _fail_generate(monkeypatch):
    async def fake_generate(self, model, prompt, **_kwargs):
        raise ConnectionError("down")

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", fake_generate)


def test_run_where_nothing_was_renamed_leaves_no_backup_folder(tmp_path, monkeypatch):
    _fail_generate(monkeypatch)
    (tmp_path / "new1.txt").write_text("hello")
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True)
    assert asyncio.run(renamer.rename_files())[:2] == (0, 1)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["new1.txt"]


def test_ollama_client_has_a_timeout():
    from ollama_rename_files.rename_files import OLLAMA_TIMEOUT_S, explain_ollama_error, ollama_client

    assert ollama_client()._client.timeout.read == OLLAMA_TIMEOUT_S
    import httpx

    assert "didn't answer" in explain_ollama_error(httpx.ReadTimeout("timed out"), "tiny:1b")


def test_context_must_be_positive():
    from ollama_rename_files.rename_files import parse_args

    for bad in ("0", "-1", "lots"):
        with pytest.raises(SystemExit):
            parse_args(["-a", "-d", ".", "-c", bad])


def test_extension_without_dot_matches_only_that_extension(tmp_path):
    for name in ("new1.txt", "new2.mytxt", "new3txt"):
        (tmp_path / name).write_text("x")
    renamer = InteractiveFileRenamer(base_dir=tmp_path, filename_extension="txt")
    assert [p.name for p in renamer.collect_files_to_rename()] == ["new1.txt"]
