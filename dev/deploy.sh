#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SwiftGet Dev Deploy Script
# Usage: bash dev/deploy.sh
# 빌드 → DMG → 설치 → 앱 재시작까지 자동화
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info() { echo -e "${CYAN}>>  $*${NC}"; }
ok()   { echo -e "${GREEN}OK  $*${NC}"; }
err()  { echo -e "${RED}!!  $*${NC}"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DMG_PATH="$SCRIPT_DIR/dist/SwiftGet.dmg"
MOUNT_POINT="/Volumes/SwiftGet"
APP_DEST="/Applications/SwiftGet.app"

echo ""
echo "  SwiftGet Dev Deploy"
echo ""

# ── Fresh install 옵션 ────────────────────────────────────────────────────────
# 첫 설치 상태 테스트 시 config.json 제거
# ex) bash dev/deploy.sh --fresh
if [[ "${1:-}" == "--fresh" ]]; then
    info "config.json 제거 (첫 설치 상태로 초기화)..."
    rm -f ~/Library/Application\ Support/SwiftGet/config.json
    ok "config.json 제거 완료"
fi

# ── Step 1: 빌드 ─────────────────────────────────────────────────────────────


# ── Step 1: 빌드 ─────────────────────────────────────────────────────────────
info "빌드 시작..."
bash "$SCRIPT_DIR/installer/install.sh"
[ -f "$DMG_PATH" ] || err "DMG 생성 실패: $DMG_PATH"
ok "빌드 완료"

# ── Step 2: 기존 앱 종료 ─────────────────────────────────────────────────────
info "기존 SwiftGet 종료 중..."
pkill -f "SwiftGet.app" 2>/dev/null || true
pkill -f "swiftget.py"  2>/dev/null || true
sleep 1
ok "종료 완료"

# ── Step 3: DMG 마운트 ────────────────────────────────────────────────────────
info "DMG 마운트 중..."
# 이미 마운트된 경우 언마운트
if [ -d "$MOUNT_POINT" ]; then
  hdiutil detach "$MOUNT_POINT" -quiet 2>/dev/null || true
  sleep 0.5
fi
hdiutil attach "$DMG_PATH" -mountpoint "$MOUNT_POINT" -quiet
ok "마운트 완료: $MOUNT_POINT"

# ── Step 4: 앱 교체 ──────────────────────────────────────────────────────────
info "/Applications 에 설치 중..."
rm -rf "$APP_DEST"
cp -R "$MOUNT_POINT/SwiftGet.app" "$APP_DEST"
ok "설치 완료: $APP_DEST"

# ── Step 5: DMG 언마운트 ─────────────────────────────────────────────────────
info "DMG 언마운트 중..."
hdiutil detach "$MOUNT_POINT" -quiet
ok "언마운트 완료"

# ── Step 6: 앱 실행 ──────────────────────────────────────────────────────────
info "SwiftGet 실행 중..."
open "$APP_DEST"
sleep 2

# ── Step 7: 매니페스트 올바른 경로로 등록 ────────────────────────────────────
info "Native Messaging 매니페스트 등록 중..."
MANIFEST_DIR="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
mkdir -p "$MANIFEST_DIR"
cat > "$MANIFEST_DIR/app.swiftget.downloader.json" << MANIFESTEOF
{
  "name": "app.swiftget.downloader",
  "description": "SwiftGet Download Manager Native Host",
  "path": "/Applications/SwiftGet.app/Contents/MacOS/swiftget-host",
  "type": "stdio",
  "allowed_extensions": [
    "swiftget@downloader.app"
  ]
}
MANIFESTEOF
ok "매니페스트 등록 완료"

echo ""
echo "  배포 완료!"
echo "  Firefox에서 우클릭으로 테스트해 보세요."
echo ""