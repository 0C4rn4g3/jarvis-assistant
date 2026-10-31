"""Jarvis Skills & Claude Plugin Bridge.
Loads skills and plugin rules from ~/.agents/skills, ~/.claude/skills, and ~/.claude/plugins
and seamlessly injects them into LLM system prompts (Gemini Argon, Claude, Ollama).
"""
import glob
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

import system

ACTIVE_SKILLS_FILE = os.path.join(system.DATA, "active_skills.json")
_lock = threading.Lock()

SKILL_DIRS = [
    os.path.expanduser("~/.agents/skills"),
    os.path.expanduser("~/.claude/skills"),
    os.path.expanduser("~/.claude/plugins/cache"),
]


def _read_active_skills() -> List[str]:
    if not os.path.exists(ACTIVE_SKILLS_FILE):
        return []
    try:
        with open(ACTIVE_SKILLS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_active_skills(skills: List[str]):
    with _lock:
        try:
            os.makedirs(os.path.dirname(ACTIVE_SKILLS_FILE), exist_ok=True)
            with open(ACTIVE_SKILLS_FILE, "w", encoding="utf-8") as f:
                json.dump(list(dict.fromkeys(skills)), f, indent=2)
        except Exception:
            pass


def discover_skills() -> Dict[str, Dict[str, Any]]:
    """Discovers all skills and Claude plugins on the local system."""
    found = {}

    # 1. Standard SKILL.md directories
    for base in [os.path.expanduser("~/.agents/skills"), os.path.expanduser("~/.claude/skills")]:
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            skill_md = os.path.join(base, name, "SKILL.md")
            if os.path.isfile(skill_md):
                info = _parse_skill(skill_md, name)
                found[info["name"]] = info

    # 2. Claude plugin cache
    cache_base = os.path.expanduser("~/.claude/plugins/cache")
    if os.path.isdir(cache_base):
        for root, dirs, files in os.walk(cache_base):
            if "SKILL.md" in files:
                skill_path = os.path.join(root, "SKILL.md")
                name = os.path.basename(os.path.dirname(skill_path))
                if name not in found:
                    found[name] = _parse_skill(skill_path, name)

    return found


def _parse_skill(path: str, fallback_name: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        content = ""

    desc = ""
    name = fallback_name
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            body = parts[2].strip()
            for line in frontmatter.splitlines():
                if line.startswith("name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()

    return {
        "name": name,
        "description": desc or f"Claude skill {name}",
        "path": path,
        "body": body,
    }


def list_skills() -> List[Dict[str, Any]]:
    active = set(_read_active_skills())
    skills = discover_skills()
    out = []
    for name, s in skills.items():
        out.append({
            "name": name,
            "description": s["description"],
            "path": s["path"],
            "active": name in active,
        })
    return sorted(out, key=lambda x: x["name"])


def set_skill_active(name: str, active: bool = True) -> bool:
    current = set(_read_active_skills())
    if active:
        current.add(name)
    else:
        current.discard(name)
    _save_active_skills(list(current))
    return active


def check_prompt_triggers(prompt: str) -> None:
    """Checks user prompt for skill activation keywords (e.g. 'caveman mode', 'stop caveman')."""
    lower = prompt.lower()
    
    # Caveman trigger
    if any(k in lower for k in ["caveman mode", "talk like caveman", "use caveman", "/caveman", "less tokens"]):
        set_skill_active("caveman", True)
        print("[skills] Caveman mode activated", flush=True)
    elif any(k in lower for k in ["stop caveman", "normal mode", "disable caveman", "exit caveman"]):
        set_skill_active("caveman", False)
        print("[skills] Caveman mode deactivated", flush=True)


def get_skills_system_prompt() -> str:
    """Returns combined prompt rules of all currently active skills (e.g. Caveman)."""
    active = set(_read_active_skills())
    if not active:
        return ""

    skills = discover_skills()
    sections = []

    for name in active:
        if name in skills:
            s = skills[name]
            sections.append(f"## ACTIVE SKILL: {s['name']}\n{s['body']}")

    if not sections:
        return ""

    return "\n\n# Active Custom Skills & Guidelines\n" + "\n\n".join(sections)


def audit_skill_hygiene(action: str = "audit", skill_name: str = "") -> Dict[str, Any]:
    """Audits local skills for unused, outdated, or conflicting extensions, proposing removals."""
    all_skills = discover_skills()
    active = set(_read_active_skills())

    conflicts = []
    unused = []
    broken = []
    healthy = []

    # Cluster skills to find overlap/redundancy
    clusters = {
        "grill": ["grill-me", "grill-with-docs", "interview-me"],
        "caveman_redundant": ["caveman-discover", "caveman-explore", "caveman-learn", "caveman-manage", "caveman-review", "caveman-setup", "caveman-stats"],
        "ponytail_redundant": ["ponytail-audit", "ponytail-debt", "ponytail-gain", "ponytail-help", "ponytail-review"],
    }

    found_conflict_skills = set()
    for grp, members in clusters.items():
        present = [m for m in members if m in all_skills]
        if len(present) > 1:
            conflicts.append({
                "group": grp,
                "skills": present,
                "reason": f"High semantic overlap across {len(present)} skills. Keep primary ({present[0]}), consolidate others."
            })
            for m in present[1:]:
                found_conflict_skills.add(m)

    for name, s in all_skills.items():
        if not s.get("body") or len(s.get("body", "").strip()) < 40:
            broken.append({"name": name, "path": s["path"], "reason": "Missing or truncated SKILL.md body"})
        elif name in found_conflict_skills:
            pass
        elif name not in active:
            unused.append({"name": name, "path": s["path"]})
        else:
            healthy.append(name)

    proposed_removals = []
    for c in conflicts:
        proposed_removals.extend(c["skills"][1:])
    for b in broken:
        proposed_removals.append(b["name"])

    removed = None
    if action == "cleanup" and skill_name:
        target = skill_name.strip()
        if target in all_skills:
            s_path = all_skills[target]["path"]
            s_dir = os.path.dirname(s_path)
            try:
                import shutil
                archive_dir = os.path.join(system.DATA, "archived_skills")
                os.makedirs(archive_dir, exist_ok=True)
                shutil.move(s_dir, os.path.join(archive_dir, target))
                set_skill_active(target, False)
                removed = target
            except Exception as e:
                return {"ok": False, "error": f"Failed to archive skill '{target}': {e}"}

    report_lines = [
        "🧹 **Skill Marketplace Hygiene Audit**",
        f"- **Total Installed Skills**: {len(all_skills)}",
        f"- **Active**: {len(active)} | **Healthy**: {len(healthy)}",
        f"- **Conflicting / Redundant**: {len(found_conflict_skills)}",
        f"- **Broken / Truncated**: {len(broken)}",
        f"- **Unused / Inactive**: {len(unused)}\n",
        "### ⚠️ Conflicting / Redundant Clusters:"
    ]
    for c in conflicts:
        report_lines.append(f"- **{c['group']}**: `{', '.join(c['skills'])}` — *{c['reason']}*")

    if broken:
        report_lines.append("\n### ❌ Broken Skills:")
        for b in broken:
            report_lines.append(f"- `{b['name']}`: {b['reason']}")

    report_lines.append("\n### 🗑️ Proposed Removals:")
    for p in proposed_removals[:8]:
        report_lines.append(f"- Propose removal: `{p}`")

    return {
        "ok": True,
        "total_skills": len(all_skills),
        "conflicts": conflicts,
        "broken": broken,
        "unused_count": len(unused),
        "proposed_removals": proposed_removals,
        "removed": removed,
        "report": "\n".join(report_lines)
    }
