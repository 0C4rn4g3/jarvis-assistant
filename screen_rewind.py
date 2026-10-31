"""Jarvis Episodic Screen Time-Machine (Local Rewind).
Captures lightweight screen frames every 12-15 seconds when active window changes,
runs rapid zero-VRAM Windows Native OCR, and indexes text + metadata into SQLite FTS5.
Allows querying: "What was that GitHub repo with the packet listener I looked at yesterday?"
"""
import asyncio
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

import hardware
import system

DB_PATH = os.path.join(system.DATA, "jarvis_temporal.db")
_db_lock = threading.Lock()
RETENTION_SECONDS = 7 * 86400  # 7 days


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db_lock:
        os.makedirs(system.DATA, exist_ok=True)
        conn = get_db()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS screen_frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    app_name TEXT,
                    window_title TEXT,
                    ocr_text TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_screen_frames_ts ON screen_frames(timestamp DESC)")
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS screen_rewind_fts USING fts5(
                    app_name,
                    window_title,
                    ocr_text,
                    content='screen_frames',
                    content_rowid='id'
                )
            """)
            # Triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS trg_screen_frames_insert AFTER INSERT ON screen_frames BEGIN
                    INSERT INTO screen_rewind_fts(rowid, app_name, window_title, ocr_text)
                    VALUES (new.id, new.app_name, new.window_title, new.ocr_text);
                END;
            """)
        conn.close()


init_db()


def extract_ocr_text_from_bgra(bgra_bytes: bytes, width: int, height: int) -> str:
    """Uses Windows Native WinRT OCR engine to extract text with zero VRAM usage."""
    if not bgra_bytes or width <= 0 or height <= 0:
        return ""
    try:
        import winsdk.windows.graphics.imaging as imaging
        import winsdk.windows.media.ocr as ocr
        import winsdk.windows.storage.streams as streams

        engine = ocr.OcrEngine.try_create_from_user_profile_languages()
        if not engine:
            return ""

        import numpy as np

        # Downsample 2x if high-res (>1280px) to slash memory and OCR latency by 4x
        if width > 1280:
            arr = np.frombuffer(bgra_bytes, dtype=np.uint8).reshape((height, width, 4))
            downsampled = np.ascontiguousarray(arr[::2, ::2, :])
            width, height = downsampled.shape[1], downsampled.shape[0]
            bgra_bytes = downsampled.tobytes()

        writer = streams.DataWriter()
        writer.write_bytes(bgra_bytes)
        ibuffer = writer.detach_buffer()

        bitmap = imaging.SoftwareBitmap.create_copy_from_buffer(
            ibuffer, imaging.BitmapPixelFormat.BGRA8, width, height
        )

        async def _run():
            res = await engine.recognize_async(bitmap)
            return res.text or ""

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(_run(), loop)
                return future.result(timeout=5)
            else:
                return loop.run_until_complete(_run())
        except Exception:
            return asyncio.run(_run())
    except Exception:
        return ""


def record_screen_frame(app_name: str, window_title: str, ocr_text: str = "") -> Optional[int]:
    """Records an episodic screen frame into SQLite and FTS5."""
    now = time.time()
    with _db_lock:
        conn = get_db()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO screen_frames (timestamp, app_name, window_title, ocr_text) VALUES (?, ?, ?, ?)",
                    (now, app_name, window_title, ocr_text),
                )
                row_id = cur.lastrowid
                # Purge older than 7 days
                conn.execute("DELETE FROM screen_frames WHERE timestamp < ?", (now - RETENTION_SECONDS,))
            return row_id
        finally:
            conn.close()


