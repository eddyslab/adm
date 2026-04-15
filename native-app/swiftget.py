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
import http.client
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import logging
import subprocess
import AppKit
import objc

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

_DEFAULTS = {
    "save_dir":           os.path.expanduser("~/Downloads"),
    "segments":           8,
    "notify_on_complete": True,
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

_cfg     = load_config()
SAVE_DIR = _cfg["save_dir"]
SEGMENTS = _cfg["segments"]

# ─────────────────────────────────────────────────────────────────────────────
# Download Engine  (unchanged)
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
    seg_downloaded: list = field(default_factory=list, repr=False)  # bytes per segment
    seg_sizes:      list = field(default_factory=list, repr=False)  # total bytes per segment
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

        # Initialise per-segment tracking
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

# Custom event to trigger UI refresh from background threads
EVT_REFRESH_ID = wx.NewEventType()
EVT_REFRESH    = wx.PyEventBinder(EVT_REFRESH_ID, 1)

class RefreshEvent(wx.PyCommandEvent):
    def __init__(self):
        super().__init__(EVT_REFRESH_ID)


# ── Segment progress bar ──────────────────────────────────────────────────────

class SegmentBar(wx.Panel):
    """Shows individual segment progress as coloured blocks side by side."""

    COL_DONE    = wx.Colour(52,  199,  89)   # green  — complete
    COL_ACTIVE  = wx.Colour(10,  132, 255)   # blue   — in progress
    COL_QUEUED  = wx.Colour(210, 210, 210)   # grey   — not started
    COL_PAUSED  = wx.Colour(255, 159,  10)   # amber  — paused
    COL_ERROR   = wx.Colour(255,  59,  48)   # red    — error
    GAP         = 2                          # px gap between segments

    def __init__(self, parent):
        super().__init__(parent, size=(-1, 5))
        self.SetMinSize((-1, 5))
        self._fractions: list[float] = []   # 0.0–1.0 per segment
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
            x = int(i * (seg_w + self.GAP))
            sw = int(seg_w)

            # Background track
            dc.SetBrush(wx.Brush(self.COL_QUEUED))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(x, 0, sw, h)

            # Filled portion
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
    """One download item rendered as a native card."""

    # Status colours — works in both light and dark mode
    STATUS_COLOUR = {
        Status.QUEUED:    wx.Colour(150, 150, 150),
        Status.RUNNING:   wx.Colour(52,  199,  89),   # macOS green
        Status.PAUSED:    wx.Colour(255, 159,  10),   # macOS yellow
        Status.DONE:      wx.Colour(52,  199,  89),
        Status.ERROR:     wx.Colour(255,  59,  48),   # macOS red
        Status.CANCELLED: wx.Colour(150, 150, 150),
    }
    STATUS_LABEL = {
        Status.QUEUED:    "대기",
        Status.RUNNING:   "다운로드 중",
        Status.PAUSED:    "일시정지",
        Status.DONE:      "완료",
        Status.ERROR:     "오류",
        Status.CANCELLED: "취소됨",
    }

    def __init__(self, parent, job: DownloadJob, engine: DownloadEngine, main_frame):
        super().__init__(parent, style=wx.BORDER_THEME)
        self.job        = job
        self.engine     = engine
        self.main_frame = main_frame

        # 카드 배경을 시스템 배경보다 약간 밝게
        base = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
        r = min(255, base.Red()   + 10)
        g = min(255, base.Green() + 10)
        b = min(255, base.Blue()  + 10)
        self.SetBackgroundColour(wx.Colour(r, g, b))

        root = wx.BoxSizer(wx.VERTICAL)
        root.AddSpacer(10)

        # ── Row 1: filename + status label ──
        r1 = wx.BoxSizer(wx.HORIZONTAL)
        self.lbl_name = wx.StaticText(self, label=job.filename)
        font = self.lbl_name.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        font.SetPointSize(font.GetPointSize() + 1)
        self.lbl_name.SetFont(font)

        self.lbl_status = wx.StaticText(self, label="")
        r1.Add(self.lbl_name,  1, wx.ALIGN_CENTER_VERTICAL)
        r1.Add(self.lbl_status, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        root.Add(r1, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 14)

        root.AddSpacer(8)

        # ── Row 2: progress bar ──
        self.gauge = wx.Gauge(self, range=1000, style=wx.GA_HORIZONTAL | wx.GA_SMOOTH)
        self.gauge.SetMinSize((-1, 6))
        root.Add(self.gauge, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 14)

        root.AddSpacer(4)

        # ── Row 2b: per-segment bars (hidden until segmented download starts) ──
        self.seg_bar = SegmentBar(self)
        self.seg_bar.Hide()
        root.Add(self.seg_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 14)

        root.AddSpacer(6)

        # ── Row 3: info text + buttons ──
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

        # Bind button events
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

        # Progress gauge (range 0–1000 for smooth rendering)
        self.gauge.SetValue(int(pct * 1000))

        # Segment bars — show only when segmented data is available
        has_segs = bool(job.seg_sizes)
        if has_segs != self.seg_bar.IsShown():
            self.seg_bar.Show(has_segs)
        if has_segs:
            self.seg_bar.update(job)

        # Status label + colour
        colour = self.STATUS_COLOUR.get(job.status, wx.Colour(150, 150, 150))
        self.lbl_status.SetLabel(self.STATUS_LABEL.get(job.status, ""))
        self.lbl_status.SetForegroundColour(colour)

        # Info text
        if job.status == Status.ERROR:
            info = f"오류: {job.error_msg[:80]}"
        else:
            info = human_size(job.downloaded)
            if job.total > 0:
                info += f" / {human_size(job.total)}  ({pct*100:.0f}%)"
            if job.status == Status.RUNNING and job.speed > 0:
                info += f"  ·  {human_speed(job.speed)}"
                if job.eta >= 0:
                    info += f"  ·  남은 시간 {human_eta(job.eta)}"
        self.lbl_info.SetLabel(info)

        # Show/hide buttons based on status
        s = job.status
        self.btn_pause.Show( s == Status.RUNNING)
        self.btn_resume.Show(s == Status.PAUSED)
        self.btn_cancel.Show(s in (Status.RUNNING, Status.PAUSED, Status.QUEUED))
        self.btn_reveal.Show(s == Status.DONE)
        self.btn_remove.Show(s in (Status.DONE, Status.ERROR, Status.CANCELLED))
        self.btn_retry.Show( s == Status.ERROR)

        self.Layout()


# ── Settings dialog ───────────────────────────────────────────────────────────

class SettingsDialog(wx.Dialog):
    def __init__(self, parent, cfg: dict):
        super().__init__(parent, title="SwiftGet 설정",
                         style=wx.DEFAULT_DIALOG_STYLE,
                         size=(480, 300))
        self.cfg = dict(cfg)

        root = wx.BoxSizer(wx.VERTICAL)

        # ── 탭 ──
        notebook = wx.Notebook(self)

        # ── 탭 1: 다운로드 ──
        tab_dl = wx.Panel(notebook)
        grid_dl = wx.FlexGridSizer(cols=3, vgap=14, hgap=10)
        grid_dl.AddGrowableCol(1, 1)

        grid_dl.Add(wx.StaticText(tab_dl, label="다운로드 경로:"),
                    0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_dir = wx.TextCtrl(tab_dl, value=cfg["save_dir"])
        grid_dl.Add(self.txt_dir, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        btn_browse = wx.Button(tab_dl, label="찾아보기…", size=(90, -1))
        grid_dl.Add(btn_browse, 0, wx.ALIGN_CENTER_VERTICAL)

        grid_dl.Add(wx.StaticText(tab_dl, label="기본 세그먼트 수:"),
                    0, wx.ALIGN_CENTER_VERTICAL)
        self.spin_seg = wx.SpinCtrl(tab_dl, value=str(cfg["segments"]),
                                    min=1, max=32, size=(64, -1))
        grid_dl.Add(self.spin_seg, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_dl.Add(wx.StaticText(tab_dl, label="(1 = 분할 안 함)"),
                    0, wx.ALIGN_CENTER_VERTICAL)

        tab_dl_sizer = wx.BoxSizer(wx.VERTICAL)
        tab_dl_sizer.Add(grid_dl, 0, wx.EXPAND | wx.ALL, 16)
        tab_dl.SetSizer(tab_dl_sizer)
        notebook.AddPage(tab_dl, "다운로드")

        # ── 탭 2: 알림 (todo #1 대비 미리 구성) ──
        tab_notify = wx.Panel(notebook)
        grid_notify = wx.FlexGridSizer(cols=2, vgap=14, hgap=10)
        grid_notify.AddGrowableCol(1, 1)

        grid_notify.Add(wx.StaticText(tab_notify, label="다운로드 완료 알림:"),
                        0, wx.ALIGN_CENTER_VERTICAL)
        self.chk_notify = wx.CheckBox(tab_notify, label="완료 시 알림 표시")
        self.chk_notify.SetValue(cfg.get("notify_on_complete", True))
        grid_notify.Add(self.chk_notify, 0, wx.ALIGN_CENTER_VERTICAL)

        tab_notify_sizer = wx.BoxSizer(wx.VERTICAL)
        tab_notify_sizer.Add(grid_notify, 0, wx.EXPAND | wx.ALL, 16)
        tab_notify.SetSizer(tab_notify_sizer)
        notebook.AddPage(tab_notify, "알림")

        root.Add(notebook, 1, wx.EXPAND | wx.ALL, 10)

        # ── OK / Cancel ──
        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        root.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.SetSizer(root)
        self.Centre()

        btn_browse.Bind(wx.EVT_BUTTON, self._on_browse)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _on_browse(self, event):
        dlg = wx.DirDialog(self, "다운로드 경로 선택",
                           defaultPath=self.txt_dir.GetValue(),
                           style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST | wx.DD_NEW_DIR_BUTTON)
        if dlg.ShowModal() == wx.ID_OK:
            self.txt_dir.SetValue(dlg.GetPath())
        dlg.Destroy()

    def _on_ok(self, event):
        self.cfg["save_dir"]          = self.txt_dir.GetValue().strip()
        self.cfg["segments"]          = self.spin_seg.GetValue()
        self.cfg["notify_on_complete"]= self.chk_notify.GetValue()
        event.Skip()

    def get_config(self) -> dict:
        return self.cfg


# ── Main window ───────────────────────────────────────────────────────────────

class SwiftGetFrame(wx.Frame):
    def __init__(self, engine: DownloadEngine, dev_mode: bool = False):
        super().__init__(None, title="SwiftGet", size=(780, 560),
                         style=wx.DEFAULT_FRAME_STYLE)
        self.engine   = engine
        self.dev_mode = dev_mode
        self._cards: dict[str, JobCard] = {}   # uid → JobCard
        self._cfg     = load_config()

        self.engine.on_update    = self._post_refresh
        self.engine.segments     = self._cfg["segments"]
        self.engine.save_dir     = self._cfg["save_dir"]

        self._build_ui()
        self.Centre()
        self.Show()

        # Bind our custom refresh event
        self.Bind(EVT_REFRESH, self._on_refresh)

        # Periodic fallback refresh (every 500 ms)
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_refresh, self._timer)
        self._timer.Start(500)

        # 윈도우 닫기 이벤트
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _on_close(self, event):
        if self.dev_mode:
            # 개발 모드: 완전 종료
            self._timer.Stop()
            wx.GetApp().ExitMainLoop()
        else:
            # 일반 모드: 창만 숨김 (메뉴바 상주)
            self.Hide()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        panel = wx.Panel(self)
        root  = wx.BoxSizer(wx.VERTICAL)

        # ── 로고 헤더 (탭 위 공통 영역) ──
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
        root.Add(hdr, 0, wx.LEFT | wx.TOP, 16)
        root.AddSpacer(10)

        # ── 메인 탭 ──
        self.notebook = wx.Notebook(panel)

        # ════════════════════════════════
        # 탭 1: 일반 (다운로드 목록)
        # ════════════════════════════════
        tab_main = wx.Panel(self.notebook)
        sizer_main = wx.BoxSizer(wx.VERTICAL)

        # 툴바
        tb = wx.BoxSizer(wx.HORIZONTAL)
        btn_clear  = wx.Button(tab_main, label="완료 항목 지우기")
        btn_folder = wx.Button(tab_main, label="폴더 열기")
        btn_add    = wx.Button(tab_main, label="＋ URL 추가")
        tb.AddStretchSpacer()
        tb.Add(btn_clear,  0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        tb.Add(btn_folder, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        tb.Add(btn_add,    0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 6)
        sizer_main.Add(tb, 0, wx.EXPAND | wx.ALL, 10)

        # URL 입력
        url_row = wx.BoxSizer(wx.HORIZONTAL)
        self.url_field = wx.TextCtrl(tab_main, style=wx.TE_PROCESS_ENTER, size=(-1, 30))
        self.url_field.SetHint("URL을 여기에 붙여넣기...")
        btn_dl = wx.Button(tab_main, label="다운로드", size=(-1, 30))
        url_row.Add(self.url_field, 1, wx.ALIGN_CENTER_VERTICAL)
        url_row.Add(btn_dl, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        sizer_main.Add(url_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # 통계
        self.lbl_stats = wx.StaticText(tab_main, label="대기 중...")
        sizer_main.Add(self.lbl_stats, 0, wx.LEFT | wx.BOTTOM, 10)

        # 다운로드 목록
        self.scroll = scrolled.ScrolledPanel(tab_main, style=wx.BORDER_NONE)
        self.scroll.SetupScrolling(scroll_x=False)
        self.job_sizer = wx.BoxSizer(wx.VERTICAL)
        self.scroll.SetSizer(self.job_sizer)

        self.lbl_empty = wx.StaticText(self.scroll, label="다운로드 항목이 없습니다")
        font_e = self.lbl_empty.GetFont()
        font_e.SetPointSize(font_e.GetPointSize() - 1)
        self.lbl_empty.SetFont(font_e)
        self.lbl_empty.SetForegroundColour(wx.Colour(150, 150, 150))
        self.job_sizer.Add(self.lbl_empty, 0, wx.ALL, 20)

        sizer_main.Add(self.scroll, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        tab_main.SetSizer(sizer_main)
        self.notebook.AddPage(tab_main, "일반")

        # ════════════════════════════════
        # 탭 2: 다운로드 설정
        # ════════════════════════════════
        tab_dl = wx.Panel(self.notebook)
        grid_dl = wx.FlexGridSizer(cols=3, vgap=14, hgap=10)
        grid_dl.AddGrowableCol(1, 1)

        grid_dl.Add(wx.StaticText(tab_dl, label="다운로드 경로:"),
                    0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_dir = wx.TextCtrl(tab_dl, value=self._cfg["save_dir"])
        grid_dl.Add(self.txt_dir, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        btn_browse = wx.Button(tab_dl, label="찾아보기…", size=(90, -1))
        grid_dl.Add(btn_browse, 0, wx.ALIGN_CENTER_VERTICAL)

        grid_dl.Add(wx.StaticText(tab_dl, label="기본 세그먼트 수:"),
                    0, wx.ALIGN_CENTER_VERTICAL)
        self.spin_seg = wx.SpinCtrl(tab_dl, value=str(self._cfg["segments"]),
                                    min=1, max=32, size=(64, -1))
        grid_dl.Add(self.spin_seg, 0, wx.ALIGN_CENTER_VERTICAL)
        grid_dl.Add(wx.StaticText(tab_dl, label="(1 = 분할 안 함)"),
                    0, wx.ALIGN_CENTER_VERTICAL)

        sizer_dl = wx.BoxSizer(wx.VERTICAL)
        sizer_dl.Add(grid_dl, 0, wx.EXPAND | wx.ALL, 16)
        tab_dl.SetSizer(sizer_dl)
        self.notebook.AddPage(tab_dl, "다운로드")

        # ════════════════════════════════
        # 탭 3: 알림 설정
        # ════════════════════════════════
        tab_notify = wx.Panel(self.notebook)
        grid_notify = wx.FlexGridSizer(cols=2, vgap=14, hgap=10)
        grid_notify.AddGrowableCol(1, 1)

        grid_notify.Add(wx.StaticText(tab_notify, label="다운로드 완료 알림:"),
                        0, wx.ALIGN_CENTER_VERTICAL)
        self.chk_notify = wx.CheckBox(tab_notify, label="완료 시 알림 표시")
        self.chk_notify.SetValue(self._cfg.get("notify_on_complete", True))
        grid_notify.Add(self.chk_notify, 0, wx.ALIGN_CENTER_VERTICAL)

        sizer_notify = wx.BoxSizer(wx.VERTICAL)
        sizer_notify.Add(grid_notify, 0, wx.EXPAND | wx.ALL, 16)
        tab_notify.SetSizer(sizer_notify)
        self.notebook.AddPage(tab_notify, "알림")

        root.Add(self.notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        panel.SetSizer(root)

        # Events
        btn_add.Bind(   wx.EVT_BUTTON,     self._on_add_url)
        btn_clear.Bind( wx.EVT_BUTTON,     self._on_clear_done)
        btn_folder.Bind(wx.EVT_BUTTON,     lambda e: subprocess.Popen(["open", self.engine.save_dir]))
        btn_dl.Bind(    wx.EVT_BUTTON,     self._on_quick_add)
        btn_browse.Bind(wx.EVT_BUTTON,     self._on_browse)
        self.url_field.Bind(wx.EVT_TEXT_ENTER, self._on_quick_add)
        self.spin_seg.Bind(wx.EVT_SPINCTRL,    self._on_seg_change)
        self.chk_notify.Bind(wx.EVT_CHECKBOX,  self._on_notify_change)
        self.notebook.SetSelection(0)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _post_refresh(self):
        """Called from background threads — safely posts to the main thread."""
        evt = RefreshEvent()
        evt.SetEventObject(self)
        wx.PostEvent(self, evt)

    def _on_refresh(self, event=None):
        jobs = list(self.engine.jobs)
        existing_uids = set(self._cards.keys())
        job_uids      = {j.uid for j in jobs}

        # Remove cards for deleted jobs
        for uid in existing_uids - job_uids:
            card = self._cards.pop(uid)
            self.job_sizer.Detach(card)
            card.Destroy()

        # Add cards for new jobs; refresh existing
        for job in jobs:
            if job.uid not in self._cards:
                card = JobCard(self.scroll, job, self.engine, self)
                self._cards[job.uid] = card
                self.job_sizer.Add(card, 0, wx.EXPAND | wx.BOTTOM, 8)
            else:
                self._cards[job.uid].refresh()

        # Empty state
        self.lbl_empty.Show(len(jobs) == 0)

        # Stats bar
        running = sum(1 for j in jobs if j.status == Status.RUNNING)
        done    = sum(1 for j in jobs if j.status == Status.DONE)
        speed   = sum(j.speed for j in jobs if j.status == Status.RUNNING)
        stat    = f"전체 {len(jobs)}개  ·  실행 중 {running}개  ·  완료 {done}개  ·  세그먼트 {self.engine.segments}개"
        if speed > 0:
            stat += f"  ·  ↓ {human_speed(speed)}"
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
        dlg = wx.TextEntryDialog(self, "다운로드 URL:", "URL 추가", "")
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue().strip()
            if url.startswith("http"):
                self.engine.add(url)
        dlg.Destroy()

    def _on_browse(self, event):
        dlg = wx.DirDialog(self, "다운로드 경로 선택",
                           defaultPath=self.txt_dir.GetValue(),
                           style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST | wx.DD_NEW_DIR_BUTTON)
        if dlg.ShowModal() == wx.ID_OK:
            self.txt_dir.SetValue(dlg.GetPath())
            self._cfg["save_dir"] = dlg.GetPath()
            self.engine.save_dir  = dlg.GetPath()
            save_config(self._cfg)
        dlg.Destroy()

    def _on_seg_change(self, event):
        self._cfg["segments"]  = self.spin_seg.GetValue()
        self.engine.segments   = self._cfg["segments"]
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
# macOS Menu Bar (AppKit — same as before)
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
            "SwiftGet 열기", "showWindow:", "")
        show_item.setTarget_(self)
        menu.addItem_(show_item)

        folder_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "다운로드 폴더", "openFolder:", "")
        folder_item.setTarget_(self)
        menu.addItem_(folder_item)

        menu.addItem_(AppKit.NSMenuItem.separatorItem())

        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "종료", "quitApp:", "q")
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
    """첫 실행 시 Firefox Native Messaging 매니페스트를 자동 등록."""
    manifest_dir  = os.path.expanduser(
        "~/Library/Application Support/Mozilla/NativeMessagingHosts")
    manifest_path = os.path.join(manifest_dir, "app.swiftget.downloader.json")

    # 번들 내 MacOS 폴더를 확실하게 찾기
    # __file__ 은 Resources/swiftget.py 를 가리킴
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
        # 이미 동일한 내용이면 스킵
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
        """Dock 아이콘 하단에 프로그레스 바 표시 (AppKit NSDockTile)."""
        try:
            app_kit = AppKit.NSApplication.sharedApplication()
            dock_tile = app_kit.dockTile()
            if visible and 0.0 <= pct <= 1.0:
                AppKit.NSApp.setApplicationIconImage_(AppKit.NSApp.applicationIconImage())
                # NSDockTile progress via badgeLabel trick — use NSProgress
                # macOS 10.12+ 에서 지원하는 NSDockTile.showsApplicationBadge 대신
                # NSProgressIndicator 를 dockTile contentView 에 올리는 방식 사용
                content_view = dock_tile.contentView()
                if content_view is None:
                    # 아이콘 이미지를 contentView 로 설정
                    icon = AppKit.NSApp.applicationIconImage()
                    image_view = AppKit.NSImageView.alloc().initWithFrame_(
                        AppKit.NSMakeRect(0, 0, 128, 128)
                    )
                    image_view.setImage_(icon)
                    dock_tile.setContentView_(image_view)
                    content_view = image_view

                # 진행바 레이어를 그려서 dockTile 갱신
                icon_size = 128
                bar_h = 12
                bar_y = 4
                bar_x = 8
                bar_w = icon_size - bar_x * 2

                image = AppKit.NSImage.alloc().initWithSize_(
                    AppKit.NSMakeSize(icon_size, icon_size)
                )
                image.lockFocus()

                # 앱 아이콘 그리기
                app_icon = AppKit.NSApp.applicationIconImage()
                app_icon.drawInRect_(AppKit.NSMakeRect(0, 0, icon_size, icon_size))

                # 진행바 배경 (회색)
                bg = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.3, 0.3, 0.3, 0.85)
                bg.setFill()
                AppKit.NSBezierPath.fillRect_(
                    AppKit.NSMakeRect(bar_x, bar_y, bar_w, bar_h))

                # 진행바 채우기 (녹색)
                fill_w = bar_w * pct
                fg = AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.2, 0.78, 0.35, 1.0)
                fg.setFill()
                AppKit.NSBezierPath.fillRect_(
                    AppKit.NSMakeRect(bar_x, bar_y, fill_w, bar_h))

                image.unlockFocus()
                dock_tile.setContentView_(None)
                AppKit.NSApp.setApplicationIconImage_(image)
            else:
                # 원래 아이콘으로 복원
                AppKit.NSApp.setApplicationIconImage_(None)

            dock_tile.display()
        except Exception as e:
            logging.debug(f"Dock progress error: {e}")

    _last_dock_pct     = [-1.0]   # 이전 진행률 캐시
    _last_dock_visible = [None]   # 이전 표시 여부 캐시

    def update_loop():
        while True:
            time.sleep(0.5)
            running = sum(1 for j in engine.jobs if j.status == Status.RUNNING)
            speed   = sum(j.speed for j in engine.jobs if j.status == Status.RUNNING)
            try:
                status_bar.update_title(running, speed)
            except:
                pass

            # Dock 프로그레스 바 — 변화가 있을 때만 업데이트
            try:
                running_jobs = [j for j in engine.jobs if j.status == Status.RUNNING]
                if running_jobs:
                    total_dl = sum(j.downloaded for j in running_jobs if j.total > 0)
                    total_sz = sum(j.total      for j in running_jobs if j.total > 0)
                    pct = round((total_dl / total_sz) if total_sz > 0 else 0.0, 2)
                    visible = True
                else:
                    pct = 0.0
                    visible = False

                # 1% 이상 변화 또는 표시 여부 변경 시에만 갱신
                if (visible != _last_dock_visible[0] or
                        abs(pct - _last_dock_pct[0]) >= 0.01):
                    _last_dock_pct[0]     = pct
                    _last_dock_visible[0] = visible
                    AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                        lambda p=pct, v=visible: update_dock_progress(p, v)
                    )
            except:
                pass

    threading.Thread(target=update_loop, daemon=True).start()

    app.MainLoop()

if __name__ == "__main__":
    main()