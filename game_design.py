"""Game Designer Mode for Jarvis.
Manages game development projects, GDD documents, HUD/UI reviews, and game design reasoning."""
import json, os, re, time, zipfile
import xml.etree.ElementTree as ET

import store
import system

GAMES_DIR = os.path.join(system.CONFIG, "games")
LEGALLY_BLIND_DOCX = r"C:\Users\User\Downloads\Legally Blind Driver — Game Design Document.docx"


def _slugify(text):
    s = re.sub(r"[^\w\s-]", "", text.strip().lower())
    return re.sub(r"[-\s]+", "-", s) or "untitled-game"


def _parse_docx_to_markdown(path):
    if not os.path.exists(path):
        return ""
    try:
        with zipfile.ZipFile(path) as z:
            tree = ET.fromstring(z.read("word/document.xml"))
            namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            lines = []
            for p in tree.iterfind(".//w:p", namespaces):
                text = "".join(t.text for t in p.iterfind(".//w:t", namespaces) if t.text).strip()
                if not text:
                    continue
                style = p.find(".//w:pStyle", namespaces)
                s_val = style.attrib.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val", "") if style is not None else ""
                if "Heading1" in s_val or "Title" in s_val:
                    lines.append(f"# {text}")
                elif "Heading2" in s_val:
                    lines.append(f"## {text}")
                elif "Heading3" in s_val:
                    lines.append(f"### {text}")
                else:
                    lines.append(text)
            return "\n\n".join(lines)
    except Exception as e:
        return f"# Error reading docx\n{e}"


def _default_ue5_gdd():
    return """# Base Defense MMO — Game Design Document

## 1. High Concept & Genre
- **High Concept**: A 3rd-person open-world multiplayer survival game where players gather resources, craft fortresses, and research tech during daylight, then band together to repel massive procedural creature hordes at night.
- **Engine**: Unreal Engine 5.8 (Gameplay Ability System, Nanite, Lumen, Server Replication).
- **Genre**: 3rd-Person Survival Crafting & Base Defense MMO.
- **Tone**: Gritty survival meets adrenaline-fueled cooperative stronghold defense.

## 2. Core Gameplay Loop
1. **Dawn / Day Phase (18 Minutes)**:
   - Exploration, resource gathering (wood, stone, metal alloys, energy cores).
   - Base expansion: building modular walls, turrets, traps, power grids, crafting benches.
   - Crafting ammo, barricades, weapon upgrades, and defensive emplacements.
2. **Dusk Warning (2 Minutes)**:
   - Sky turns blood red, sirens sound, players return to base, load turret ammo, test power generators.
3. **Night Phase (10 Minutes)**:
   - Horde assault: Creatures pathfind toward base structural weak points (doors, generators).
   - Combat: 3rd-person gunplay and melee abilities, repairing damaged walls mid-fight, activating electric/flame traps.
   - Survival reward: Elite creature loot drops, rare salvage, tech tokens.
4. **Daybreak (Cycle Reset)**:
   - Clear debris, assess damage, harvest night creature corpses, prep for next wave (which scales higher).

## 3. Systems & Mechanics
- **Base Building**: Modular grid with stability physics (structural integrity calculations).
- **Power & Traps**: Wired generators, batteries, tripwire explosives, automated searchlights and sentries.
- **Player Roles / Specializations**:
  - *Combat Engineer*: Fast structure repairs, turret buffs, trap placement efficiency.
  - *Scout / Harvester*: Fast sprint, resource yield bonus, early detection of night horde spawn directions.
  - *Heavy Gunner*: High-caliber weaponry, suppression fire, armor durability.
- **AI & Horde Pathfinding**:
  - Flowfield navigation on dynamic UE5 NavMesh.
  - Breachers (explode against walls), Swarmers (scale obstacles), Behemoths (smash structural supports).

## 4. UI / HUD Design Rules
- Minimal screen clutter during day (compass, quick inventory bar, stamina/vitals meter).
- Combat HUD at night: Base integrity health bar, horde progress meter, ammo counter, active trap status overlay.
"""


