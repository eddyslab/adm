"""
setup_dist.py — 배포용 빌드 (완전 독립 번들)
  python setup_dist.py py2app
"""
from setuptools import setup

APP        = ["swiftget.py"]
DATA_FILES = []

# OPTIONS = {
#     "argv_emulation":  False,
#     "strip":           False,
#     "no_strip":        True,
#     "semi_standalone": False,  # Python 프레임워크 포함 (완전 독립)

#     "iconfile": "icons/SwiftGet.icns",

#     "plist": {
#         "CFBundleName":               "SwiftGet",
#         "CFBundleDisplayName":        "SwiftGet",
#         "CFBundleIdentifier":         "app.swiftget.downloader",
#         "CFBundleVersion":            "1.1.0",
#         "CFBundleShortVersionString": "1.1",
#         "CFBundleIconFile":           "SwiftGet",
#         "LSUIElement":                False,
#         "NSHighResolutionCapable":    True,
#     },

#     "packages": ["wx"],
#     "includes": ["uuid", "AppKit", "objc"],
#     "excludes": ["tkinter", "rumps", "matplotlib", "numpy", "scipy"],
# }

OPTIONS = {
    "argv_emulation":  False,
    "strip":           False,
    "no_strip":        True,
    "semi_standalone": False,

    "iconfile": "icons/SwiftGet.icns",

    "frameworks": [
        "/opt/anaconda3/envs/swiftget/lib/libffi.8.dylib",  # ← 추가
    ],

    "plist": {
        "CFBundleName":               "SwiftGet",
        "CFBundleDisplayName":        "SwiftGet",
        "CFBundleIdentifier":         "app.swiftget.downloader",
        "CFBundleVersion":            "1.1.0",
        "CFBundleShortVersionString": "1.1",
        "CFBundleIconFile":           "SwiftGet",
        "LSUIElement":                False,
        "NSHighResolutionCapable":    True,
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