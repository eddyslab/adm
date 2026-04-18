#!/usr/bin/env python3
"""
SwiftGet — macOS Download Manager GUI
- Multi-threaded downloads (up to 8 segments per file)
- Pause / Resume / Cancel
- Menu bar (system tray) resident
- Receives jobs from Firefox addon via Unix socket
- UI: wxPython (native Cocoa widgets)
"""

import os
import sys
import json
import struct
import socket
import threading
import time
import urllib.request
import urllib.parse
import urllib.error
import re
import http.client
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import logging
import subprocess
import AppKit
import objc

# ─────────────────────────────────────────────────────────────────────────────
# i18n
# ─────────────────────────────────────────────────────────────────────────────

# i18n.py 를 번들 내 Resources 또는 소스 디렉터리에서 임포트
_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

try:
    from i18n import STRINGS, LANGUAGES, get_strings
except ImportError:
    # 폴백: 빈 딕셔너리
    LANGUAGES = {"ko": "한국어"}
    STRINGS   = {}
    def get_strings(lang): return {}

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

APP_NAME     = "SwiftGet"
CONFIG_DIR   = os.path.expanduser("~/Library/Application Support/SwiftGet")
CONFIG_PATH  = os.path.join(CONFIG_DIR, "config.json")
SOCKET_PATH  = os.path.join(CONFIG_DIR, "swiftget.sock")
LOG_DIR      = os.path.expanduser("~/Library/Logs/SwiftGet")
CHUNK_SIZE   = 65536

os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(filename=os.path.join(LOG_DIR, "swiftget.log"),
                    level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

# ── Persistent settings ──────────────────────────────────────────────────────

def _detect_system_lang() -> str:
    """macOS 시스템 언어를 감지하여 지원 언어 코드 반환. 없으면 'en'."""
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleLanguages"],
            capture_output=True, text=True)
        for line in result.stdout.splitlines():
            code = line.strip().strip('",()').split("-")[0]
            if code in ("ko", "en", "ja", "zh", "fr", "es"):
                return code
    except Exception:
        pass
    return "en"

_DEFAULTS = {
    "save_dir":           os.path.expanduser("~/Downloads"),
    "segments":           8,
    "notify_on_complete": True,
    "language":           _detect_system_lang(),
}

def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)

def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logging.warning(f"Config save failed: {e}")

def send_notification(title: str, message: str):
    """macOS 알림 센터에 알림 전송."""
    try:
        script = f'display notification "{message}" with title "{title}"'
        subprocess.run(["osascript", "-e", script], check=False)
    except Exception as e:
        logging.warning(f"알림 전송 실패: {e}")

_cfg     = load_config()
SAVE_DIR = _cfg["save_dir"]
SEGMENTS = _cfg["segments"]

# 현재 언어 문자열 로드
T = get_strings(_cfg.get("language", "ko"))

# ─────────────────────────────────────────────────────────────────────────────
# Download Engine
# ─────────────────────────────────────────────────────────────────────────────

class Status(Enum):
    QUEUED    = auto()
    RUNNING   = auto()
    PAUSED    = auto()
    DONE      = auto()
    ERROR     = auto()
    CANCELLED = auto()

@dataclass
class DownloadJob:
    uid:        str
    url:        str
    filename:   str
    save_path:  str
    referrer:   str    = ""
    cookies:    str    = ""
    total:      int    = -1
    downloaded: int    = 0
    status:     Status = Status.QUEUED
    error_msg:  str    = ""
    speed:      float  = 0.0
    eta:        int    = -1
    seg_downloaded: list = field(default_factory=list, repr=False)
    seg_sizes:      list = field(default_factory=list, repr=False)
    _pause_evt: threading.Event = field(default_factory=threading.Event, repr=False)
    _cancel_evt:threading.Event = field(default_factory=threading.Event, repr=False)
    _lock:      threading.Lock  = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        self._pause_evt.set()

def human_size(n: int) -> str:
    if n < 0:      return "?"
    if n < 1024:   return f"{n} B"
    if n < 1<<20:  return f"{n/1024:.1f} KB"
    if n < 1<<30:  return f"{n/(1<<20):.1f} MB"
    return f"{n/(1<<30):.2f} GB"

def human_speed(bps: float) -> str:
    return human_size(int(bps)) + "/s"

def human_eta(secs: int) -> str:
    if secs < 0:    return "--:--"
    if secs < 60:   return f"{secs}s"
    if secs < 3600: return f"{secs//60}m {secs%60}s"
    return f"{secs//3600}h {(secs%3600)//60}m"

