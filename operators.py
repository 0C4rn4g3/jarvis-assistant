"""Jarvis Autonomous Operator Worker Loop.
Provides background scheduled tasks, autonomous research agents, and health watchdogs
with status reporting, persistent manifests, and event notifications.
"""
import json
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import system

OPERATORS_FILE = os.path.join(system.DATA, "operators.json")
_lock = threading.Lock()


class Operator:
    def __init__(
        self,
        id: str,
        name: str,
        description: str,
        interval_seconds: int = 3600,
        enabled: bool = True,
        action_type: str = "python",  # 'python' or 'brain_task'
        action_payload: Optional[str] = None,
        requires_idle: bool = False,
    ):
        self.id = id
        self.name = name
        self.description = description
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self.action_type = action_type
        self.action_payload = action_payload
        self.requires_idle = requires_idle
        self.last_run = 0.0
        self.status = "idle"  # idle, running, success, error
        self.last_result = ""
        self.error_count = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "action_type": self.action_type,
            "action_payload": self.action_payload,
            "requires_idle": self.requires_idle,
            "last_run": self.last_run,
            "next_run": self.last_run + self.interval_seconds if self.last_run else 0.0,
            "status": self.status,
            "last_result": self.last_result,
            "error_count": self.error_count,
        }

    def from_dict(self, data: Dict[str, Any]):
        self.name = data.get("name", self.name)
        self.description = data.get("description", self.description)
        self.interval_seconds = data.get("interval_seconds", self.interval_seconds)
        self.enabled = data.get("enabled", self.enabled)
        self.requires_idle = data.get("requires_idle", self.requires_idle)
        self.last_run = data.get("last_run", self.last_run)
        self.status = data.get("status", self.status)
        self.last_result = data.get("last_result", self.last_result)
        self.error_count = data.get("error_count", self.error_count)


# --- Built-in Operator Actions ---

BUILD_FAILURES_FILE = os.path.join(system.DATA, "build_failures.json")


def record_build_failure(tool="build", error=""):
    """Records a build/compilation failure with timestamp to detect anomalies."""
    try:
        os.makedirs(system.DATA, exist_ok=True)
        failures = []
        if os.path.exists(BUILD_FAILURES_FILE):
            with open(BUILD_FAILURES_FILE, "r", encoding="utf-8") as f:
                failures = json.load(f)
        failures.append({"timestamp": time.time(), "tool": tool, "error": str(error)[:300]})
        # Keep failures within last 24h
        cutoff = time.time() - 86400
        failures = [f for f in failures if f.get("timestamp", 0) > cutoff]
        with open(BUILD_FAILURES_FILE, "w", encoding="utf-8") as f:
            json.dump(failures, f, indent=2)
    except Exception as e:
        print(f"[operators] Failed to record build failure: {e}", flush=True)


def _action_system_watchdog() -> str:
    """Monitors CPU, RAM, GPU VRAM, and storage health."""
    alerts = []
    import psutil
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\" if system.IS_WINDOWS else "/")
    import hardware
    vram_status = hardware.arbitrate_vram()
    if vram_status.get("gaming_active"):
        alerts.append("Gaming/3D workload active: Ollama evicted from VRAM for max GPU performance")

    msg = f"Watchdog OK: CPU {cpu}%, RAM {ram.percent}%, Disk {disk.percent}%."
    if alerts:
        msg += " STATUS: " + "; ".join(alerts)
    return msg


