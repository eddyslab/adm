"""
setup.py — Build SwiftGet.app with py2app
Run: python setup.py py2app
"""
from setuptools import setup

APP = ["swiftget.py"]
DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "SwiftGet",
        "CFBundleDisplayName": "SwiftGet",
        "CFBundleIdentifier": "app.swiftget.downloader",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "LSUIElement": True,       # Hide from Dock, appear in menu bar only
        "NSHighResolutionCapable": True,
    },
    "packages": ["tkinter", "rumps"],
    "includes": ["uuid"],
    "excludes": ["matplotlib", "numpy", "scipy"],
    # "iconfile": "icons/swiftget.icns",
}

setup(
    name="SwiftGet",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
