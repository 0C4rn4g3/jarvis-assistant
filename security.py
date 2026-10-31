"""Action Tiering, Human-in-the-Loop (HITL) Guardrails and Pre-Execution Snapshots.
Classifies tool calls into Green, Yellow, and Red risk tiers.
Red actions (destructive shell commands, file deletions, process termination, outbound writes)
require explicit Human-in-the-Loop approval with a 15-second auto-deny countdown.
Automatically creates Git stashes or shadow copies before file mutations for one-click rollback.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

import store

SNAPSHOTS_FILE = os.path.join(store.DATA, "snapshots.json")
AUDIT_LOG_FILE = os.path.join(store.DATA, "action_audit.jsonl")
TOKEN_STATS_FILE = os.path.join(store.DATA, "token_stats.json")

SNAPSHOT_DIR = os.path.join(tempfile.gettempdir(), "jarvis_shadow_snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

# Risk Tiers
GREEN = "green"    # Read-only, safe, search, RAG, inspect
YELLOW = "yellow"  # Reversible state changes (reminders, window focus, notes)
RED = "red"        # Destructive (shell execution, file deletion/mutation, process kill)

TOOL_TIERS = {
    # Green
    "read_web_page": GREEN,
    "web_search": GREEN,
    "youtube_search": GREEN,
    "search_memory": GREEN,
    "index_memory": GREEN,
    "skill": GREEN,
    "read_file": GREEN,
    "list_files": GREEN,
    "list_windows": GREEN,
    "look": GREEN,
    "screenshot": GREEN,
    "system_stats": GREEN,
    "briefing": GREEN,
    "weather": GREEN,
    "recall": GREEN,
    "selection": GREEN,
    "classroom_due": GREEN,
    "classroom_announcements": GREEN,
    "drive_file": GREEN,
    # Yellow
    "focus_window": YELLOW,
    "set_reminder": YELLOW,
    "remember": YELLOW,
    "forget": YELLOW,
    "notes": YELLOW,
    "media": YELLOW,
    "manage_operators": YELLOW,
    # Red
    "run_command": RED,
    "close_window": RED,
    "write_file": RED,
    "edit_file": RED,
    "delete_file": RED,
}

# Red command keywords for shell commands
DESTRUCTIVE_COMMAND_PATTERNS = re.compile(
    r"\b(rm|del|rmdir|Remove-Item|format|Stop-Process|taskkill|drop\s+database|drop\s+table|"
    r"git\s+reset|git\s+clean|git\s+push\s+--force|shutdown|reboot|Set-ExecutionPolicy|reg\s+add|"
    r"Invoke-WebRequest|curl|wget|chmod\s+777|dd\s+if=)\b",
    re.I
)

# Global HITL pending requests: id -> dict
_pending_approvals = {}
_approval_lock = threading.Lock()

# Snapshot history stack
_snapshots = []  # list of dicts: {"id", "timestamp", "type": "git"|"file", "target", "backup"}


def classify_tool(tool_name: str, args: dict) -> str:
    """Classifies a tool execution into Green, Yellow, or Red using Jev System 1 risk assessment."""
    tier = TOOL_TIERS.get(tool_name, YELLOW)
    if tool_name == "run_command":
        cmd = args.get("command", "") or args.get("cmd", "") or args.get("CommandLine", "") or ""
        try:
            import jev
            risk = jev.assess_command_risk(cmd)
            return risk.get("tier", RED)
        except Exception:
            return RED
    if tool_name in ("write_file", "edit_file", "delete_file"):
        return RED
    return tier


class ApprovalTimeout(Exception):
    pass


def request_hitl_approval(tool_name: str, args: dict, timeout_sec: float = 15.0) -> bool:
    """Pops an interactive approval request and waits up to timeout_sec (default 15s auto-deny).
    Returns True if approved, False if denied or timed out.
    """
    req_id = str(uuid.uuid4())[:8]
    summary = f"{tool_name}: " + (args.get("command") or str(args))[:60]
    event = threading.Event()
    decision = {"approved": False, "timeout": False}

    with _approval_lock:
        _pending_approvals[req_id] = {
            "id": req_id,
            "tool": tool_name,
            "args": args,
            "summary": summary,
            "created_at": time.time(),
            "expires_at": time.time() + timeout_sec,
            "event": event,
            "decision": decision,
        }

    # Notify UI / Notch
    try:
        import jarvis
        jarvis.emit("hitl_required", id=req_id, tool=tool_name, summary=summary, timeout=timeout_sec)
        # Update notch text with countdown alert
        jarvis.notch_line[:] = [f"⚠️ APPROVE? {summary[:35]} (15s)", time.time()]
    except Exception:
        pass

    # Wait for approval
    got_signal = event.wait(timeout=timeout_sec)

    with _approval_lock:
        _pending_approvals.pop(req_id, None)

    if not got_signal:
        decision["timeout"] = True
        try:
            import jarvis
            jarvis.notch_line[:] = ["❌ Security: Action Auto-Denied", time.time()]
        except Exception:
            pass
        return False

    return decision["approved"]


def approve_request(req_id: str) -> bool:
    """Approve a pending HITL request."""
    with _approval_lock:
        req = _pending_approvals.get(req_id)
        if req:
            req["decision"]["approved"] = True
            req["event"].set()
            return True
    return False


def deny_request(req_id: str) -> bool:
    """Deny a pending HITL request."""
    with _approval_lock:
        req = _pending_approvals.get(req_id)
        if req:
            req["decision"]["approved"] = False
            req["event"].set()
            return True
    return False


def list_pending_approvals():
    with _approval_lock:
        now = time.time()
        return [
            {
                "id": r["id"],
                "tool": r["tool"],
                "summary": r["summary"],
                "time_remaining": max(0.0, round(r["expires_at"] - now, 1)),
            }
            for r in _pending_approvals.values()
            if r["expires_at"] > now
        ]


# ---------------------------------------------------------------- Snapshots & Rollback
def create_snapshot(target_path=None, description="Pre-execution snapshot"):
    """Creates a git stash or shadow copy backup before destructive mutations."""
    snapshot_id = str(uuid.uuid4())[:8]
    now = time.time()

    # 1. If target is in a git repo, use git stash create
    if target_path and os.path.exists(target_path):
        folder = target_path if os.path.isdir(target_path) else os.path.dirname(target_path)
    else:
        folder = os.getcwd()

    git_dir = None
    curr = folder
    while curr and os.path.splitdrive(curr)[1] != "\\":
        if os.path.exists(os.path.join(curr, ".git")):
            git_dir = curr
            break
        parent = os.path.dirname(curr)
        if parent == curr:
            break
        curr = parent

    if git_dir:
        try:
            stash_sha = subprocess.check_output(
                ["git", "-C", git_dir, "stash", "create"],
                stderr=subprocess.DEVNULL,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            ).strip()
            if stash_sha:
                _snapshots.append({
                    "id": snapshot_id,
                    "timestamp": now,
                    "type": "git",
                    "repo": git_dir,
                    "sha": stash_sha,
                    "description": description,
                })
                return snapshot_id
        except Exception:
            pass

    # 2. File shadow copy fallback
    if target_path and os.path.isfile(target_path):
        try:
            backup_file = os.path.join(SNAPSHOT_DIR, f"{snapshot_id}_{os.path.basename(target_path)}")
            shutil.copy2(target_path, backup_file)
            _snapshots.append({
                "id": snapshot_id,
                "timestamp": now,
                "type": "file",
                "target": target_path,
                "backup": backup_file,
                "description": description,
            })
            return snapshot_id
        except Exception:
            pass

    return None


def rollback_last_snapshot():
    """Rolls back the last recorded snapshot."""
    if not _snapshots:
        return "No snapshots available to roll back."

    snap = _snapshots.pop()
    if snap["type"] == "file":
        if os.path.exists(snap["backup"]):
            try:
                shutil.copy2(snap["backup"], snap["target"])
                return f"Rolled back {snap['target']} from snapshot {snap['id']}."
            except Exception as e:
                return f"Rollback failed: {e}"
        return "Backup file missing."
    elif snap["type"] == "git":
        try:
            subprocess.run(
                ["git", "-C", snap["repo"], "stash", "apply", snap["sha"]],
                check=True,
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return f"Restored git snapshot {snap['sha'][:7]} in {snap['repo']}."
        except Exception as e:
            return f"Git rollback error: {e}"

    return "Unknown snapshot type."


def _load_persistent_snapshots():
    if os.path.exists(SNAPSHOTS_FILE):
        try:
            with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_persistent_snapshots(snapshots):
    try:
        os.makedirs(os.path.dirname(SNAPSHOTS_FILE), exist_ok=True)
        # Keep last 500 snapshots
        trimmed = snapshots[-500:]
        with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, indent=2)
    except Exception as e:
        print(f"[security] Failed to save snapshots: {e}", flush=True)


def snapshot_file_edit(target_path: str, description: str = "Assistant file edit") -> str:
    """Version-stamps and creates a shadow snapshot of any file before modification."""
    if not target_path or not os.path.exists(target_path) or not os.path.isfile(target_path):
        return ""
    snap_id = str(uuid.uuid4())[:8]
    now = time.time()
    try:
        backup_file = os.path.join(SNAPSHOT_DIR, f"{snap_id}_{os.path.basename(target_path)}")
        shutil.copy2(target_path, backup_file)
        snap_entry = {
            "id": snap_id,
            "timestamp": now,
            "type": "file",
            "target": os.path.abspath(target_path),
            "backup": backup_file,
            "description": description,
        }
        _snapshots.append(snap_entry)
        persistent = _load_persistent_snapshots()
        persistent.append(snap_entry)
        _save_persistent_snapshots(persistent)
        return snap_id
    except Exception as e:
        print(f"[security] snapshot_file_edit failed: {e}", flush=True)
        return ""


def revert_today_changes() -> dict:
    """One-voice-command rollback: reverts all files modified by Jarvis today since midnight."""
    now = datetime.datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    # Combine in-memory and persistent snapshots
    all_snaps = _load_persistent_snapshots()
    for s in _snapshots:
        if not any(x.get("id") == s.get("id") for x in all_snaps):
            all_snaps.append(s)

    today_snaps = [s for s in all_snaps if s.get("timestamp", 0) >= midnight]
    if not today_snaps:
        return {
            "ok": True,
            "reverted_count": 0,
            "reverted_files": [],
            "report": "No file changes recorded for today. Everything is clean!"
        }

    # Sort descending to rollback newest first
    today_snaps.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    reverted_targets = set()
    failed = []

    for snap in today_snaps:
        target = snap.get("target")
        backup = snap.get("backup")
        if target and target not in reverted_targets:
            if backup and os.path.exists(backup):
                try:
                    shutil.copy2(backup, target)
                    reverted_targets.add(target)
                except Exception as e:
                    failed.append(f"{target} ({e})")
            else:
                failed.append(f"{target} (backup missing)")

    file_list = list(reverted_targets)
    report_lines = [
        f"⏪ **Reverted Today's File Edits** ({len(file_list)} files restored):",
    ]
    for fpath in file_list:
        report_lines.append(f"- 📄 `{os.path.basename(fpath)}` ({fpath})")
    if failed:
        report_lines.append(f"\n⚠️ *Failed to revert:* {', '.join(failed)}")

    return {
        "ok": True,
        "reverted_count": len(file_list),
        "reverted_files": file_list,
        "failed": failed,
        "report": "\n".join(report_lines)
    }


# ---------------------------------------------------------------- Action Audit Log with Replay
def log_action(tool_name: str, args: dict, tier: str = None, status: str = "success", duration_ms: int = 0, details: str = "") -> dict:
    """Logs an assistant tool/command execution into the searchable audit log."""
    act_id = str(uuid.uuid4())[:8]
    if not tier:
        tier = classify_tool(tool_name, args)
    entry = {
        "id": act_id,
        "timestamp": time.time(),
        "tool": tool_name,
        "tier": tier,
        "args": {k: (str(v)[:200] if not isinstance(v, (int, float, bool)) else v) for k, v in args.items()},
        "status": status,
        "duration_ms": duration_ms,
        "details": details[:300]
    }
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[security] Failed to write audit log: {e}", flush=True)
    return entry


def get_audit_log(limit: int = 50, query: str = "", tier: str = "") -> list:
    """Retrieves searchable audit history filtered by query and safety tier."""
    if not os.path.exists(AUDIT_LOG_FILE):
        return []
    entries = []
    q = (query or "").lower().strip()
    tier_filter = (tier or "").lower().strip()
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if tier_filter and e.get("tier", "").lower() != tier_filter:
                        continue
                    if q:
                        blob = f"{e.get('tool', '')} {json.dumps(e.get('args', {}))} {e.get('details', '')}".lower()
                        if q not in blob:
                            continue
                    entries.append(e)
                except Exception:
                    pass
    except Exception:
        pass
    entries.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
    return entries[:limit]


def replay_action(action_id: str) -> dict:
    """Replays or inspects a recorded audit action."""
    log = get_audit_log(limit=200)
    target = next((e for e in log if e.get("id") == action_id), None)
    if not target:
        return {"ok": False, "error": f"Action ID '{action_id}' not found in audit log."}

    tool = target.get("tool")
    args = target.get("args", {})
    tier = target.get("tier")

    if tier == RED:
        return {
            "ok": False,
            "error": f"Action '{tool}' was classified as RED ({tier}). Manual re-approval required before replay.",
            "action": target
        }

    # Execute safe replay
    try:
        import brain
        if tool in brain.TOOLS:
            fn, _, _ = brain.TOOLS[tool]
            res = fn(**args)
            return {"ok": True, "replayed": True, "action": target, "result": res}
        return {"ok": True, "replayed": False, "message": f"Action {tool} recorded but has no direct replay runner.", "action": target}
    except Exception as e:
        return {"ok": False, "error": f"Replay execution error: {e}", "action": target}


# ---------------------------------------------------------------- Spending / Token Dashboard
def record_token_usage(model: str, input_tokens: int = 0, output_tokens: int = 0, source: str = "antigravity", vram_saved: bool = False):
    """Tracks token volume, model tier, and estimated commercial cost savings."""
    data = {"total_requests": 0, "antigravity_tokens": 0, "ollama_tokens": 0, "estimated_savings_usd": 0.0, "vram_arbitrations": 0, "models": {}}
    if os.path.exists(TOKEN_STATS_FILE):
        try:
            with open(TOKEN_STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    data["total_requests"] += 1
    total_toks = input_tokens + output_tokens

    if "ollama" in model.lower() or source == "ollama":
        data["ollama_tokens"] = data.get("ollama_tokens", 0) + total_toks
    else:
        data["antigravity_tokens"] = data.get("antigravity_tokens", 0) + total_toks
        # Retail savings: approx $0.003 / 1k tokens (Claude Sonnet / Opus blended)
        savings = (input_tokens * 0.000003) + (output_tokens * 0.000015)
        data["estimated_savings_usd"] = round(data.get("estimated_savings_usd", 0.0) + savings, 4)

    if vram_saved:
        data["vram_arbitrations"] = data.get("vram_arbitrations", 0) + 1

    m_key = model.split()[0] if model else "unknown"
    data["models"].setdefault(m_key, {"calls": 0, "tokens": 0})
    data["models"][m_key]["calls"] += 1
    data["models"][m_key]["tokens"] += total_toks

    try:
        os.makedirs(os.path.dirname(TOKEN_STATS_FILE), exist_ok=True)
        with open(TOKEN_STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[security] Failed to record token usage: {e}", flush=True)


def get_token_dashboard() -> dict:
    """Returns token usage, model tier distribution, and VRAM savings."""
    data = {"total_requests": 0, "antigravity_tokens": 0, "ollama_tokens": 0, "estimated_savings_usd": 0.0, "vram_arbitrations": 0, "models": {}}
    if os.path.exists(TOKEN_STATS_FILE):
        try:
            with open(TOKEN_STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    report_lines = [
        "💳 **Jarvis Model Usage & Spending Dashboard**",
        f"- ⚡ **Total AI Requests**: {data.get('total_requests', 0)}",
        f"- ☁️ **Antigravity Tokens (Zero-Cost Pro)**: {data.get('antigravity_tokens', 0):,}",
        f"- 🖥️ **Ollama Local Fallback Tokens**: {data.get('ollama_tokens', 0):,}",
        f"- 💰 **Estimated API Dollars Saved**: ${data.get('estimated_savings_usd', 0.0):.2f}",
        f"- 🎮 **VRAM Arbitrator Evictions**: {data.get('vram_arbitrations', 0)} times (saved GPU memory for gaming)\n",
        "**Per-Model Breakdown:**"
    ]
    for m_name, stats in data.get("models", {}).items():
        report_lines.append(f"- `{m_name}`: {stats.get('calls', 0)} calls ({stats.get('tokens', 0):,} tokens)")

    return {
        "ok": True,
        "commercial_equivalent_saved_usd": data.get("estimated_savings_usd", 0.0),
        "estimated_savings_usd": data.get("estimated_savings_usd", 0.0),
        "stats": data,
        "report": "\n".join(report_lines)
    }

