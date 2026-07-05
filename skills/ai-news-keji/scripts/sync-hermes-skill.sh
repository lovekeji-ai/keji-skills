#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${AI_NEWS_KEJI_REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
HERMES_DIR="${AI_NEWS_KEJI_HERMES_DIR:-${HOME}/.hermes/skills/research/ai-news-keji}"
BACKUP_ROOT="${AI_NEWS_KEJI_BACKUP_ROOT:-$(dirname "$HERMES_DIR")/_backups}"
STAMP="$(date '+%Y%m%d-%H%M%S')"
BACKUP_DIR="$BACKUP_ROOT/ai-news-keji-$STAMP"

SHARED_ITEMS=(
  "SKILL.md"
  "README.md"
  "README.en.md"
  "LICENSE"
  ".gitignore"
  "requirements.txt"
  "config.example.yaml"
  "sources.example.yaml"
  "agents"
  "prompts"
  "references"
  "scripts"
)

LOCAL_ITEMS=(
  "config.yaml"
  "sources.yaml"
  ".venv"
  ".git"
)

item_exists() {
  [[ -e "$1" || -L "$1" ]]
}

copy_item_if_exists() {
  local source="$1"
  local target_dir="$2"
  if item_exists "$source"; then
    cp -a "$source" "$target_dir/" 2>/dev/null || true
  fi
}

mkdir -p "$BACKUP_ROOT"
mkdir -p "$BACKUP_DIR"

if [[ -e "$HERMES_DIR" && ! -d "$HERMES_DIR" && ! -L "$HERMES_DIR" ]]; then
  printf 'Error: Hermes path exists but is not a directory or symlink: %s\n' "$HERMES_DIR" >&2
  exit 1
fi

if [[ -L "$HERMES_DIR" ]]; then
  printf '%s\n' "$(readlink "$HERMES_DIR")" > "$BACKUP_DIR/hermes-dir-symlink-target.txt"
  for item in "${LOCAL_ITEMS[@]}"; do
    if [[ "$item" == ".git" ]]; then
      continue
    fi
    copy_item_if_exists "$HERMES_DIR/$item" "$BACKUP_DIR"
  done
  rm "$HERMES_DIR"
  mkdir -p "$HERMES_DIR"
  for item in "${LOCAL_ITEMS[@]}"; do
    if [[ "$item" == ".git" ]]; then
      continue
    fi
    copy_item_if_exists "$BACKUP_DIR/$item" "$HERMES_DIR"
  done
else
  mkdir -p "$HERMES_DIR"
  for item in "${SHARED_ITEMS[@]}" "${LOCAL_ITEMS[@]}"; do
    copy_item_if_exists "$HERMES_DIR/$item" "$BACKUP_DIR"
  done
fi

for item in "${SHARED_ITEMS[@]}"; do
  if ! item_exists "$REPO_DIR/$item"; then
    printf 'Error: shared item missing from repo: %s\n' "$REPO_DIR/$item" >&2
    exit 1
  fi
done

for item in "${SHARED_ITEMS[@]}"; do
  rm -rf "$HERMES_DIR/$item"
  ln -s "$REPO_DIR/$item" "$HERMES_DIR/$item"
done

printf 'Synced shared items from repo to Hermes skill.\n'
printf 'Repo: %s\nHermes: %s\nBackup: %s\n' "$REPO_DIR" "$HERMES_DIR" "$BACKUP_DIR"
printf '\nShared symlinks:\n'
for item in "${SHARED_ITEMS[@]}"; do
  printf '  %s -> %s\n' "$item" "$(readlink "$HERMES_DIR/$item")"
done

printf '\nLocal-only items kept in Hermes:\n'
for item in "${LOCAL_ITEMS[@]}"; do
  if [[ -e "$HERMES_DIR/$item" || -L "$HERMES_DIR/$item" ]]; then
    printf '  %s\n' "$item"
  fi
done
