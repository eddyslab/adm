#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# SwiftGet Dev Runner
# Usage: bash dev/run.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE_APP_DIR="$SCRIPT_DIR/native-app"
MANIFEST_DIR="$HOME/Library/Application Support/Mozilla/NativeMessagingHosts"
MANIFEST_PATH="$MANIFEST_DIR/app.swiftget.downloader.json"
MANIFEST_BAK="$MANIFEST_DIR/app.swiftget.downloader.json.bak"

# 의존성 확인
if ! python3 -c "import wx" &>/dev/null; then
  echo "wxPython 이 설치되어 있지 않습니다."
  echo "  pip3 install wxPython"
  exit 1
fi

# 이전 인스턴스 종료
pkill -f "SwiftGet.app" 2>/dev/null || true
pkill -f "swiftget.py"  2>/dev/null || true
sleep 0.5

# 잔여 소켓 파일 삭제
SOCK_PATH="$HOME/Library/Application Support/SwiftGet/swiftget.sock"
if [ -S "$SOCK_PATH" ]; then
  rm -f "$SOCK_PATH"
  echo ">> 잔여 소켓 파일 삭제 완료"
fi

# Native Messaging 매니페스트를 개발 경로로 임시 교체
mkdir -p "$MANIFEST_DIR"

# 기존 매니페스트 백업
if [ -f "$MANIFEST_PATH" ]; then
  cp "$MANIFEST_PATH" "$MANIFEST_BAK"
fi

# 래퍼 스크립트를 절대 경로로 동적 생성
WRAPPER="$NATIVE_APP_DIR/swiftget-host"
PYTHON3="$(which python3)"
cat > "$WRAPPER" << WRAPEOF
#!/bin/bash
exec "$PYTHON3" "$NATIVE_APP_DIR/swiftget-host.py" "\$@"
WRAPEOF
chmod +x "$WRAPPER"

# 개발용 매니페스트 생성
cat > "$MANIFEST_PATH" << MANIFEST
{
  "name": "app.swiftget.downloader",
  "description": "SwiftGet Download Manager Native Host",
  "path": "$WRAPPER",
  "type": "stdio",
  "allowed_extensions": ["swiftget@downloader.app"]
}
MANIFEST

echo ">> Native Messaging 매니페스트: 개발 경로로 전환"
echo "   $WRAPPER"

# 종료 시 매니페스트 복원
cleanup() {
  echo ""
  echo ">> Native Messaging 매니페스트: 원래 경로로 복원"
  if [ -f "$MANIFEST_BAK" ]; then
    mv "$MANIFEST_BAK" "$MANIFEST_PATH"
  else
    rm -f "$MANIFEST_PATH"
  fi
}
trap cleanup EXIT

echo ">> SwiftGet 실행 중... (개발 모드: 창 닫기 = 완전 종료)"
cd "$NATIVE_APP_DIR"
python3 swiftget.py --dev