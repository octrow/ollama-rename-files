import argparse
import asyncio
import codecs
import contextlib
import logging
import re
import shutil
import sys
import textwrap
import threading
import uuid
from collections import Counter
from collections.abc import Collection
from datetime import datetime
from pathlib import Path

import httpx
from ollama import AsyncClient, Client, ResponseError
from pypdf import PdfReader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_CONTEXT_LENGTH = 2048
DEFAULT_PREFIX = "new"
DEFAULT_EXTENSION = ".txt"
MAX_FILE_NAME_LENGTH = 128
# a cold 7B model on a CPU can take minutes for its first answer; a hung Ollama must not block the run forever
OLLAMA_TIMEOUT_S = 300
OLLAMA_INFO_TIMEOUT_S = 10  # `ollama list` / `ollama show` answer at once or not at all
MAX_FILE_NAME_BYTES = 255  # ext4, APFS and NTFS limits; Cyrillic takes 2 bytes a character
TOP_PATTERNS = 5
FILE_LIST_LIMIT = 20  # files the interactive CLI lists before asking to rename

PROMPT_TEMPLATE = textwrap.dedent("""\
    The following text is from a file in a software development project:

    ```
    {content}
    ```

    Suggest a file name using the following pattern:

    `<Type> - <Action> - <Component> - <Short Description>.<Extension>`

    Where:
    * **Type:** task, issue, doc, snippet, review, idea
    * **Action:** create, fix, update, review, discuss, complete
    * **Component:** backend, frontend, database, api, auth, testing, or a more specific component name
    * **Short Description:** A concise summary of the file's content.
    * **Extension:** Based on the content (e.g., .md, .txt, .py). If unsure, use .md

    Provide only the file name as output, maximum {max_len} characters, lowercase.
    """)

FailedFiles = list[tuple[str, str]]

# The context length is in characters; Ollama's window (num_ctx) is in tokens and is otherwise the server's default,
# which silently cuts a longer prompt. Size the window from the characters instead.
# ponytail: 2 characters a token is conservative for English (~4) and Cyrillic (~2.5); CJK (~1) can still be cut
CHARS_PER_TOKEN = 2
NUM_CTX_STEP = 1024  # one window per run: Ollama reloads the model whenever num_ctx changes
MIN_NUM_CTX = 4096  # a common server default; never shrink below it, or a model already loaded at it is reloaded


