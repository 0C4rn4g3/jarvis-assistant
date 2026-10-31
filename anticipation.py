"""
J.A.R.V.I.S. Proactive Briefings & Anticipation Engine
=====================================================
Transforms Jarvis from reactive to proactive:
  1. Meeting & Doc Prep Anticipator: "Your meeting is in 20 minutes and you haven't opened the doc"
  2. Multi-Pillar Morning Briefing: Synthesizes weather, schedule, urgent emails, deadlines & overnight subagents
  3. Urgent Email Radar: Detects unread high-priority emails with critical action keywords
  4. Deadline & Classroom Radar: Warns about impending submissions due today
  5. Subagent Swarm Digest: Announces completed background worker results
  6. Context & Focus Awareness: Suppresses spoken interruptions if user is in a full-screen 3D game
"""

import os
import re
import json
import time
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import store
import system
import hardware

STATE_FILE = os.path.join(store.DATA, "anticipation_state.json")
DOC_URL_PATTERN = re.compile(
    r"https?://(?:docs\.google\.com/(?:document|spreadsheets|presentation)/d/[^\s\"'>]+|"
    r"notion\.so/[^\s\"'>]+|figma\.com/[^\s\"'>]+|[^\s\"'>]+\.sharepoint\.com/[^\s\"'>]+|"
    r"[^\s\"'>]+\.(?:pdf|docx?|xlsx?|pptx?))",
    re.I
)
DOC_NAME_PATTERN = re.compile(
    r"\b(?:doc|deck|sheet|slides?|agenda|notes?|brief|proposal|spec|prd|roadmap)\s*[:\-]?\s*[\"']?([A-Za-z0-9 _\-\.]{3,40})[\"']?",
    re.I
)
URGENT_EMAIL_PATTERN = re.compile(
    r"\b(urgent|asap|action required|important|deadline|invoice|payment due|contract|immediate attention|emergency)\b",
    re.I
)


class AnticipationStore:
    """Manages persistent state and cooldowns for proactive alerts."""

    def __init__(self, path: str = STATE_FILE):
        self.path = path
        self._lock = threading.RLock()
        self.state: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        data = store.read_json(self.path, {})
        data.setdefault("seen_alerts", {})           # id -> alert_metadata
        data.setdefault("seen_emails", [])           # list of email IDs
        data.setdefault("seen_subagents", [])        # list of subagent task IDs
        data.setdefault("last_briefing_day", "")     # YYYY-MM-DD
        data.setdefault("last_alert_time", 0.0)      # timestamp
        return data

    def save(self):
        with self._lock:
            # Prune old alerts older than 7 days
            now = time.time()
            self.state["seen_alerts"] = {
                k: v for k, v in self.state.get("seen_alerts", {}).items()
                if now - v.get("time", 0) < 7 * 86400
            }
            store.write_json(self.path, self.state, private=True)

    def is_alert_seen(self, alert_id: str) -> bool:
        with self._lock:
            return alert_id in self.state.get("seen_alerts", {})

    def record_alert(self, alert_id: str, metadata: Optional[Dict[str, Any]] = None):
        with self._lock:
            self.state["seen_alerts"][alert_id] = {
                "time": time.time(),
                **(metadata or {})
            }
            self.state["last_alert_time"] = time.time()
            self.save()

    def is_email_seen(self, email_id: str) -> bool:
        with self._lock:
            return email_id in self.state.get("seen_emails", [])

    def record_email(self, email_id: str):
        with self._lock:
            emails = self.state.setdefault("seen_emails", [])
            if email_id not in emails:
                emails.append(email_id)
                if len(emails) > 200:
                    self.state["seen_emails"] = emails[-100:]
                self.save()

    def is_subagent_seen(self, sub_id: str) -> bool:
        with self._lock:
            return sub_id in self.state.get("seen_subagents", [])

    def record_subagent(self, sub_id: str):
        with self._lock:
            subs = self.state.setdefault("seen_subagents", [])
            if sub_id not in subs:
                subs.append(sub_id)
                if len(subs) > 100:
                    self.state["seen_subagents"] = subs[-50:]
                self.save()

    def was_briefing_given_today(self) -> bool:
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            return self.state.get("last_briefing_day") == today

    def mark_briefing_given_today(self):
        with self._lock:
            today = datetime.now().strftime("%Y-%m-%d")
            self.state["last_briefing_day"] = today
            self.save()

    def can_announce_voice(self, min_interval_sec: int = 300) -> bool:
        with self._lock:
            return time.time() - self.state.get("last_alert_time", 0.0) >= min_interval_sec


