#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SwiftGet Dev Cleanup Script
# Usage: bash dev/cleanup.sh
# - Removes build artifacts and temp files from git tracking
# - Safe to run multiple times
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'
info() { echo -e "${CYAN}>>  $*${NC}"; }
ok()   { echo -e "${GREEN}OK  $*${NC}"; }
warn() { echo -e "${YELLOW}--  $*${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  SwiftGet Dev Cleanup"
echo ""

# ── 1. 빌드 산출물 git 추적 해제 ─────────────────────────────────────────────
info "Removing build artifacts from git tracking..."

GIT_RM_TARGETS=(
    "native-app/build"
    "native-app/dist"
    "dist"
)

for target in "${GIT_RM_TARGETS[@]}"; do
    if git ls-files --error-unmatch "$target" &>/dev/null 2>&1; then
        git rm -r --cached "$target"
        ok "Untracked: $target"
    else
        warn "Already untracked: $target"
    fi
done

# ── 2. 임시/백업 파일 git 추적 해제 ──────────────────────────────────────────
info "Removing temp and backup files from git tracking..."

TEMP_FILES=(
    "swiftget.xpi"
    "tree.bak"
    "native-app/swiftget.py.bak"
    "native-app/swiftget.py.bak2"
    "native-app/swiftget.py.orig"
    "native-app/setup.py.bak"
    "addon/background.js.bak"
    "addon/manifest.json.bak"
)

for f in "${TEMP_FILES[@]}"; do
    if [ -f "$f" ] && git ls-files --error-unmatch "$f" &>/dev/null 2>&1; then
        git rm --cached "$f"
        ok "Untracked: $f"
    else
        warn "Already untracked or not found: $f"
    fi
done

# ── 3. 로컬 파일 삭제 (빌드 산출물) ──────────────────────────────────────────
info "Cleaning local build directories..."

LOCAL_CLEAN=(
    "native-app/build"
    "native-app/dist"
    "dist"
)

for target in "${LOCAL_CLEAN[@]}"; do
    if [ -e "$target" ]; then
        rm -rf "$target"
        ok "Deleted: $target"
    else
        warn "Not found: $target"
    fi
done

# ── 4. 백업/임시 파일 로컬 삭제 ──────────────────────────────────────────────
info "Cleaning local temp files..."

for f in "${TEMP_FILES[@]}"; do
    if [ -f "$f" ]; then
        rm -f "$f"
        ok "Deleted: $f"
    fi
done

# 혹시 남아있는 .bak, .orig 파일 정리
find . -name "*.bak" -o -name "*.bak2" -o -name "*.orig" | \
    grep -v ".git" | while read -r f; do
    rm -f "$f"
    ok "Deleted: $f"
done

# ── 5. 주요 설정 파일 스테이징 ───────────────────────────────────────────────
info "Staging config files..."

STAGE_FILES=(
    ".gitignore"
    "README.md"
    "dev/cleanup.sh"
)

for f in "${STAGE_FILES[@]}"; do
    if [ -f "$f" ]; then
        git add "$f"
        ok "Staged: $f"
    else
        warn "Not found: $f"
    fi
done

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "  Cleanup complete. Review changes and commit:"
echo ""
echo "    git status"
echo "    git commit -m \"chore: clean up build artifacts\""
echo "    git push"
echo ""