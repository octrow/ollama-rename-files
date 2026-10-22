import asyncio

from ollama_rename_files.rename_files import (
    InteractiveFileRenamer,
    clean_model_response,
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

    async def fake_generate(self, model, prompt, **kwargs):
        return {"response": "doc-same-name.md"}

    monkeypatch.setattr("ollama_rename_files.rename_files.AsyncClient.generate", fake_generate)
    renamer = InteractiveFileRenamer(base_dir=tmp_path, auto_mode=True)

    renamed, failed, failed_files = asyncio.run(renamer.rename_files(parallel_count=2))

    assert (renamed, failed, failed_files) == (2, 0, [])
    contents = {(tmp_path / n).read_text() for n in ("doc-same-name.txt", "doc-same-name-1.txt")}
    assert contents == {"new1.txt", "new2.txt"}
    assert sorted(p.name for p in renamer.backup_dir.iterdir()) == ["new1.txt", "new2.txt"]
    assert (tmp_path / "other.md").exists()


def test_parse_args_defaults_are_not_none():
    from ollama_rename_files.rename_files import parse_args
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


def test_discover_keeps_whole_leading_word(tmp_path):
    for name in ("Untitled.md", "Untitled 1.md"):
        (tmp_path / name).write_text("x")
    assert InteractiveFileRenamer(base_dir=tmp_path).discover_file_patterns() == [(("Untitled", ".md"), 2)]


def test_clean_model_response_ignores_fence_language_tag():
    reply = "```md\nsnippet - create - utils - retry.md\n```"
    assert clean_model_response(reply) == "snippet - create - utils - retry.md"


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

    async def fake_generate(self, model, prompt, **kwargs):
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
