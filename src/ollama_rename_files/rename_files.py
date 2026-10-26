import argparse
import asyncio
import codecs
import logging
import re
import shutil
import sys
import textwrap
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path

from ollama import AsyncClient, Client
from pypdf import PdfReader

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_CONTEXT_LENGTH = 2048
DEFAULT_PREFIX = "new"
DEFAULT_EXTENSION = ".txt"
MAX_FILE_NAME_LENGTH = 128
TOP_PATTERNS = 5

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


def clean_model_response(text: str) -> str:
    """Extract the bare file name from a model reply (drops <think> blocks, fences, extra lines)."""
    text = re.sub(r"<think>.*?(</think>|$)", "", text, flags=re.DOTALL)
    lines = [line.strip() for line in text.splitlines()]
    # drop fence lines before stripping backticks, or "```md" leaves "md" behind
    lines = [line.strip("`*\"'") for line in lines if not line.startswith("```")]
    lines = [line for line in lines if line]
    return lines[0].lower() if lines else ""


def sanitize_filename(suggested_name: str, original_ext: str, max_len: int = MAX_FILE_NAME_LENGTH) -> str:
    name = re.sub(r"\.\w+$", "", suggested_name)
    name = re.sub(r"[.`',;]", "", name)
    name = re.sub(r'[<>/\\|?*:"+%!@]', "_", name)
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = re.sub(r"^[^a-zA-Z]+", "", name)
    name = name[:max_len - len(original_ext)]
    name = re.sub(r"[^a-zA-Z0-9]+$", "", name)
    if not name:
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
    return codecs.getincrementaldecoder("utf-8")().decode(data)[:limit]


def list_ollama_models() -> list[str]:
    try:
        return [m.model for m in Client().list().models]
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
        # serialize backup+rename so parallel workers can't pick the same free name
        self._rename_lock = asyncio.Lock()

    def create_backup_directory(self) -> Path:
        backup_dir = unique_path(self.base_dir / f"backup_{datetime.now():%Y%m%d_%H%M%S}")
        backup_dir.mkdir(parents=True)
        return backup_dir

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
        prefix = input('Enter file prefix: ').strip()
        ext = input('Enter file extension (with dot): ').strip().lower()
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

    def _get_model_max_context(self, model_name: str) -> int:
        try:
            modelinfo = Client().show(model_name).modelinfo or {}
            for key, value in modelinfo.items():
                if key.endswith(".context_length"):
                    return int(value)
            logger.warning(f"Could not determine context length for {model_name} (key not found)")
        except Exception as e:  # noqa: BLE001 - best effort, default is fine
            logger.warning(f"Could not retrieve model info: {e}")
        return DEFAULT_CONTEXT_LENGTH

    def interactive_configuration(self) -> None:
        if self.auto_mode:
            return
        self.base_dir = self._interactive_directory_selection()
        self.filename_prefix, self.filename_extension = self._interactive_file_pattern_selection(
            self.discover_file_patterns())
        self.model_name = self._interactive_model_selection(list_ollama_models())
        self.context_length = self._interactive_context_selection(self._get_model_max_context(self.model_name))
        self._print_summary()

    @staticmethod
    def _interactive_context_selection(max_context: int) -> int:
        while True:
            choice = input(
                f"\nModel max context: {max_context}. Enter characters to read per file, "
                f"`500` will work (or press Enter for max): ").strip()
            if not choice:
                return max_context
            if choice.isdigit() and 0 < int(choice) <= max_context:
                return int(choice)
            print(f"Invalid context length. Please enter a number between 1 and {max_context}.")

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
            options={"num_predict": self.max_file_name_length},
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
            return False, str(e)

        new_filename = sanitize_filename(suggested_name, file_path.suffix, self.max_file_name_length)
        async with self._rename_lock:
            return self._backup_and_rename(file_path, new_filename)

    def _backup_and_rename(self, file_path: Path, new_filename: str) -> tuple[bool, str]:
        """Copy to backup_dir, then rename to a free name. Never overwrites."""
        try:
            shutil.copy2(file_path, unique_path(self.backup_dir / file_path.name))
            new_file_path = unique_path(self.base_dir / new_filename)
            file_path.rename(new_file_path)
        except OSError as e:
            logger.error(f"Backup/rename failed for {file_path.name}: {e}")
            return False, str(e)
        logger.info(f"Renamed: {file_path.name} -> {new_file_path.name}")
        return True, new_file_path.name

    def collect_files_to_rename(self) -> list[Path]:
        if not self.base_dir or not self.base_dir.is_dir():
            raise ValueError(f"Invalid directory: {self.base_dir}")
        ext = self.filename_extension.lower()
        return sorted(
            p for p in self.base_dir.iterdir()
            if p.is_file() and p.name.startswith(self.filename_prefix) and p.name.lower().endswith(ext)
        )

    async def rename_files(self, parallel_count: int = 0) -> tuple[int, int, FailedFiles]:
        files_to_rename = self.collect_files_to_rename()
        if not files_to_rename:
            logger.info("No files found to rename.")
            return 0, 0, []
        logger.info(f"Found {len(files_to_rename)} files to rename")
        if self.backup_dir is None:
            self.backup_dir = self.create_backup_directory()

        client = AsyncClient()
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
        failed_files = [(p.name, msg) for p, (ok, msg) in zip(files_to_rename, results, strict=True) if not ok]
        return len(results) - len(failed_files), len(failed_files), failed_files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename files by their content with a local Ollama model.",
        epilog="Run `ollama-rename gui` for the desktop window.",
    )
    parser.add_argument("-a", "--auto", action="store_true",
                        help="Run in auto mode without interactive prompts (requires -d)")
    parser.add_argument("-d", "--directory", help="Specify directory non-interactively")
    parser.add_argument('-m', '--model', default=DEFAULT_MODEL, help='Specify the Ollama model')
    parser.add_argument('-c', '--context', type=int, default=DEFAULT_CONTEXT_LENGTH,
                        help='Characters of each file to send to the model')
    parser.add_argument('--prefix', default=DEFAULT_PREFIX, help="Specify the file prefix")
    parser.add_argument('--ext', default=DEFAULT_EXTENSION, help="Specify the file extension")
    parser.add_argument('-p', '--parallel', type=int, default=0,
                        help='Number of parallel rename operations (default: sequential)')
    args = parser.parse_args(argv)
    if args.auto and not args.directory:
        parser.error("--auto requires --directory")
    return args


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
    renamer.interactive_configuration()
    try:
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