def context_window(context_chars: int, reply_tokens: int) -> int:
    """num_ctx that holds the prompt template, `context_chars` of file text and the reply."""
    tokens = (context_chars + len(PROMPT_TEMPLATE)) // CHARS_PER_TOKEN + reply_tokens
    return max(MIN_NUM_CTX, -(-tokens // NUM_CTX_STEP) * NUM_CTX_STEP)


def max_context_chars(model_tokens: int) -> int:
    """How many characters of a file fit in a model with `model_tokens` of context, next to the prompt and reply."""
    return max(1, (model_tokens - MAX_FILE_NAME_LENGTH) * CHARS_PER_TOKEN - len(PROMPT_TEMPLATE))


# One lock for every renamer in the process: CLI workers share a renamer, GUI requests each build their own
# on a threaded server. Picking a free name and renaming to it must not interleave, or one file replaces another.
# ponytail: process-wide; two processes renaming in one folder at once (CLI + GUI) still race
_RENAME_LOCK = threading.Lock()


def _same_run(a: str, b: str) -> bool:
    """Discovery keeps two letters or two digits in one prefix run (`new2` → `new`, `newsletter` stays whole)."""
    return (a.isalpha() and b.isalpha()) or (a.isdecimal() and b.isdecimal())


def matches_prefix(name: str, prefix: str, whole_prefix: bool = True) -> bool:
    """`new` takes new1.txt and new.txt; with whole_prefix it skips newsletter.txt, as discovery counts it."""
    if not name.startswith(prefix):
        return False
    rest = name[len(prefix) :]
    return not (whole_prefix and prefix and rest and _same_run(prefix[-1], rest[0]))


def _name_in_line(line: str) -> str:
    """`**Filename:** `a-b.md`` → `a-b.md`; `File name: a-b.md` → `a-b.md`."""
    span = re.search(r"`([^`]+)`", line)
    if span:
        line = span.group(1)
    line = line.replace("*", "").strip().strip("`\"'")
    line = re.sub(r"^(\d+[.)]|[-•])\s+", "", line)  # list markers: "1. a-b.md", "- a-b.md"
    return re.sub(r"^[^\W\d_][\w ]{0,19}:\s+", "", line)  # a short label before the name


def _looks_like_name(line: str) -> bool:
    # ponytail: the prompt asks for `a - b - c.ext`, so a dash or an extension; a bare word like "readme" fails the file
    return not line.endswith(":") and ("-" in line or re.search(r"\.\w{1,5}$", line) is not None)


def clean_model_response(text: str) -> str:
    """The file name in a model reply: skips <think> blocks, fences and chatter like "Here is a name:"; "" if none."""
    text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.DOTALL)
    # drop fence lines before reading names, or "```md" leaves "md" behind
    lines = [_name_in_line(line) for line in text.splitlines() if not line.strip().startswith("```")]
    return next((line.lower() for line in lines if _looks_like_name(line)), "")


def sanitize_filename(suggested_name: str, original_ext: str, max_len: int = MAX_FILE_NAME_LENGTH) -> str:
    name = re.sub(r"\.\w+$", "", suggested_name)
    name = re.sub(r"[.`',;]", "", name)
    name = re.sub(r'[<>/\\|?*:"+%!@]', "_", name)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = re.sub(r"^[\W_]+", "", name)
    name = name[: max_len - len(original_ext)]
    while len(f"{name}{original_ext}".encode()) > MAX_FILE_NAME_BYTES:
        name = name[:-1]
    name = re.sub(r"[\W_]+$", "", name)
    if not any(c.isalpha() for c in name):  # "123" or "" says nothing about the file
        name = f"untitled-document-{uuid.uuid4().hex[:8]}"
    return f"{name}{original_ext}"


def unique_path(path: Path) -> Path:
    """Return `path`, or `path` with a -1, -2, ... suffix if it already exists."""
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate


def read_content(path: Path, limit: int) -> str:
    """First `limit` characters of a file's text: PDF text layer, or the file decoded as UTF-8."""
    if path.suffix.lower() == ".pdf":
        text = ""
        for page in PdfReader(path).pages:
            text += page.extract_text() + "\n"
            if len(text) >= limit:
                break
        if not text.strip():
            raise ValueError("PDF has no text layer (scanned image?)")
        return text.strip()[:limit]
    with path.open("rb") as f:
        data = f.read(limit * 4)  # 4 bytes is the longest UTF-8 character
    if b"\0" in data:
        raise ValueError("binary or UTF-16 file, only UTF-8 text and PDF files are supported")
    # incremental decoder: a character cut in half by the read above is dropped, not an error
    text = codecs.getincrementaldecoder("utf-8")().decode(data)[:limit]
    if not text.strip():
        raise ValueError("file is empty, nothing to name it by")
    return text


def explain_ollama_error(error: Exception, model_name: str) -> str:
    """Ollama's error plus the command that fixes it, for the two errors a first run hits."""
    if isinstance(error, ConnectionError):
        return "Ollama isn't reachable. Start it with `ollama serve` (or the Ollama app), or set OLLAMA_HOST."
    if isinstance(error, ResponseError) and error.status_code == 404:
        return f"Model {model_name} isn't installed. Run `ollama pull {model_name}`."
    if isinstance(error, httpx.TimeoutException):
        return f"Ollama didn't answer in {OLLAMA_TIMEOUT_S} s. Try a smaller model or fewer characters (-c)."
    return str(error) or type(error).__name__


def ollama_client() -> AsyncClient:
    return AsyncClient(timeout=OLLAMA_TIMEOUT_S)


def list_ollama_models() -> list[str]:
    try:
        return [m.model for m in Client(timeout=OLLAMA_INFO_TIMEOUT_S).list().models if m.model]
    except Exception as e:  # noqa: BLE001 - Ollama down or unreachable: GUI/CLI fall back to a default
        logger.error(f"Error retrieving Ollama models: {e}")
        return []


class InteractiveFileRenamer:
    def __init__(
        self,
        base_dir: str | Path | None = None,
        auto_mode: bool = False,
        model_name: str = DEFAULT_MODEL,
        context_length: int = DEFAULT_CONTEXT_LENGTH,
        filename_prefix: str = DEFAULT_PREFIX,
        filename_extension: str = DEFAULT_EXTENSION,
        max_file_name_length: int = MAX_FILE_NAME_LENGTH,
        backup_dir: str | Path | None = None,
    ):
        self.base_dir: Path | None = Path(base_dir) if base_dir else None
        self.auto_mode = auto_mode
        self.model_name = model_name
        self.context_length = context_length
        self.filename_prefix = filename_prefix
        self.filename_extension = filename_extension
        self.max_file_name_length = max_file_name_length
        self.backup_dir: Path | None = Path(backup_dir) if backup_dir else None

    def create_backup_directory(self) -> Path:
        assert self.base_dir is not None, "base_dir is set before backups are made"
        backup_dir = unique_path(self.base_dir / f"backup_{datetime.now():%Y%m%d_%H%M%S}")
        try:
            backup_dir.mkdir(parents=True)
        except OSError as e:
            raise ValueError(f"Can't create a backup folder in {self.base_dir}: {e.strerror or e}") from e
        return backup_dir

    def remove_backup_if_empty(self) -> None:
        """Drop the backup folder when no original was copied into it (every file failed); keeps it otherwise."""
        if self.backup_dir:
            with contextlib.suppress(OSError):  # rmdir refuses a non-empty folder: exactly the check we want
                self.backup_dir.rmdir()

    def discover_file_patterns(self) -> list[tuple[tuple[str, str], int]]:
        """Most common (prefix, extension) pairs among files in base_dir."""
        if not self.base_dir or not self.base_dir.is_dir():
            raise ValueError("Invalid directory")
        patterns = Counter()
        for path in self.base_dir.iterdir():
            if path.is_file():
                prefix_match = re.match(r"^([^\W\d_]+|\d+|[^.\w]+)", path.name)
                if prefix_match:
                    patterns[(prefix_match.group(1), path.suffix.lower())] += 1
        return patterns.most_common(TOP_PATTERNS)

    @staticmethod
    def _choose(prompt: str, count: int) -> int | None:
        """Ask for a 1-based number in [1, count]; None on empty input."""
        while True:
            choice = input(prompt).strip()
            if not choice:
                return None
            if choice.isdigit() and 1 <= int(choice) <= count:
                return int(choice)
            print("Invalid selection. Please try again.")

    def _interactive_directory_selection(self) -> Path:
        while True:
            dir_path_str = input("Enter the directory path (press Enter for current directory): ").strip()
            dir_path = Path(dir_path_str).expanduser() if dir_path_str else Path.cwd()
            if dir_path.is_dir():
                return dir_path
            print(f"Error: '{dir_path}' is not a valid directory. Please try again.")

    def _interactive_file_pattern_selection(self, patterns: list[tuple[tuple[str, str], int]]) -> tuple[str, str]:
        print("\nChoose pattern of names for renaming:")
        for i, ((prefix, ext), count) in enumerate(patterns, 1):
            print(f"{i}. `{prefix}` - {count} files, {ext[1:] or '(no extension)'}")
        print(f"{len(patterns) + 1}. Write your pattern")
        choice = self._choose("Press number of chosen variant: ", len(patterns) + 1)
        if choice is None:
            return patterns[0][0] if patterns else (DEFAULT_PREFIX, DEFAULT_EXTENSION)
        if choice <= len(patterns):
            return patterns[choice - 1][0]
        prefix = input("Enter file prefix: ").strip()
        ext = input("Enter file extension (with dot): ").strip().lower()
        return prefix, ext

    def _interactive_model_selection(self, available_models: list[str]) -> str:
        if not available_models:
            print(f"No Ollama models found. Using default model {DEFAULT_MODEL}.")
            return DEFAULT_MODEL
        print("\nAvailable Ollama models:")
        for i, model in enumerate(available_models, 1):
            print(f"{i}. {model}")
        print(f"{len(available_models) + 1}. Enter custom model name")
        choice = self._choose("Select model number (or press Enter for first model): ", len(available_models) + 1)
        if choice is None:
            return available_models[0]
        if choice <= len(available_models):
            return available_models[choice - 1]
        return input("Enter full model name: ").strip()

    def _get_model_max_context(self, model_name: str) -> int | None:
        """The model's context length in tokens, from `ollama show`; None if unknown."""
        try:
            modelinfo = Client(timeout=OLLAMA_INFO_TIMEOUT_S).show(model_name).modelinfo or {}
            for key, value in modelinfo.items():
                if key.endswith(".context_length"):
                    return int(value)
            logger.warning(f"Could not determine context length for {model_name} (key not found)")
        except Exception as e:  # noqa: BLE001 - best effort, default is fine
            logger.warning(f"Could not retrieve model info: {e}")
        return None

    def interactive_configuration(self, given: Collection[str] = ()) -> None:
        """Ask for every setting except those in `given` (option names set on the command line)."""
        if self.auto_mode:
            return
        if "directory" not in given:
            self.base_dir = self._interactive_directory_selection()
        if not {"prefix", "ext"} & set(given):
            self.filename_prefix, self.filename_extension = self._interactive_file_pattern_selection(
                self.discover_file_patterns()
            )
        if "model" not in given:
            self.model_name = self._interactive_model_selection(list_ollama_models())
        if "context" not in given:
            self.context_length = self._interactive_context_selection(self._get_model_max_context(self.model_name))
        self._print_summary()

    @staticmethod
    def _interactive_context_selection(model_tokens: int | None) -> int:
        """Characters of each file to send; Enter = the default. Capped by what the model's context holds."""
        limit = max_context_chars(model_tokens) if model_tokens else None
        default = min(DEFAULT_CONTEXT_LENGTH, limit) if limit else DEFAULT_CONTEXT_LENGTH
        bound = f", up to {limit}" if limit else ""
        while True:
            choice = input(f"\nCharacters of each file to send to the model (Enter for {default}{bound}): ").strip()
            if not choice:
                return default
            if choice.isdecimal() and 0 < int(choice) <= (limit or int(choice)):
                return int(choice)
            print(f"Enter a number of characters from 1{' to ' + str(limit) if limit else ''}.")

    def _print_summary(self) -> None:
        print("\n--- Configuration Summary ---")
        print(f"Directory: {self.base_dir}")
        print(f"File Pattern: '{self.filename_prefix}*{self.filename_extension}'")
        print(f"Model: {self.model_name}")
        print(f"Context Length: {self.context_length} characters")

    async def suggest_name(self, client: AsyncClient, content: str) -> str:
        response = await client.generate(
            self.model_name,
            PROMPT_TEMPLATE.format(content=content, max_len=self.max_file_name_length),
            think=False,
            options={
                "num_predict": self.max_file_name_length,
                "num_ctx": context_window(self.context_length, self.max_file_name_length),
            },
        )
        return clean_model_response(response["response"])

    async def analyze_and_rename(self, client: AsyncClient, file_path: Path) -> tuple[bool, str]:
        """Returns (success, message)."""
        filename = file_path.name
        try:
            content = await asyncio.to_thread(read_content, file_path, self.context_length)
        except Exception as e:  # noqa: BLE001 - pypdf raises arbitrary errors on corrupt or encrypted PDFs
            logger.error(f"Error reading file {filename}: {e}")
            return False, str(e)

        try:
            suggested_name = await self.suggest_name(client, content)
            if not suggested_name:
                raise ValueError("model returned no file name")
        except Exception as e:  # noqa: BLE001 - any model/transport error fails just this file
            logger.error(f"Error generating new filename for {filename}: {e}")
            return False, explain_ollama_error(e, self.model_name)

        new_filename = sanitize_filename(suggested_name, file_path.suffix, self.max_file_name_length)
        return self._backup_and_rename(file_path, new_filename)

    def _backup_and_rename(self, file_path: Path, new_filename: str) -> tuple[bool, str]:
        """Copy to backup_dir, then rename to a free name. Never overwrites."""
        if new_filename == file_path.name:
            return True, file_path.name
        assert self.base_dir is not None and self.backup_dir is not None, "rename_files sets both first"
        try:
            with _RENAME_LOCK:
                shutil.copy2(file_path, unique_path(self.backup_dir / file_path.name))
                new_file_path = unique_path(self.base_dir / new_filename)
                file_path.rename(new_file_path)
        except OSError as e:
            logger.error(f"Backup/rename failed for {file_path.name}: {e}")
            return False, str(e)
        logger.info(f"Renamed: {file_path.name} -> {new_file_path.name}")
        return True, new_file_path.name

    def collect_files_to_rename(self, as_discovered: bool = True) -> list[Path]:
        """Files that match the pattern, sorted.

        as_discovered (CLI, a pattern picked in the GUI): match as discovery counts the pattern, so the prefix is a
        whole word and an empty extension means files without one. Otherwise (typed in the GUI): plain starts-with,
        and an empty extension means any.
        """
        if not self.base_dir or not self.base_dir.is_dir():
            raise ValueError(f"Invalid directory: {self.base_dir}")
        ext = self.filename_extension.lower()
        if ext and not ext.startswith("."):
            ext = f".{ext}"  # "txt" means .txt, not every name ending in "txt"

        def has_extension(path: Path) -> bool:
            return path.suffix == "" if as_discovered and not ext else path.name.lower().endswith(ext)

        return sorted(
            p
            for p in self.base_dir.iterdir()
            if p.is_file() and matches_prefix(p.name, self.filename_prefix, as_discovered) and has_extension(p)
        )

    async def rename_files(self, parallel_count: int = 0) -> tuple[int, int, FailedFiles]:
        files_to_rename = self.collect_files_to_rename()
        if not files_to_rename:
            logger.info("No files found to rename.")
            return 0, 0, []
        logger.info(f"Found {len(files_to_rename)} files to rename")
        if self.backup_dir is None:
            # created before any model call so a read-only folder stops the run at once; removed below if unused
            self.backup_dir = self.create_backup_directory()

        client = ollama_client()
        semaphore = asyncio.Semaphore(max(parallel_count, 1))
        done = 0

        async def worker(path: Path) -> tuple[bool, str]:
            nonlocal done
            async with semaphore:
                result = await self.analyze_and_rename(client, path)
            done += 1
            if done % 10 == 0 or done == len(files_to_rename):
                logger.info(f"Progress: {done}/{len(files_to_rename)}")
            return result

        results = await asyncio.gather(*(worker(p) for p in files_to_rename))
        self.remove_backup_if_empty()
        failed_files = [(p.name, msg) for p, (ok, msg) in zip(files_to_rename, results, strict=True) if not ok]
        return len(results) - len(failed_files), len(failed_files), failed_files


def _positive_int(value: str) -> int:
    if not value.isdecimal() or int(value) < 1:
        raise argparse.ArgumentTypeError(f"expected a number of characters, 1 or more, got {value!r}")
    return int(value)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename files by their content with a local Ollama model.",
        epilog="Run `ollama-rename gui` for the desktop window.",
    )
    parser.add_argument(
        "-a", "--auto", action="store_true", help="Run in auto mode without interactive prompts (requires -d)"
    )
    parser.add_argument("-d", "--directory", help="Specify directory non-interactively")
    parser.add_argument("-m", "--model", help=f"Specify the Ollama model (default {DEFAULT_MODEL})")
    parser.add_argument(
        "-c",
        "--context",
        type=_positive_int,
        help=f"Characters of each file to send to the model (default {DEFAULT_CONTEXT_LENGTH})",
    )
    parser.add_argument(
        "--prefix", help=f"File prefix, matched as a whole word: `new` skips newsletter.txt (default {DEFAULT_PREFIX})"
    )
    parser.add_argument("--ext", help=f"Specify the file extension (default {DEFAULT_EXTENSION})")
    parser.add_argument(
        "-p", "--parallel", type=int, default=0, help="Number of parallel rename operations (default: sequential)"
    )
    args = parser.parse_args(argv)
    if args.auto and not args.directory:
        parser.error("--auto requires --directory")
    # options set on the command line are not asked again in interactive mode
    defaults = {
        "model": DEFAULT_MODEL,
        "context": DEFAULT_CONTEXT_LENGTH,
        "prefix": DEFAULT_PREFIX,
        "ext": DEFAULT_EXTENSION,
    }
    args.given = {name for name in ("directory", *defaults) if getattr(args, name) is not None}
    for name, default in defaults.items():
        if getattr(args, name) is None:
            setattr(args, name, default)
    return args


