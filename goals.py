"""
J.A.R.V.I.S. Persistent Task & Goal Tracker
============================================
Enables long-running goals with milestones (e.g., "ship v1 of my plugin by Friday").
Key Capabilities:
  1. Persistent Multi-Session Goals: Tracks objectives, target deadlines, and progress across sessions.
  2. Autonomous Milestone Decomposition: Breaks goals into 3-6 actionable milestone steps.
  3. Swarm Subagent Dispatch: Assigns milestone steps to autonomous background subagents and auto-completes when workers finish.
  4. Proactive Nudge Engine: Anticipates stalled goals and approaching deadlines, generating contextual check-ins.
  5. Multi-Channel Integration: Surfaced in Morning Briefing, QML Chat, Floating Notch, and Mobile.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

import store
import system

GOALS_FILE = os.path.join(store.DATA, "goals.json")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_target_date(text: str) -> Tuple[Optional[float], str]:
    """Parses relative day, weekday, or ISO date into timestamp and display string."""
    if not text:
        return None, ""
    clean = text.strip().lower()
    now_dt = datetime.now()

    # Relative days
    if clean in ("today", "tonight"):
        target_dt = now_dt.replace(hour=23, minute=59, second=59)
        return target_dt.timestamp(), "Today"
    if clean == "tomorrow":
        target_dt = (now_dt + timedelta(days=1)).replace(hour=23, minute=59, second=59)
        return target_dt.timestamp(), "Tomorrow"
    if m := re.search(r"in\s+(\d+)\s+days?", clean):
        days = int(m.group(1))
        target_dt = (now_dt + timedelta(days=days)).replace(hour=23, minute=59, second=59)
        return target_dt.timestamp(), f"In {days} days ({target_dt.strftime('%a %d %b')})"
    if m := re.search(r"in\s+(\d+)\s+weeks?", clean):
        weeks = int(m.group(1))
        target_dt = (now_dt + timedelta(weeks=weeks)).replace(hour=23, minute=59, second=59)
        return target_dt.timestamp(), f"In {weeks} weeks ({target_dt.strftime('%a %d %b')})"

    # Weekday check (e.g. "by friday", "friday")
    for idx, day_name in enumerate(WEEKDAYS):
        if day_name in clean:
            cur_idx = now_dt.weekday()
            days_ahead = (idx - cur_idx) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next occurrence
            target_dt = (now_dt + timedelta(days=days_ahead)).replace(hour=18, minute=0, second=0)
            return target_dt.timestamp(), f"{day_name.capitalize()} ({target_dt.strftime('%b %d')})"

    # ISO formats
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(clean, fmt)
            if parsed.year < 2000:
                parsed = parsed.replace(year=now_dt.year)
            return parsed.timestamp(), parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None, text.strip()


@dataclass
class GoalStep:
    id: str
    title: str
    status: str = "pending"          # pending, in_progress, completed, blocked
    assigned_to: str = "user"        # user, subagent, jarvis
    subagent_id: Optional[str] = None
    notes: str = ""
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "assigned_to": self.assigned_to,
            "subagent_id": self.subagent_id,
            "notes": self.notes,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GoalStep":
        return cls(
            id=data.get("id") or f"step-{uuid.uuid4().hex[:6]}",
            title=data.get("title", "Milestone step"),
            status=data.get("status", "pending"),
            assigned_to=data.get("assigned_to", "user"),
            subagent_id=data.get("subagent_id"),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", time.time()),
            completed_at=data.get("completed_at", 0.0)
        )


@dataclass
class Goal:
    id: str
    title: str
    description: str = ""
    target_date: str = ""
    target_timestamp: Optional[float] = None
    status: str = "active"           # active, completed, paused, abandoned
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    steps: List[GoalStep] = field(default_factory=list)
    progress: float = 0.0            # 0.0 to 1.0
    auto_dispatch: bool = False
    last_nudged_at: float = 0.0
    tags: List[str] = field(default_factory=list)

    def recalculate_progress(self):
        """Updates progress fraction and auto-completes goal if all steps are done."""
        if not self.steps:
            self.progress = 0.0
            return
        completed_count = sum(1 for s in self.steps if s.status == "completed")
        self.progress = round(completed_count / len(self.steps), 2)
        if completed_count == len(self.steps) and self.steps:
            if self.status == "active":
                self.status = "completed"
                self.completed_at = time.time()
        elif self.status == "completed" and completed_count < len(self.steps):
            self.status = "active"
            self.completed_at = 0.0
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "target_date": self.target_date,
            "target_timestamp": self.target_timestamp,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "steps": [s.to_dict() for s in self.steps],
            "progress": self.progress,
            "auto_dispatch": self.auto_dispatch,
            "last_nudged_at": self.last_nudged_at,
            "tags": list(self.tags)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Goal":
        steps_raw = data.get("steps") or []
        steps = [GoalStep.from_dict(s) for s in steps_raw]
        g = cls(
            id=data.get("id") or f"goal-{uuid.uuid4().hex[:6]}",
            title=data.get("title", "Untitled Goal"),
            description=data.get("description", ""),
            target_date=data.get("target_date", ""),
            target_timestamp=data.get("target_timestamp"),
            status=data.get("status", "active"),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            completed_at=data.get("completed_at", 0.0),
            steps=steps,
            progress=data.get("progress", 0.0),
            auto_dispatch=bool(data.get("auto_dispatch", False)),
            last_nudged_at=data.get("last_nudged_at", 0.0),
            tags=list(data.get("tags") or [])
        )
        g.recalculate_progress()
        return g


class GoalTracker:
    """Manages multi-session persistence, step progression, and autonomous execution."""

    def __init__(self, brain=None, emitter=None, path: str = GOALS_FILE):
        self.brain = brain
        self.emitter = emitter or (lambda event, **data: None)
        self.path = path
        self._lock = threading.RLock()
        self.goals: Dict[str, Goal] = {}
        self._load()

    def _load(self):
        with self._lock:
            data = store.read_json(self.path, {})
            goals_list = data.get("goals") or []
            self.goals = {}
            for item in goals_list:
                try:
                    g = Goal.from_dict(item)
                    self.goals[g.id] = g
                except Exception as e:
                    print(f"[goals] Error loading goal: {e}", flush=True)

    def _save(self):
        with self._lock:
            payload = {
                "goals": [g.to_dict() for g in self.goals.values()],
                "saved_at": time.time()
            }
            store.write_json(self.path, payload, private=True)

    # -------------------------------------------------------------------------
    # Goal Creation & Decomposition
    # -------------------------------------------------------------------------

    def create_goal(
        self,
        title: str,
        description: str = "",
        target_date: str = "",
        steps: Optional[List[Dict[str, Any]]] = None,
        auto_decompose: bool = True,
        auto_dispatch: bool = False,
        tags: Optional[List[str]] = None
    ) -> Goal:
        """Creates a persistent goal, optionally decomposing into milestone steps."""
        goal_id = f"goal-{uuid.uuid4().hex[:6]}"
        target_ts, date_label = parse_target_date(target_date)

        goal = Goal(
            id=goal_id,
            title=title.strip(),
            description=description.strip(),
            target_date=date_label or target_date,
            target_timestamp=target_ts,
            status="active",
            auto_dispatch=auto_dispatch,
            tags=tags or []
        )

        if steps:
            for s in steps:
                if isinstance(s, dict):
                    goal.steps.append(GoalStep.from_dict(s))
                elif isinstance(s, str) and s.strip():
                    goal.steps.append(GoalStep(id=f"step-{uuid.uuid4().hex[:4]}", title=s.strip()))
        elif auto_decompose:
            decomposed_steps = self.decompose_goal_steps(goal.title, goal.description)
            goal.steps = decomposed_steps

        goal.recalculate_progress()

        with self._lock:
            self.goals[goal_id] = goal
            self._save()

        # Emit events for QML chat and floating notch
        self.emitter("goal_created", goal=goal.to_dict())
        self.emitter("log", who="jarvis", text=f"🎯 **New Goal Recorded**: {goal.title} ({len(goal.steps)} milestones)")

        # If auto-dispatch enabled, launch first subagent step if available
        if auto_dispatch and goal.steps:
            first_sub = next((s for s in goal.steps if s.assigned_to == "subagent" and s.status == "pending"), None)
            if first_sub:
                self.dispatch_step_worker(goal.id, first_sub.id)

        return goal

    def decompose_goal_steps(self, title: str, description: str = "") -> List[GoalStep]:
        """Decomposes a high-level goal into 3-6 actionable milestone steps."""
        # 1. Try Brain AI decomposition if brain is available
        if self.brain and hasattr(self.brain, "ask"):
            try:
                prompt = (
                    f"Break down this goal into 3 to 5 clear, actionable sequential milestone steps:\n"
                    f"Goal: '{title}'\n"
                    f"Details: '{description}'\n\n"
                    f"Respond ONLY with a valid JSON array of objects with keys:\n"
                    f"  - 'title': concise step name\n"
                    f"  - 'assigned_to': 'user' if it requires human decision/testing, or 'subagent' if Jarvis can research/code/execute it autonomously.\n"
                    f"Example:\n"
                    f"[{{\"title\": \"Design database schema\", \"assigned_to\": \"subagent\"}}, {{\"title\": \"Review and approve API routes\", \"assigned_to\": \"user\"}}]"
                )
                raw = self.brain.ask(prompt, unattended=True)
                clean_json = raw.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()

                parsed = json.loads(clean_json)
                if isinstance(parsed, list) and parsed:
                    steps = []
                    for i, item in enumerate(parsed[:6], 1):
                        steps.append(GoalStep(
                            id=f"step-{i}",
                            title=str(item.get("title", f"Step {i}")).strip(),
                            assigned_to="subagent" if item.get("assigned_to") == "subagent" else "user"
                        ))
                    if steps:
                        return steps
            except Exception as e:
                print(f"[goals] AI decomposition fallback to heuristic: {e}", flush=True)

        # 2. Robust Heuristic Rule-Based Decomposition Fallback
        t_lower = title.lower()
        if any(w in t_lower for w in ("plugin", "mod", "spigot", "paper", "minecraft")):
            return [
                GoalStep(id="step-1", title="Define plugin architecture & configuration schema", assigned_to="user"),
                GoalStep(id="step-2", title="Scaffold project build scripts and event listeners", assigned_to="subagent"),
                GoalStep(id="step-3", title="Implement core game logic and command handlers", assigned_to="user"),
                GoalStep(id="step-4", title="Compile test JAR and audit runtime logs", assigned_to="subagent"),
                GoalStep(id="step-5", title="Package release and publish documentation", assigned_to="user")
            ]
        elif any(w in t_lower for w in ("app", "website", "frontend", "ui", "hud")):
            return [
                GoalStep(id="step-1", title="Draft wireframe layout and user flows", assigned_to="user"),
                GoalStep(id="step-2", title="Build component layout and mock data structures", assigned_to="subagent"),
                GoalStep(id="step-3", title="Wire API endpoints and state management", assigned_to="user"),
                GoalStep(id="step-4", title="Test viewport responsiveness and accessibility", assigned_to="subagent"),
                GoalStep(id="step-5", title="Deploy build and run user acceptance checks", assigned_to="user")
            ]
        elif any(w in t_lower for w in ("research", "study", "paper", "learn", "course")):
            return [
                GoalStep(id="step-1", title="Gather top authoritative sources and papers", assigned_to="subagent"),
                GoalStep(id="step-2", title="Synthesize core findings and comparative summary", assigned_to="subagent"),
                GoalStep(id="step-3", title="Review insights and draft executive brief", assigned_to="user"),
                GoalStep(id="step-4", title="Complete final review and archive notes", assigned_to="user")
            ]
        else:
            return [
                GoalStep(id="step-1", title="Plan scope, deliverables and requirements", assigned_to="user"),
                GoalStep(id="step-2", title="Execute foundational implementation", assigned_to="subagent"),
                GoalStep(id="step-3", title="Iterate on core features and solve blockers", assigned_to="user"),
                GoalStep(id="step-4", title="Perform final testing and ship release", assigned_to="user")
            ]

    # -------------------------------------------------------------------------
    # Management & Queries
    # -------------------------------------------------------------------------

    def list_goals(self, status: Optional[str] = "active") -> List[Dict[str, Any]]:
        """Returns goals matching status (or all if status is None/all)."""
        self.sync_subagents()
        with self._lock:
            res = []
            for g in self.goals.values():
                if status and status != "all" and g.status != status:
                    continue
                res.append(g.to_dict())
            return sorted(res, key=lambda x: (x["status"] != "active", x["target_timestamp"] or 1e12))

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        self.sync_subagents()
        with self._lock:
            return self.goals.get(goal_id)

    def update_step(
        self,
        goal_id: str,
        step_id: str,
        status: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Updates status of a milestone step (pending, in_progress, completed, blocked)."""
        with self._lock:
            goal = self.goals.get(goal_id)
            if not goal:
                return {"ok": False, "error": f"Goal {goal_id} not found"}

            step = next((s for s in goal.steps if s.id == step_id), None)
            if not step:
                return {"ok": False, "error": f"Step {step_id} not found in goal {goal_id}"}

            step.status = status
            if notes is not None:
                step.notes = notes
            if status == "completed":
                step.completed_at = time.time()
            elif status != "completed":
                step.completed_at = 0.0

            goal.recalculate_progress()
            self._save()

        self.emitter("goal_updated", goal=goal.to_dict())
        pct = int(goal.progress * 100)
        self.emitter("log", who="jarvis", text=f"🎯 Goal '{goal.title}' updated: Step '{step.title}' is **{status}** ({pct}% complete)")

        return {"ok": True, "goal": goal.to_dict(), "step": step.to_dict()}

    def add_step(self, goal_id: str, title: str, assigned_to: str = "user") -> Dict[str, Any]:
        """Adds a new milestone step to an existing goal."""
        with self._lock:
            goal = self.goals.get(goal_id)
            if not goal:
                return {"ok": False, "error": f"Goal {goal_id} not found"}
            step_id = f"step-{len(goal.steps) + 1}"
            new_step = GoalStep(id=step_id, title=title.strip(), assigned_to=assigned_to)
            goal.steps.append(new_step)
            goal.recalculate_progress()
            self._save()

        self.emitter("goal_updated", goal=goal.to_dict())
        return {"ok": True, "goal": goal.to_dict(), "step": new_step.to_dict()}

    def delete_goal(self, goal_id: str) -> bool:
        """Deletes a goal from the tracker."""
        with self._lock:
            if goal_id in self.goals:
                del self.goals[goal_id]
                self._save()
                self.emitter("goal_deleted", id=goal_id)
                return True
            return False

    # -------------------------------------------------------------------------
    # Subagent Swarm Integration
    # -------------------------------------------------------------------------

    def dispatch_step_worker(self, goal_id: str, step_id: str) -> Dict[str, Any]:
        """Spawns an autonomous background subagent to execute a milestone step."""
        with self._lock:
            goal = self.goals.get(goal_id)
            if not goal:
                return {"ok": False, "error": f"Goal {goal_id} not found"}
            step = next((s for s in goal.steps if s.id == step_id), None)
            if not step:
                return {"ok": False, "error": f"Step {step_id} not found in goal {goal_id}"}

        try:
            import subagents
            mgr = subagents.get_subagent_manager(brain=self.brain, emitter=self.emitter)
            task_prompt = (
                f"Work on Milestone Step for Goal '{goal.title}':\n"
                f"Step: {step.title}\n"
                f"Goal Context: {goal.description or goal.title}\n"
                f"Perform the necessary research, coding, or testing, and summarize key deliverables."
            )
            cat = "coding" if any(w in step.title.lower() for w in ("code", "build", "script", "test", "jar", "compile")) else "research"
            sub = mgr.spawn(task_prompt, category=cat, brain=self.brain)

            with self._lock:
                step.assigned_to = "subagent"
                step.subagent_id = sub.id
                step.status = "in_progress"
                goal.updated_at = time.time()
                self._save()

            self.emitter("goal_step_dispatched", goal_id=goal.id, step_id=step.id, subagent_id=sub.id)
            self.emitter("log", who="jarvis", text=f"🤖 Dispatched background subagent `{sub.id}` to tackle '{step.title}'.")

            return {"ok": True, "subagent_id": sub.id, "step": step.to_dict()}
        except Exception as e:
            return {"ok": False, "error": f"Failed to dispatch subagent: {e}"}

    def sync_subagents(self):
        """Scans active goals for linked subagents that finished, and auto-completes steps."""
        try:
            import subagents
            mgr = subagents.get_subagent_manager(brain=self.brain)
            all_subs = {s["id"]: s for s in mgr.list_subagents()}
        except Exception:
            return

        with self._lock:
            changed = False
            for goal in self.goals.values():
                if goal.status != "active":
                    continue
                for step in goal.steps:
                    if step.subagent_id and step.status == "in_progress":
                        sub_info = all_subs.get(step.subagent_id)
                        if sub_info and sub_info.get("status") == "completed":
                            step.status = "completed"
                            step.completed_at = time.time()
                            res = sub_info.get("result_summary") or sub_info.get("result", "")
                            step.notes = f"Completed by subagent {step.subagent_id}: {res[:200]}"
                            changed = True
                            pct = int(goal.progress * 100)
                            self.emitter("log", who="jarvis", text=f"✅ Subagent finished milestone '{step.title}' for goal '{goal.title}'!")

                if changed:
                    goal.recalculate_progress()

            if changed:
                self._save()

    # -------------------------------------------------------------------------
    # Proactive Nudge Engine
    # -------------------------------------------------------------------------

    def evaluate_goal_nudges(self, min_nudge_interval: int = 43200) -> List[Dict[str, Any]]:
        """Scans active goals and generates contextual nudges for approaching deadlines or stalled steps."""
        self.sync_subagents()
        now = time.time()
        nudges = []

        with self._lock:
            for goal in self.goals.values():
                if goal.status != "active":
                    continue

                # Don't nudge too frequently for the same goal (default: 12 hours)
                if now - goal.last_nudged_at < min_nudge_interval:
                    continue

                # Find next pending or in_progress step
                next_step = next((s for s in goal.steps if s.status in ("pending", "in_progress")), None)
                if not next_step:
                    continue

                pct = int(goal.progress * 100)
                nudge_text = ""
                urgency = "medium"

                # Check 1: Impending deadline within 48h
                if goal.target_timestamp:
                    hours_left = (goal.target_timestamp - now) / 3600.0
                    if 0 < hours_left <= 48 and goal.progress < 0.8:
                        time_left_str = f"{int(round(hours_left))} hours" if hours_left < 24 else f"{int(round(hours_left/24))} days"
                        nudge_text = (
                            f"Goal '{goal.title}' is due in {time_left_str} and is {pct}% complete. "
                            f"Next milestone: '{next_step.title}'. "
                            f"{'Shall I dispatch a background subagent for it?' if next_step.assigned_to == 'subagent' else 'Ready to move this forward?'}"
                        )
                        urgency = "high"

                # Check 2: Stalled goal (no progress in 24 hours)
                if not nudge_text and (now - goal.updated_at > 86400):
                    nudge_text = (
                        f"Check-in on goal '{goal.title}' ({pct}% done). "
                        f"Current milestone: '{next_step.title}'. "
                        f"Would you like me to tackle this or break it down further?"
                    )
                    urgency = "low"

                if nudge_text:
                    goal.last_nudged_at = now
                    nudges.append({
                        "id": f"nudge_{goal.id}_{int(now)}",
                        "goal_id": goal.id,
                        "goal_title": goal.title,
                        "step_id": next_step.id,
                        "step_title": next_step.title,
                        "text": nudge_text,
                        "progress": goal.progress,
                        "urgency": urgency,
                        "action": {
                            "type": "dispatch_goal_step" if next_step.assigned_to == "subagent" else "view_goal",
                            "goal_id": goal.id,
                            "step_id": next_step.id
                        }
                    })

            if nudges:
                self._save()

        return nudges


# -----------------------------------------------------------------------------
# Singleton Instance
# -----------------------------------------------------------------------------
_tracker_instance: Optional[GoalTracker] = None


def get_goal_tracker(brain=None, emitter=None) -> GoalTracker:
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = GoalTracker(brain=brain, emitter=emitter)
    else:
        if brain and not _tracker_instance.brain:
            _tracker_instance.brain = brain
        if emitter:
            _tracker_instance.emitter = emitter
    return _tracker_instance