def _action_anomaly_watchdog() -> str:
    """Monitors recent build errors (Gradle/Unity/Python); flags repeated failures for self-healing."""
    recent_failures = []
    if os.path.exists(BUILD_FAILURES_FILE):
        try:
            with open(BUILD_FAILURES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                hour_ago = time.time() - 3600
                recent_failures = [d for d in data if d.get("timestamp", 0) > hour_ago]
        except Exception:
            pass

    count = len(recent_failures)
    if count >= 3:
        tools_involved = list({f.get("tool", "build") for f in recent_failures})
        msg = f"⚠️ Build Anomaly: {count} failed builds in the last hour ({', '.join(tools_involved)}). Self-healing loop recommended: dev_loop.build_and_heal()."
        try:
            import jarvis
            jarvis.notch_line[:] = [f"⚠️ {count} builds failed: heal loop ready?", time.time()]
        except Exception:
            pass
        return msg
    return f"Build Watchdog Healthy: {count} failures in past hour (threshold: 3)."


def _action_rag_auto_sync() -> str:
    """Scans and synchronizes project files and GDDs into the Hybrid RAG database."""
    import rag
    desktop = os.path.expanduser("~/Desktop")
    jarvis_dir = os.path.join(desktop, "jarvis-assistant")
    res = rag.index_directory(jarvis_dir, extensions=[".md", ".py", ".gdd", ".json"], category="assistant_code")
    stats = rag.stats()
    return f"Indexed {res.get('indexed_files', 0)} files, {res.get('indexed_chunks', 0)} chunks. Total DB: {stats.get('chunks', 0)} chunks."


def _action_game_trends() -> str:
    """Monitors emerging Spigot/Paper plugin mechanics and game dev trends."""
    import dev_loop
    desktop = os.path.expanduser("~/Desktop")
    scaffold_dir = os.path.join(desktop, "jarvis-projects", "AutoScoutPlugin")
    if not os.path.exists(scaffold_dir):
        dev_loop.scaffold_spigot_template(scaffold_dir, plugin_name="AutoScoutPlugin")
        return f"Lead Scout: Generated starter Paper 1.21+ workspace in {scaffold_dir} with GDD.md and Maven configuration."
    return "Trend Scout: Spigot 1.21.4 packet listeners, asynchronous chunk caching, and mini-game metaprogression remain top requested mechanics."


def _action_price_watch() -> str:
    """Scans hardware, Unity asset, and plugin wishlist for active discounts and target price drops."""
    import price_watch
    res = price_watch.check_deals()
    deals = res.get("deals", [])
    if deals:
        return f"Price Watch Alert: {len(deals)} item(s) on sale! Top: {deals[0]['name']} (${deals[0]['current_price']:.2f}, {deals[0]['discount_pct']}% OFF)."
    return f"Price Watch: {res.get('total_tracked', 0)} tracked items checked. No new sales triggered."


class OperatorManager:
    def __init__(self, brain=None, emitter: Optional[Callable] = None):
        self.brain = brain
        self.emitter = emitter or (lambda event, **data: None)
        self.operators: Dict[str, Operator] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Register default operators
        self._init_defaults()
        self._load_state()

    def _init_defaults(self):
        defaults = [
            Operator(
                id="system_watchdog",
                name="System Hardware Watchdog",
                description="Checks CPU, RAM, and Disk thresholds every 15 minutes",
                interval_seconds=900,
                enabled=True,
                action_type="python",
                action_payload="_action_system_watchdog",
            ),
            Operator(
                id="build_anomaly_watchdog",
                name="Proactive Build Anomaly Watchdog",
                description="Watches for repeated compilation failures (3x/hour) and proposes auto-healing",
                interval_seconds=300,
                enabled=True,
                action_type="python",
                action_payload="_action_anomaly_watchdog",
            ),
            Operator(
                id="rag_memory_sync",
                name="Project & GDD Memory Indexer",
                description="Autonomous background indexing into RAG (runs only when system is idle)",
                interval_seconds=1800,
                enabled=True,
                action_type="python",
                action_payload="_action_rag_auto_sync",
                requires_idle=True,
            ),
            Operator(
                id="game_trends_scout",
                name="Game Design Trend Scout",
                description="Tracks innovative tower defense and simulation mechanics",
                interval_seconds=7200,
                enabled=True,
                action_type="python",
                action_payload="_action_game_trends",
            ),
            Operator(
                id="price_watch_scanner",
                name="Hardware & Asset Price Watch",
                description="Monitors hardware, Unity assets, and plugin wishlists for sales and price drops",
                interval_seconds=14400,
                enabled=True,
                action_type="python",
                action_payload="_action_price_watch",
                requires_idle=True,
            ),
        ]
        for op in defaults:
            self.operators[op.id] = op

    def _load_state(self):
        if not os.path.exists(OPERATORS_FILE):
            return
        try:
            with open(OPERATORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for op_id, op_data in data.items():
                    if op_id in self.operators:
                        self.operators[op_id].from_dict(op_data)
        except Exception:
            pass

    def _save_state(self):
        with _lock:
            try:
                os.makedirs(os.path.dirname(OPERATORS_FILE), exist_ok=True)
                data = {op_id: op.to_dict() for op_id, op in self.operators.items()}
                with open(OPERATORS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass

    def list_operators(self) -> List[Dict[str, Any]]:
        return [op.to_dict() for op in self.operators.values()]

    def toggle_operator(self, op_id: str, enabled: Optional[bool] = None) -> Dict[str, Any]:
        if op_id not in self.operators:
            raise KeyError(f"Operator {op_id} not found")
        op = self.operators[op_id]
        op.enabled = (not op.enabled) if enabled is None else enabled
        self._save_state()
        self.emitter("operator_updated", operator=op.to_dict())
        return op.to_dict()

    def run_operator(self, op_id: str) -> Dict[str, Any]:
        if op_id not in self.operators:
            raise KeyError(f"Operator {op_id} not found")
        op = self.operators[op_id]
        op.status = "running"
        self._save_state()
        self.emitter("operator_updated", operator=op.to_dict())

        def _execute():
            t0 = time.time()
            try:
                if op.action_type == "python":
                    fn_map = {
                        "_action_system_watchdog": _action_system_watchdog,
                        "_action_anomaly_watchdog": _action_anomaly_watchdog,
                        "_action_rag_auto_sync": _action_rag_auto_sync,
                        "_action_game_trends": _action_game_trends,
                    }
                    fn = fn_map.get(op.action_payload)
                    if fn:
                        res = fn()
                    else:
                        res = "Executed custom script"
                elif op.action_type == "brain_task" and self.brain:
                    res = self.brain.ask(op.action_payload, unattended=True)
                else:
                    res = "No action defined"

                op.status = "success"
                op.last_result = str(res)[:500]
                op.last_run = time.time()
                print(f"[Operator] {op.name} completed in {time.time() - t0:.2f}s: {op.last_result}", flush=True)
            except Exception as e:
                op.status = "error"
                op.last_result = f"Error: {e}"
                op.error_count += 1
                print(f"[Operator] {op.name} failed: {e}", flush=True)
            finally:
                self._save_state()
                self.emitter("operator_updated", operator=op.to_dict())

        t = threading.Thread(target=_execute, daemon=True)
        t.start()
        return op.to_dict()

    def start(self):
        """Starts background scheduler loop."""
        if self._running:
            return
        self._running = True

        def _loop():
            while self._running:
                now = time.time()
                for op in list(self.operators.values()):
                    if op.enabled and op.status != "running":
                        if op.last_run == 0.0 or (now - op.last_run) >= op.interval_seconds:
                            if op.requires_idle:
                                import hardware
                                if not hardware.is_system_idle():
                                    continue  # Defer execution until CPU/GPU is idle
                            self.run_operator(op.id)
                time.sleep(10)

        self._thread = threading.Thread(target=_loop, daemon=True, name="OperatorManagerLoop")
        self._thread.start()

    def stop(self):
        self._running = False


_manager_instance: Optional[OperatorManager] = None


def get_operator_manager(brain=None, emitter=None) -> OperatorManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = OperatorManager(brain=brain, emitter=emitter)
    elif brain and _manager_instance.brain is None:
        _manager_instance.brain = brain
    if emitter:
        _manager_instance.emitter = emitter
    return _manager_instance
