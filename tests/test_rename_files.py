import asyncio

from rename_files import InteractiveFileRenamer, clean_model_response, sanitize_filename, unique_path


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

    async def fake_generate(self, model, prompt, **kwargs):
        return {"response": "doc-same-name.md"}

    monkeypatch.setattr("rename_files.AsyncClient.generate", fake_generate)
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True)

    renamed, failed, failed_files = asyncio.run(renamer.rename_files(parallel_count=2))

    assert (renamed, failed, failed_files) == (2, 0, [])
    contents = {(tmp_path / n).read_text() for n in ("doc-same-name.txt", "doc-same-name-1.txt")}
    assert contents == {"new1.txt", "new2.txt"}
    assert sorted(p.name for p in renamer.backup_dir.iterdir()) == ["new1.txt", "new2.txt"]
    assert (tmp_path / "other.md").exists()


def test_parse_args_defaults_are_not_none():
    from rename_files import parse_args
    args = parse_args(["-a", "-d", "."])
    assert None not in (args.model, args.context, args.prefix, args.ext)


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
