"""Unified Memory Resolver & Habit Heatmap Engine.
Cross-indexes RAG, Screen Rewind, and Clipboard streams into a single natural-language query,
tracks repeated workflow patterns, and maintains GDD project versioning.
"""
import difflib
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import rag
import store
import system

HEATMAP_FILE = os.path.join(system.DATA, "habit_heatmap.json")
GDD_HISTORY_DIR = os.path.join(system.CONFIG, "gdd_history")
os.makedirs(GDD_HISTORY_DIR, exist_ok=True)


def recall_everything(query: str, days: int = 7) -> Dict[str, Any]:
    """Unified search across RAG indexed documents, Screen Rewind OCR history, and clipboard snippets."""
    results = {
        "rag": [],
        "clipboard": [],
        "screen_rewind": []
    }

    # 1. Query RAG Memory
    try:
        rag_hits = rag.search(query, top_k=4)
        for h in rag_hits:
            results["rag"].append({
                "title": h.get("title", "Document"),
                "snippet": h.get("snippet", "")[:400],
                "score": round(h.get("score", 0.0), 2)
            })
    except Exception as e:
        results["rag_error"] = str(e)

    # 2. Query Clipboard Daemon History
    try:
        import clipboard_daemon
        cb_daemon = clipboard_daemon.get_clipboard_daemon()
        entries = cb_daemon.search(query, limit=5)
        for item in entries:
            results["clipboard"].append({
                "text": item.get("text", "")[:300],
                "source": item.get("source", "clipboard"),
                "timestamp": item.get("timestamp", 0)
            })
    except Exception as e:
        results["clipboard_error"] = str(e)

    # 3. Query Screen Rewind History
    try:
        import screen_rewind
        rewind = screen_rewind.get_rewind_sampler()
        rewind_hits = rewind.search(query, max_results=5)
        for rh in rewind_hits:
            results["screen_rewind"].append({
                "text": rh.get("ocr_text", "")[:300],
                "app": rh.get("active_app", ""),
                "timestamp": rh.get("timestamp", 0)
            })
    except Exception as e:
        results["screen_rewind_error"] = str(e)

    # Format unified markdown report
    report_lines = [f"🧠 **Unified Memory Recall for: '{query}'**\n"]
    if results["rag"]:
        report_lines.append("**📚 Indexed Documents / RAG:**")
        for r in results["rag"]:
            report_lines.append(f"- **{r['title']}** (score: {r['score']}): {r['snippet'][:180]}...")
        report_lines.append("")
    if results["clipboard"]:
        report_lines.append("**📋 Clipboard History:**")
        for c in results["clipboard"]:
            t_str = time.strftime('%m-%d %H:%M', time.localtime(c['timestamp'])) if c.get('timestamp') else ''
            report_lines.append(f"- `{t_str}`: {c['text'][:180]}...")
        report_lines.append("")
    if results["screen_rewind"]:
        report_lines.append("**🖥️ Screen Rewind (Visual History):**")
        for s in results["screen_rewind"]:
            t_str = time.strftime('%m-%d %H:%M', time.localtime(s['timestamp'])) if s.get('timestamp') else ''
            report_lines.append(f"- `{t_str}` [{s['app']}]: {s['text'][:180]}...")
        report_lines.append("")

    if not (results["rag"] or results["clipboard"] or results["screen_rewind"]):
        report_lines.append("No matches found across RAG, Clipboard, or Screen Rewind for this query.")

    return {
        "ok": True,
        "query": query,
        "results": results,
        "report": "\n".join(report_lines)
    }


def log_app_activity(app_name: str, window_title: str):
    """Tracks app and task frequency to detect repeated habit patterns."""
    if not app_name:
        return
    now = time.time()
    heatmap = store.read_json(HEATMAP_FILE, {"apps": {}, "patterns": {}})
    
    app_key = app_name.lower().strip()
    entry = heatmap["apps"].setdefault(app_key, {"count": 0, "last_seen": now, "titles": []})
    entry["count"] += 1
    entry["last_seen"] = now
    if window_title and window_title not in entry["titles"]:
        entry["titles"].append(window_title[:100])
        entry["titles"] = entry["titles"][-15:]

    store.write_json(HEATMAP_FILE, heatmap)


def check_habit_suggestions() -> Dict[str, Any]:
    """Analyzes habit patterns and suggests automated workflows if repetitive behavior is detected."""
    heatmap = store.read_json(HEATMAP_FILE, {"apps": {}, "patterns": {}})
    suggestions = []
    
    for app, data in heatmap.get("apps", {}).items():
        count = data.get("count", 0)
        if count >= 25:
            suggestions.append(f"You've accessed {app} heavily ({count} times recently). Want me to configure a one-click macro or background watchdog for it?")
    if not suggestions:
        suggestions = ["No repetitive bottleneck detected yet. Continue working normally; Jarvis will surface workflow triggers as habits form."]
    return {
        "ok": True,
        "count": len(suggestions),
        "suggestions": suggestions,
        "report": "\n".join(f"- 💡 {s}" for s in suggestions)
    }


def snapshot_gdd_version(project_id: str, gdd_content: str, note: str = "Auto-save") -> str:
    """Saves a timestamped version snapshot of a project's GDD."""
    proj_dir = os.path.join(GDD_HISTORY_DIR, project_id)
    os.makedirs(proj_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{stamp}.md"
    file_path = os.path.join(proj_dir, filename)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(gdd_content)
        
    index_file = os.path.join(proj_dir, "versions.json")
    versions = store.read_json(index_file, [])
    versions.append({
        "file": filename,
        "timestamp": time.time(),
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "note": note,
        "chars": len(gdd_content)
    })
    store.write_json(index_file, versions)
    return filename


def diff_gdd_history(project_id: str, version_a: Optional[str] = None, version_b: Optional[str] = None, since_timestamp: float = 0.0) -> Dict[str, Any]:
    """Generates a diff between two GDD revisions or between earliest and latest."""
    proj_dir = os.path.join(GDD_HISTORY_DIR, project_id)
    index_file = os.path.join(proj_dir, "versions.json")
    versions = store.read_json(index_file, [])
    
    if len(versions) < 2:
        return {"ok": True, "diff": "Need at least 2 saved versions to generate diff.", "versions": versions}
    
    file_a = version_a or versions[0]["file"]
    file_b = version_b or versions[-1]["file"]
    
    path_a = os.path.join(proj_dir, file_a)
    path_b = os.path.join(proj_dir, file_b)
    
    if not (os.path.exists(path_a) and os.path.exists(path_b)):
        return {"ok": False, "error": "Specified version file not found"}
        
    with open(path_a, "r", encoding="utf-8") as f:
        lines_a = f.readlines()
    with open(path_b, "r", encoding="utf-8") as f:
        lines_b = f.readlines()
        
    diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=file_a, tofile=file_b))
    return {
        "ok": True,
        "project": project_id,
        "from": file_a,
        "to": file_b,
        "diff": "".join(diff[:200])  # limit diff preview
    }