def init_projects():
    """Ensure games folder exists and default projects are initialized."""
    os.makedirs(GAMES_DIR, exist_ok=True)

    # 1. Legally Blind Driver
    lbd_dir = os.path.join(GAMES_DIR, "legally-blind-driver")
    if not os.path.exists(lbd_dir):
        os.makedirs(lbd_dir, exist_ok=True)
        gdd = _parse_docx_to_markdown(LEGALLY_BLIND_DOCX)
        if not gdd or len(gdd) < 100:
            gdd = "# Legally Blind Driver\n\nCooperative asymmetric party game for Unity."
        with open(os.path.join(lbd_dir, "gdd.md"), "w", encoding="utf-8") as f:
            f.write(gdd)
        meta = {
            "id": "legally-blind-driver",
            "name": "Legally Blind Driver",
            "engine": "Unity 6 (URP)",
            "genre": "Co-op Asymmetric Party Driving",
            "summary": "Three players in one beat-up moving van: Driver steers blind, Navigator reads map, Mechanic manages pedals & engine.",
            "roles": ["Driver (Blind)", "Navigator (Map)", "Mechanic (Speed & Engine)"],
            "docx_path": LEGALLY_BLIND_DOCX if os.path.exists(LEGALLY_BLIND_DOCX) else ""
        }
        with open(os.path.join(lbd_dir, "project.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    # 2. UE5 Base Defense MMO
    ue5_dir = os.path.join(GAMES_DIR, "ue5-base-defense")
    if not os.path.exists(ue5_dir):
        os.makedirs(ue5_dir, exist_ok=True)
        with open(os.path.join(ue5_dir, "gdd.md"), "w", encoding="utf-8") as f:
            f.write(_default_ue5_gdd())
        meta = {
            "id": "ue5-base-defense",
            "name": "Base Defense MMO",
            "engine": "Unreal Engine 5.8",
            "genre": "3rd-Person Survival Craft & Base Defense MMO",
            "summary": "3rd person open world base defense MMO. Day: gather resources, upgrades, repairs. Night: defend base from escalating creature hordes.",
            "roles": ["Combat Engineer", "Scout Harvester", "Heavy Gunner"]
        }
        with open(os.path.join(ue5_dir, "project.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)


def list_projects():
    """List all game projects in games directory."""
    init_projects()
    projects = []
    active_id = get_active_project_id()
    for entry in os.listdir(GAMES_DIR):
        p_dir = os.path.join(GAMES_DIR, entry)
        if not os.path.isdir(p_dir):
            continue
        meta_file = os.path.join(p_dir, "project.json")
        gdd_file = os.path.join(p_dir, "gdd.md")
        if os.path.exists(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {"id": entry, "name": entry.replace("-", " ").title()}
        else:
            meta = {
                "id": entry,
                "name": entry.replace("-", " ").title(),
                "engine": "Unknown",
                "genre": "Game",
                "summary": "Game project"
            }
        meta["id"] = meta.get("id") or entry
        meta["has_gdd"] = os.path.exists(gdd_file)
        meta["active"] = (meta["id"] == active_id)
        projects.append(meta)
    return projects


def get_active_project_id():
    """Current active project ID from store settings."""
    cfg = store.settings()
    act = cfg.get("active_game_project")
    if not act:
        act = "legally-blind-driver"
        store.update_settings({"active_game_project": act})
    return act


def set_active_project_id(project_id):
    """Switch active game project."""
    init_projects()
    projects = [p["id"] for p in list_projects()]
    if project_id not in projects:
        # Match case-insensitive
        match = next((p for p in projects if p.lower() == project_id.lower()), None)
        if not match:
            return {"error": f"Project '{project_id}' not found. Available: {projects}"}
        project_id = match
    store.update_settings({"active_game_project": project_id})
    return {"ok": True, "active": project_id}


def get_active_project():
    """Get active project data and GDD preview."""
    init_projects()
    act_id = get_active_project_id()
    p_dir = os.path.join(GAMES_DIR, act_id)
    if not os.path.exists(p_dir):
        act_id = "legally-blind-driver"
        p_dir = os.path.join(GAMES_DIR, act_id)
    meta_file = os.path.join(p_dir, "project.json")
    gdd_file = os.path.join(p_dir, "gdd.md")
    meta = {}
    if os.path.exists(meta_file):
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
    gdd = ""
    if os.path.exists(gdd_file):
        with open(gdd_file, "r", encoding="utf-8") as f:
            gdd = f.read()
    return {
        "id": act_id,
        "name": meta.get("name", act_id),
        "engine": meta.get("engine", "Unity"),
        "genre": meta.get("genre", ""),
        "summary": meta.get("summary", ""),
        "roles": meta.get("roles", []),
        "gdd": gdd
    }


def get_gdd(project_id=None):
    """Return full GDD content for project."""
    init_projects()
    pid = project_id or get_active_project_id()
    gdd_file = os.path.join(GAMES_DIR, pid, "gdd.md")
    if os.path.exists(gdd_file):
        with open(gdd_file, "r", encoding="utf-8") as f:
            return f.read()
    return ""



def create_project(name, engine="Unity", genre="", summary="", gdd_content=""):
    """Create a new game project and auto-select it."""
    init_projects()
    slug = _slugify(name)
    p_dir = os.path.join(GAMES_DIR, slug)
    os.makedirs(p_dir, exist_ok=True)
    if not gdd_content:
        gdd_content = f"""# {name} — Game Design Document

## 1. High Concept & Overview
- **Name**: {name}
- **Engine**: {engine}
- **Genre**: {genre or 'Video Game'}
- **Summary**: {summary or 'Initial game design document.'}

## 2. Core Gameplay Loop
- Primary loop: ...
- Pacing & session length: ...

## 3. Mechanics & Rules
- Player inputs & controls: ...
- Win / failure states: ...

## 4. UI / HUD Wireframe & Aesthetics
- Essential HUD elements: ...
- Art direction & color palette: ...
"""
    with open(os.path.join(p_dir, "gdd.md"), "w", encoding="utf-8") as f:
        f.write(gdd_content)
    meta = {
        "id": slug,
        "name": name.strip(),
        "engine": engine.strip(),
        "genre": genre.strip(),
        "summary": summary.strip(),
        "created_at": time.strftime("%Y-%m-%d")
    }
    with open(os.path.join(p_dir, "project.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    set_active_project_id(slug)
    return meta


def update_gdd_section(section, content, project_id=None):
    """Update or append a section to the GDD."""
    init_projects()
    pid = project_id or get_active_project_id()
    gdd_path = os.path.join(GAMES_DIR, pid, "gdd.md")
    existing = ""
    if os.path.exists(gdd_path):
        with open(gdd_path, "r", encoding="utf-8") as f:
            existing = f.read()
    # Check if section heading exists
    pattern = rf"(##\s+{re.escape(section)}[\s\S]*?)(?=\n##\s+|\Z)"
    new_entry = f"## {section}\n\n{content}\n"
    if re.search(pattern, existing, re.IGNORECASE):
        updated = re.sub(pattern, new_entry, existing, count=1, flags=re.IGNORECASE)
    else:
        updated = existing.rstrip() + f"\n\n{new_entry}"
    with open(gdd_path, "w", encoding="utf-8") as f:
        f.write(updated)
    return {"ok": True, "section": section, "project": pid}


def get_game_designer_prompt():
    """Generates the injected game designer system prompt."""
    act = get_active_project()
    gdd_excerpt = act["gdd"][:3500] if act.get("gdd") else "None provided yet."
    return f"""# ACTIVE MODE: VIDEOGAME DESIGNER MODE
You are acting as an elite Game Designer, Creative Director, and Systems Architect.
Your developer is a 3rd-year video game engineering student in Bucharest.

## CURRENT ACTIVE PROJECT
- **Project Name**: {act['name']}
- **Engine**: {act['engine']}
- **Genre**: {act['genre']}
- **Core Summary**: {act['summary']}
- **Key Roles / Archetypes**: {', '.join(act.get('roles', [])) or 'Standard'}

## ACTIVE GDD CONTEXT
{gdd_excerpt}

## YOUR DESIGN PRINCIPLES
1. **Rational Game Design & MDA Framework**:
   - Always trace mechanics -> dynamic player behavior -> emotional aesthetic response.
   - For *Legally Blind Driver*: prioritize hilarious asymmetric communication breakdown, high tension, slapstick failure states, clear audio cues.
   - For *Base Defense MMO*: prioritize tight day/night pacing curves, fortress structural integrity, satisfying resource economy, and horde AI threat escalation.
2. **UI & HUD Ergonomics**:
   - Diegetic UI first (gauges on dashboard, cracked dials, radio frequency dials, environmental meters).
   - Low visual clutter: player eyes must focus on the game world, not floating numbers.
   - Contrast & accessibility: clear fonts, distinct color coding for alerts vs normal states.
3. **Actionable Technical Advice**:
   - For Unity: recommend appropriate components (WheelColliders, Rigidbody physics tuning, Netcode for GameObjects/Relay, ScriptableObjects for tuning).
   - For Unreal Engine 5.8: recommend GAS (Gameplay Ability System), Nanite foliage/mesh handling, Lumen performance tuning, NavMesh dynamic generation, C++ vs Blueprint boundary.
4. **Visual Redesigns**:
   - When asked to critique or redesign HUD/UI, use `tool_critique_hud` or examine screen with `tool_look` and propose specific visual mockups via `tool_make_image`.
5. **Creative Game Ideation & The Inversion Principle**:
   - When asked to brainstorm ideas or "make a game fun", NEVER give generic textbook tropes (e.g. "add fire and ice towers, upgrade paths, wave counters").
   - Propose **Genre Inversions & High-Agency Mechanical Twists**:
     * Invert a core genre constraint (e.g. physical logistics/ammo supply lines, destructible terrain/maze routing, tower synergies/mutations, friendly-fire physics).
     * Introduce **Tension & High-Risk Agency** during active waves (overclocking mechanics with blowout risks, manual hazard triggers, active player abilities).
     * Provide 3 distinct, high-concept mechanical pillars with concrete gameplay examples (player input -> dynamic reaction -> why it feels satisfying).
6. **Collaborative "Yes, and..." Design Philosophy**:
   - The user is the Creative Director: always build ON TOP of their ideas instead of discarding or overwriting their vision.
   - When the user shares a mechanic or idea:
     1. Adopt the core vision immediately.
     2. Flesh out the mechanical mechanics (inputs, constraints, visual/audio feedback).
     3. Add risk/reward trade-offs and emergent synergies with other systems.
     4. Identify edge cases and failure states.
     5. If an idea has an exploit or balance flaw, point it out constructively and propose 2 seamless fixes that keep the original fun intact.
"""
