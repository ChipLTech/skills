#!/usr/bin/env bash
set -euo pipefail

# Link Matt Pocock skills into Kilo Code's global config directory.
#
# Default behavior:
#   - Links published skills from engineering/, productivity/, and misc/
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

write_command_wrapper() {
  local name="$1"
  local skill_md="$2"
  local command_file="$COMMAND_DEST/$name.md"
  local description

  description="$(read_skill_description "$skill_md")"
  if [ -z "$description" ]; then
    description="Use Matt Pocock $name skill"
  fi

  if [ -e "$command_file" ] && [ ! -L "$command_file" ]; then
    echo "skip command $name: $command_file already exists"
    return 0
  fi

  cat > "$command_file" <<EOF
---
description: $description
---

请使用 \`$name\` skill，严格按它的流程处理下面的问题：

\$ARGUMENTS
EOF

  echo "command $name -> $command_file"
}

mkdir -p "$DEST"

if [ "$WITH_COMMANDS" -eq 1 ]; then
  mkdir -p "$COMMAND_DEST"
fi

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

  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "skip $name: $target already exists and is not a symlink"
    skipped_count=$((skipped_count + 1))
    continue
  fi

  ln -sfn "$src" "$target"
  echo "linked $name -> $src"
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
