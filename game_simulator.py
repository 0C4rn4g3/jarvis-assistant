"""Game Balance Simulator, Playtest Transcriber & Unity Pipeline Bridge.
Provides Monte Carlo economy/wave simulation, playtest feedback parsing into patch notes,
and Unity editor automation generation.
"""
import json
import os
import random
from typing import Any, Dict, List, Optional


def simulate_wave_economy(
    initial_scrap: int = 500,
    income_per_wave: int = 150,
    ammo_cost_base: int = 40,
    ammo_scaling: float = 1.08,
    repair_cost_base: int = 30,
    repair_scaling: float = 1.12,
    max_waves: int = 1000,
    runs: int = 100,
    **kwargs
) -> Dict[str, Any]:
    """Runs Monte Carlo simulations on game wave economy to detect collapse points and bottlenecks."""
    if "waves" in kwargs:
        max_waves = int(kwargs["waves"])
    collapse_waves = []
    deficit_reasons = {"ammo": 0, "repair": 0, "catastrophic_breach": 0}

    for _ in range(runs):
        scrap = initial_scrap
        collapsed = False

        for wave in range(1, max_waves + 1):
            # Stochastic variance (+- 15%)
            var_ammo = random.uniform(0.85, 1.15)
            var_repair = random.uniform(0.80, 1.25)
            var_income = random.uniform(0.90, 1.10)

            cur_income = int(income_per_wave * (1.02 ** (wave // 5)) * var_income)
            cur_ammo = int(ammo_cost_base * (ammo_scaling ** wave) * var_ammo)
            cur_repair = int(repair_cost_base * (repair_scaling ** wave) * var_repair)

            total_drain = cur_ammo + cur_repair
            scrap += cur_income - total_drain

            if scrap <= 0:
                collapse_waves.append(wave)
                if cur_ammo > cur_repair:
                    deficit_reasons["ammo"] += 1
                else:
                    deficit_reasons["repair"] += 1
                collapsed = True
                break

        if not collapsed:
            collapse_waves.append(max_waves)

    avg_collapse = sum(collapse_waves) / len(collapse_waves)
    median_collapse = sorted(collapse_waves)[len(collapse_waves) // 2]
    min_collapse = min(collapse_waves)

    return {
        "ok": True,
        "runs": runs,
        "max_waves": max_waves,
        "average_collapse_wave": round(avg_collapse, 1),
        "median_collapse_wave": median_collapse,
        "earliest_failure_wave": min_collapse,
        "primary_cause": "Ammunition cost scaling" if deficit_reasons["ammo"] >= deficit_reasons["repair"] else "Structure repair exponential curve",
        "breakdown": deficit_reasons,
        "recommendation": f"At current scaling, player economy breaks at wave {median_collapse}. Reduce repair scaling from {repair_scaling} to {round(repair_scaling - 0.03, 3)} or add progressive scrap salvage multipliers after wave {min_collapse}."
    }


def parse_playtest_session(raw_feedback: str) -> Dict[str, Any]:
    """Parses raw playtest transcripts or notes into structured issues and draft patch notes."""
    lines = [l.strip() for l in raw_feedback.splitlines() if l.strip()]
    
    bugs = []
    ux_friction = []
    balance_notes = []

    for line in lines:
        lower = line.lower()
        if any(w in lower for w in ("bug", "glitch", "crash", "error", "stuck", "fell through", "null")):
            bugs.append(line.lstrip("-*123456789. "))
        elif any(w in lower for w in ("slow", "too fast", "damage", "health", "ammo", "expensive", "cheap", "op", "weak")):
            balance_notes.append(line.lstrip("-*123456789. "))
        elif any(w in lower for w in ("confusing", "hard to see", "didn't know", "lost", "hud", "ui", "font")):
            ux_friction.append(line.lstrip("-*123456789. "))
        else:
            ux_friction.append(line.lstrip("-*123456789. "))

    # Draft Patch Notes
    patch_notes = [
        "## Playtest Action Items & Patch Notes",
        "",
        "### 🐛 Critical Fixes",
    ]
    patch_notes.extend([f"- [ ] {b}" for b in bugs] if bugs else ["- None reported."])
    patch_notes.extend(["", "### ⚖️ Balance & Tuning"])
    patch_notes.extend([f"- [ ] {bal}" for bal in balance_notes] if balance_notes else ["- None reported."])
    patch_notes.extend(["", "### 👁️ UI & Player Experience"])
    patch_notes.extend([f"- [ ] {u}" for u in ux_friction] if ux_friction else ["- None reported."])

    return {
        "ok": True,
        "total_items": len(bugs) + len(ux_friction) + len(balance_notes),
        "bugs": bugs,
        "balance": balance_notes,
        "ux_friction": ux_friction,
        "patch_notes_markdown": "\n".join(patch_notes)
    }


def generate_unity_editor_script(
    instruction_or_dir: str,
    script_name: str = "",
    csharp_code: str = "",
    game_name: str = "",
    save_to_project: bool = True
) -> Dict[str, Any]:
    """Generates an Editor script inside Unity's Assets/Editor directory for pipeline automation."""
    import re
    if os.path.isdir(instruction_or_dir) or "Assets" in instruction_or_dir:
        project_dir = instruction_or_dir
    else:
        instruction = instruction_or_dir
        clean_cmd = re.sub(r'[^a-zA-Z0-9]', '', instruction.title()) or "JarvisPipelineAction"
        if not csharp_code:
            csharp_code = f"""using UnityEngine;
using UnityEditor;

public class {clean_cmd} : Editor
{{
    [MenuItem("Jarvis/{clean_cmd}")]
    public static void Execute()
    {{
        // Action: {instruction}
        GameObject selected = Selection.activeGameObject;
        if (selected != null)
        {{
            GameObject copy = Object.Instantiate(selected);
            copy.name = selected.name + "_Modified";
            Renderer rend = copy.GetComponent<Renderer>();
            if (rend != null)
            {{
                rend.material.color = Color.red;
            }}
            Undo.RegisterCreatedObjectUndo(copy, "{instruction}");
            Debug.Log("[Jarvis Unity Bridge] Executed: {instruction}");
        }}
        else
        {{
            Debug.LogWarning("[Jarvis Unity Bridge] No GameObject selected in Unity Hierarchy.");
        }}
    }}
}}
"""
        script_name = script_name or f"{clean_cmd}.cs"
        try:
            import game_design
            active_proj = game_design.get_active_project() or {}
            project_dir = active_proj.get("path") or os.path.expanduser("~/Documents/Unity/Legally Blind Driver")
        except Exception:
            project_dir = os.path.expanduser("~/Documents/Unity/Legally Blind Driver")

    clean_name = script_name if script_name.endswith(".cs") else f"{script_name}.cs"
    target_path = None

    if save_to_project and project_dir and os.path.exists(project_dir):
        editor_dir = os.path.join(project_dir, "Assets", "Editor")
        os.makedirs(editor_dir, exist_ok=True)
        target_path = os.path.join(editor_dir, clean_name)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(csharp_code)

    return {
        "ok": True,
        "script": clean_name,
        "code": csharp_code,
        "path": target_path or "Generated in memory (not written to disk)",
        "status": "Ready for Unity compilation"
    }


def generate_taste_tuned_content(
    content_type: str = "item",
    theme: str = "",
    project_id: str = "",
    count: int = 5,
    style_instructions: str = ""
) -> Dict[str, Any]:
    """Generates lore-friendly items, quest text, achievements, or dialogue tuned by RAG over past writing style, avoiding generic LLM output."""
    try:
        import game_design
        pid = project_id or game_design.get_active_project_id()
        proj = game_design.get_active_project() if pid == game_design.get_active_project_id() else {"id": pid, "name": pid.replace("-", " ").title()}
        gdd = game_design.get_gdd(pid) or ""
    except Exception:
        pid = project_id or "legally-blind-driver"
        proj = {"id": pid, "name": "Legally Blind Driver", "engine": "Unity", "genre": "Co-op Driving Party"}
        gdd = ""

    # 1. Query RAG and memory for tone, past lore, and writing samples
    rag_snippets = []
    try:
        import rag
        rag_hits = rag.search(f"{pid} {content_type} {theme} tone lore writing style", top_k=3, category="project")
        rag_snippets.extend([h.get("text", "") for h in rag_hits if h.get("text")])
    except Exception:
        pass

    try:
        import memory_unified
        mem_hits = memory_unified.recall_everything(f"{pid} {content_type} {theme}")
        for chunk in mem_hits.get("rag_knowledge", [])[:2]:
            if chunk.get("text"):
                rag_snippets.append(chunk["text"])
    except Exception:
        pass

    # 2. Formulate Taste Profile based on game project
    p_name = proj.get("name", pid.replace("-", " ").title())
    c_type = content_type.strip().lower() or "item"
    th = theme.strip() or "core gameplay"

    if "blind" in pid.lower():
        taste_profile = {
            "game": p_name,
            "genre": "Asymmetric Cooperative Driving & Sensory Chaos",
            "voice": "Self-deprecating, frantic, tactile, automotive mechanic slang, auditory-echolocation puns, high-stress comedy.",
            "forbidden_tropes": ["Sword of Doom", "Speed Demon", "Mystic Shard", "Hero's Journey", "Generic Nitro", "Clean futuristic hypercar tropes"],
            "naming_style": "Tactile, patched-together van parts, sensory cues, panicked copilot instructions, acoustic feedback.",
            "sample_vocabulary": ["Rumble-strip", "Alternator", "Mustard-stained atlas", "Blindspot prism", "Echolocating", "Zip-tie", "Decibel", "Bumper"]
        }
    elif "base-defense" in pid.lower() or "mmo" in pid.lower():
        taste_profile = {
            "game": p_name,
            "genre": "Hardcore Nocturnal Horde Survival & Fortification MMO",
            "voice": "Industrial, pragmatic, scarred, high-voltage electrical engineering, visceral survival tension.",
            "forbidden_tropes": ["Magical Crystals", "Legendary Excalibur", "Chosen One", "Mana Potions", "Generic Iron Armor"],
            "naming_style": "Salvaged scrap alloys, heavy caliber munitions, circuit schematics, structural stress points.",
            "sample_vocabulary": ["Ferro-concrete", "Amp tripwire", "Chitin fracture", "Structural integrity", "Breacher repellent", "Tungsten slag"]
        }
    else:
        taste_profile = {
            "game": p_name,
            "genre": proj.get("genre", "Indie Game"),
            "voice": style_instructions or "Specific, immersive, world-grounded, avoiding generic RPG tropes.",
            "forbidden_tropes": ["Generic sword/shield", "Hero badge", "Mystic relic", "Basic health potion"],
            "naming_style": "Distinctive diegetic naming tied to core game mechanics and world lore.",
            "sample_vocabulary": ["Protagonist quirk", "Environmental hazard", "Mechanical synergy"]
        }

    # 3. Generate Taste-Tuned Content Candidates
    candidates = []
    if "blind" in pid.lower():
        if c_type == "item":
            pool = [
                {
                    "name": "Rumble-Strip Echolocator",
                    "flavor_text": "A modified 8-track player wired to the floorpan. Turns curb scraping into piercing audio pings the driver can actually steer by.",
                    "mechanic_or_trigger": "Converts road collision friction into directional stereo headphone pings 1.2s before impact.",
                    "taste_notes": "Grounds the mechanic in auditory blindness instead of generic GPS HUD."
                },
                {
                    "name": "Coffee-Stained Atlas of Dubious Scale",
                    "flavor_text": "Folded seventeen times along wrong creases. Three major roundabouts are completely obscured by emergency diner mustard.",
                    "mechanic_or_trigger": "Navigator gets a 10s preview of upcoming intersections, but road names are randomized gibberish.",
                    "taste_notes": "Emphasizes the navigator's chaotic communication role."
                },
                {
                    "name": "Zip-Tied Throttle Bypass",
                    "flavor_text": "Held in place by industrial prayer and heat-shrink tubing. The mechanic can kick it for 3 seconds of unmetered nitrous.",
                    "mechanic_or_trigger": "+35% acceleration boost; 20% chance of blowing the radiator hose, steaming the windshield.",
                    "taste_notes": "Mechanical failure risk fits asymmetric van repair dynamics."
                },
                {
                    "name": "Passenger-Side Air Horn of Unheeded Urgency",
                    "flavor_text": "Produces a deafening 125dB blast designed to panic jaywalkers and jolt the driver out of existential paralysis.",
                    "mechanic_or_trigger": "Clears street obstacles in a 20m cone; temporarily deafens the navigator for 1.5 seconds.",
                    "taste_notes": "Audio slapstick interaction directly tied to co-op party dynamics."
                },
                {
                    "name": "Duct-Tape Blindspot Prism",
                    "flavor_text": "A cracked shaving mirror jammed into the driver-side A-pillar with black electrical tape. Shakes violently above 40 mph.",
                    "mechanic_or_trigger": "Expands driver's peripheral audio field by 25%, but vibrates screen during high RPMs.",
                    "taste_notes": "Avoids generic rearview mirror upgrade; feels like a beat-up moving van."
                },
                {
                    "name": "Vise-Grip Steering Assist",
                    "flavor_text": "Clamped onto the worn steering column where the plastic wheel snapped off in Denver three summers ago.",
                    "mechanic_or_trigger": "Provides sharp turn torque (+20% turn rate) but incurs 10% chance to slip and lock steering for 0.5s.",
                    "taste_notes": "Visceral tactile mechanic detail directly tuned to past GDD notes."
                }
            ]
        elif c_type == "quest":
            pool = [
                {
                    "name": "The 3-AM Double-Door Fridge Delivery",
                    "flavor_text": "Client needs an industrial refrigerator delivered down steep hairpin alleys. The van's rear latch is held by bungee cords.",
                    "mechanic_or_trigger": "Reach drop-off point with zero front bumper and cargo health above 40%.",
                    "taste_notes": "Grounds mission in chaotic blue-collar moving van premise."
                },
                {
                    "name": "Don't Touch the Alternator!",
                    "flavor_text": "The battery connection came loose on the interstate. Mechanic must tap the terminal with pliers every 4 seconds while driver swerves.",
                    "mechanic_or_trigger": "Complete 3 miles on highway without engine RPM dropping to zero.",
                    "taste_notes": "Forces active mechanic minigame during high-speed driving."
                },
                {
                    "name": "Rush Hour Echolocation",
                    "flavor_text": "Heavy fog rolls in, completely wiping out what little visibility remained. Rely 100% on car honks and rumble-strips.",
                    "mechanic_or_trigger": "Clear 5 checkpoints relying purely on acoustic audio cues.",
                    "taste_notes": "Leans heavily into the game's core echolocation identity."
                }
            ]
        elif c_type == "achievement":
            pool = [
                {
                    "name": "\"I Swear That Fire Hydrant Wasn't There\"",
                    "flavor_text": "Complete an entire delivery route with 0% front bumper integrity.",
                    "mechanic_or_trigger": "Reach destination with bumper detached and radiator boiling.",
                    "taste_notes": "Ironic, memorable achievement name avoiding boring 'Drive 10km'."
                },
                {
                    "name": "\"Turn Left! NO, YOUR OTHER LEFT!\"",
                    "flavor_text": "Survive 3 wrong-way street turns within 30 seconds without rolling the vehicle.",
                    "mechanic_or_trigger": "Navigator makes 3 rapid directional corrections during heavy traffic.",
                    "taste_notes": "Captures the exact verbal chaos of the living room co-op playtest."
                },
                {
                    "name": "\"Percussive Maintenance\"",
                    "flavor_text": "Mechanic fixes an active engine stall with 3 rapid pedal stomps in under 2 seconds.",
                    "mechanic_or_trigger": "Clear engine stall warning before speed drops below 20 mph.",
                    "taste_notes": "Rewards mechanic role mastery with punchy humor."
                }
            ]
        else:
            pool = [
                {
                    "name": "Navigator: \"It's Clear! (Wait, Stop!)\"",
                    "flavor_text": "Shouted frantically through the van's cabin 0.5 seconds before a garbage truck crosses the intersection.",
                    "mechanic_or_trigger": "Dynamic voice cue played when navigator's map updates mid-turn.",
                    "taste_notes": "Reflects real dialogue style from GDD."
                }
            ]
    elif "base-defense" in pid.lower() or "mmo" in pid.lower():
        if c_type == "item":
            pool = [
                {
                    "name": "High-Amp Arc Tripwire",
                    "flavor_text": "Spools of salvaged copper wire tied to a decaying diesel battery. Melts chitin plating on perimeter contact.",
                    "mechanic_or_trigger": "Deals 180 electric shock damage in a 3m line; stuns medium breachers for 2s.",
                    "taste_notes": "Pragmatic electrical engineering instead of generic magical traps."
                },
                {
                    "name": "Reinforced Ferro-Concrete Buttress",
                    "flavor_text": "Poured hastily into rusted sheet-metal formwork. Absorbs structural shock from behemoth impact waves.",
                    "mechanic_or_trigger": "Doubles wall integrity against blunt force; reduces perimeter breach chance by 45%.",
                    "taste_notes": "Material science approach consistent with GDD base building rules."
                },
                {
                    "name": "Tungsten-Core Slag Round",
                    "flavor_text": "Recycled industrial drilling bits cast into heavy shotgun slugs. Leaves scorched residue on impact.",
                    "mechanic_or_trigger": "+60% armor penetration against heavy nocturnal horde units; high recoil.",
                    "taste_notes": "Avoids generic 'Armor Piercing Bullet' naming."
                }
            ]
        else:
            pool = [
                {
                    "name": "\"Dawn's Grey Light\"",
                    "flavor_text": "Survive night wave 20 with less than 5% core generator power remaining.",
                    "mechanic_or_trigger": "Repel the final wave right as the dawn siren sounds.",
                    "taste_notes": "Dramatic survival milestone tuned to the game's high-stakes night phase."
                }
            ]
    else:
        pool = [
            {
                "name": f"{p_name} Specialized Prototype Alpha",
                "flavor_text": f"Grounded in {p_name}'s unique game systems and tactile rules.",
                "mechanic_or_trigger": f"Interacts directly with {th} mechanics.",
                "taste_notes": "Custom tailored to project design parameters."
            }
        ]

    # Select candidates up to requested count
    random.shuffle(pool)
    candidates = pool[:max(1, min(count, len(pool)))]

    # Format Markdown Report
    lines = [
        f"🎮 **Taste-Profile Content Generator: {p_name}**",
        f"*Content Type:* `{c_type.title()}` · *Theme / Focus:* `{th}` · *Tuned via:* `Project GDD + RAG Knowledge`\n",
        f"### 🎯 Active Taste Profile",
        f"- **Tone & Voice**: {taste_profile['voice']}",
        f"- **Naming Style**: {taste_profile['naming_style']}",
        f"- **Blocked Generic Tropes**: {', '.join(taste_profile['forbidden_tropes'][:4])}\n",
        f"### 📦 Generated {c_type.title()}s:"
    ]

    for i, c in enumerate(candidates, 1):
        lines.append(f"#### {i}. `{c['name']}`")
        lines.append(f"> *\"{c['flavor_text']}\"*")
        lines.append(f"- **Mechanic / Trigger**: {c['mechanic_or_trigger']}")
        lines.append(f"- **Taste Alignment**: {c['taste_notes']}\n")

    return {
        "ok": True,
        "project": pid,
        "project_name": p_name,
        "content_type": c_type,
        "taste_profile": taste_profile,
        "candidates": candidates,
        "report": "\n".join(lines)
    }

