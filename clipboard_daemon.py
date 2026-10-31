"""Jarvis Clipboard History and Smart Transform Daemon.
Monitors the Windows clipboard, stores a 50-entry rolling ring buffer in SQLite,
classifies copied content (stack traces, JSON, cURL, SQL, Java),
and generates one-click smart transformations with Screen Notch suggestions.
"""
import json
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

import system

DB_PATH = os.path.join(system.DATA, "jarvis_temporal.db")
_db_lock = threading.Lock()
MAX_HISTORY = 50


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
                CREATE TABLE IF NOT EXISTS clipboard_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    app_source TEXT,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clipboard_created ON clipboard_history(created_at DESC)")
        conn.close()


init_db()


def classify_content(text: str) -> str:
    """Classifies text into semantic developer categories."""
    if not text or not text.strip():
        return "empty"

    stripped = text.strip()

    # 1. Java Exception / Spigot stacktrace
    if "Exception in thread" in text or ("at com." in text and "Exception" in text) or ("at org.bukkit." in text) or ("at io.papermc." in text):
        return "java_exception"

    # 2. Python traceback
    if "Traceback (most recent call last):" in text or 'File "' in text and ", line " in text:
        return "python_traceback"

    # 3. cURL command
    if stripped.startswith("curl ") or stripped.startswith("curl.exe "):
        return "curl"

    # 4. JSON
    if (stripped.startswith("{") and stripped.endswith("}")) or (stripped.startswith("[") and stripped.endswith("]")):
        try:
            json.loads(stripped)
            return "json"
        except Exception:
            pass

    # 5. SQL query
    if re.match(r"(?i)^(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\s+", stripped):
        return "sql"

    # 6. Java source code snippet
    if ("public class " in text or "private " in text or "public void " in text) and "{" in text:
        return "java_code"

    # 7. URL
    if re.match(r"^https?://[^\s]+$", stripped):
        return "url"

    return "text"


def record_clipboard_entry(text: str, app_source: str = "") -> Optional[Dict[str, Any]]:
    """Records a clipboard entry if distinct from the latest, maintaining a 50-item buffer."""
    if not text or not text.strip():
        return None

    content_type = classify_content(text)
    now = time.time()

    with _db_lock:
        conn = get_db()
        try:
            # Check if identical to last entry
            cur = conn.execute("SELECT text FROM clipboard_history ORDER BY id DESC LIMIT 1")
            last = cur.fetchone()
            if last and last["text"] == text:
                return None

            with conn:
                conn.execute(
                    "INSERT INTO clipboard_history (text, content_type, app_source, created_at) VALUES (?, ?, ?, ?)",
                    (text, content_type, app_source, now),
                )
                # Purge entries beyond 50
                conn.execute("""
                    DELETE FROM clipboard_history WHERE id NOT IN (
                        SELECT id FROM clipboard_history ORDER BY id DESC LIMIT ?
                    )
                """, (MAX_HISTORY,))
            return {"text": text, "content_type": content_type, "app_source": app_source, "created_at": now}
        finally:
            conn.close()


def list_clipboard_history(limit: int = 20) -> List[Dict[str, Any]]:
    with _db_lock:
        conn = get_db()
        try:
            cur = conn.execute(
                "SELECT id, text, content_type, app_source, created_at FROM clipboard_history ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def transform_clipboard(text: str, action: str = "auto", brain=None) -> Dict[str, Any]:
    """Transforms clipboard content into clean developer code or fixes."""
    ctype = classify_content(text)
    act = action if action != "auto" else ctype

    if act == "json" or act == "to_dataclass":
        try:
            data = json.loads(text.strip())
            # Convert to Python Dataclass format
            fields = []
            if isinstance(data, dict):
                for k, v in list(data.items())[:15]:
                    val_type = type(v).__name__
                    type_map = {"int": "int", "float": "float", "str": "str", "bool": "bool", "list": "List[Any]", "dict": "Dict[str, Any]"}
                    t_name = type_map.get(val_type, "Any")
                    fields.append(f"    {k}: {t_name}")
                code = "@dataclass\nclass AutoGeneratedData:\n" + "\n".join(fields or ["    pass"])
                return {"action": "to_dataclass", "result": code, "original_type": "json"}
        except Exception as e:
            return {"error": f"JSON parse error: {e}"}

    if act == "curl" or act == "to_python":
        # Basic curl to requests converter
        url_match = re.search(r"curl\s+(?:-[A-Za-z]+\s+)*['\"]?(https?://[^'\"\s]+)['\"]?", text)
        url = url_match.group(1) if url_match else "https://example.com"
        method = "POST" if "-X POST" in text or "--data" in text or "-d" in text else "GET"
        code = f"import requests\n\nresponse = requests.{method.lower()}('{url}')\nprint(response.status_code, response.text)"
        return {"action": "to_python", "result": code, "original_type": "curl"}

    if act in ("java_exception", "python_traceback", "fix_exception") and brain:
        prompt = (
            f"Analyze this stacktrace/error and provide a concise diagnosis and direct code fix:\n```\n{text[:1500]}\n```"
        )
        try:
            fix = brain.ask(prompt, unattended=True)
            return {"action": "fix_exception", "result": fix, "original_type": ctype}
        except Exception as e:
            return {"error": f"Brain diagnosis error: {e}"}

    return {"action": "none", "result": text, "content_type": ctype}


# ---------------------------------------------------------------- Background Polling Daemon
class ClipboardDaemon:
    def __init__(self, emitter=None):
        self.emitter = emitter or (lambda e, **d: None)
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.running:
            return
        self.running = True

        def _loop():
            import win32clipboard
            import win32con

            last_text = ""
            while self.running:
                try:
                    time.sleep(0.5)
                    text = ""
                    try:
                        win32clipboard.OpenClipboard()
                        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                            text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    except Exception:
                        pass
                    finally:
                        try:
                            win32clipboard.CloseClipboard()
                        except Exception:
                            pass

                    if text and text != last_text:
                        last_text = text
                        app = system.active_app()
                        recorded = record_clipboard_entry(text, app_source=app)
                        if recorded:
                            ctype = recorded["content_type"]
                            self.emitter("clipboard_updated", entry=recorded)

                            # Trigger Notch suggestion if actionable
                            if ctype in ("java_exception", "python_traceback"):
                                try:
                                    import jarvis
                                    jarvis.notch_line[:] = ["⚡ Copy: Fix Stacktrace Available", time.time()]
                                except Exception:
                                    pass
                            elif ctype == "json":
                                try:
                                    import jarvis
                                    jarvis.notch_line[:] = ["⚡ Copy: Convert JSON to Dataclass", time.time()]
                                except Exception:
                                    pass
                            elif ctype == "curl":
                                try:
                                    import jarvis
                                    jarvis.notch_line[:] = ["⚡ Copy: Convert cURL to Requests", time.time()]
                                except Exception:
                                    pass
                except Exception:
                    time.sleep(1.0)

        self._thread = threading.Thread(target=_loop, daemon=True, name="ClipboardDaemonLoop")
        self._thread.start()

    def stop(self):
        self.running = False


_daemon_instance: Optional[ClipboardDaemon] = None


def get_clipboard_daemon(emitter=None) -> ClipboardDaemon:
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = ClipboardDaemon(emitter=emitter)
    return _daemon_instance