class DownloadEngine:
    def __init__(self, on_update):
        self.jobs: list[DownloadJob] = []
        self.on_update = on_update
        self._lock = threading.Lock()
        self._max_concurrent = 3
        self.segments = SEGMENTS

    def add(self, url, filename="", referrer="", cookies="") -> DownloadJob:
        if not filename:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path) or "download"
            filename = urllib.parse.unquote(filename)

            # 확장자가 없으면 HEAD 요청으로 Content-Type 확인
            # if not os.path.splitext(filename)[1]:
            #     try:
            #         headers = {"User-Agent": "SwiftGet/1.0"}
            #         if referrer: headers["Referer"] = referrer
            #         if cookies:  headers["Cookie"]  = cookies
            #         req = urllib.request.Request(url, headers=headers, method="HEAD")
            #         with urllib.request.urlopen(req, timeout=10) as resp:
            #             ct = resp.headers.get("Content-Type", "")
            #             ct = ct.split(";")[0].strip().lower()
            #             ext_map = {
            #                 "image/jpeg":       ".jpg",
            #                 "image/png":        ".png",
            #                 "image/gif":        ".gif",
            #                 "image/webp":       ".webp",
            #                 "image/svg+xml":    ".svg",
            #                 "video/mp4":        ".mp4",
            #                 "video/webm":       ".webm",
            #                 "audio/mpeg":       ".mp3",
            #                 "audio/ogg":        ".ogg",
            #                 "application/pdf":  ".pdf",
            #                 "application/zip":  ".zip",
            #                 "text/plain":       ".txt",
            #                 "text/html":        ".html",
            #             }
            #             ext = ext_map.get(ct, "")
            #             if ext:
            #                 filename += ext
            #     except Exception as e:
            #         logging.debug(f"HEAD request failed for {url}: {e}")

            # 확장자가 없으면 HEAD → GET fallback으로 Content-Type 확인
            if not os.path.splitext(filename)[1]:
                ext_map = {
                    "image/jpeg":       ".jpg",
                    "image/png":        ".png",
                    "image/gif":        ".gif",
                    "image/webp":       ".webp",
                    "image/svg+xml":    ".svg",
                    "image/avif":       ".avif",
                    "video/mp4":        ".mp4",
                    "video/webm":       ".webm",
                    "video/quicktime":  ".mov",
                    "audio/mpeg":       ".mp3",
                    "audio/ogg":        ".ogg",
                    "audio/flac":       ".flac",
                    "application/pdf":  ".pdf",
                    "application/zip":  ".zip",
                    "text/plain":       ".txt",
                    "text/html":        ".html",
                }
                headers = {"User-Agent": "SwiftGet/1.0"}
                if referrer: headers["Referer"] = referrer
                if cookies:  headers["Cookie"]  = cookies

                def _get_ext_from_resp(resp):
                    # Content-Disposition 우선
                    cd = resp.headers.get("Content-Disposition", "")
                    cd_match = re.search(r'filename[*]?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', cd, re.I)
                    if cd_match:
                        cd_name = urllib.parse.unquote(cd_match.group(1).strip())
                        cd_ext  = os.path.splitext(cd_name)[1]
                        if cd_ext:
                            return cd_name, cd_ext
                    ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    return None, ext_map.get(ct, "")

                ext = ""
                try:
                    req = urllib.request.Request(url, headers=headers, method="HEAD")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        cd_name, ext = _get_ext_from_resp(resp)
                        if cd_name:
                            filename = cd_name
                            ext = ""
                except Exception as e:
                    logging.debug(f"HEAD request failed for {url}: {e}")
                    # GET fallback — Range로 첫 1KB만 요청
                    try:
                        get_headers = {**headers, "Range": "bytes=0-1023"}
                        req = urllib.request.Request(url, headers=get_headers, method="GET")
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            cd_name, ext = _get_ext_from_resp(resp)
                            if cd_name:
                                filename = cd_name
                                ext = ""
                    except Exception as e2:
                        logging.debug(f"GET fallback failed for {url}: {e2}")

                if ext:
                    filename += ext
                    
        save_dir  = getattr(self, "save_dir", SAVE_DIR)
        save_path = os.path.join(save_dir, filename)
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base} ({counter}){ext}"
            counter += 1
        import uuid
        job = DownloadJob(uid=str(uuid.uuid4())[:8], url=url,
                          filename=os.path.basename(save_path),
                          save_path=save_path, referrer=referrer, cookies=cookies)
        with self._lock:
            self.jobs.append(job)
        self._try_start(job)
        return job

    def _try_start(self, job):
        with self._lock:
            running = sum(1 for j in self.jobs if j.status == Status.RUNNING)
        if running < self._max_concurrent:
            threading.Thread(target=self._run, args=(job,), daemon=True).start()

    def _run(self, job):
        job.status = Status.RUNNING
        self.on_update()
        try:
            self._download(job)
            if not job._cancel_evt.is_set():
                job.status = Status.DONE
                job.speed  = 0
                cfg = load_config()
                if cfg.get("notify_on_complete", True):
                    fname = os.path.basename(job.filename) if job.filename else job.url
                    if len(fname) > 40:
                        fname = fname[:37] + "..."
                    t = get_strings(cfg.get("language", "ko"))
                    send_notification("SwiftGet", t.get("notif_done", "Done: {fname}").format(fname=fname))
        except Exception as e:
            job.status = Status.CANCELLED if job._cancel_evt.is_set() else Status.ERROR
            if job.status == Status.ERROR:
                job.error_msg = str(e)
                logging.error(f"Download error [{job.uid}]: {e}")
        finally:
            self.on_update()
            self._start_queued()

    def _start_queued(self):
        with self._lock:
            running = sum(1 for j in self.jobs if j.status == Status.RUNNING)
            queued  = [j for j in self.jobs if j.status == Status.QUEUED]
        for j in queued[:max(0, self._max_concurrent - running)]:
            threading.Thread(target=self._run, args=(j,), daemon=True).start()

    def _download(self, job):
        headers = {"User-Agent": "SwiftGet/1.0"}
        if job.referrer: headers["Referer"] = job.referrer
        if job.cookies:  headers["Cookie"]  = job.cookies
        req = urllib.request.Request(job.url, headers={**headers, "Range": "bytes=0-0"})
        n_seg = self.segments
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                cr = resp.headers.get("Content-Range", "")
                supports_range = resp.status == 206
                job.total = int(cr.split("/")[-1]) if cr else \
                            (int(resp.headers.get("Content-Length")) if resp.headers.get("Content-Length") else -1)
        except Exception:
            supports_range = False
            job.total = -1
        if supports_range and job.total > 0 and n_seg > 1:
            self._segmented_download(job, headers, n_seg)
        else:
            self._simple_download(job, headers)

    def _simple_download(self, job, headers):
        req = urllib.request.Request(job.url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            if job.total < 0:
                cl = resp.headers.get("Content-Length")
                if cl: job.total = int(cl)
            t0 = time.time()
            win = 0
            with open(job.save_path, "wb") as f:
                while True:
                    if job._cancel_evt.is_set(): raise Exception("Cancelled")
                    job._pause_evt.wait()
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk: break
                    f.write(chunk)
                    with job._lock: job.downloaded += len(chunk)
                    win += len(chunk)
                    elapsed = time.time() - t0
                    if elapsed >= 0.5:
                        job.speed = win / elapsed
                        if job.total > 0:
                            job.eta = int((job.total - job.downloaded) / job.speed) if job.speed > 0 else -1
                        t0 = time.time(); win = 0
                        self.on_update()

    def _segmented_download(self, job, headers, n_seg):
        seg_size  = job.total // n_seg
        ranges    = [(i * seg_size, (i+1) * seg_size - 1) for i in range(n_seg)]
        ranges[-1]= (ranges[-1][0], job.total - 1)
        tmp_files = [f"{job.save_path}.part{i}" for i in range(n_seg)]
        errors    = [None] * n_seg
        threads   = []
        t_start   = time.time(); prev_dl = 0

        job.seg_sizes      = [end - start + 1 for start, end in ranges]
        job.seg_downloaded = [0] * n_seg

        def dl_seg(idx, start, end):
            h = {**headers, "Range": f"bytes={start}-{end}"}
            try:
                with urllib.request.urlopen(urllib.request.Request(job.url, headers=h), timeout=30) as resp, \
                     open(tmp_files[idx], "wb") as f:
                    while True:
                        if job._cancel_evt.is_set(): return
                        job._pause_evt.wait()
                        chunk = resp.read(CHUNK_SIZE)
                        if not chunk: break
                        f.write(chunk)
                        with job._lock:
                            job.downloaded += len(chunk)
                            job.seg_downloaded[idx] += len(chunk)
            except Exception as e:
                errors[idx] = e

        for i, (s, e) in enumerate(ranges):
            t = threading.Thread(target=dl_seg, args=(i, s, e), daemon=True)
            threads.append(t); t.start()

        while any(t.is_alive() for t in threads):
            if job._cancel_evt.is_set(): break
            time.sleep(0.5)
            dl_now = job.downloaded
            job.speed = (dl_now - prev_dl) / 0.5; prev_dl = dl_now
            if job.total > 0 and job.speed > 0:
                job.eta = int((job.total - dl_now) / job.speed)
            self.on_update()

        for t in threads: t.join()
        if job._cancel_evt.is_set():
            for f in tmp_files:
                try: os.remove(f)
                except: pass
            return
        errs = [e for e in errors if e]
        if errs: raise Exception(f"Segment error: {errs[0]}")
        with open(job.save_path, "wb") as out:
            for part in tmp_files:
                with open(part, "rb") as inp:
                    while True:
                        chunk = inp.read(1 << 20)
                        if not chunk: break
                        out.write(chunk)
                os.remove(part)

    def pause(self, job):
        if job.status == Status.RUNNING:
            job._pause_evt.clear(); job.status = Status.PAUSED; self.on_update()

    def resume(self, job):
        if job.status == Status.PAUSED:
            job.status = Status.RUNNING; job._pause_evt.set(); self.on_update()

    def cancel(self, job):
        job._cancel_evt.set(); job._pause_evt.set()

    def remove(self, job):
        self.cancel(job)
        with self._lock:
            self.jobs = [j for j in self.jobs if j.uid != job.uid]
        self.on_update()

# ─────────────────────────────────────────────────────────────────────────────
# wxPython GUI
# ─────────────────────────────────────────────────────────────────────────────

import wx
import wx.lib.scrolledpanel as scrolled

EVT_REFRESH_ID = wx.NewEventType()
EVT_REFRESH    = wx.PyEventBinder(EVT_REFRESH_ID, 1)

class RefreshEvent(wx.PyCommandEvent):
    def __init__(self):
        super().__init__(EVT_REFRESH_ID)


# ── Segment progress bar ──────────────────────────────────────────────────────

class SegmentBar(wx.Panel):
    COL_DONE    = wx.Colour(52,  199,  89)
    COL_ACTIVE  = wx.Colour(10,  132, 255)
    COL_QUEUED  = wx.Colour(210, 210, 210)
    COL_PAUSED  = wx.Colour(255, 159,  10)
    COL_ERROR   = wx.Colour(255,  59,  48)
    GAP         = 2

    def __init__(self, parent):
        super().__init__(parent, size=(-1, 5))
        self.SetMinSize((-1, 5))
        self._fractions: list[float] = []
        self._job_status = Status.RUNNING
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE,  lambda e: self.Refresh())

    def update(self, job: 'DownloadJob'):
        if job.seg_sizes and job.seg_downloaded:
            self._fractions = [
                min(dl / sz, 1.0) if sz > 0 else 0.0
                for dl, sz in zip(job.seg_downloaded, job.seg_sizes)
            ]
        else:
            self._fractions = []
        self._job_status = job.status
        self.Refresh()

    def _on_paint(self, event):
        dc   = wx.PaintDC(self)
        w, h = self.GetClientSize()
        n    = len(self._fractions)
        if n == 0:
            return
        total_gap = self.GAP * (n - 1)
        seg_w     = max(1, (w - total_gap) / n)
        for i, frac in enumerate(self._fractions):
            x  = int(i * (seg_w + self.GAP))
            sw = int(seg_w)
            dc.SetBrush(wx.Brush(self.COL_QUEUED))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(x, 0, sw, h)
            if frac > 0:
                if self._job_status == Status.PAUSED:
                    fill_col = self.COL_PAUSED
                elif self._job_status == Status.ERROR:
                    fill_col = self.COL_ERROR
                elif frac >= 1.0:
                    fill_col = self.COL_DONE
                else:
                    fill_col = self.COL_ACTIVE
                dc.SetBrush(wx.Brush(fill_col))
                dc.DrawRectangle(x, 0, max(1, int(sw * frac)), h)