class ProactiveEngine:
    """Core proactive coordinator checking context, calendar, email, and deadlines."""

    def __init__(self, brain=None, live=None, emitter=None):
        self.brain = brain
        self.live = live
        self.emitter = emitter or (lambda event, **data: None)
        self.store = AnticipationStore()
        self.active_anticipations: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Starts the proactive background anticipation thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AnticipationEngine")
        self._thread.start()
        print("[anticipation] Proactive briefings & anticipation engine started", flush=True)

    def stop(self):
        self._running = False

    def _loop(self):
        # Allow system to finish initializing first
        time.sleep(10)
        while self._running:
            try:
                self.evaluate_anticipation_cycle()
            except Exception as e:
                print(f"[anticipation] cycle error: {e}", flush=True)
            # Sleep 60s between proactive sweeps
            time.sleep(60)

    # -------------------------------------------------------------------------
    # Evaluation Cycle
    # -------------------------------------------------------------------------

    def evaluate_anticipation_cycle(self):
        """Runs one full anticipation scan across all context channels."""
        cfg = store.settings()
        if not cfg.get("anticipation_engine", True):
            return

        # 1. Morning Briefing Check (5:00 AM - 11:30 AM)
        now_dt = datetime.now()
        if (
            cfg.get("morning_briefing", True)
            and 5 <= now_dt.hour < 12
            and not self.store.was_briefing_given_today()
        ):
            self.trigger_morning_briefing(force=False)

        # 2. Meeting & Document Preparation Anticipation
        lead_min = int(cfg.get("anticipation_meeting_lead_min", 20))
        self.check_meeting_prep(lead_minutes=lead_min)

        # 3. Urgent Unread Email Radar
        if cfg.get("anticipation_urgent_emails", True):
            self.check_urgent_emails()

        # 4. Completed Subagent Swarm Results
        self.check_subagent_completions()

        # 5. Deadlines Due Today
        self.check_impending_deadlines()

        # 6. Persistent Goal Tracker Nudges
        self.check_goal_nudges()

    # -------------------------------------------------------------------------
    # 1. Meeting & Document Prep Anticipation
    # -------------------------------------------------------------------------

    def check_meeting_prep(self, lead_minutes: int = 20):
        """Watches upcoming calendar events and checks if linked docs are already open."""
        if not self.brain or "googlecalendar" not in getattr(self.brain, "connected", set()):
            return

        now = time.time()
        from datetime import datetime
        stamp = lambda t: datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")
        # Look ahead 45 minutes
        data = self.brain.app_data(
            "GOOGLECALENDAR_EVENTS_LIST",
            {
                "calendarId": "primary",
                "timeMin": stamp(now),
                "timeMax": stamp(now + 45 * 60),
                "singleEvents": True,
                "orderBy": "startTime"
            }
        )
        if not data or not data.get("items"):
            return

        open_windows_str = " ".join(system.list_windows()).lower()

        for event in data["items"]:
            event_id = event.get("id")
            start_str = (event.get("start") or {}).get("dateTime")
            if not start_str or not event_id:
                continue

            # Parse start time
            try:
                # Handle RFC3339 timezone string
                clean_ts = re.sub(r":(\d\d)$", r"\1", start_str)
                event_start = datetime.fromisoformat(clean_ts).timestamp()
            except Exception:
                continue

            mins_until = int((event_start - now) / 60)
            # Trigger between [lead_minutes - 3, lead_minutes + 5] (e.g. 17-25 min)
            if not (lead_minutes - 4 <= mins_until <= lead_minutes + 5):
                continue

            alert_id = f"meeting_doc_{event_id}_{int(event_start)}"
            if self.store.is_alert_seen(alert_id):
                continue

            summary = event.get("summary", "Upcoming Meeting").strip()
            desc = (event.get("description") or "") + " " + summary

            # Look for docs / slide decks / spreadsheets
            doc_urls = DOC_URL_PATTERN.findall(desc)
            doc_names = DOC_NAME_PATTERN.findall(desc)

            target_doc = doc_urls[0] if doc_urls else (doc_names[0] if doc_names else None)

            # Check if doc or meeting app is already on screen
            doc_is_open = False
            if target_doc:
                clean_kw = re.sub(r"https?://|www\.|\.com|/.*", "", target_doc).lower()
                doc_is_open = clean_kw in open_windows_str or any(w in open_windows_str for w in re.findall(r"\w{4,}", str(target_doc).lower()))

            # If user hasn't opened doc or meeting
            if not doc_is_open and target_doc:
                msg = (
                    f"Your meeting '{summary}' is in {mins_until} minutes and you haven't opened the doc yet ({target_doc}). "
                    f"Shall I open it for you?"
                )
                self._dispatch_anticipation(
                    anticipation_id=alert_id,
                    kind="meeting_prep",
                    title=f"Meeting in {mins_until}m: {summary}",
                    text=msg,
                    action={"type": "open_url" if doc_urls else "open_target", "target": target_doc},
                    urgency="high" if mins_until <= 15 else "medium"
                )
                self.store.record_alert(alert_id, {"summary": summary, "mins": mins_until, "doc": target_doc})

    # -------------------------------------------------------------------------
    # 2. Urgent Unread Email Radar
    # -------------------------------------------------------------------------

    def check_urgent_emails(self):
        """Scans unread emails for high-priority / urgent triggers."""
        if not self.brain or "gmail" not in getattr(self.brain, "connected", set()):
            return

        try:
            res = self.brain.app_data(
                "GMAIL_FETCH_EMAILS",
                {"query": "is:unread (urgent OR ASAP OR \"action required\" OR deadline OR invoice OR payment OR critical)", "max_results": 3}
            )
            if not res:
                return

            messages = res.get("messages") or []
            for m in messages:
                m_id = m.get("id")
                if not m_id or self.store.is_email_seen(m_id):
                    continue

                subject = m.get("subject", "No subject").strip()
                sender = m.get("from", "Someone").strip()
                # Clean sender name
                sender_clean = re.sub(r"<[^>]+>", "", sender).strip() or sender

                alert_id = f"email_{m_id}"
                msg = f"Priority email from {sender_clean}: \"{subject}\"."

                self._dispatch_anticipation(
                    anticipation_id=alert_id,
                    kind="urgent_email",
                    title=f"Priority Email: {sender_clean}",
                    text=msg,
                    action={"type": "open_url", "target": f"https://mail.google.com/mail/u/0/#inbox/{m_id}"},
                    urgency="high"
                )
                self.store.record_email(m_id)
                self.store.record_alert(alert_id, {"sender": sender_clean, "subject": subject})
        except Exception as e:
            print(f"[anticipation] check_urgent_emails error: {e}", flush=True)

    # -------------------------------------------------------------------------
    # 3. Subagent Swarm Digest
    # -------------------------------------------------------------------------

    def check_subagent_completions(self):
        """Detects completed background subagents and surfaces their findings."""
        try:
            import subagents
            mgr = subagents.get_subagent_manager(brain=self.brain)
            recent = mgr.list_subagents()
            for sub in recent:
                s_id = sub.get("id")
                status = sub.get("status")
                if not s_id or status != "completed" or self.store.is_subagent_seen(s_id):
                    continue

                task = sub.get("task", "Background task")
                result = str(sub.get("result", "")).strip()
                preview = (result[:140] + "…") if len(result) > 140 else (result or "Ready.")

                alert_id = f"subagent_{s_id}"
                msg = f"Background subagent finished '{task}': {preview}"

                self._dispatch_anticipation(
                    anticipation_id=alert_id,
                    kind="subagent_done",
                    title=f"Subagent Completed: {task[:30]}",
                    text=msg,
                    action={"type": "view_subagent", "target": s_id},
                    urgency="low"
                )
                self.store.record_subagent(s_id)
                self.store.record_alert(alert_id, {"task": task})
        except Exception as e:
            print(f"[anticipation] check_subagent_completions error: {e}", flush=True)

    # -------------------------------------------------------------------------
    # 4. Impending Deadlines
    # -------------------------------------------------------------------------

    def check_impending_deadlines(self):
        """Warns about homework or project deadlines due today."""
        if not self.brain or "google_classroom" not in getattr(self.brain, "connected", set()):
            return

        try:
            now = time.time()
            for item in self.brain.classroom_work(days=2):
                if item.get("done"):
                    continue
                due = item.get("due", 0)
                hours_left = (due - now) / 3600.0
                if 0 < hours_left <= 12:
                    w_id = str(item.get("id", ""))
                    alert_id = f"deadline_today_{w_id}"
                    if not self.store.is_alert_seen(alert_id):
                        due_time = time.strftime("%H:%M", time.localtime(due))
                        title = item.get("title", "Assignment")
                        course = item.get("course", "Class")
                        msg = f"Deadline today: '{title}' ({course}) is due at {due_time}."

                        self._dispatch_anticipation(
                            anticipation_id=alert_id,
                            kind="deadline_warning",
                            title=f"Due at {due_time}: {title}",
                            text=msg,
                            action={"type": "open_url", "target": item.get("link") or "https://classroom.google.com"},
                            urgency="medium"
                        )
                        self.store.record_alert(alert_id, {"title": title, "course": course})
        except Exception as e:
            print(f"[anticipation] check_impending_deadlines error: {e}", flush=True)

    # -------------------------------------------------------------------------
    # 5. Persistent Goal Tracker Nudges
    # -------------------------------------------------------------------------

    def check_goal_nudges(self):
        """Scans active long-running goals and surfaces milestone nudges or subagent offers."""
        try:
            import goals
            tracker = goals.get_goal_tracker(brain=self.brain, emitter=self.emitter)
            nudges = tracker.evaluate_goal_nudges()
            for n in nudges:
                alert_id = n["id"]
                if not self.store.is_alert_seen(alert_id):
                    self._dispatch_anticipation(
                        anticipation_id=alert_id,
                        kind="goal_nudge",
                        title=f"Goal Check-In: {n['goal_title']}",
                        text=n["text"],
                        action=n.get("action"),
                        urgency=n.get("urgency", "medium")
                    )
                    self.store.record_alert(alert_id, {"goal_id": n["goal_id"], "progress": n["progress"]})
        except Exception as e:
            print(f"[anticipation] check_goal_nudges error: {e}", flush=True)

    # -------------------------------------------------------------------------
    # 6. Multi-Pillar Morning Briefing
    # -------------------------------------------------------------------------

    def generate_morning_briefing(self, force: bool = False) -> Dict[str, Any]:
        """Synthesizes weather, schedule, urgent emails, deadlines, and overnight subagent tasks."""
        now_dt = datetime.now()
        greeting = "Good morning!" if now_dt.hour < 12 else ("Good afternoon!" if now_dt.hour < 18 else "Good evening!")

        # 1. Weather
        weather_summary = "Weather currently unavailable."
        try:
            w = self.brain.tool_weather() if self.brain else {}
            if isinstance(w, dict) and w.get("now"):
                place = w.get("place", "").split(",")[0]
                now_str = w.get("now", "")
                weather_summary = f"In {place}, it's {now_str}."
        except Exception:
            pass

        # 2. Schedule
        schedule_items = []
        schedule_text = "No calendar events scheduled today."
        try:
            if self.brain and "googlecalendar" in getattr(self.brain, "connected", set()):
                midnight = now_dt.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
                day_start = midnight.isoformat()
                day_end = midnight.replace(hour=23, minute=59, second=59).isoformat()
                data = self.brain.app_data(
                    "GOOGLECALENDAR_EVENTS_LIST",
                    {"calendarId": "primary", "timeMin": day_start, "timeMax": day_end, "singleEvents": True, "orderBy": "startTime"}
                )
                for e in (data or {}).get("items") or []:
                    t_str = (e.get("start") or {}).get("dateTime", "All-day")[11:16]
                    schedule_items.append(f"{t_str} {e.get('summary', 'Meeting')}")
                if schedule_items:
                    schedule_text = f"You have {len(schedule_items)} event{'s' if len(schedule_items) > 1 else ''} today: " + ", ".join(schedule_items[:3]) + "."
        except Exception:
            pass

        # 3. Urgent Emails
        unread_count = 0
        email_text = ""
        try:
            if self.brain and "gmail" in getattr(self.brain, "connected", set()):
                unread = (self.brain.app_data("GMAIL_GET_LABEL", {"user_id": "me", "id": "INBOX"}) or {}).get("messagesUnread", 0)
                unread_count = int(unread)
                if unread_count > 0:
                    email_text = f"You have {unread_count} unread email{'s' if unread_count > 1 else ''} in your inbox."
        except Exception:
            pass

        # 4. Deadlines
        deadline_text = ""
        try:
            if self.brain and "google_classroom" in getattr(self.brain, "connected", set()):
                due_soon = [x for x in self.brain.classroom_work(days=2) if not x.get("done")]
                if due_soon:
                    top = due_soon[0]
                    t_str = time.strftime("%H:%M", time.localtime(top.get("due", 0)))
                    deadline_text = f"Classroom work due: '{top.get('title')}' at {t_str}."
        except Exception:
            pass

        # 5. Overnight Subagents & Leads
        subagents_text = ""
        try:
            import subagents
            mgr = subagents.get_subagent_manager(brain=self.brain)
            completed = [s for s in mgr.list_subagents() if s.get("status") == "completed"]
            if completed:
                subagents_text = f"Overnight subagents finished {len(completed)} background task{'s' if len(completed) > 1 else ''}."
        except Exception:
            pass

        # 6. Active Goals & Milestones
        goals_text = ""
        try:
            import goals
            tracker = goals.get_goal_tracker(brain=self.brain)
            active_goals = tracker.list_goals(status="active")
            if active_goals:
                top_goal = active_goals[0]
                pct = int(top_goal.get("progress", 0) * 100)
                next_step = next((s["title"] for s in top_goal.get("steps", []) if s.get("status") in ("pending", "in_progress")), None)
                next_str = f", next: '{next_step}'" if next_step else ""
                goals_text = f"Active goal '{top_goal['title']}' is {pct}% complete{next_str}."
        except Exception:
            pass

        # Synthesize spoken voice script (warm, brief 2-3 sentences)
        speech_parts = [greeting, weather_summary, schedule_text]
        if email_text:
            speech_parts.append(email_text)
        if deadline_text:
            speech_parts.append(deadline_text)
        if goals_text:
            speech_parts.append(goals_text)
        elif subagents_text:
            speech_parts.append(subagents_text)

        spoken_script = " ".join(p for p in speech_parts if p).strip()

        # Build Rich Markdown for Chat & Notch
        md_lines = [
            f"### ☀️ {greeting}",
            f"- **🌤️ Weather**: {weather_summary}",
            f"- **📅 Schedule**: {schedule_text}",
        ]
        if email_text:
            md_lines.append(f"- **📬 Inbox**: {email_text}")
        if deadline_text:
            md_lines.append(f"- **📚 Deadlines**: {deadline_text}")
        if goals_text:
            md_lines.append(f"- **🎯 Goals**: {goals_text}")
        if subagents_text:
            md_lines.append(f"- **🤖 Subagents**: {subagents_text}")

        markdown_report = "\n".join(md_lines)

        self.store.mark_briefing_given_today()

        return {
            "speech": spoken_script,
            "markdown": markdown_report,
            "weather": weather_summary,
            "schedule": schedule_items,
            "unread_count": unread_count,
            "timestamp": time.time()
        }

    def trigger_morning_briefing(self, force: bool = False):
        """Dispatches the morning briefing across UI, Voice, Notch, and Phone."""
        brief = self.generate_morning_briefing(force=force)

        # Emit to QML chat and notch
        self.emitter("log", who="jarvis", text=brief["markdown"])

        # Speak aloud if permitted and not gaming
        if self.live and not hardware.is_gaming_active():
            try:
                self.live.announce(brief["speech"])
            except Exception as e:
                print(f"[anticipation] voice announcement failed: {e}", flush=True)

        # Notify mobile phone
        try:
            system.notify("Morning Briefing", brief["speech"][:200])
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Proactive Dispatcher
    # -------------------------------------------------------------------------

    def _dispatch_anticipation(
        self,
        anticipation_id: str,
        kind: str,
        title: str,
        text: str,
        action: Optional[Dict[str, Any]] = None,
        urgency: str = "medium"
    ):
        """Surfaces proactive intelligence across Desktop, Notch, Voice, and Phone."""
        data = {
            "id": anticipation_id,
            "category": kind,
            "kind": kind,
            "title": title,
            "text": text,
            "action": action,
            "urgency": urgency,
            "time": time.time()
        }
        self.active_anticipations[anticipation_id] = data

        # 1. Desktop QML Chat and Floating Notch
        self.emitter("log", who="jarvis", text=f"💡 **Anticipation**: {text}")
        payload = {k: v for k, v in data.items() if k != "kind"}
        self.emitter("anticipation", **payload)

        # 2. Native OS Toast
        try:
            system.notify(f"Jarvis Anticipation", text[:250])
        except Exception:
            pass

        # 3. Spoken Voice Announcement (with Focus & Gaming Guard)
        is_gaming = hardware.is_gaming_active()
        can_voice = (
            self.live
            and not is_gaming
            and self.store.can_announce_voice(min_interval_sec=240 if urgency == "high" else 600)
        )
        if can_voice:
            try:
                self.live.announce(text)
            except Exception as e:
                print(f"[anticipation] live voice dispatch failed: {e}", flush=True)

        print(f"[anticipation] Surfaced: {title} ({urgency})", flush=True)

    def dismiss(self, anticipation_id: str):
        """Dismisses an active anticipation."""
        self.active_anticipations.pop(anticipation_id, None)

    def execute_action(self, anticipation_id: str) -> Dict[str, Any]:
        """Executes an action tied to an anticipation (e.g. opening a meeting doc)."""
        item = self.active_anticipations.pop(anticipation_id, None)
        if not item or not item.get("action"):
            return {"ok": False, "error": "Anticipation or action not found"}

        act = item["action"]
        act_type = act.get("type")
        target = act.get("target")

        if act_type == "open_url" and target:
            system.open_target(target)
            return {"ok": True, "action": "open_url", "target": target}
        elif act_type == "open_target" and target:
            system.open_target(target)
            return {"ok": True, "action": "open_target", "target": target}
        elif act_type == "dispatch_goal_step":
            import goals
            g_id = act.get("goal_id")
            s_id = act.get("step_id")
            return goals.get_goal_tracker(brain=self.brain, emitter=self.emitter).dispatch_step_worker(g_id, s_id)

        return {"ok": False, "error": f"Unknown action type: {act_type}"}


# Singleton Management
_engine_instance: Optional[ProactiveEngine] = None


def get_anticipation_engine(brain=None, live=None, emitter=None) -> ProactiveEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ProactiveEngine(brain=brain, live=live, emitter=emitter)
    else:
        if brain and not _engine_instance.brain:
            _engine_instance.brain = brain
        if live and not _engine_instance.live:
            _engine_instance.live = live
        if emitter:
            _engine_instance.emitter = emitter
    return _engine_instance
