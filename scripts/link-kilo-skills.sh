#!/usr/bin/env bash
set -euo pipefail

# Link Matt Pocock skills into Kilo Code's global config directory.
#
# Default behavior:
#   - Links published skills from engineering/, productivity/, and misc/
#   - Includes stable vLLM-DLC engineering skills such as model-adaptation and main-to-main-upgrade by bucket membership, not --all
#   - Writes symlinks to ~/.config/kilo/skills/<skill-name>
#   - Skips existing real directories/files instead of deleting them
#   - Optionally writes thin slash-command wrappers to ~/.config/kilo/command/
#
# Usage:
#   scripts/link-kilo-skills.sh
#   scripts/link-kilo-skills.sh --with-commands
#   scripts/link-kilo-skills.sh --project /path/to/project --with-commands
#   scripts/link-kilo-skills.sh --all
#   scripts/link-kilo-skills.sh --dest /custom/kilo/config/skills

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_ROOT="$REPO/skills"

DEST="$HOME/.config/kilo/skills"
COMMAND_DEST="$HOME/.config/kilo/command"
WITH_COMMANDS=0
INCLUDE_ALL=0
PROJECT_INSTALL=0
RETIRED=(diagnose to-prd to-issues write-a-skill review)
WRAPPER_MARKER="kilo-generated-wrapper: mattpocock-skills/link-kilo-skills.sh/v2"
PROJECT_SKILL_MARKER=".kilo-link-source"

usage() {
  cat <<'USAGE'
Link Matt Pocock skills into Kilo Code.

Options:
  --with-commands       Also create slash-command wrappers in command/.
  --project <path>      Install into <path>/.kilo instead of ~/.config/kilo.
  --dest <path>         Custom skills destination directory.
  --command-dest <path> Custom command destination directory.
  --all                 Include personal/ and in-progress/ skills too.
  -h, --help            Show this help.

Examples:
  scripts/link-kilo-skills.sh
  scripts/link-kilo-skills.sh --with-commands
  scripts/link-kilo-skills.sh --project /work/my-app --with-commands
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --with-commands)
      WITH_COMMANDS=1
      shift
      ;;
    --project)
      if [ "$#" -lt 2 ]; then
        echo "error: --project requires a path" >&2
        exit 1
      fi
      PROJECT_PATH="$2"
      DEST="$PROJECT_PATH/.kilo/skills"
      COMMAND_DEST="$PROJECT_PATH/.kilo/command"
      PROJECT_INSTALL=1
      shift 2
      ;;
    --dest)
      if [ "$#" -lt 2 ]; then
        echo "error: --dest requires a path" >&2
        exit 1
      fi
      DEST="$2"
      shift 2
      ;;
    --command-dest)
      if [ "$#" -lt 2 ]; then
        echo "error: --command-dest requires a path" >&2
        exit 1
      fi
      COMMAND_DEST="$2"
      shift 2
      ;;
    --all)
      INCLUDE_ALL=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

is_selected_skill() {
  local skill_md="$1"

  case "$skill_md" in
    */deprecated/*)
      return 1
      ;;
  esac

  if [ "$INCLUDE_ALL" -eq 1 ]; then
    return 0
  fi

  case "$skill_md" in
    "$SKILLS_ROOT"/engineering/*/SKILL.md|"$SKILLS_ROOT"/productivity/*/SKILL.md|"$SKILLS_ROOT"/misc/*/SKILL.md)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

read_skill_description() {
  local skill_md="$1"
  awk '
    BEGIN { in_frontmatter = 0 }
    NR == 1 && $0 == "---" { in_frontmatter = 1; next }
    in_frontmatter && $0 == "---" { exit }
    in_frontmatter && /^description:/ {
      sub(/^description:[[:space:]]*/, "")
      print
      exit
    }
  ' "$skill_md"
}

