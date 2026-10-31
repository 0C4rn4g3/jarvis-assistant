"""
Automated Test Suite for Proactive Briefings & Anticipation Engine
Tests:
  1. AnticipationStore persistence, deduplication, cooldowns, and 7-day pruning.
  2. Meeting & Doc Prep Anticipator: detects unopened doc for meeting in ~20 min.
  3. Window suppression: if doc is already open on screen, no alert is raised.
  4. Urgent Email Radar: detects priority keywords (urgent, invoice) and deduplicates.
  5. Subagent Swarm Completion Digest: alerts on finished background jobs.
  6. Multi-Pillar Morning Briefing: synthesizes weather, schedule, emails, deadlines, subagents.
  7. Action Execution & Dismissal: execute_action opens target, dismiss removes active alert.
  8. REST API Endpoints: /api/anticipation/status, /api/anticipation/briefing, /api/anticipation/action, /api/anticipation/dismiss.
"""

import os
import sys
import time
import json
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

# Ensure desktop repo is in sys.path
REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import store
import anticipation
import jarvis


class TestAnticipationEngine(unittest.TestCase):

    def setUp(self):
        # Use a temporary state file in store.DATA for tests
        self.test_state_file = os.path.join(store.DATA, "test_anticipation_state.json")
        if os.path.exists(self.test_state_file):
            try:
                os.remove(self.test_state_file)
            except OSError:
                pass
        self.store = anticipation.AnticipationStore(path=self.test_state_file)

    def tearDown(self):
        if os.path.exists(self.test_state_file):
            try:
                os.remove(self.test_state_file)
            except OSError:
                pass

    def test_01_store_deduplication_and_cooldown(self):
        """Verify AnticipationStore records alerts, emails, subagents, and handles cooldowns."""
        self.assertFalse(self.store.is_alert_seen("alert_1"))
        self.store.record_alert("alert_1", {"title": "Meeting Doc"})
        self.assertTrue(self.store.is_alert_seen("alert_1"))

        # Email deduplication
        self.assertFalse(self.store.is_email_seen("email_101"))
        self.store.record_email("email_101")
        self.assertTrue(self.store.is_email_seen("email_101"))

        # Subagent deduplication
        self.assertFalse(self.store.is_subagent_seen("sub_99"))
        self.store.record_subagent("sub_99")
        self.assertTrue(self.store.is_subagent_seen("sub_99"))

        # Cooldown check: recorded alert just now, so min_interval 300s should return False
        self.assertFalse(self.store.can_announce_voice(min_interval_sec=300))

        # Morning briefing day tracking
        self.assertFalse(self.store.was_briefing_given_today())
        self.store.mark_briefing_given_today()
        self.assertTrue(self.store.was_briefing_given_today())

        # Prune old alerts
        self.store.state["seen_alerts"]["old_alert"] = {"time": time.time() - 8 * 86400}
        self.store.save()
        self.assertNotIn("old_alert", self.store.state["seen_alerts"])
        self.assertIn("alert_1", self.store.state["seen_alerts"])

    def test_02_meeting_prep_unopened_doc_detection(self):
        """Verify engine detects upcoming meeting with unopened doc and dispatches anticipation."""
        emitted_events = []
        def mock_emitter(event, **data):
            emitted_events.append((event, data))

        mock_brain = MagicMock()
        mock_brain.connected = {"googlecalendar"}

        # Meeting starting in exactly 20 minutes with a Google Doc link
        now = time.time()
        start_ts = datetime.fromtimestamp(now + 20 * 60).astimezone().isoformat(timespec="seconds")
        
        doc_url = "https://docs.google.com/document/d/1a2b3c4d5e_meeting_notes/edit"
        mock_calendar_response = {
            "items": [
                {
                    "id": "event_sync_123",
                    "summary": "Product Strategy Sync",
                    "description": f"Agenda and roadmap: {doc_url}",
                    "start": {"dateTime": start_ts}
                }
            ]
        }
        mock_brain.app_data.return_value = mock_calendar_response

        engine = anticipation.ProactiveEngine(brain=mock_brain, emitter=mock_emitter)
        engine.store = self.store

        with patch("system.list_windows", return_value=["Discord", "Visual Studio Code", "Calculator"]):
            engine.check_meeting_prep(lead_minutes=20)

        # Should have dispatched meeting_prep anticipation
        self.assertEqual(len(engine.active_anticipations), 1)
        alert_id = list(engine.active_anticipations.keys())[0]
        alert = engine.active_anticipations[alert_id]

        self.assertEqual(alert["kind"], "meeting_prep")
        self.assertIn("Product Strategy Sync", alert["title"])
        self.assertIn("haven't opened the doc yet", alert["text"])
        self.assertEqual(alert["action"]["type"], "open_url")
        self.assertEqual(alert["action"]["target"], doc_url)

        # Verify second check deduplicates
        engine.check_meeting_prep(lead_minutes=20)
        self.assertEqual(len(engine.active_anticipations), 1)

    def test_03_meeting_prep_already_open_suppression(self):
        """Verify engine does NOT alert if doc or document title is already open in windows."""
        emitted_events = []
        mock_brain = MagicMock()
        mock_brain.connected = {"googlecalendar"}

        now = time.time()
        start_ts = datetime.fromtimestamp(now + 20 * 60).astimezone().isoformat(timespec="seconds")
        doc_url = "https://docs.google.com/document/d/12345/edit"
        mock_brain.app_data.return_value = {
            "items": [
                {
                    "id": "event_sync_456",
                    "summary": "Marketing Review",
                    "description": f"Notes: {doc_url}",
                    "start": {"dateTime": start_ts}
                }
            ]
        }

        engine = anticipation.ProactiveEngine(brain=mock_brain, emitter=lambda ev, **d: emitted_events.append((ev, d)))
        engine.store = self.store

        # Window list has Google Docs open
        with patch("system.list_windows", return_value=["Google Chrome - Marketing Review - Google Docs"]):
            engine.check_meeting_prep(lead_minutes=20)

        # Zero anticipations because the doc is already visible
        self.assertEqual(len(engine.active_anticipations), 0)

    def test_04_urgent_email_detection(self):
        """Verify urgent unread emails are detected, alerted, and deduplicated."""
        emitted_events = []
        mock_brain = MagicMock()
        mock_brain.connected = {"gmail"}

        mock_brain.app_data.return_value = {
            "messages": [
                {
                    "id": "msg_urgent_888",
                    "from": "Alex CEO <alex@company.com>",
                    "subject": "Action Required: Q3 Server Infrastructure Invoice Overdue"
                }
            ]
        }

        engine = anticipation.ProactiveEngine(brain=mock_brain, emitter=lambda ev, **d: emitted_events.append((ev, d)))
        engine.store = self.store

        engine.check_urgent_emails()
        self.assertEqual(len(engine.active_anticipations), 1)
        alert = list(engine.active_anticipations.values())[0]

        self.assertEqual(alert["kind"], "urgent_email")
        self.assertIn("Alex CEO", alert["title"])
        self.assertIn("Action Required", alert["text"])
        self.assertEqual(alert["urgency"], "high")

        # Second sweep must deduplicate
        engine.check_urgent_emails()
        self.assertEqual(len(engine.active_anticipations), 1)

    def test_05_subagent_completion_detection(self):
        """Verify finished background subagent swarms surface automatically."""
        emitted_events = []
        engine = anticipation.ProactiveEngine(brain=MagicMock(), emitter=lambda ev, **d: emitted_events.append((ev, d)))
        engine.store = self.store

        mock_subagent_mgr = MagicMock()
        mock_subagent_mgr.list_subagents.return_value = [
            {
                "id": "sub_scrape_01",
                "task": "Find top 10 indie games on Steam",
                "status": "completed",
                "result": "Found 10 games with 90%+ positive reviews. Top game is Crow Country."
            }
        ]

        with patch("subagents.get_subagent_manager", return_value=mock_subagent_mgr):
            engine.check_subagent_completions()

        self.assertEqual(len(engine.active_anticipations), 1)
        alert = list(engine.active_anticipations.values())[0]
        self.assertEqual(alert["kind"], "subagent_done")
        self.assertIn("Crow Country", alert["text"])

    def test_06_morning_briefing_synthesis(self):
        """Verify multi-pillar morning briefing compiles weather, schedule, emails, and subagents."""
        mock_brain = MagicMock()
        mock_brain.connected = {"googlecalendar", "gmail"}
        mock_brain.tool_weather.return_value = {"place": "Bucharest, Romania", "now": "18°C, Partly cloudy"}
        mock_brain.app_data.side_effect = lambda tool, args: (
            {"items": [{"summary": "Quarterly Planning", "start": {"dateTime": "2026-10-31T14:00:00"}}]}
            if "CALENDAR" in tool else
            {"messagesUnread": 4}
        )

        engine = anticipation.ProactiveEngine(brain=mock_brain, emitter=MagicMock())
        engine.store = self.store

        brief = engine.generate_morning_briefing(force=True)

        self.assertIn("speech", brief)
        self.assertIn("markdown", brief)
        self.assertIn("18°C", brief["weather"])
        self.assertIn("Quarterly Planning", brief["speech"])
        self.assertIn("4 unread emails", brief["speech"])
        self.assertIn("### ☀️ Good", brief["markdown"])
        self.assertIn("Weather", brief["markdown"])

    def test_07_action_execution_and_dismissal(self):
        """Verify execute_action triggers system opener and dismiss removes alert."""
        engine = anticipation.ProactiveEngine()
        engine.store = self.store

        engine._dispatch_anticipation(
            anticipation_id="action_test_1",
            kind="meeting_prep",
            title="Prep Doc",
            text="Open doc?",
            action={"type": "open_url", "target": "https://docs.google.com/test"},
            urgency="high"
        )
        self.assertIn("action_test_1", engine.active_anticipations)

        # Test execution
        with patch("system.open_target") as mock_open:
            res = engine.execute_action("action_test_1")
            self.assertTrue(res["ok"])
            mock_open.assert_called_once_with("https://docs.google.com/test")

        # After execution, it's popped from active
        self.assertNotIn("action_test_1", engine.active_anticipations)

        # Test dismiss
        engine._dispatch_anticipation(
            anticipation_id="action_test_2",
            kind="info",
            title="Info",
            text="Some info"
        )
        self.assertIn("action_test_2", engine.active_anticipations)
        engine.dismiss("action_test_2")
        self.assertNotIn("action_test_2", engine.active_anticipations)

    def test_08_rest_api_routes(self):
        """Verify jarvis.py api_get and api_post handle anticipation endpoints."""
        mock_brain = MagicMock()
        mock_live = MagicMock()

        engine = anticipation.get_anticipation_engine(brain=mock_brain, live=mock_live)
        engine.active_anticipations.clear()
        engine._dispatch_anticipation("api_test_alert", "test", "Test Title", "Test Message")

        # GET /api/anticipation/status
        status_res = jarvis.api_get("/api/anticipation/status", mock_brain)
        self.assertIn("anticipations", status_res)
        self.assertEqual(len(status_res["anticipations"]), 1)
        self.assertEqual(status_res["anticipations"][0]["id"], "api_test_alert")

        # POST /api/anticipation/dismiss
        dismiss_res = jarvis.api_post("/api/anticipation/dismiss", {"id": "api_test_alert"}, mock_live, mock_brain)
        self.assertTrue(dismiss_res.get("ok"))
        self.assertNotIn("api_test_alert", engine.active_anticipations)

        # POST /api/anticipation/briefing
        brief_res = jarvis.api_post("/api/anticipation/briefing", {"force": True}, mock_live, mock_brain)
        self.assertTrue(brief_res.get("ok"))
        self.assertIn("speech", brief_res["briefing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