def _confirm_files(files: list[Path]) -> bool:
    """Interactive CLI: show the files that will change and rename them only on an explicit yes."""
    if not files:
        return True  # rename_files reports "No files found to rename."
    print(f"\nFiles to rename ({len(files)}):")
    for path in files[:FILE_LIST_LIMIT]:
        print(f"  {path.name}")
    if len(files) > FILE_LIST_LIMIT:
        print(f"  ... and {len(files) - FILE_LIST_LIMIT} more")
    files_word = "file" if len(files) == 1 else "files"
    return input(f"Rename {len(files)} {files_word}? [y/N] ").strip().lower() in {"y", "yes", "д", "да"}


async def _main(argv: list[str] | None) -> None:
    args = parse_args(argv)
    renamer = InteractiveFileRenamer(
        base_dir=args.directory,
        auto_mode=args.auto,
        model_name=args.model,
        context_length=args.context,
        filename_prefix=args.prefix,
        filename_extension=args.ext,
    )
    try:
        renamer.interactive_configuration(args.given)
        if not args.auto and not _confirm_files(renamer.collect_files_to_rename()):
            print("Nothing renamed.")
            return
        renamed_count, failed_count, failed_files = await renamer.rename_files(args.parallel)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)
    print("\n--- Renaming Operation Summary ---")
    print(f"Total files processed: {renamed_count + failed_count}")
    print(f"Successfully renamed: {renamed_count}")
    print(f"Failed to rename: {failed_count}")
    if failed_files:
        print("\nFiles that failed to rename:")
        for file, error in failed_files:
            print(f"  - {file}: {error}")


def run(argv: list[str] | None = None) -> None:
    try:
        asyncio.run(_main(argv))
    except KeyboardInterrupt:
        print("\nOperation interrupted by user.")


if __name__ == "__main__":
    run()
