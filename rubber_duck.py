"""Rubber-Duck Mode for Jarvis.
Voice-first design & pairing sessions where Jarvis asks Socratic questions about GDD or code,
identifying blind spots and automatically logging resolved conclusions into RAG knowledge.
"""
import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import store
import system

SESSION_FILE = os.path.join(store.DATA, "rubber_duck_session.json")

_active_session: Dict[str, Any] = {
    "active": False,
    "topic": "",
    "focus": "code",  # "code", "gdd", "architecture"
    "project_id": "",
    "step": 0,
    "turns": [],
    "conclusions": [],
    "started_at": 0.0
}


def _save_session(sess: Dict[str, Any]):
    global _active_session
    _active_session = sess
    try:
        os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(sess, f, indent=2)
    except Exception:
        pass


def _load_session() -> Dict[str, Any]:
    global _active_session
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                _active_session = json.load(f)
        except Exception:
            pass
    return _active_session


def start_session(topic: str, focus: str = "code", project_id: str = "") -> Dict[str, Any]:
    """Starts a voice-first Socratic pairing/design session on a code module, GDD topic, or architecture dilemma."""
    try:
        import game_design
        pid = project_id or game_design.get_active_project_id()
        proj = game_design.get_active_project() or {}
        gdd = game_design.get_gdd(pid) or ""
    except Exception:
        pid = project_id or "legally-blind-driver"
        proj = {"name": "Legally Blind Driver"}
        gdd = ""

    focus_type = focus.lower() if focus in ("code", "gdd", "architecture") else "code"
    topic_clean = topic.strip() or "Core Game Loop"

    # Formulate first Socratic probe based on focus
    if focus_type == "gdd":
        probe = (
            f"Alright, let's stress-test the design of '{topic_clean}' in {proj.get('name', 'your game')}. "
            f"What is the single biggest point of friction for the player here: is it cognitive overload, "
            f"or is the mechanical reward loop failing to incentivize the right behavior?"
        )
    elif focus_type == "architecture":
        probe = (
            f"Examining the architecture of '{topic_clean}'. "
            f"Where does state ownership live, and if two systems write to it simultaneously during a frame, "
            f"which one guarantees deterministic authority?"
        )
    else:  # code
        probe = (
            f"Rubber-duck session initiated on '{topic_clean}'. "
            f"Walk me through the happy path first: what is the input, what transformation happens, "
            f"and what is the exact failure case if that input is null or delayed by one frame?"
        )

    sess = {
        "active": True,
        "topic": topic_clean,
        "focus": focus_type,
        "project_id": pid,
        "project_name": proj.get("name", pid),
        "step": 1,
        "turns": [{"role": "jarvis", "text": probe, "time": time.time()}],
        "conclusions": [],
        "started_at": time.time()
    }
    _save_session(sess)

    try:
        import jarvis
        jarvis.notch_line[:] = [f"🦆 Rubber Duck: {topic_clean[:22]}", time.time()]
    except Exception:
        pass

    return {
        "ok": True,
        "session_active": True,
        "topic": topic_clean,
        "focus": focus_type,
        "socratic_question": probe,
        "instruction": "Answer the question out loud or by typing; Jarvis will probe edge cases and commit decisions to RAG."
    }


