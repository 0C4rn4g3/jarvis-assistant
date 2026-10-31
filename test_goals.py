"""
Automated Test Suite for Persistent Task & Goal Tracker
Tests:
  1. Goal creation, target date parsing, and multi-session JSON persistence.
  2. Autonomous milestone decomposition into sequential steps.
  3. Milestone step updates, notes, and dynamic progress recalculation (auto-completion).
  4. Swarm subagent dispatch and two-way status synchronization (auto-completing on worker finish).
  5. Proactive goal nudge generation for approaching deadlines and stalled milestones.
  6. Anticipation engine & Morning Briefing integration (Pillar 6 inclusion and action execution).
  7. REST API endpoints: GET /api/goals, POST /api/goals/create, step, dispatch, nudge, delete, and /api/today.
"""

import os
import sys
import time
import json
import unittest
from unittest.mock import MagicMock, patch

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
if REPO_DIR not in sys.path:
    sys.path.insert(0, REPO_DIR)

import store
import goals
import anticipation
import jarvis


class TestGoalTracker(unittest.TestCase):

    def setUp(self):
        self.test_goals_path = os.path.join(store.DATA, "test_goals.json")
        if os.path.exists(self.test_goals_path):
            try:
                os.remove(self.test_goals_path)
            except OSError:
                pass
        self.tracker = goals.GoalTracker(path=self.test_goals_path)

    def tearDown(self):
        if os.path.exists(self.test_goals_path):
            try:
                os.remove(self.test_goals_path)
            except OSError:
                pass

    def test_01_goal_creation_and_persistence(self):
        """Verify goals persist to disk, parse deadlines, and reload across sessions."""
        g = self.tracker.create_goal(
            title="Ship v1 of my Spigot plugin by Friday",
            description="Paper 1.21 anti-grief packet filter",
            target_date="Friday",
            auto_decompose=True
        )

        self.assertIsNotNone(g.id)
        self.assertEqual(g.title, "Ship v1 of my Spigot plugin by Friday")
        self.assertIn("Friday", g.target_date)
        self.assertIsNotNone(g.target_timestamp)
        self.assertTrue(g.target_timestamp > time.time())
        self.assertTrue(len(g.steps) >= 3)
        self.assertEqual(g.progress, 0.0)
        self.assertEqual(g.status, "active")

        # Reload a fresh tracker from the same file to verify multi-session persistence
        fresh_tracker = goals.GoalTracker(path=self.test_goals_path)
        loaded = fresh_tracker.get_goal(g.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.title, g.title)
        self.assertEqual(len(loaded.steps), len(g.steps))
        self.assertEqual(loaded.steps[0].title, g.steps[0].title)

    def test_02_step_updates_and_auto_completion(self):
        """Verify updating milestone steps recalculates progress and auto-completes goal."""
        g = self.tracker.create_goal(
            title="Launch landing page",
            steps=[
                {"title": "Draft copy", "assigned_to": "user"},
                {"title": "Implement HTML/CSS", "assigned_to": "subagent"},
                {"title": "Deploy to Vercel", "assigned_to": "user"}
            ],
            auto_decompose=False
        )
        self.assertEqual(len(g.steps), 3)
        self.assertEqual(g.progress, 0.0)

        # Complete step 1
        res1 = self.tracker.update_step(g.id, g.steps[0].id, status="completed", notes="Copy reviewed")
        self.assertTrue(res1["ok"])
        g = self.tracker.get_goal(g.id)
        self.assertEqual(g.progress, 0.33)
        self.assertEqual(g.status, "active")

        # Complete step 2
        self.tracker.update_step(g.id, g.steps[1].id, status="completed")
        g = self.tracker.get_goal(g.id)
        self.assertEqual(g.progress, 0.67)
        self.assertEqual(g.status, "active")

        # Complete step 3 -> Goal should auto-complete!
        self.tracker.update_step(g.id, g.steps[2].id, status="completed")
        g = self.tracker.get_goal(g.id)
        self.assertEqual(g.progress, 1.0)
        self.assertEqual(g.status, "completed")
        self.assertTrue(g.completed_at > 0)

        # Reverting a step re-opens the goal
        self.tracker.update_step(g.id, g.steps[2].id, status="pending")
        g = self.tracker.get_goal(g.id)
        self.assertEqual(g.progress, 0.67)
        self.assertEqual(g.status, "active")

    def test_03_subagent_worker_dispatch_and_sync(self):
        """Verify subagents can be dispatched for milestones and auto-resolve steps on finish."""
        g = self.tracker.create_goal(
            title="Analyze Indie Game Market",
            steps=[
                {"title": "Scrape top 10 RPGs on Steam", "assigned_to": "subagent"},
                {"title": "Write executive summary", "assigned_to": "user"}
            ],
            auto_decompose=False
        )
        step_id = g.steps[0].id

        mock_subagent = MagicMock()
        mock_subagent.id = "sub-test-99"
        mock_subagent.task = "Scrape top 10 RPGs on Steam"

        mock_mgr = MagicMock()
        mock_mgr.spawn.return_value = mock_subagent
        mock_mgr.list_subagents.return_value = [
            {
                "id": "sub-test-99",
                "status": "in_progress",
                "result": ""
            }
        ]

        with patch("subagents.get_subagent_manager", return_value=mock_mgr):
            # Dispatch subagent worker
            res = self.tracker.dispatch_step_worker(g.id, step_id)
            self.assertTrue(res["ok"])
            self.assertEqual(res["subagent_id"], "sub-test-99")

            g = self.tracker.get_goal(g.id)
            step = next(s for s in g.steps if s.id == step_id)
            self.assertEqual(step.status, "in_progress")
            self.assertEqual(step.subagent_id, "sub-test-99")

            # Simulate subagent completing its work
            mock_mgr.list_subagents.return_value = [
                {
                    "id": "sub-test-99",
                    "status": "completed",
                    "result_summary": "Extracted top 10 RPGs with 95% positive reviews."
                }
            ]

            # Trigger sync
            self.tracker.sync_subagents()

            # Verify step was automatically completed and notes populated!
            g = self.tracker.get_goal(g.id)
            step = next(s for s in g.steps if s.id == step_id)
            self.assertEqual(step.status, "completed")
            self.assertIn("Extracted top 10 RPGs", step.notes)
            self.assertEqual(g.progress, 0.5)

    def test_04_proactive_goal_nudges(self):
        """Verify nudge engine detects approaching deadlines and generates actionable check-ins."""
        now = time.time()
        # Goal due in 18 hours (approaching deadline)
        g = self.tracker.create_goal(
            title="Finish AI Video Generation Pipeline",
            target_date="Tomorrow",
            steps=[
                {"title": "Configure ComfyUI API wrapper", "assigned_to": "subagent"},
                {"title": "Test end-to-end rendering", "assigned_to": "user"}
            ],
            auto_decompose=False
        )
        g.target_timestamp = now + 18 * 3600
        self.tracker._save()

        nudges = self.tracker.evaluate_goal_nudges(min_nudge_interval=0)
        self.assertTrue(len(nudges) >= 1)
        nudge = next(n for n in nudges if n["goal_id"] == g.id)

        self.assertIn("Finish AI Video Generation Pipeline", nudge["goal_title"])
        self.assertIn("18 hours", nudge["text"])
        self.assertEqual(nudge["urgency"], "high")
        self.assertEqual(nudge["action"]["type"], "dispatch_goal_step")

    def test_05_anticipation_and_morning_briefing_integration(self):
        """Verify goals are included in multi-pillar morning briefings and anticipation cycles."""
        g = self.tracker.create_goal(
            title="Ship v1 of my Spigot plugin",
            target_date="Friday",
            steps=[{"title": "Write unit tests", "assigned_to": "subagent"}],
            auto_decompose=False
        )

        mock_brain = MagicMock()
        mock_brain.tool_weather.return_value = {"place": "Bucharest", "now": "15°C"}

        engine = anticipation.ProactiveEngine(brain=mock_brain)
        engine.store = anticipation.AnticipationStore(path=os.path.join(store.DATA, "test_ant_store.json"))

        with patch("goals.get_goal_tracker", return_value=self.tracker):
            brief = engine.generate_morning_briefing(force=True)

            # Pillar 6 should be in markdown and spoken script
            self.assertIn("Ship v1 of my Spigot plugin", brief["markdown"])
            self.assertIn("Write unit tests", brief["markdown"])
            self.assertIn("Ship v1 of my Spigot plugin", brief["speech"])

            # Test action execution of dispatch_goal_step
            with patch.object(self.tracker, "dispatch_step_worker", return_value={"ok": True, "subagent_id": "sub-1"}) as mock_dispatch:
                engine._dispatch_anticipation(
                    anticipation_id="test_goal_act",
                    kind="goal_nudge",
                    title="Goal Nudge",
                    text="Dispatch subagent?",
                    action={"type": "dispatch_goal_step", "goal_id": g.id, "step_id": g.steps[0].id}
                )
                res = engine.execute_action("test_goal_act")
                self.assertTrue(res["ok"])
                mock_dispatch.assert_called_once_with(g.id, g.steps[0].id)

    def test_06_rest_api_endpoints(self):
        """Verify jarvis.py REST API endpoints handle goal CRUD, dispatch, and /api/today."""
        mock_brain = MagicMock()
        mock_live = MagicMock()

        with patch("goals.get_goal_tracker", return_value=self.tracker):
            # POST /api/goals/create
            res = jarvis.api_post("/api/goals/create", {
                "title": "Build Discord Bot",
                "target_date": "Sunday",
                "description": "Slash commands for guild management"
            }, mock_live, mock_brain)

            self.assertTrue(res.get("ok"))
            created_goal = res["goal"]
            self.assertEqual(created_goal["title"], "Build Discord Bot")
            g_id = created_goal["id"]

            # GET /api/goals
            get_all = jarvis.api_get("/api/goals", mock_brain)
            self.assertTrue(any(g["id"] == g_id for g in get_all["goals"]))

            # GET /api/goals/<id>
            get_single = jarvis.api_get(f"/api/goals/{g_id}", mock_brain)
            self.assertIsNotNone(get_single.get("goal"))
            self.assertEqual(get_single["goal"]["id"], g_id)

            # POST /api/goals/step
            step_id = created_goal["steps"][0]["id"]
            step_res = jarvis.api_post("/api/goals/step", {
                "goal_id": g_id,
                "step_id": step_id,
                "status": "completed",
                "notes": "Done via REST"
            }, mock_live, mock_brain)
            self.assertTrue(step_res.get("ok"))
            self.assertEqual(step_res["step"]["status"], "completed")

            # POST /api/goals/nudge
            nudge_res = jarvis.api_post("/api/goals/nudge", {}, mock_live, mock_brain)
            self.assertTrue(nudge_res.get("ok"))

            # GET /api/today includes goals
            with patch("jarvis.weather", return_value={"temp": "15°C"}), \
                 patch("jarvis.store.read_json", return_value={}):
                today_res = jarvis.api_get("/api/today", mock_brain)
                self.assertIn("goals", today_res)
                self.assertTrue(any(g["id"] == g_id for g in today_res["goals"]))

            # POST /api/goals/delete
            del_res = jarvis.api_post("/api/goals/delete", {"id": g_id}, mock_live, mock_brain)
            self.assertTrue(del_res.get("ok"))
            self.assertIsNone(self.tracker.get_goal(g_id))


if __name__ == "__main__":
    unittest.main(verbosity=2)