old_command_wrapper() {
  local name="$1"
  local description="$2"
  cat <<EOF
---
description: $description
---

请使用 \`$name\` skill，严格按它的流程处理下面的问题：

\$ARGUMENTS
EOF
}

new_command_wrapper() {
  local name="$1"
  local description="$2"
  cat <<EOF
---
description: $description
---

<!-- $WRAPPER_MARKER -->

请使用 \`$name\` skill，严格按它的流程处理下面的问题：

\$ARGUMENTS
EOF
}

fail_if_symlink_path() {
  local path="$1"
  local root="$2"
  local current="$root"
  local relative

  relative="${path#$root/}"
  if [ "$relative" = "$path" ]; then
    echo "error: destination escapes selected config root: $path" >&2
    return 1
  fi
  IFS='/' read -r -a parts <<< "$relative"
  for part in "${parts[@]}"; do
    current="$current/$part"
    if [ -L "$current" ]; then
      echo "error: refusing symlinked destination path: $current" >&2
      return 1
    fi
  done
}

ensure_directory_chain() {
  local directory="$1"
  local root="$2"
  local parent

  if [ "$directory" = "$root" ]; then
    if [ -L "$directory" ]; then
      echo "error: refusing symlinked config root: $directory" >&2
      return 1
    fi
    mkdir -p "$directory"
    return 0
  fi
  parent="$(dirname "$directory")"
  if [ "$parent" != "$directory" ] && [ ! -e "$parent" ]; then
    ensure_directory_chain "$parent" "$root"
  fi
  fail_if_symlink_path "$directory" "$root"
  if [ -e "$directory" ] && [ ! -d "$directory" ]; then
    echo "error: destination is not a directory: $directory" >&2
    return 1
  fi
  mkdir -p "$directory"
}

write_command_wrapper() {
  local name="$1"
  local skill_md="$2"
  local command_file="$COMMAND_DEST/$name.md"
  local description

  description="$(read_skill_description "$skill_md")"
  if [ -z "$description" ]; then
    description="Use Matt Pocock $name skill"
  fi

  local next
  local legacy
  next="$(new_command_wrapper "$name" "$description")"
  legacy="$(old_command_wrapper "$name" "$description")"

  if [ -L "$command_file" ]; then
    echo "skip command $name: $command_file is a symlink"
    return 0
  fi

  if [ -e "$command_file" ]; then
    python3 - "$command_file" "$next" "$legacy" "$WRAPPER_MARKER" <<'PY'
import os, sys
path, new, legacy, marker = sys.argv[1:]
fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
try:
    current = os.read(fd, 1024 * 1024).decode("utf-8")
    if marker not in current and current != legacy:
        print(f"preserve command: {path} already exists", file=sys.stderr)
        raise SystemExit(3)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, new.encode("utf-8"))
    os.ftruncate(fd, len(new.encode("utf-8")))
    os.fsync(fd)
finally:
    os.close(fd)
PY
    case "$?" in
      0) ;;
      3) return 0 ;;
      *) return 1 ;;
    esac
  else
    python3 - "$command_file" "$next" <<'PY'
import os, sys
path, payload = sys.argv[1:]
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
try:
    os.write(fd, payload.encode("utf-8"))
    os.fsync(fd)
finally:
    os.close(fd)
PY
  fi

  echo "command $name -> $command_file"
}

install_project_skill_directory() {
  local name="$1"
  local src="$2"
  local target="$3"
  local marker="$target/$PROJECT_SKILL_MARKER"
  local tmp

  if [ -e "$target" ] && [ ! -L "$target" ]; then
    if [ -f "$marker" ] && [ "$(cat "$marker")" = "$src" ]; then
      tmp="$DEST/.$name.tmp.$$"
      rm -rf "$tmp"
      python3 - "$src" "$tmp" "$PROJECT_SKILL_MARKER" <<'PY'
import shutil, sys
from pathlib import Path

src = Path(sys.argv[1])
tmp = Path(sys.argv[2])
marker = sys.argv[3]
shutil.copytree(src, tmp, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
(tmp / marker).write_text(str(src) + "\n", encoding="utf-8")
PY
      rm -rf "$target"
      mv "$tmp" "$target"
      echo "refreshed $name -> $src"
      return 0
    fi
    echo "skip $name: $target already exists and is not a linker-owned directory"
    skipped_count=$((skipped_count + 1))
    return 2
  fi

  if [ -L "$target" ]; then
    current_target="$(readlink "$target")"
    old_target="$SKILLS_ROOT/in-progress/$name"
    if [ "$current_target" != "$src" ] && [ "$current_target" != "$old_target" ]; then
      echo "skip $name: $target is an unrelated symlink"
      skipped_count=$((skipped_count + 1))
      return 2
    fi
    rm "$target"
  fi

  tmp="$DEST/.$name.tmp.$$"
  rm -rf "$tmp"
  python3 - "$src" "$tmp" "$PROJECT_SKILL_MARKER" <<'PY'
import shutil, sys
from pathlib import Path

src = Path(sys.argv[1])
tmp = Path(sys.argv[2])
marker = sys.argv[3]
shutil.copytree(src, tmp, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
(tmp / marker).write_text(str(src) + "\n", encoding="utf-8")
PY
  mv "$tmp" "$target"
  echo "linked $name -> $src"
}

CONFIG_ROOT="$(dirname "$DEST")"
if [ -L "$CONFIG_ROOT" ]; then
  echo "error: refusing symlinked config root: $CONFIG_ROOT" >&2
  exit 1
fi
ensure_directory_chain "$DEST" "$CONFIG_ROOT"

if [ "$WITH_COMMANDS" -eq 1 ]; then
  case "$COMMAND_DEST" in
    "$CONFIG_ROOT"/*) ;;
    *)
      echo "error: command destination must be under selected config root" >&2
      exit 1
      ;;
  esac
  ensure_directory_chain "$COMMAND_DEST" "$CONFIG_ROOT"
fi

for name in "${RETIRED[@]}"; do
  skill_target="$DEST/$name"
  if [ -L "$skill_target" ]; then
    rm "$skill_target"
    echo "removed stale skill symlink $skill_target"
  fi

  if [ "$WITH_COMMANDS" -eq 1 ]; then
    command_target="$COMMAND_DEST/$name.md"
    if [ -f "$command_target" ] && grep -Fq "请使用 \`$name\` skill，严格按它的流程处理下面的问题：" "$command_target"; then
      rm "$command_target"
      echo "removed stale generated command $command_target"
    fi
  fi
done

linked_count=0
skipped_count=0
command_count=0

while IFS= read -r -d '' skill_md; do
  if ! is_selected_skill "$skill_md"; then
    continue
  fi

  src="$(dirname "$skill_md")"
  name="$(basename "$src")"
  target="$DEST/$name"

  if [ "$PROJECT_INSTALL" -eq 1 ]; then
    if ! install_project_skill_directory "$name" "$src" "$target"; then
      continue
    fi
  else
    if [ -e "$target" ] && [ ! -L "$target" ]; then
      echo "skip $name: $target already exists and is not a symlink"
      skipped_count=$((skipped_count + 1))
      continue
    fi

    if [ -L "$target" ]; then
      current_target="$(readlink "$target")"
      old_target="$SKILLS_ROOT/in-progress/$name"
      if [ "$current_target" = "$src" ]; then
        echo "linked $name -> $src"
      elif [ "$current_target" = "$old_target" ]; then
        rm "$target"
        ln -s "$src" "$target"
        echo "migrated $name -> $src"
      else
        echo "skip $name: $target is an unrelated symlink"
        skipped_count=$((skipped_count + 1))
        continue
      fi
    else
      ln -s "$src" "$target"
      echo "linked $name -> $src"
    fi
  fi
  linked_count=$((linked_count + 1))

  if [ "$WITH_COMMANDS" -eq 1 ]; then
    write_command_wrapper "$name" "$skill_md"
    command_count=$((command_count + 1))
  fi
done < <(find "$SKILLS_ROOT" -name SKILL.md -not -path '*/node_modules/*' -print0 | sort -z)

echo
echo "Kilo skills destination: $DEST"
echo "Linked skills: $linked_count"
echo "Skipped existing non-symlinks: $skipped_count"

if [ "$WITH_COMMANDS" -eq 1 ]; then
  echo "Kilo command destination: $COMMAND_DEST"
  echo "Command wrappers written: $command_count"
fi

echo
echo "Restart Kilo Code or open a new session if the skills do not appear immediately."
