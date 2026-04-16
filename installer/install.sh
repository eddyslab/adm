#!/usr/bin/env bash
# SwiftGet DMG Builder
# Usage: bash installer/install.sh

set -euo pipefail

CYAN='\033[0;36m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${CYAN}>>  $*${NC}"; }
ok()    { echo -e "${GREEN}OK  $*${NC}"; }
err()   { echo -e "${RED}!!  $*${NC}"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE_APP_DIR="$SCRIPT_DIR/native-app"
ADDON_DIR="$SCRIPT_DIR/addon"
DIST_DIR="$SCRIPT_DIR/dist"
DMG_STAGING="$DIST_DIR/dmg-staging"
DMG_PATH="$DIST_DIR/SwiftGet.dmg"

echo ""
echo "  SwiftGet DMG Builder v1.2"
echo ""

# Step 1: Python
info "Python 3 check..."
command -v python3 &>/dev/null || err "Python 3 required"
PY_VER=$(python3 --version 2>&1 | cut -d' ' -f2)
ok "Python $PY_VER"

# Step 2: packages
info "Installing packages..."
pip3 install --quiet wxPython py2app
ok "Packages ready"

# Step 3: icon
info "Checking icon..."
ICON_PATH="$NATIVE_APP_DIR/icons/SwiftGet.icns"
[ -f "$ICON_PATH" ] || err "Icon not found: $ICON_PATH"
ok "Icon found"

# Step 4: patch py2app to disable strip, then build
info "Building SwiftGet.app..."
cd "$NATIVE_APP_DIR"
rm -rf build dist

# Write patch script to temp file
PATCH_PY="$(mktemp /tmp/swiftget_patch_XXXX.py)"
cat > "$PATCH_PY" << 'PATCHEOF'
import sys

path = sys.argv[1]
with open(path, "r") as f:
    lines = f.readlines()

patched = []
for line in lines:
    s = line.strip()
    # strip 을 실제 실행하는 라인 모두 pass 로 교체
    is_strip_call = (
        "strip" in s and
        not s.startswith("#") and
        "def " not in s and
        ("spawnl" in s or "spawnv" in s or
         "subprocess" in s or "os.system" in s or
         "Popen" in s or "call(" in s or
         "run(" in s)
    )
    if is_strip_call:
        indent = len(line) - len(line.lstrip())
        patched.append(" " * indent + "pass  # strip disabled\n")
        print("  patched: " + s)
    else:
        patched.append(line)

with open(path, "w") as f:
    f.writelines(patched)

print("Done: " + path)
PATCHEOF

# MachOStandalone.py 패치 — 서명된 파일 건너뛰기
MACHO_PATCH_PY="$(mktemp /tmp/swiftget_macho_patch_XXXX.py)"
cat > "$MACHO_PATCH_PY" << 'MACHOEOF'
import sys, re

path = sys.argv[1]
with open(path, "r") as f:
    src = f.read()

old = """            if rewroteAny:
                old_mode = flipwritable(fn)
                try:
                    with open(fn, "rb+") as f:
                        for _header in node.headers:
                            f.seek(0)
                            node.write(f)
                        f.seek(0, 2)
                        f.flush()
                finally:
                    flipwritable(fn, old_mode)"""

new = """            if rewroteAny:
                try:
                    old_mode = flipwritable(fn)
                except Exception:
                    # Apple 서명된 바이너리는 수정 불가 — 건너뜀
                    continue
                try:
                    with open(fn, "rb+") as f:
                        for _header in node.headers:
                            f.seek(0)
                            node.write(f)
                        f.seek(0, 2)
                        f.flush()
                except Exception:
                    pass
                finally:
                    flipwritable(fn, old_mode)"""

if old in src:
    src = src.replace(old, new)
    with open(path, "w") as f:
        f.write(src)
    print("Patched MachOStandalone: " + path)
else:
    print("Pattern not found in: " + path)
MACHOEOF

PY2APP_FILE="$(python3 -c "import py2app.build_app as m; print(m.__file__)")"
[ -n "$PY2APP_FILE" ] || err "py2app not found"

cp "$PY2APP_FILE" "${PY2APP_FILE}.bak"
python3 "$PATCH_PY" "$PY2APP_FILE"
rm -f "$PATCH_PY"

# MachOStandalone.py 패치 — 서명된 바이너리 건너뛰기
MACHO_FILE="$(python3 -c "import macholib.MachOStandalone as m; print(m.__file__)")"
if [ -n "$MACHO_FILE" ]; then
  cp "$MACHO_FILE" "${MACHO_FILE}.bak"
  python3 "$MACHO_PATCH_PY" "$MACHO_FILE"
fi
rm -f "$MACHO_PATCH_PY"

# Python3.framework 쓰기 권한 허용 (strip 권한 오류 방지)
PY_FW="$(python3 -c "import sys; print(sys.prefix)")"
find "$PY_FW" -type f \( -name "*.dylib" -o -name "Python3" -o -name "Python" \)     -exec chmod u+w {} + 2>/dev/null || true

python3 setup_dist.py py2app --quiet 2>&1 | tail -5

# Restore py2app + MachOStandalone
mv "${PY2APP_FILE}.bak" "$PY2APP_FILE"
[ -f "${MACHO_FILE}.bak" ] && mv "${MACHO_FILE}.bak" "$MACHO_FILE"

APP_PATH="$NATIVE_APP_DIR/dist/SwiftGet.app"
[ -d "$APP_PATH" ] || err "Build failed"
ok "SwiftGet.app built"

# Step 5: force icon into bundle
info "Applying icon..."
cp "$ICON_PATH" "$APP_PATH/Contents/Resources/SwiftGet.icns"
/usr/libexec/PlistBuddy -c \
  "Set :CFBundleIconFile SwiftGet" \
  "$APP_PATH/Contents/Info.plist" 2>/dev/null || \
/usr/libexec/PlistBuddy -c \
  "Add :CFBundleIconFile string SwiftGet" \
  "$APP_PATH/Contents/Info.plist"
touch "$APP_PATH"
ok "Icon applied"

# Step 6: native host script
info "Installing native host..."
HOST_SCRIPT="$APP_PATH/Contents/MacOS/swiftget-host"
cat > "$HOST_SCRIPT" << 'HOSTEOF'
#!/usr/bin/env python3
import sys, os
host = os.path.join(os.path.dirname(__file__), '..', 'Resources', 'swiftget-host.py')
exec(open(host).read())
HOSTEOF
chmod +x "$HOST_SCRIPT"
cp "$NATIVE_APP_DIR/swiftget-host.py" \
   "$APP_PATH/Contents/Resources/swiftget-host.py"
ok "Native host ready"

# Step 7: copy signed addon
info "Copying signed Firefox addon..."
XPI_PATH="$NATIVE_APP_DIR/dist/SwiftGet.xpi"
SIGNED_XPI="$ADDON_DIR/SwiftGet-signed.xpi"
[ -f "$SIGNED_XPI" ] || err "서명된 XPI 없음: $SIGNED_XPI"
cp "$SIGNED_XPI" "$XPI_PATH"
ok "SwiftGet.xpi ready"

# Step 8: build DMG
info "Building DMG..."
mkdir -p "$DMG_STAGING"
rm -rf "$DMG_STAGING"/*

cp -R "$APP_PATH" "$DMG_STAGING/SwiftGet.app"
cp    "$XPI_PATH" "$DMG_STAGING/SwiftGet.xpi"
ln -sf /Applications "$DMG_STAGING/Applications"

cat > "$DMG_STAGING/README.txt" << 'READMEEOF'
SwiftGet Installation

1. Drag SwiftGet.app to the Applications folder.
2. Launch SwiftGet.app once.
   (If blocked: System Settings > Privacy & Security > Open Anyway)
3. In Firefox: about:addons > gear icon > Install Add-on From File
   Select SwiftGet.xpi
READMEEOF

mkdir -p "$DIST_DIR"
rm -f "$DMG_PATH"

hdiutil create \
  -volname "SwiftGet" \
  -srcfolder "$DMG_STAGING" \
  -ov -format UDZO -fs HFS+ \
  "$DMG_PATH" > /dev/null

rm -rf "$DMG_STAGING"
ok "DMG created: $DMG_PATH"

echo ""
echo "  Done! Distribute: $DMG_PATH"
echo ""