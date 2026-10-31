import sys
import time
import unittest

sys.path.insert(0, r"C:\Users\User\Desktop\jarvis-assistant")
import jev
import subagents
from subagents import SubagentManager, get_subagent_manager


class MockBrain:
    def __init__(self):
        self.contents = []

    def ask_subagent(self, text, on_tool=None, on_thought=None, cancel_event=None):
        for i in range(3):
            if cancel_event and cancel_event.is_set():
                return "Cancelled early."
            if on_tool:
                on_tool(f"mock_tool_step_{i+1}", {"step": i+1})
            time.sleep(0.08)
        return f"Mock subagent finished: analyzed {text}"

    def ask(self, text, unattended=False):
        return f"Instant reply to: {text}"


class TestSubagents(unittest.TestCase):
    def test_jev_background_routing(self):
        r1 = jev.route_intent("Audit our entire codebase for memory leaks in the background")
        self.assertTrue(r1.get("is_background"))
        self.assertEqual(r1.get("intent"), "background")
        self.assertIn("Audit our entire codebase for memory leaks", r1.get("background_task"))

        r2 = jev.route_intent("Spawn subagent to simulate 500 waves of Base Defense")
        self.assertTrue(r2.get("is_background"))

        r3 = jev.route_intent("What is the weather in Bucharest today?")
        self.assertFalse(r3.get("is_background", False))

    def test_subagent_lifecycle(self):
        mock_brain = MockBrain()
        events = []
        mgr = SubagentManager(brain=mock_brain, emitter=lambda ev, **kw: events.append((ev, kw)))

        # 1. Spawn subagent
        sub = mgr.spawn("Test background audit", category="audit", brain=mock_brain)
        self.assertTrue(sub.id.startswith("sub-"))
        self.assertEqual(sub.category, "audit")

        # 2. Wait for completion (3 steps of 0.08s = ~0.24s)
        for _ in range(20):
            time.sleep(0.05)
            if sub.status == "completed":
                break

        # 3. Check status
        tasks = mgr.list_subagents()
        finished = next((t for t in tasks if t["id"] == sub.id), None)
        self.assertIsNotNone(finished)
        self.assertEqual(finished["status"], "completed")
        self.assertIn("Mock subagent finished", finished["result_summary"])
        self.assertEqual(len(finished["steps"]), 3)

        # 4. Check events
        event_names = [e[0] for e in events]
        self.assertIn("subagent_started", event_names)
        self.assertIn("subagent_progress", event_names)
        self.assertIn("subagent_finished", event_names)

    def test_subagent_cancellation(self):
        class SlowBrain:
            def ask_subagent(self, text, on_tool=None, on_thought=None, cancel_event=None):
                while not (cancel_event and cancel_event.is_set()):
                    time.sleep(0.05)
                return "Stopped."

        mgr = SubagentManager(brain=SlowBrain())
        sub = mgr.spawn("Long running task", category="general")
        self.assertIn(sub.status, ("pending", "running"))
        time.sleep(0.1)

        ok = mgr.cancel(sub.id)
        self.assertTrue(ok)
        for _ in range(15):
            time.sleep(0.05)
            if sub.status == "cancelled":
                break
        self.assertEqual(sub.status, "cancelled")

    def test_non_blocking_chat_concurrency(self):
        # Verify that while subagent is running, main chat is responsive instantly
        mock_brain = MockBrain()
        mgr = SubagentManager(brain=mock_brain)

        t0 = time.time()
        sub = mgr.spawn("Heavy 5000-wave Monte Carlo simulation", brain=mock_brain)

        # Chat ask should be instant (<0.05s), not blocked by subagent!
        chat_reply = mock_brain.ask("What is 10 + 20?")
        chat_elapsed = time.time() - t0

        self.assertLess(chat_elapsed, 0.08)
        self.assertEqual(chat_reply, "Instant reply to: What is 10 + 20?")

        for _ in range(20):
            time.sleep(0.05)
            if sub.status == "completed":
                break
        self.assertEqual(sub.status, "completed")


if __name__ == "__main__":
    unittest.main()