def advance_session(user_statement: str) -> Dict[str, Any]:
    """Processes user voice response, identifies design decisions, and asks the next Socratic follow-up."""
    sess = _load_session()
    if not sess.get("active"):
        return start_session(user_statement, focus="code")

    sess["turns"].append({"role": "user", "text": user_statement, "time": time.time()})
    step = sess.get("step", 1) + 1
    sess["step"] = step

    topic = sess.get("topic", "System")
    p_name = sess.get("project_name", "Game")
    focus = sess.get("focus", "code")

    # Detect if user formulated a concrete conclusion or decision
    lower = user_statement.lower()
    decision_triggers = ["decided to", "we should", "will use", "the fix is", "solution is", "instead of", "because", "agreed"]
    auto_conclusion = None
    if any(t in lower for t in decision_triggers) or len(user_statement.split()) > 15:
        auto_conclusion = f"[{topic}] {user_statement.strip()}"
        sess["conclusions"].append(auto_conclusion)
        log_conclusion_to_rag(auto_conclusion, topic=topic, project_id=sess.get("project_id", ""))

    # Formulate next Socratic question
    if step == 2:
        next_question = (
            f"Understood. Now what about edge cases: what happens under extreme stress or network lag? "
            f"Could this cause an unintended cascading failure in related systems?"
        )
    elif step == 3:
        next_question = (
            f"Good. What is the performance or complexity cost of this approach? "
            f"Are we introducing premature optimization, or is there a simpler 10-line alternative?"
        )
    elif step >= 4:
        concl_summary = f" We've logged {len(sess['conclusions'])} design conclusions to RAG." if sess['conclusions'] else ""
        next_question = (
            f"We've covered the core logic, failure modes, and trade-offs for '{topic}'.{concl_summary} "
            f"Ready to wrap up and commit this architecture decision, or is there another facet to grill?"
        )

    sess["turns"].append({"role": "jarvis", "text": next_question, "time": time.time()})
    _save_session(sess)

    return {
        "ok": True,
        "step": step,
        "topic": topic,
        "conclusions_logged": len(sess["conclusions"]),
        "latest_conclusion": auto_conclusion,
        "next_question": next_question
    }


def log_conclusion_to_rag(conclusion: str, topic: str = "", project_id: str = "") -> Dict[str, Any]:
    """Logs an established architecture or design conclusion directly into RAG with metadata tagging."""
    pid = project_id or _load_session().get("project_id", "active_project")
    top = topic or _load_session().get("topic", "Architecture")

    content = (
        f"# Design Decision: {top} ({pid})\n"
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"**Context:** Rubber-Duck Socratic Pairing Session\n\n"
        f"### Conclusion & Rationale:\n"
        f"{conclusion}\n\n"
        f"Tagged: #rubber-duck-decision #{pid} #{top.replace(' ', '-').lower()}"
    )

    indexed = False
    try:
        import rag
        res = rag.index_document(f"rubber_duck_{pid}_{int(time.time())}.md", content=content, category="project")
        indexed = bool(res)
    except Exception:
        pass

    try:
        import graph_rag
        graph_rag.add_relationship(pid, "implemented_design_decision", top, source_type="Project", target_type="Decision")
    except Exception:
        pass

    return {
        "ok": True,
        "indexed_to_rag": indexed,
        "topic": top,
        "conclusion": conclusion
    }


def get_active_session() -> Dict[str, Any]:
    return _load_session()


def end_session() -> Dict[str, Any]:
    """Ends current rubber-duck session and outputs final decision summary."""
    sess = _load_session()
    if not sess.get("active"):
        return {"ok": True, "message": "No active rubber-duck session."}

    topic = sess.get("topic", "")
    conclusions = sess.get("conclusions", [])

    sess["active"] = False
    sess["ended_at"] = time.time()
    _save_session(sess)

    try:
        import jarvis
        jarvis.notch_line[:] = ["Ready", time.time()]
    except Exception:
        pass

    report = [
        f"🦆 **Rubber-Duck Session Summary: {topic}**",
        f"- **Turns**: {len(sess.get('turns', []))}",
        f"- **Conclusions Logged to RAG**: {len(conclusions)}\n",
        "### Key Decisions Committed:"
    ]
    for i, c in enumerate(conclusions, 1):
        report.append(f"{i}. {c}")
    if not conclusions:
        report.append("- Explored design space; no hard commitments logged.")

    return {
        "ok": True,
        "topic": topic,
        "conclusions": conclusions,
        "report": "\n".join(report)
    }
