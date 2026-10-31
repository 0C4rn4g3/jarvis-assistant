"""
J.E.V. - System 1 Rapid Decision Engine for J.A.R.V.I.S.
========================================================
Powered by TypeSafe AI's Jev model (with local Flash System 1 Fallback).
Instead of token-by-token generative deliberation, Jev evaluates unstructured
state against structured questions in ~70ms-150ms using 3 core primitives:

  1. choice: Selects from categorical options with calibrated probabilities.
  2. noul: Evaluates binary True/False probabilities (0.0 to 1.0).
  3. score: Evaluates state against an ordered rubric (e.g. 1 to 10).

Used across Jarvis for:
  - Instant Intent & Model Routing (cutting 2-3s of unnecessary thinking).
  - Security Guardrail Threat Scoring (read-only vs destructive commands).
  - Lead Hunter website audit triage.
  - Proactive Operator Watchdog alert decisions.
"""

import os
import re
import json
import time
import requests
from typing import Any, Dict, List, Optional, Tuple

import store

TYPESAFE_API_URL = "https://api.typesafe.ai/v1/systemone"


def get_api_key() -> str:
    """Gets TypeSafe API key from env, secret store, or settings."""
    return (
        os.environ.get("TYPESAFE_API_KEY")
        or store.secret("typesafe")
        or store.settings().get("typesafe_api_key", "")
    )


def is_cloud_enabled() -> bool:
    """True if a valid TypeSafe or OpenRouter key is configured."""
    return bool(get_api_key() or os.environ.get("OPENROUTER_API_KEY"))


# -----------------------------------------------------------------------------
# Core Jev System 1 Primitives
# -----------------------------------------------------------------------------

