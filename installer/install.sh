#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SwiftGet Installer for macOS
# Usage: bash install.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${CYAN}▶  $*${NC}"; }
ok()    { echo -e "${GREEN}✓  $*${NC}"; }
err()   { echo -e "${RED}✗  $*${NC}"; exit 1; }

# SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NATIVE_APP_DIR="$SCRIPT_DIR/native-app"
ADDON_DIR="$SCRIPT_DIR/addon"
APP_SUPPORT="$HOME/Library/Application Support/SwiftGet"
LOG_DIR="$HOME/Library/Logs/SwiftGet"

# Native Messaging host manifest location for Firefox
NATIVE_MSG_DIR="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║     SwiftGet Installer v1.0      ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── Step 1: Check Python 3 ──────────────────────────────────────────────────
info "Python 3 확인 중..."
if ! command -v python3 &>/dev/null; then
  err "Python 3가 필요합니다. https://python.org 에서 설치하세요."
fi
PY_VER=$(python3 --version 2>&1 | cut -d' ' -f2)
ok "Python $PY_VER 발견"

# ── Step 2: Install Python dependencies ─────────────────────────────────────
info "Python 패키지 설치 중..."
pip3 install --quiet rumps py2app
ok "패키지 설치 완료"

# ── Step 3: Create directories ───────────────────────────────────────────────
info "디렉토리 생성 중..."
mkdir -p "$APP_SUPPORT" "$LOG_DIR" "$NATIVE_MSG_DIR"
ok "디렉토리 생성 완료"

# ── Step 4: Build .app bundle ────────────────────────────────────────────────
info "SwiftGet.app 빌드 중 (시간이 걸릴 수 있습니다)..."
cd "$NATIVE_APP_DIR"
python3 setup.py py2app --quiet 2>&1 | tail -5
APP_PATH="$NATIVE_APP_DIR/dist/SwiftGet.app"
if [ ! -d "$APP_PATH" ]; then
  err ".app 빌드 실패. 로그를 확인하세요."
fi
ok "SwiftGet.app 빌드 완료"

# ── Step 5: Copy .app to /Applications ──────────────────────────────────────
info "/Applications 에 설치 중..."
rm -rf "/Applications/SwiftGet.app"
cp -R "$APP_PATH" "/Applications/SwiftGet.app"
ok "설치 완료: /Applications/SwiftGet.app"

# ── Step 6: Create native host wrapper script ────────────────────────────────
HOST_SCRIPT="/Applications/SwiftGet.app/Contents/MacOS/swiftget-host"
info "Native Messaging 호스트 스크립트 생성 중..."
cat > "$HOST_SCRIPT" << 'HOSTEOF'
#!/usr/bin/env python3
# Auto-generated native messaging host wrapper
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Resources', 'lib', 'python3.x', 'site-packages'))
# Locate and run the host script
host = os.path.join(os.path.dirname(__file__), '..', 'Resources', 'swiftget-host.py')
exec(open(host).read())
HOSTEOF
chmod +x "$HOST_SCRIPT"

# Copy host script into .app bundle
cp "$NATIVE_APP_DIR/swiftget-host.py" \
   "/Applications/SwiftGet.app/Contents/Resources/swiftget-host.py"
ok "Native Messaging 호스트 설치 완료"

# ── Step 7: Register Native Messaging manifest ───────────────────────────────
info "Firefox Native Messaging 매니페스트 등록 중..."
cat > "$NATIVE_MSG_DIR/app.swiftget.downloader.json" << EOF
{
  "name": "app.swiftget.downloader",
  "description": "SwiftGet Download Manager Native Host",
  "path": "/Applications/SwiftGet.app/Contents/MacOS/swiftget-host",
  "type": "stdio",
  "allowed_extensions": ["swiftget@downloader.app"]
}
EOF
ok "매니페스트 등록: $NATIVE_MSG_DIR/app.swiftget.downloader.json"

# ── Step 8: Package Firefox addon as .xpi ───────────────────────────────────
info "Firefox 애드온 패키징 중..."
XPI_PATH="$SCRIPT_DIR/swiftget.xpi"
cd "$ADDON_DIR"
zip -r "$XPI_PATH" . -x "*.DS_Store" -x "__MACOSX/*" > /dev/null
ok "애드온 패키징 완료: $XPI_PATH"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  설치 완료! 다음 단계를 진행하세요:${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  1. SwiftGet.app 을 처음 한 번 실행하세요:"
echo "     open /Applications/SwiftGet.app"
echo ""
echo "  2. Firefox 에서 애드온을 설치하세요:"
echo "     about:addons → 톱니바퀴 → 파일에서 부가 기능 설치"
echo "     파일 선택: $XPI_PATH"
echo ""
echo "  3. (선택) macOS 보안 설정에서 앱 허용:"
echo "     시스템 설정 → 개인정보 보호 및 보안 → 허용"
echo ""
