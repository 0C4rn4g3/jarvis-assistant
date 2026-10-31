import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store
import brain
import jarvis
import subagents

print("--- TEST 1: Deadlock check in store.Sessions ---")
sess = store.Sessions()
t0 = time.time()
sess.add({"who": "tool", "text": "weather", "label": "Checking the weather"})
print(f"sess.add completed in {time.time()-t0:.4f}s (NO DEADLOCK)!")
assert sess.messages[-1]["who"] == "activity"
assert sess.messages[-1]["caption"] == "working"

print("--- TEST 2: Sessions.stop_activity ---")
sess.stop_activity()
assert sess.messages[-1]["caption"] == "stopped"
assert sess.messages[-1]["text"] == "Stopped"
print("stop_activity successfully updated activity status to stopped!")

print("--- TEST 3: brain.here() and tool_weather() ---")
t0 = time.time()
city = brain.here()
safe_city = city.encode("ascii", errors="replace").decode("ascii")
print(f"brain.here() returned in {time.time()-t0:.4f}s: {safe_city}")
t0 = time.time()
w = brain.tool_weather()
safe_place = w.get("place", "").encode("ascii", errors="replace").decode("ascii")
safe_now = w.get("now", "").encode("ascii", errors="replace").decode("ascii")
print(f"tool_weather() returned in {time.time()-t0:.2f}s: {safe_place}, {safe_now}")

print("--- TEST 4: SubagentManager.cancel_all ---")
b = brain.Brain()
mgr = subagents.get_subagent_manager(brain=b)
cancelled = mgr.cancel_all()
print(f"cancel_all executed cleanly, cancelled {cancelled} tasks")

print("--- TEST 5: api_post /api/stop responsiveness ---")
class DummyLive:
    def __init__(self):
        self.stopped = False
        self.session = None
        self.mic = False
    def stop(self):
        self.stopped = True
    def barge_in(self):
        pass
    def announce(self, text):
        pass

dummy_live = DummyLive()
jarvis.sessions.add({"who": "activity", "caption": "working", "text": "Working on it…"})
t0 = time.time()
out = jarvis.api_post("/api/stop", {}, dummy_live, b)
dt = (time.time() - t0) * 1000
print(f"/api/stop completed in {dt:.2f}ms, returned: {out}")
assert out.get("ok") is True
assert dummy_live.stopped is True
assert any(m.get("caption") == "stopped" or "Stopped" in m.get("text", "") for m in jarvis.sessions.messages)

print("--- TEST 6: End-to-end /api/ask weather query ---")
t0 = time.time()
jarvis.api_post("/api/ask", {"text": "whats the weather outside"}, dummy_live, b)
# Wait up to 8s for the worker thread to finish
for _ in range(80):
    time.sleep(0.1)
    if jarvis.shown_state[0] == "idle" and any(m.get("who") == "jarvis" for m in jarvis.sessions.messages[-3:]):
        break
dt = time.time() - t0
last_jarvis = next(m["text"] for m in reversed(jarvis.sessions.messages) if m.get("who") == "jarvis")
safe_reply = last_jarvis.encode("ascii", errors="replace").decode("ascii")
print(f"/api/ask answered in {dt:.2f}s: {safe_reply}")
assert dt < 8.0

print("\n>>> ALL 6 REGRESSION TESTS PASSED! <<<")