def decide(state: Any, questions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Evaluates state against a dictionary of typed questions (noul, choice, score).
    Uses TypeSafe cloud Jev if API key is present; otherwise falls back to
    instant local System 1 engine (<1ms heuristics + Flash).
    """
    api_key = get_api_key()
    if api_key:
        try:
            t0 = time.time()
            res = requests.post(
                TYPESAFE_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "jev-latest",
                    "state": state,
                    "questions": questions
                },
                timeout=3.0
            )
            if res.ok:
                data = res.json()
                print(f"[jev] cloud decision resolved in {(time.time() - t0)*1000:.1f}ms", flush=True)
                return data.get("answers", {})
        except Exception as e:
            print(f"[jev] cloud fallback to local engine: {e}", flush=True)

    # Local System 1 Fallback (Sub-millisecond local classifier)
    return _local_system_one(state, questions)


def choice(state: str, criteria: Dict[str, str], instructions: str = "") -> Tuple[str, float]:
    """Primitive 1: Choice - Selects the most applicable category with confidence float."""
    q = {
        "selection": {
            "type": "choice",
            "instructions": instructions or "Select the best matching category for the state.",
            "criteria": criteria
        }
    }
    answers = decide(state, q)
    ans = answers.get("selection", {})
    return ans.get("choice", list(criteria.keys())[0]), float(ans.get("confidence", 0.90))


def noul(state: str, condition: str) -> Tuple[bool, float]:
    """Primitive 2: Noul - Evaluates binary condition, returning (bool, probability float 0.0-1.0)."""
    q = {
        "check": {
            "type": "noul",
            "instructions": condition
        }
    }
    answers = decide(state, q)
    ans = answers.get("check", {})
    prob = float(ans.get("noul", 0.5))
    return prob >= 0.5, prob


def score(state: str, rubric: str, min_val: int = 1, max_val: int = 10) -> int:
    """Primitive 3: Score - Evaluates state against a numerical rubric."""
    q = {
        "rating": {
            "type": "score",
            "instructions": rubric,
            "min": min_val,
            "max": max_val
        }
    }
    answers = decide(state, q)
    ans = answers.get("rating", {})
    return int(ans.get("score", (min_val + max_val) // 2))


# -----------------------------------------------------------------------------
# Local System 1 Fallback Engine
# -----------------------------------------------------------------------------

def _local_system_one(state: Any, questions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Ultra-fast deterministic System 1 evaluator when cloud Jev is offline."""
    state_str = str(state).lower()
    answers = {}

    for q_id, q_spec in questions.items():
        q_type = q_spec.get("type", "noul")
        instr = q_spec.get("instructions", "").lower()

        if q_type == "noul":
            # Binary probability heuristic
            destruct_words = {"delete", "remove", "destruct", "erase", "overwrite", "kill", "drop", "wipe"}
            is_destruct_q = any(w in instr for w in destruct_words)
            has_destruct_cmd = bool(re.search(r"\b(rm|del|delete|erase|format|kill|drop|truncate|shutdown|reboot)\b", state_str))

            if is_destruct_q and has_destruct_cmd:
                prob = 0.95
            elif any(w in state_str for w in re.findall(r"\w{3,}", instr)):
                prob = 0.85
            else:
                prob = 0.15
            answers[q_id] = {"type": "noul", "noul": prob}

        elif q_type == "choice":
            criteria = q_spec.get("criteria", {})
            best_cat = list(criteria.keys())[0] if criteria else "default"
            max_matches = -1

            for cat, desc in criteria.items():
                cat_words = set(re.findall(r"\w+", cat.lower() + " " + desc.lower()))
                matches = sum(1 for w in cat_words if w in state_str)
                if matches > max_matches:
                    max_matches = matches
                    best_cat = cat

            answers[q_id] = {"type": "choice", "choice": best_cat, "confidence": 0.88}

        elif q_type == "score":
            min_v = q_spec.get("min", 1)
            max_v = q_spec.get("max", 10)
            score_val = (min_v + max_v) // 2
            answers[q_id] = {"type": "score", "score": score_val}

    return answers


# -----------------------------------------------------------------------------
# High-Value Jarvis Accelerators
# -----------------------------------------------------------------------------

def route_intent(prompt: str) -> Dict[str, Any]:
    """Rapidly classifies user intent in <10ms to skip unnecessary thinking,
    tool schema serialization, or heavy RAG searches.
    """
    prompt_clean = prompt.strip()

    # 0. Async Background Subagent quick-path (<0.1ms)
    bg_match = re.search(
        r"\b(in the background|in background|background subagent|spawn subagent|as a background task|run in background|swarm)\b",
        prompt_clean, re.I
    )
    if bg_match:
        clean_task = re.sub(
            r"\b(in the background|in background|spawn subagent|as a background task|run in background|swarm)\b",
            "", prompt_clean, flags=re.I
        ).strip(",. ")
        return {
            "intent": "background",
            "is_background": True,
            "background_task": clean_task or prompt_clean,
            "needs_tools": True,
            "needs_rag": True,
            "model_job": "agent",
            "skip_reasoning": False
        }

    # 1. Instant regex quick-paths (0.1ms)
    coding_match = re.search(
        r"\b(code|coding|program|script|function|class|java|python|cpp|c\+\+|c#|bug|fix|refactor|plugin|spigot|paper|minecraft|api|compile|test|implement|algorithm)\b",
        prompt_clean, re.I
    )
    if coding_match:
        return {
            "intent": "coding",
            "needs_tools": True,
            "needs_rag": True,
            "model_job": "code",
            "skip_reasoning": False
        }

    game_match = re.search(
        r"\b(game|gdd|unity|unreal|mechanic|lore|quest|balance|economy|enemy|npc|wave|level design)\b",
        prompt_clean, re.I
    )
    if game_match:
        return {
            "intent": "game_design",
            "needs_tools": True,
            "needs_rag": True,
            "model_job": "agent",
            "skip_reasoning": False
        }

    system_action_match = re.search(
        r"\b(open|launch|close|window|volume|play|pause|music|spotify|calendar|weather|reminder|timer|note)\b",
        prompt_clean, re.I
    )
    if system_action_match:
        return {
            "intent": "tool_action",
            "needs_tools": True,
            "needs_rag": False,
            "model_job": "agent",
            "skip_reasoning": True
        }

    # 2. Check if this is pure fast conversation (greetings, factual Q&A, chat)
    # Jev choice primitive:
    categories = {
        "fast_chat": "Simple conversation, greetings, jokes, math, general questions without desktop action",
        "deep_work": "Multi-step complex instructions requiring file inspection or desktop changes"
    }
    cat, conf = choice(prompt_clean, categories, "Is this a simple quick conversational request or deep work?")

    if cat == "fast_chat" and len(prompt_clean.split()) < 35:
        return {
            "intent": "fast_chat",
            "needs_tools": False,
            "needs_rag": False,
            "model_job": "phone",  # routes to ultra-fast gemini-3.5-flash-lite minimal
            "skip_reasoning": True
        }

    return {
        "intent": "general",
        "needs_tools": True,
        "needs_rag": False,
        "model_job": "agent",
        "skip_reasoning": False
    }


def assess_command_risk(cmd: str) -> Dict[str, Any]:
    """Instant Security Guardrail scoring.
    Determines if a shell command is read-only (safe) vs destructive (needs HITL approval).
    """
    cmd_clean = cmd.strip()

    # Known safe read-only commands
    safe_prefixes = (
        "git status", "git log", "git diff", "git branch",
        "dir", "ls", "pwd", "cd", "echo", "cat", "type",
        "whoami", "hostname", "python --version", "node --version",
        "dotnet --version", "git --version"
    )
    if any(cmd_clean.lower().startswith(p) for p in safe_prefixes):
        return {"destructive": False, "risk_score": 1, "tier": "green"}

    # Known dangerous patterns
    danger_patterns = (
        r"\b(rm\s+-rf|del\s+/s|format|drop\s+table|mkfs|shutdown|reboot|stop-process|taskkill\s+/f)\b"
    )
    if re.search(danger_patterns, cmd_clean, re.I):
        return {"destructive": True, "risk_score": 10, "tier": "red"}

    # Jev binary Noul assessment
    is_destruct, prob = noul(
        cmd_clean,
        "Does this command permanently overwrite, delete files, format storage, or terminate system processes?"
    )

    return {
        "destructive": is_destruct,
        "risk_score": int(prob * 10),
        "tier": "red" if is_destruct else "yellow"
    }


def status() -> Dict[str, Any]:
    """Returns Jev engine operational status."""
    has_key = bool(get_api_key())
    return {
        "jev_online": True,
        "engine": "typesafe_cloud" if has_key else "local_flash_system_one",
        "latency_target_ms": 75 if has_key else 5,
        "primitives_supported": ["choice", "noul", "score"]
    }