def search_screen_rewind(query: str, minutes_ago: Optional[int] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Full-text search over episodic screen rewind memory."""
    if not query or not query.strip():
        return []

    # Clean query for FTS5 syntax
    clean_q = re.sub(r"[^\w\s]", " ", query).strip()
    if not clean_q:
        return []

    fts_query = " OR ".join(f'"{word}"' for word in clean_q.split() if len(word) >= 2)
    now = time.time()
    min_ts = (now - minutes_ago * 60) if minutes_ago else 0.0

    with _db_lock:
        conn = get_db()
        try:
            cur = conn.execute("""
                SELECT f.id, f.timestamp, f.app_name, f.window_title,
                       snippet(screen_rewind_fts, 2, '<b>', '</b>', '...', 24) as snippet,
                       f.ocr_text
                FROM screen_rewind_fts s
                JOIN screen_frames f ON f.id = s.rowid
                WHERE screen_rewind_fts MATCH ? AND f.timestamp >= ?
                ORDER BY rank
                LIMIT ?
            """, (fts_query, min_ts, limit))

            results = []
            for row in cur.fetchall():
                elapsed = now - row["timestamp"]
                if elapsed < 60:
                    time_ago = f"{int(elapsed)}s ago"
                elif elapsed < 3600:
                    time_ago = f"{int(elapsed // 60)}m ago"
                elif elapsed < 86400:
                    time_ago = f"{int(elapsed // 3600)}h ago"
                else:
                    time_ago = f"{int(elapsed // 86400)}d ago"

                results.append({
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "time_ago": time_ago,
                    "app_name": row["app_name"],
                    "window_title": row["window_title"],
                    "snippet": row["snippet"] or (row["ocr_text"][:200] if row["ocr_text"] else ""),
                })
            return results
        finally:
            conn.close()


def get_recent_timeline(limit: int = 15) -> List[Dict[str, Any]]:
    """Returns recent episodic timeline frames."""
    now = time.time()
    with _db_lock:
        conn = get_db()
        try:
            cur = conn.execute("""
                SELECT id, timestamp, app_name, window_title, SUBSTR(ocr_text, 1, 150) as preview
                FROM screen_frames
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            out = []
            for r in cur.fetchall():
                elapsed = now - r["timestamp"]
                out.append({
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "time_ago": f"{int(elapsed // 60)}m ago" if elapsed >= 60 else f"{int(elapsed)}s ago",
                    "app_name": r["app_name"],
                    "window_title": r["window_title"],
                    "preview": r["preview"] or "",
                })
            return out
        finally:
            conn.close()


# ---------------------------------------------------------------- Background Rewind Sampler
class ScreenRewindSampler:
    def __init__(self, interval: float = 18.0):
        self.interval = interval
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True

        def _loop():
            last_title = ""
            last_app = ""
            while self.running:
                try:
                    time.sleep(self.interval)

                    # 1. Skip if heavy 3D game active
                    if hardware.is_gaming_active():
                        continue

                    # 2. Check active foreground window
                    app = system.active_app()
                    import pywinctl
                    w = pywinctl.getActiveWindow()
                    title = (w.title or "").strip() if w else ""

                    if not app and not title:
                        continue

                    # 3. Only sample when window context changes
                    if app == last_app and title == last_title:
                        continue

                    last_app, last_title = app, title

                    # 4. Attempt rapid OCR capture if interactive desktop
                    ocr_text = ""
                    try:
                        import mss
                        with mss.mss() as sct:
                            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                            # sample 800x600 scaled region
                            shot = sct.grab(mon)
                            ocr_text = extract_ocr_text_from_bgra(bytes(shot.bgra), shot.width, shot.height)
                    except Exception:
                        pass

                    record_screen_frame(app_name=app, window_title=title, ocr_text=ocr_text)

                except Exception:
                    time.sleep(self.interval)

        self._thread = threading.Thread(target=_loop, daemon=True, name="ScreenRewindSamplerLoop")
        self._thread.start()

    def stop(self):
        self.running = False


_sampler_instance: Optional[ScreenRewindSampler] = None


def get_rewind_sampler() -> ScreenRewindSampler:
    global _sampler_instance
    if _sampler_instance is None:
        _sampler_instance = ScreenRewindSampler()
    return _sampler_instance