# ── Per-job card panel ────────────────────────────────────────────────────────

class JobCard(wx.Panel):
    STATUS_COLOUR = {
        Status.QUEUED:    wx.Colour(150, 150, 150),
        Status.RUNNING:   wx.Colour(52,  199,  89),
        Status.PAUSED:    wx.Colour(255, 159,  10),
        Status.DONE:      wx.Colour(52,  199,  89),
        Status.ERROR:     wx.Colour(255,  59,  48),
        Status.CANCELLED: wx.Colour(150, 150, 150),
    }

    def __init__(self, parent, job: DownloadJob, engine: DownloadEngine, main_frame):
        super().__init__(parent, style=wx.BORDER_THEME)
        self.job        = job
        self.engine     = engine
        self.main_frame = main_frame

        base = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        r = min(255, base.Red()   + 10)
        g = min(255, base.Green() + 10)
        b = min(255, base.Blue()  + 10)
        self.SetBackgroundColour(wx.Colour(r, g, b))

        root = wx.BoxSizer(wx.VERTICAL)
        root.AddSpacer(10)

        r1 = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_name = wx.StaticText(self, label=job.filename)
        font = self.lbl_name.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        font.SetPointSize(font.GetPointSize() + 1)
        self.lbl_name.SetFont(font)
        self.lbl_status = wx.StaticText(self, label="")
        r1.Add(self.lbl_name,   1, wx.ALIGN_CENTER_VERTICAL)
        r1.Add(self.lbl_status, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        root.Add(r1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 14)
        root.AddSpacer(8)

        self.gauge = wx.Gauge(self, range=1000, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self.gauge.SetMinSize((-1, 6))
        root.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 14)
        root.AddSpacer(4)

        self.seg_bar = SegmentBar(self)
        self.seg_bar.Hide()
        root.Add(self.seg_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 14)
        root.AddSpacer(6)

        r3 = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_info = wx.StaticText(self, label="")
        r3.Add(self.lbl_info, 1, wx.ALIGN_CENTER_VERTICAL)

        self.btn_pause  = wx.Button(self, label="⏸",  size=(32, 26))
        self.btn_resume = wx.Button(self, label="▶",  size=(32, 26))
        self.btn_cancel = wx.Button(self, label="✕",  size=(32, 26))
        self.btn_reveal = wx.Button(self, label="📂", size=(32, 26))
        self.btn_remove = wx.Button(self, label="🗑",  size=(32, 26))
        self.btn_retry  = wx.Button(self, label="↺",  size=(32, 26))

        for btn in (self.btn_pause, self.btn_resume, self.btn_cancel,
                    self.btn_reveal, self.btn_remove, self.btn_retry):
            r3.Add(btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)

        root.Add(r3, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 14)
        root.AddSpacer(10)
        self.SetSizer(root)

        self.btn_pause.Bind( wx.EVT_BUTTON, lambda e: engine.pause(job))
        self.btn_resume.Bind(wx.EVT_BUTTON, lambda e: engine.resume(job))
        self.btn_cancel.Bind(wx.EVT_BUTTON, lambda e: engine.cancel(job))
        self.btn_reveal.Bind(wx.EVT_BUTTON, lambda e: subprocess.Popen(["open", "-R", job.save_path]))
        self.btn_remove.Bind(wx.EVT_BUTTON, lambda e: engine.remove(job))
        self.btn_retry.Bind( wx.EVT_BUTTON, lambda e: (engine.remove(job),
                                                         engine.add(job.url, job.filename,
                                                                    job.referrer, job.cookies)))
        self.refresh()

    def refresh(self):
        job = self.job
        pct = 0.0
        if job.total > 0 and job.downloaded > 0:
            pct = min(job.downloaded / job.total, 1.0)

        self.gauge.SetValue(int(pct * 1000))

        has_segs = bool(job.seg_sizes)
        if has_segs != self.seg_bar.IsShown():
            self.seg_bar.Show(has_segs)
        if has_segs:
            self.seg_bar.update(job)

        colour = self.STATUS_COLOUR.get(job.status, wx.Colour(150, 150, 150))
        status_labels = {
            Status.QUEUED:    T.get("status_queued",    "대기"),
            Status.RUNNING:   T.get("status_running",   "다운로드 중"),
            Status.PAUSED:    T.get("status_paused",    "일시정지"),
            Status.DONE:      T.get("status_done",      "완료"),
            Status.ERROR:     T.get("status_error",     "오류"),
            Status.CANCELLED: T.get("status_cancelled", "취소됨"),
        }
        self.lbl_status.SetLabel(status_labels.get(job.status, ""))
        self.lbl_status.SetForegroundColour(colour)

        if job.status == Status.ERROR:
            info = T.get("info_error", "오류: {msg}").format(msg=job.error_msg[:80])
        else:
            info = human_size(job.downloaded)
            if job.total > 0:
                info += f" / {human_size(job.total)}  ({pct*100:.0f}%)"
            if job.status == Status.RUNNING and job.speed > 0:
                info += f"  ·  {human_speed(job.speed)}"
                if job.eta >= 0:
                    info += f"  ·  {T.get('info_eta', '남은 시간 {eta}').format(eta=human_eta(job.eta))}"
        self.lbl_info.SetLabel(info)

        s = job.status
        self.btn_pause.Show( s == Status.RUNNING)
        self.btn_resume.Show(s == Status.PAUSED)
        self.btn_cancel.Show(s in (Status.RUNNING, Status.PAUSED, Status.QUEUED))
        self.btn_reveal.Show(s == Status.DONE)
        self.btn_remove.Show(s in (Status.DONE, Status.ERROR, Status.CANCELLED))
        self.btn_retry.Show( s == Status.ERROR)
        self.Layout()


# ── Main window ───────────────────────────────────────────────────────────────

class SwiftGetFrame(wx.Frame):
    def __init__(self, engine: DownloadEngine, dev_mode: bool = False):
        super().__init__(None, title="SwiftGet", size=(780, 560),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.SetMinSize((780, 560))
        self.engine   = engine
        self.dev_mode = dev_mode
        self._cards: dict[str, JobCard] = {}
        self._cfg     = load_config()

        self.engine.on_update = self._post_refresh
        self.engine.segments  = self._cfg["segments"]
        self.engine.save_dir  = self._cfg["save_dir"]

        self._build_ui()
        self.Centre()
        self.Show()

        self.Bind(EVT_REFRESH, self._on_refresh)
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_refresh, self._timer)
        self._timer.Start(500)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _on_close(self, event):
        if self.dev_mode:
            self._timer.Stop()
            wx.GetApp().ExitMainLoop()
        else:
            self.Hide()

    def _build_ui(self):
        panel = wx.Panel(self)
        root  = wx.BoxSizer(wx.VERTICAL)

        # ── 헤더: 로고(좌) + 언어 선택(우) ──
        hdr = wx.BoxSizer(wx.HORIZONTAL)
        lbl = wx.StaticText(panel, label="Swift")
        font = lbl.GetFont()
        font.SetPointSize(font.GetPointSize() + 8)
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        lbl.SetFont(font)
        lbl2 = wx.StaticText(panel, label="Get")
        lbl2.SetFont(font)
        lbl2.SetForegroundColour(wx.Colour(52, 199, 89))
        hdr.Add(lbl,  0, wx.ALIGN_CENTER_VERTICAL)
        hdr.Add(lbl2, 0, wx.ALIGN_CENTER_VERTICAL)
        hdr.AddStretchSpacer()

        # 언어 선택 드롭다운
        lang_choices = list(LANGUAGES.values())
        lang_codes   = list(LANGUAGES.keys())
        cur_lang     = self._cfg.get("language", "ko")
        cur_idx      = lang_codes.index(cur_lang) if cur_lang in lang_codes else 0
        self._lang_codes  = lang_codes
        self.choice_lang  = wx.Choice(panel, choices=lang_choices)
        self.choice_lang.SetSelection(cur_idx)
        self.choice_lang.Bind(wx.EVT_CHOICE, self._on_lang_change)
        hdr.Add(self.choice_lang, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 16)

        root.Add(hdr, 0, wx.EXPAND | wx.LEFT | wx.TOP, 16)
        root.AddSpacer(10)

        # ── 메인 탭 ──
        self.notebook = wx.Notebook(panel)

        # ════════════════════════════════
        # 탭 1: 일반
        # ════════════════════════════════
        tab_main   = wx.Panel(self.notebook)
        sizer_main = wx.BoxSizer(wx.VERTICAL)

        tb = wx.BoxSizer(wx.HORIZONTAL)
        btn_clear  = wx.Button(tab_main, label=T.get("btn_clear_done", "완료 항목 지우기"))
        btn_folder = wx.Button(tab_main, label=T.get("btn_folder",     "폴더 열기"))
        btn_import = wx.Button(tab_main, label=T.get("btn_import",     "URL 임포트"))
        btn_add    = wx.Button(tab_main, label=T.get("btn_add_url",    "＋ URL 추가"))
        tb.AddStretchSpacer()
        tb.Add(btn_clear,  0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        tb.Add(btn_folder, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        tb.Add(btn_import, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        tb.Add(btn_add,    0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        sizer_main.Add(tb, 0, wx.EXPAND | wx.ALL, 10)

        url_row = wx.BoxSizer(wx.HORIZONTAL)
        self.url_field = wx.TextCtrl(tab_main, style=wx.TE_PROCESS_ENTER, size=(-1, 30))
        self.url_field.SetHint(T.get("url_hint", "URL을 여기에 붙여넣기..."))
        btn_dl = wx.Button(tab_main, label=T.get("btn_download", "다운로드"), size=(-1, 30))
        url_row.Add(self.url_field, 1, wx.ALIGN_CENTER_VERTICAL)
        url_row.Add(btn_dl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        sizer_main.Add(url_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        self.lbl_stats = wx.StaticText(tab_main, label=T.get("stats_idle", "대기 중..."))
        sizer_main.Add(self.lbl_stats, 0, wx.LEFT | wx.BOTTOM, 10)

        self.scroll = scrolled.ScrolledPanel(tab_main, style=wx.BORDER_NONE)
        self.scroll.SetupScrolling(scroll_x=False)
        self.job_sizer = wx.BoxSizer(wx.VERTICAL)
        self.scroll.SetSizer(self.job_sizer)

        self.lbl_empty = wx.StaticText(self.scroll, label=T.get("empty_list", "다운로드 항목이 없습니다"))
        font_e = self.lbl_empty.GetFont()
        font_e.SetPointSize(font_e.GetPointSize() - 1)
        self.lbl_empty.SetFont(font_e)
        self.lbl_empty.SetForegroundColour(wx.Colour(150, 150, 150))
        self.job_sizer.Add(self.lbl_empty, 0, wx.ALL, 20)

        sizer_main.Add(self.scroll, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        tab_main.SetSizer(sizer_main)
        self.notebook.AddPage(tab_main, T.get("tab_general", "일반"))

        # ════════════════════════════════
        # 탭 2: 다운로드 설정
        # ════════════════════════════════
        tab_dl   = wx.Panel(self.notebook)
        grid_dl  = wx.FlexGridSizer(cols=3, vgap=14, hgap=10)
        grid_dl.AddGrowableCol(1, 1)

        grid_dl.Add(wx.StaticText(tab_dl, label=T.get("lbl_save_dir", "다운로드 경로:")),
                    0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_dir = wx.TextCtrl(tab_dl, value=self._cfg["save_dir"])
        grid_dl.Add(self.txt_dir, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        btn_browse = wx.Button(tab_dl, label=T.get("btn_browse", "찾아보기…"), size=(90, -1))
        grid_dl.Add(btn_browse, 0, wx.ALIGN_CENTER_VERTICAL)

        grid_dl.Add(wx.StaticText(tab_dl, label=T.get("lbl_segments", "기본 세그먼트 수:")),
                    0, wx.ALIGN_CENTER_VERTICAL)
        self.spin_seg = wx.SpinCtrl(tab_dl, value=str(self._cfg["segments"]),
                                    min=1, max=32, size=(64, -1))
        grid_dl.Add(self.spin_seg, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_dl.Add(wx.StaticText(tab_dl, label=T.get("lbl_seg_hint", "(1 = 분할 안 함)")),
                    0, wx.ALIGN_CENTER_VERTICAL)

        sizer_dl = wx.BoxSizer(wx.VERTICAL)
        sizer_dl.Add(grid_dl, 0, wx.EXPAND | wx.ALL, 16)
        tab_dl.SetSizer(sizer_dl)
        self.notebook.AddPage(tab_dl, T.get("tab_download", "다운로드"))

        # ════════════════════════════════
        # 탭 3: 알림
        # ════════════════════════════════
        tab_notify   = wx.Panel(self.notebook)
        grid_notify  = wx.FlexGridSizer(cols=2, vgap=14, hgap=10)
        grid_notify.AddGrowableCol(1, 1)

        grid_notify.Add(wx.StaticText(tab_notify, label=T.get("lbl_notify", "다운로드 완료 알림:")),
                        0, wx.ALIGN_CENTER_VERTICAL)
        self.chk_notify = wx.CheckBox(tab_notify, label=T.get("chk_notify", "완료 시 알림 표시"))
        self.chk_notify.SetValue(self._cfg.get("notify_on_complete", True))
        grid_notify.Add(self.chk_notify, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer_notify = wx.BoxSizer(wx.VERTICAL)
        sizer_notify.Add(grid_notify, 0, wx.EXPAND | wx.ALL, 16)
        tab_notify.SetSizer(sizer_notify)
        self.notebook.AddPage(tab_notify, T.get("tab_notify", "알림"))

        # ════════════════════════════════
        # 탭 4: 대기 중
        # ════════════════════════════════
        tab_queue   = wx.Panel(self.notebook)
        sizer_queue = wx.BoxSizer(wx.VERTICAL)

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.chk_auto_dedup = wx.CheckBox(tab_queue, label=T.get("chk_auto_dedup", "중복 자동 제거"))
        self.chk_auto_dedup.SetValue(True)
        row1.Add(self.chk_auto_dedup, 0, wx.ALIGN_CENTER_VERTICAL)
        row1.AddStretchSpacer()

        btn_q_import = wx.Button(tab_queue, label=T.get("btn_import",   "URL 임포트"))
        btn_q_delete = wx.Button(tab_queue, label=T.get("btn_q_delete", "삭제"))
        btn_q_dedup  = wx.Button(tab_queue, label=T.get("btn_q_dedup",  "중복 제거"))
        btn_q_run    = wx.Button(tab_queue, label=T.get("btn_q_run",    "실행"))

        row1.Add(btn_q_import, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        row1.Add(btn_q_delete, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        row1.Add(btn_q_dedup,  0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        row1.Add(btn_q_run,    0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        sizer_queue.Add(row1, 0, wx.EXPAND | wx.ALL, 10)

        self.lbl_queue_count = wx.StaticText(tab_queue,
                                             label=T.get("queue_count", "전체 {n}개").format(n=0))
        sizer_queue.Add(self.lbl_queue_count, 0, wx.LEFT | wx.BOTTOM, 10)

        self.queue_scroll = scrolled.ScrolledPanel(tab_queue, style=wx.BORDER_NONE)
        self.queue_scroll.SetupScrolling(scroll_x=False)
        self.queue_sizer = wx.BoxSizer(wx.VERTICAL)
        self.queue_scroll.SetSizer(self.queue_sizer)

        lbl_qe = wx.StaticText(self.queue_scroll, label=T.get("queue_empty", "임포트된 URL이 없습니다"))
        font_qe = lbl_qe.GetFont()
        font_qe.SetPointSize(font_qe.GetPointSize() - 1)
        lbl_qe.SetFont(font_qe)
        lbl_qe.SetForegroundColour(wx.Colour(150, 150, 150))
        self.queue_sizer.Add(lbl_qe, 0, wx.ALL, 20)

        sizer_queue.Add(self.queue_scroll, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        tab_queue.SetSizer(sizer_queue)
        self.notebook.AddPage(tab_queue, T.get("tab_queue", "대기 중"))

        self._import_urls:   list[str]      = []
        self._import_checks: list[wx.CheckBox] = []

        # ════════════════════════════════
        # 탭 5: 기타 (언어 설정)
        # ════════════════════════════════
        tab_misc  = wx.Panel(self.notebook)
        grid_misc = wx.FlexGridSizer(cols=2, vgap=14, hgap=10)
        grid_misc.AddGrowableCol(1, 1)

        grid_misc.Add(wx.StaticText(tab_misc, label=T.get("lbl_language", "언어:")),
                      0, wx.ALIGN_CENTER_VERTICAL)
        # 언어 선택은 헤더 드롭다운과 동일하게 표시 (읽기 전용 안내)
        lbl_lang_hint = wx.StaticText(tab_misc, label=T.get("lbl_lang_hint",
                                      "언어 변경 후 앱을 재시작해 주세요."))
        lbl_lang_hint.SetForegroundColour(wx.Colour(120, 120, 120))
        grid_misc.Add(lbl_lang_hint, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer_misc = wx.BoxSizer(wx.VERTICAL)
        sizer_misc.Add(grid_misc, 0, wx.EXPAND | wx.ALL, 16)
        tab_misc.SetSizer(sizer_misc)
        self.notebook.AddPage(tab_misc, T.get("tab_misc", "기타"))

        root.Add(self.notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        panel.SetSizer(root)

        # ── Events ──
        btn_import.Bind(wx.EVT_BUTTON,     self._on_import_urls)
        btn_add.Bind(   wx.EVT_BUTTON,     self._on_add_url)
        btn_clear.Bind( wx.EVT_BUTTON,     self._on_clear_done)
        btn_folder.Bind(wx.EVT_BUTTON,     lambda e: subprocess.Popen(["open", self.engine.save_dir]))
        btn_dl.Bind(    wx.EVT_BUTTON,     self._on_quick_add)
        btn_browse.Bind(wx.EVT_BUTTON,     self._on_browse)
        btn_q_import.Bind(wx.EVT_BUTTON,   self._on_import_urls)
        btn_q_delete.Bind(wx.EVT_BUTTON,   self._on_queue_delete)
        btn_q_dedup.Bind( wx.EVT_BUTTON,   self._on_queue_dedup)
        btn_q_run.Bind(   wx.EVT_BUTTON,   self._on_queue_run)
        self.url_field.Bind(wx.EVT_TEXT_ENTER, self._on_quick_add)
        self.spin_seg.Bind(wx.EVT_SPINCTRL,    self._on_seg_change)
        self.chk_notify.Bind(wx.EVT_CHECKBOX,  self._on_notify_change)
        self.notebook.SetSelection(0)

    # ── 언어 변경 ─────────────────────────────────────────────────────────────

    def _on_lang_change(self, event):
        idx      = self.choice_lang.GetSelection()
        new_lang = self._lang_codes[idx]
        if new_lang == self._cfg.get("language", "ko"):
            return
        self._cfg["language"] = new_lang
        save_config(self._cfg)

        t = get_strings(new_lang)

        # 진행 중인 다운로드 확인
        running = [j for j in self.engine.jobs if j.status == Status.RUNNING]

        if running:
            msg = (f"다운로드 중인 항목이 {len(running)}개 있습니다.\n"
                   f"지금 재시작하면 다운로드가 중단됩니다.\n\n"
                   f"지금 재시작할까요?")
        else:
            msg = (t.get("lbl_lang_hint", "언어 변경 후 앱을 재시작해 주세요.") +
                   "\n\n지금 재시작할까요?")

        dlg = wx.MessageDialog(
            self, msg, "SwiftGet",
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION
        )
        dlg.SetYesNoLabels("지금 재시작", "나중에")
        result = dlg.ShowModal()
        dlg.Destroy()

        if result == wx.ID_YES:
            python = sys.executable
            os.execv(python, [python] + sys.argv)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _post_refresh(self):
        evt = RefreshEvent()
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)

    def _on_refresh(self, event=None):
        jobs = list(self.engine.jobs)
        existing_uids = set(self._cards.keys())
        job_uids      = {j.uid for j in jobs}

        for uid in existing_uids - job_uids:
            card = self._cards.pop(uid)
            self.job_sizer.Detach(card)
            card.Destroy()

        for job in jobs:
            if job.uid not in self._cards:
                card = JobCard(self.scroll, job, self.engine, self)
                self._cards[job.uid] = card
                self.job_sizer.Add(card, 0, wx.EXPAND | wx.BOTTOM, 8)
            else:
                self._cards[job.uid].refresh()

        self.lbl_empty.Show(len(jobs) == 0)

        running = sum(1 for j in jobs if j.status == Status.RUNNING)
        done    = sum(1 for j in jobs if j.status == Status.DONE)
        speed   = sum(j.speed for j in jobs if j.status == Status.RUNNING)
        stat    = T.get("stats_fmt",
                        "전체 {total}개  ·  실행 중 {running}개  ·  완료 {done}개  ·  세그먼트 {seg}개"
                        ).format(total=len(jobs), running=running, done=done, seg=self.engine.segments)
        if speed > 0:
            stat += T.get("stats_speed", "  ·  ↓ {speed}").format(speed=human_speed(speed))
        self.lbl_stats.SetLabel(stat)

        self.scroll.FitInside()
        self.scroll.Layout()
        self.scroll.Refresh()

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_quick_add(self, event=None):
        url = self.url_field.GetValue().strip()
        if url.startswith("http"):
            self.engine.add(url)
            self.url_field.SetValue("")

    def _on_add_url(self, event):
        dlg = wx.TextEntryDialog(self,
                                 T.get("dlg_add_url_prompt", "다운로드 URL:"),
                                 T.get("dlg_add_url_title",  "URL 추가"), "")
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue().strip()
            if url.startswith("http"):
                self.engine.add(url)
        dlg.Destroy()

    def _on_import_urls(self, event):
        dlg = wx.FileDialog(
            self, T.get("dlg_import_title", "URL 목록 파일 선택"),
            wildcard=T.get("dlg_import_filter",
                           "텍스트 파일 (*.txt)|*.txt|모든 파일 (*.*)|*.*"),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST
        )
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            urls = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    url = line.strip()
                    if url.startswith("http"):
                        urls.append(url)
            if self.chk_auto_dedup.GetValue():
                seen = set(); deduped = []
                for u in urls:
                    if u not in seen:
                        seen.add(u); deduped.append(u)
                urls = deduped
            self._import_urls = urls
            self._refresh_queue()
            self.notebook.SetSelection(3)
        dlg.Destroy()

    def _refresh_queue(self):
        self.queue_sizer.Clear(True)
        self._import_checks = []
        urls = self._import_urls

        if not urls:
            lbl = wx.StaticText(self.queue_scroll,
                                label=T.get("queue_empty", "임포트된 URL이 없습니다"))
            font_qe = lbl.GetFont()
            font_qe.SetPointSize(font_qe.GetPointSize() - 1)
            lbl.SetFont(font_qe)
            lbl.SetForegroundColour(wx.Colour(150, 150, 150))
            self.queue_sizer.Add(lbl, 0, wx.ALL, 20)
        else:
            grid = wx.FlexGridSizer(cols=3, vgap=4, hgap=8)
            grid.AddGrowableCol(2, 1)
            for i, url in enumerate(urls):
                chk = wx.CheckBox(self.queue_scroll)
                chk.SetValue(True)
                lbl_idx = wx.StaticText(self.queue_scroll, label=str(i + 1))
                lbl_idx.SetForegroundColour(wx.Colour(150, 150, 150))
                lbl_url = wx.StaticText(self.queue_scroll, label=url)
                grid.Add(chk,     0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
                grid.Add(lbl_idx, 0, wx.ALIGN_CENTER_VERTICAL)
                grid.Add(lbl_url, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
                self._import_checks.append(chk)
            self.queue_sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 8)

        self.lbl_queue_count.SetLabel(
            T.get("queue_count", "전체 {n}개").format(n=len(urls)))
        self.queue_scroll.FitInside()
        self.queue_scroll.Layout()
        self.queue_scroll.Refresh()

    def _on_queue_delete(self, event):
        remaining = [url for url, chk in zip(self._import_urls, self._import_checks)
                     if not chk.GetValue()]
        self._import_urls = remaining
        self._refresh_queue()

    def _on_queue_dedup(self, event):
        seen = set(); deduped = []
        for u in self._import_urls:
            if u not in seen:
                seen.add(u); deduped.append(u)
        removed = len(self._import_urls) - len(deduped)
        self._import_urls = deduped
        self._refresh_queue()
        wx.MessageBox(T.get("dedup_result", "{n}개의 중복 항목이 제거됐습니다.").format(n=removed),
                      T.get("dedup_title", "중복 제거"), wx.OK | wx.ICON_INFORMATION)

    def _on_queue_run(self, event):
        remaining = []
        for url, chk in zip(self._import_urls, self._import_checks):
            if chk.GetValue():
                self.engine.add(url)
            else:
                remaining.append(url)
        self._import_urls = remaining
        self._refresh_queue()
        self.notebook.SetSelection(0)

    def _on_browse(self, event):
        dlg = wx.DirDialog(self, T.get("dlg_dir_title", "다운로드 경로 선택"),
                           defaultPath=self.txt_dir.GetValue(),
                           style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST | wx.DD_NEW_DIR_BUTTON)
        if dlg.ShowModal() == wx.ID_OK:
            self.txt_dir.SetValue(dlg.GetPath())
            self._cfg["save_dir"] = dlg.GetPath()
            self.engine.save_dir  = dlg.GetPath()
            save_config(self._cfg)
        dlg.Destroy()

    def _on_seg_change(self, event):
        self._cfg["segments"] = self.spin_seg.GetValue()
        self.engine.segments  = self._cfg["segments"]
        save_config(self._cfg)

    def _on_notify_change(self, event):
        self._cfg["notify_on_complete"] = self.chk_notify.GetValue()
        save_config(self._cfg)

    def _on_clear_done(self, event):
        for j in list(self.engine.jobs):
            if j.status in (Status.DONE, Status.ERROR, Status.CANCELLED):
                self.engine.remove(j)

    def bring_to_front(self):
        wx.CallAfter(self._do_bring_to_front)

    def _do_bring_to_front(self):
        if self.IsIconized():
            self.Restore()
        self.Show()
        self.Raise()


# ─────────────────────────────────────────────────────────────────────────────
# macOS Menu Bar
# ─────────────────────────────────────────────────────────────────────────────

class StatusBarController:
    def __init__(self, frame: SwiftGetFrame):
        self.frame = frame
        self._bar  = AppKit.NSStatusBar.systemStatusBar()
        self._item = self._bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)
        self._item.setTitle_("SwiftGet")
        self._item.setHighlightMode_(True)

        menu = AppKit.NSMenu.alloc().init()

        show_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T.get("menu_open", "SwiftGet 열기"), "showWindow:", "")
        show_item.setTarget_(self)
        menu.addItem_(show_item)

        folder_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T.get("menu_folder", "다운로드 폴더"), "openFolder:", "")
        folder_item.setTarget_(self)
        menu.addItem_(folder_item)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            T.get("menu_quit", "종료"), "quitApp:", "q")
        quit_item.setTarget_(self)
        menu.addItem_(quit_item)

        self._item.setMenu_(menu)

    @objc.python_method
    def update_title(self, running: int, speed: float):
        title = f"↓ {human_speed(speed)}" if running > 0 else "SwiftGet"
        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
            lambda: self._item.setTitle_(title)
        )

    def showWindow_(self, sender):
        self.frame.bring_to_front()

    def openFolder_(self, sender):
        subprocess.Popen(["open", SAVE_DIR])

    def quitApp_(self, sender):
        wx.GetApp().ExitMainLoop()


# ─────────────────────────────────────────────────────────────────────────────
# Unix Socket Server
# ─────────────────────────────────────────────────────────────────────────────

def start_socket_server(engine: DownloadEngine, frame: SwiftGetFrame):
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(5)
    logging.info(f"Socket listening at {SOCKET_PATH}")

    def handle(conn):
        try:
            raw_len = conn.recv(4)
            if len(raw_len) < 4: return
            length = struct.unpack(">I", raw_len)[0]
            data = b""
            while len(data) < length:
                chunk = conn.recv(length - len(data))
                if not chunk: break
                data += chunk
            msg = json.loads(data.decode("utf-8"))
            logging.info(f"Socket message: {msg.get('action')}")
            if msg.get("action") == "download":
                engine.add(url=msg["url"], filename=msg.get("filename", ""),
                            referrer=msg.get("referrer", ""), cookies=msg.get("cookies", ""))
                frame.bring_to_front()
            elif msg.get("action") == "focus":
                frame.bring_to_front()
        except Exception as e:
            logging.error(f"Socket handler error: {e}")
        finally:
            conn.close()

    def serve():
        while True:
            try:
                conn, _ = server.accept()
                threading.Thread(target=handle, args=(conn,), daemon=True).start()
            except Exception as e:
                logging.error(f"Socket accept error: {e}")
                break

    threading.Thread(target=serve, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Native Messaging 자동 등록
# ─────────────────────────────────────────────────────────────────────────────

def register_native_messaging():
    manifest_dir  = os.path.expanduser(
        "~/Library/Application Support/Mozilla/NativeMessagingHosts")
    manifest_path = os.path.join(manifest_dir, "app.swiftget.downloader.json")

    resources_dir = os.path.dirname(os.path.abspath(__file__))
    contents_dir  = os.path.dirname(resources_dir)
    macos_dir     = os.path.join(contents_dir, "MacOS")
    host_path     = os.path.join(macos_dir, "swiftget-host")

    manifest = {
        "name":               "app.swiftget.downloader",
        "description":        "SwiftGet Download Manager Native Host",
        "path":               host_path,
        "type":               "stdio",
        "allowed_extensions": ["swiftget@downloader.app"]
    }

    try:
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                existing = json.load(f)
            if existing.get("path") == host_path:
                return
        os.makedirs(manifest_dir, exist_ok=True)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        logging.info(f"Native Messaging 매니페스트 등록 완료: {manifest_path}")
    except Exception as e:
        logging.warning(f"Native Messaging 등록 실패: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    dev_mode = "--dev" in sys.argv

    if not dev_mode:
        register_native_messaging()

    app    = wx.App(False)
    engine = DownloadEngine(on_update=lambda: None)
    frame  = SwiftGetFrame(engine, dev_mode=dev_mode)

    start_socket_server(engine, frame)
    status_bar = StatusBarController(frame)

    def update_dock_progress(pct: float, visible: bool):
        try:
            app_kit   = AppKit.NSApplication.sharedApplication()
            dock_tile = app_kit.dockTile()
            if visible and 0.0 <= pct <= 1.0:
                AppKit.NSApp.setApplicationIconImage_(AppKit.NSApp.applicationIconImage())
                content_view = dock_tile.contentView()
                if content_view is None:
                    icon = AppKit.NSApp.applicationIconImage()
                    image_view = AppKit.NSImageView.alloc().initWithFrame_(
                        AppKit.NSMakeRect(0, 0, 128, 128))
                    image_view.setImage_(icon)
                    dock_tile.setContentView_(image_view)
                    content_view = image_view

                icon_size = 128
                bar_h = 12; bar_y = 4; bar_x = 8
                bar_w = icon_size - bar_x * 2

                image = AppKit.NSImage.alloc().initWithSize_(
                    AppKit.NSMakeSize(icon_size, icon_size))
                image.lockFocus()

                app_icon = AppKit.NSApp.applicationIconImage()
                app_icon.drawInRect_(AppKit.NSMakeRect(0, 0, icon_size, icon_size))

                bg = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.3, 0.3, 0.3, 0.85)
                bg.setFill()
                AppKit.NSBezierPath.fillRect_(AppKit.NSMakeRect(bar_x, bar_y, bar_w, bar_h))

                fill_w = bar_w * pct
                fg = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.78, 0.35, 1.0)
                fg.setFill()
                AppKit.NSBezierPath.fillRect_(AppKit.NSMakeRect(bar_x, bar_y, fill_w, bar_h))

                image.unlockFocus()
                dock_tile.setContentView_(None)
                AppKit.NSApp.setApplicationIconImage_(image)
            else:
                AppKit.NSApp.setApplicationIconImage_(None)
            dock_tile.display()
        except Exception as e:
            logging.debug(f"Dock progress error: {e}")

    _last_dock_pct     = [-1.0]
    _last_dock_visible = [None]

    def update_loop():
        while True:
            time.sleep(0.5)
            running = sum(1 for j in engine.jobs if j.status == Status.RUNNING)
            speed   = sum(j.speed for j in engine.jobs if j.status == Status.RUNNING)
            try:
                status_bar.update_title(running, speed)
            except:
                pass
            try:
                running_jobs = [j for j in engine.jobs if j.status == Status.RUNNING]
                if running_jobs:
                    total_dl = sum(j.downloaded for j in running_jobs if j.total > 0)
                    total_sz = sum(j.total      for j in running_jobs if j.total > 0)
                    pct      = round((total_dl / total_sz) if total_sz > 0 else 0.0, 2)
                    visible  = True
                else:
                    pct = 0.0; visible = False

                if (visible != _last_dock_visible[0] or
                        abs(pct - _last_dock_pct[0]) >= 0.01):
                    _last_dock_pct[0]     = pct
                    _last_dock_visible[0] = visible
                    AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                        lambda p=pct, v=visible: update_dock_progress(p, v))
            except:
                pass

    threading.Thread(target=update_loop, daemon=True).start()
    app.MainLoop()

if __name__ == "__main__":
    main()