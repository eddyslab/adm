"""
setup.py — Build SwiftGet.app with py2app

사전 준비:
  pip install py2app wxPython

빌드:
  python setup.py py2app

결과물: dist/SwiftGet.app
"""
from setuptools import setup

APP        = ["swiftget.py"]
DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,
    "strip": False,        # wxPython 서명 바이너리 보존
    "no_strip": True,      # py2app 버전에 따른 별칭

    # ── 아이콘 — 빌드 시 자동으로 번들에 포함됨 ──
    "iconfile": "icons/SwiftGet.icns",

    "plist": {
        "CFBundleName":              "SwiftGet",
        "CFBundleDisplayName":       "SwiftGet",
        "CFBundleIdentifier":        "app.swiftget.downloader",
        "CFBundleVersion":           "1.1.0",
        "CFBundleShortVersionString":"1.1",
        "CFBundleIconFile":          "SwiftGet",   # .icns 확장자 생략
        "LSUIElement":               False,        # Dock 아이콘 표시
        "NSHighResolutionCapable":   True,
    },

    "packages": ["wx"],
    "includes": ["uuid", "AppKit", "objc"],
    "excludes": ["tkinter", "rumps", "matplotlib", "numpy", "scipy"],
}

setup(
    name="SwiftGet",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)