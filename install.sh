#!/bin/sh
# ollama-rename installer for macOS / Linux.
#   curl -LsSf https://raw.githubusercontent.com/octrow/ollama-rename-files/main/install.sh | sh
#   ... | sh -s -- --version 0.1.0   # a specific release instead of the latest one
#   ... | sh -s -- --main            # current main branch instead of a release
#   ... | sh -s -- --no-launch       # install only, do not offer to start it
#   ... | sh -s -- --uninstall       # remove the app, keep its data
# Re-running it updates. INSTALL_SOURCE=<path or uv spec> installs from there instead (CI, local testing).
set -eu

REPO="octrow/ollama-rename-files"
NAME="ollama-rename-files"      # distribution name from pyproject.toml [project] name
CMD="ollama-rename"       # the command from [project.scripts]
PYTHON="3.12"   # pinned so binary wheels of the dependencies exist; bump when they ship for newer Pythons
VERSION=""
MAIN=0
LAUNCH=1
UNINSTALL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --version) [ $# -ge 2 ] || { echo "Add a version number: --version 0.1.0" >&2; exit 2; }
               VERSION="${2#v}"; shift ;;
    --main) MAIN=1 ;;
    --no-launch) LAUNCH=0 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) echo "options: --version X.Y.Z | --main | --no-launch | --uninstall"; exit 0 ;;
    *) echo "Unknown option: $1. See: --help" >&2; exit 2 ;;
  esac
  shift
done

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }
# curl | sh takes stdin from the pipe, so interactive steps read the terminal directly
has_tty() { (: </dev/tty) 2>/dev/null; }

export PATH="$HOME/.local/bin:$PATH"

if [ "$UNINSTALL" = 1 ]; then
  if have uv; then uv tool uninstall "$NAME" || true; fi
  say "$CMD is removed."
  exit 0
fi

# 1. uv: installs Python and the app into an isolated environment, no system Python or sudo needed
if ! have uv; then
  say "Installing uv (it installs Python and $CMD)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  have uv || die "uv is installed, but this terminal does not see it. Open a new terminal and run this command again."
fi

# Ollama runs the model; it's a separate app, so point at it rather than install it
if ! have ollama; then
  warn "Ollama is not installed. $CMD needs it to name files: https://ollama.com/download"
fi

# 2. the app: the release wheel built and tested by CI, or the main branch
if [ -n "${INSTALL_SOURCE:-}" ]; then
  SPEC="$INSTALL_SOURCE"
elif [ "$MAIN" = 1 ]; then
  SPEC="$NAME @ https://github.com/$REPO/archive/refs/heads/main.tar.gz"
else
  if [ -z "$VERSION" ]; then
    # /releases/latest redirects to /releases/tag/vX.Y.Z; with no release yet it lands on /releases
    URL="$(curl -fsSLo /dev/null -w '%{url_effective}' "https://github.com/$REPO/releases/latest")" \
      || die "GitHub is not reachable. Check your internet connection and run this command again."
    case "$URL" in */tag/v*) VERSION="${URL##*/tag/v}" ;; *) die "No release yet. Run this command again with --main." ;; esac
  fi
  WHEEL="$(printf %s "$NAME" | tr '-' '_')-$VERSION-py3-none-any.whl"
  SPEC="$NAME @ https://github.com/$REPO/releases/download/v$VERSION/$WHEEL"
fi
say "Installing $CMD${VERSION:+ $VERSION}"
uv tool install --reinstall --python "$PYTHON" "$SPEC"
uv tool update-shell >/dev/null 2>&1 || true
BIN="$(uv tool dir --bin)/$CMD"

say "$CMD is installed. Desktop window: $CMD gui   Command line: $CMD --help"
note "No model yet? Pull a small one: ollama pull qwen2.5-coder:7b"
note "Command not found? Open a new terminal or run: $BIN"

if [ "$LAUNCH" = 1 ] && has_tty; then
  printf 'Open the %s window now? [Y/n] ' "$CMD"
  read -r answer </dev/tty || answer=n
  case "$answer" in [nN]*) ;; *) exec "$BIN" gui ;; esac
fi
