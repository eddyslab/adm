#!/usr/bin/env python3
"""
SwiftGet Native Messaging Host
Bridges Firefox addon ↔ SwiftGet GUI app via a local socket.
Firefox communicates via stdin/stdout (Native Messaging protocol).
The GUI app listens on a local Unix socket.
"""

import sys
import json
import struct
import socket
import threading
import os
import subprocess
import time
import logging

LOG_FILE = os.path.expanduser("~/Library/Logs/SwiftGet/host.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG,
                    format="%(asctime)s %(levelname)s %(message)s")

SOCKET_PATH = os.path.expanduser("~/Library/Application Support/SwiftGet/swiftget.sock")
APP_BUNDLE   = "/Applications/SwiftGet.app"
GUI_SCRIPT   = os.path.join(APP_BUNDLE, "Contents/MacOS/swiftget")

# ── Native Messaging I/O ──────────────────────────────────────────────────────

def read_message():
    """Read one message from Firefox (4-byte LE length prefix + JSON)."""
    raw_len = sys.stdin.buffer.read(4)
    if len(raw_len) < 4:
        return None
    msg_len = struct.unpack("<I", raw_len)[0]
    data = sys.stdin.buffer.read(msg_len)
    return json.loads(data.decode("utf-8"))

def send_message(msg):
    """Send one message to Firefox."""
    data = json.dumps(msg).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()

# ── GUI App Socket ────────────────────────────────────────────────────────────

def ensure_app_running():
    """Launch the GUI app if not already running."""
    if os.path.exists(SOCKET_PATH):
        return  # Already running
    if os.path.exists(GUI_SCRIPT):
        logging.info("Launching SwiftGet GUI app")
        subprocess.Popen([GUI_SCRIPT], close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Wait for socket to appear (up to 5s)
        for _ in range(50):
            if os.path.exists(SOCKET_PATH):
                break
            time.sleep(0.1)

def send_to_gui(payload: dict):
    """Send a JSON message to the running GUI app over Unix socket."""
    ensure_app_running()
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(SOCKET_PATH)
        data = json.dumps(payload).encode("utf-8")
        sock.sendall(struct.pack(">I", len(data)) + data)
        sock.close()
        logging.info(f"Sent to GUI: {payload.get('action')}")
        return True
    except Exception as e:
        logging.error(f"Socket send failed: {e}")
        return False

# ── Main Loop ─────────────────────────────────────────────────────────────────

def main():
    logging.info("SwiftGet host started")
    while True:
        try:
            msg = read_message()
            if msg is None:
                break

            logging.debug(f"From Firefox: {msg}")
            action = msg.get("action")

            if action == "download":
                ok = send_to_gui(msg)
                if not ok:
                    send_message({"type": "error", "message": "GUI 앱에 연결할 수 없습니다."})

            elif action == "focus":
                send_to_gui({"action": "focus"})

            elif action == "pong":
                pass  # Heartbeat response

            else:
                logging.warning(f"Unknown action: {action}")

        except Exception as e:
            logging.exception(f"Host error: {e}")
            break

    logging.info("SwiftGet host exiting")

if __name__ == "__main__":
    main()
