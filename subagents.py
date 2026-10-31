"""Jarvis Asynchronous Task Subagents (The Swarm Pattern).
Enables dynamic background worker agents that execute complex, long-running tasks
(codebase audits, game economy simulations, lead scanning, deep research) without
locking the user's conversation or UI.
"""
from dataclasses import asdict, dataclass, field
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid

import system
import store

SUBAGENTS_FILE = os.path.join(system.DATA, "subagents.json")
_lock = threading.Lock()


@dataclass
class SubagentTask:
    id: str
    task: str
    category: str = "general"
    status: str = "pending"  # pending, running, completed, failed, cancelled
    progress: float = 0.0
    progress_label: str = "Initializing..."
    created_at: float = field(default_factory=time.time)
    started_at: float = 0.0
    completed_at: float = 0.0
    steps: List[str] = field(default_factory=list)
    result_summary: str = ""
    snapshot_id: str = ""
    error: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "category": self.category,
            "status": self.status,
            "progress": self.progress,
            "progress_label": self.progress_label,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "steps": list(self.steps),
            "result_summary": self.result_summary,
            "snapshot_id": self.snapshot_id,
            "error": self.error,
        }


class SubagentManager:
    def __init__(self, brain=None, emitter=None):
        self.brain = brain
        self.emitter = emitter or (lambda e, **kw: None)
        self.active_tasks: Dict[str, SubagentTask] = {}
        self.history: List[Dict[str, Any]] = []
        self._load_history()

    def _load_history(self):
        with _lock:
            if os.path.exists(SUBAGENTS_FILE):
                try:
                    with open(SUBAGENTS_FILE, "r", encoding="utf-8") as f:
                        self.history = json.load(f)
                except Exception:
                    self.history = []

    def _save_history(self):
        with _lock:
            try:
                os.makedirs(system.DATA, exist_ok=True)
                with open(SUBAGENTS_FILE, "w", encoding="utf-8") as f:
                    # Keep latest 50 tasks
                    json.dump(self.history[-50:], f, indent=2)
            except Exception as e:
                print(f"[subagents] Failed to save history: {e}", flush=True)

    def spawn(self, task: str, category: str = "general", brain=None) -> SubagentTask:
        """Spawns an asynchronous background subagent for a heavy task."""
        b = brain or self.brain
        task_id = "sub-" + uuid.uuid4().hex[:6]
        sub = SubagentTask(
            id=task_id,
            task=task.strip(),
            category=category.strip().lower() or "general",
            status="pending"
        )
        self.active_tasks[task_id] = sub

        # Create safety snapshot if this is an audit or coding task
        try:
            import security
            sub.snapshot_id = security.create_snapshot(description=f"Pre-subagent ({task_id}): {task[:40]}")
        except Exception:
            pass

        def _worker():
            sub.started_at = time.time()
            sub.status = "running"
            sub.progress_label = "Started execution..."
            self.emitter("subagent_started", subagent=sub.to_dict())

            try:
                import jarvis
                jarvis.notch_line[:] = [f"⚙️ Subagent {task_id}: {sub.task[:32]}…", time.time()]
            except Exception:
                pass

            def on_tool(tool_name, args=None):
                if sub.cancel_event.is_set():
                    return
                sub.steps.append(tool_name)
                # Count progress heuristically based on tool steps
                step_count = len(sub.steps)
                sub.progress = min(0.95, round(step_count * 0.15, 2))
                try:
                    import jarvis
                    lbl = jarvis.tool_label(tool_name, args)
                    sub.progress_label = lbl
                    jarvis.notch_line[:] = [f"⚙️ {task_id}: {lbl}…", time.time()]
                except Exception:
                    sub.progress_label = f"Running {tool_name}"

                self.emitter("subagent_progress", subagent=sub.to_dict())

            try:
                if b and hasattr(b, "ask_subagent"):
                    reply = b.ask_subagent(sub.task, on_tool=on_tool, cancel_event=sub.cancel_event)
                elif b:
                    # Fallback to unattended ask if ask_subagent not yet registered
                    reply = b.ask(sub.task, on_tool=on_tool, unattended=True)
                else:
                    reply = "Brain not attached to subagent manager."

                if sub.cancel_event.is_set():
                    sub.status = "cancelled"
                    sub.progress_label = "Cancelled by user"
                    sub.result_summary = "Task was cancelled before completion."
                else:
                    sub.status = "completed"
                    sub.progress = 1.0
                    sub.progress_label = "Complete"
                    sub.result_summary = reply

            except Exception as e:
                sub.status = "failed"
                sub.error = str(e)
                sub.progress_label = "Failed"
                sub.result_summary = f"Subagent error: {e}"
                print(f"[subagents] Subagent {task_id} failed: {e}", flush=True)

            finally:
                sub.completed_at = time.time()
                data = sub.to_dict()
                self.history.append(data)
                self.active_tasks.pop(task_id, None)
                self._save_history()

                # Notify UI, Chat session, and Notch
                self.emitter("subagent_finished", subagent=data)

                # Add result card into conversation session so user sees the report
                clean_title = sub.task[:60] + ("..." if len(sub.task) > 60 else "")
                status_icon = "✅" if sub.status == "completed" else "⚠️"
                notice = (
                    f"{status_icon} **Background Subagent Report [{sub.id}]**\n"
                    f"*Task:* {clean_title}\n"
                    f"*Duration:* {round(sub.completed_at - sub.started_at, 1)}s | *Steps:* {len(sub.steps)}\n\n"
                    f"{sub.result_summary}"
                )
                if sub.snapshot_id:
                    notice += f"\n\n*(Snapshot `{sub.snapshot_id}` created. Say 'undo last action' to revert if needed.)*"

                try:
                    self.emitter("log", who="jarvis", text=notice)
                except Exception:
                    pass

                try:
                    import jarvis
                    jarvis.notch_line[:] = [f"{status_icon} Subagent done: {clean_title[:35]}", time.time()]
                except Exception:
                    pass

                system.notify(f"Jarvis Subagent {sub.id}", f"{status_icon} {clean_title}")

        thread = threading.Thread(target=_worker, daemon=True, name=f"Subagent-{task_id}")
        thread.start()
        return sub

    def cancel(self, task_id: str) -> bool:
        """Cancels a running background subagent."""
        sub = self.active_tasks.get(task_id)
        if sub:
            sub.cancel_event.set()
            sub.status = "cancelling"
            sub.progress_label = "Cancelling..."
            self.emitter("subagent_progress", subagent=sub.to_dict())
            return True
        return False

    def cancel_all(self) -> int:
        """Cancels all running background subagents."""
        count = 0
        for sub_id in list(self.active_tasks.keys()):
            if self.cancel(sub_id):
                count += 1
        return count

    def list_subagents(self) -> List[Dict[str, Any]]:
        """Returns all running and recent subagent tasks."""
        active = [s.to_dict() for s in self.active_tasks.values()]
        recent = sorted(self.history, key=lambda x: x.get("completed_at", 0), reverse=True)[:15]
        return active + recent

    def get_status_summary(self) -> Dict[str, Any]:
        """Provides high-level telemetry for Notch, Mobile app, and HUD."""
        running = [s.to_dict() for s in self.active_tasks.values() if s.status == "running"]
        return {
            "running_count": len(running),
            "running_tasks": running,
            "total_completed": len([h for h in self.history if h.get("status") == "completed"]),
        }


_manager_instance: Optional[SubagentManager] = None


def get_subagent_manager(brain=None, emitter=None) -> SubagentManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SubagentManager(brain=brain, emitter=emitter)
    elif brain and _manager_instance.brain is None:
        _manager_instance.brain = brain
    if emitter:
        _manager_instance.emitter = emitter
    return _manager_instance
