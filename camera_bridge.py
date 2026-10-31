"""Camera Bridge: Connects mobile phone camera snaps, sketches, whiteboards,
and documents directly to the Jarvis desktop workstation.

Features:
- Instant image beam & persistence to ~/.jarvis/scans/
- Desktop QML chat display (instant photo bubble)
- Gemini Multimodal Vision analysis (extracts diagrams, OCRs documents, structures game mechanics)
- Screen Notch & system notification feedback
- Auto-indexing to Unified Memory / RAG for context retrieval
"""

import os
import sys
import time
import base64
import uuid
from typing import Dict, Any, List, Optional

import system

SCANS_DIR = os.path.join(system.DATA, "scans")
os.makedirs(SCANS_DIR, exist_ok=True)


def save_scan(image_bytes: bytes, ext: str = "jpg") -> str:
    """Saves raw image bytes to the Jarvis scans directory and returns normalized forward-slash path."""
    os.makedirs(SCANS_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    token = uuid.uuid4().hex[:6]
    filename = f"scan_{ts}_{token}.{ext}"
    filepath = os.path.join(SCANS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    return filepath.replace("\\", "/")


def list_scans(limit: int = 20) -> List[Dict[str, Any]]:
    """Returns recent camera scans sorted newest first."""
    if not os.path.exists(SCANS_DIR):
        return []
    items = []
    for f in os.listdir(SCANS_DIR):
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            full = os.path.join(SCANS_DIR, f)
            try:
                st = os.stat(full)
                items.append({
                    "path": full.replace("\\", "/"),
                    "filename": f,
                    "timestamp": st.st_mtime,
                    "size_kb": round(st.st_size / 1024, 1)
                })
            except OSError:
                pass
    items.sort(key=lambda x: x["timestamp"], reverse=True)
    return items[:limit]


def analyze_scan(image_bytes: bytes, prompt: str = "", mode: str = "auto", brain = None) -> str:
    """Runs multimodal vision analysis on the scanned photo."""
    img_b64 = base64.b64encode(image_bytes).decode("ascii")

    # Tailor vision instructions based on user intent and mode
    system_instruction = (
        "You are Jarvis Mobile Lens, analyzing a photo taken directly from the user's phone camera "
        "and beamed to their PC workstation.\n"
        "Carefully examine the image and provide a thorough, structured, and insightful analysis.\n\n"
        "Guidelines:\n"
        "1. Sketch / Whiteboard / Level Design: Detail all nodes, arrows, entities, mechanics, and flowchart paths. "
        "Provide concrete Unity / C# component architecture or data structure recommendations.\n"
        "2. Code / Terminal / Error Screens: Transcribe the code or error accurately, identify the root cause, and offer the exact code fix.\n"
        "3. Physical Document / Hardware / Book: Perform accurate OCR transcription and extract key bullet points.\n"
        "4. Formatting: Use clean GitHub markdown with bold headers, bullet points, and code blocks."
    )

    user_query = prompt.strip() if prompt.strip() else "Analyze this image and explain what is depicted in full detail."
    if mode and mode != "auto":
        user_query = f"Mode: {mode.upper()}.\n{user_query}"

    contents = [{
        "role": "user",
        "parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": img_b64}},
            {"text": f"{system_instruction}\n\nUser Request: {user_query}"}
        ]
    }]

    analysis = ""
    if brain is not None:
        try:
            entries = brain.models_for("look") if hasattr(brain, "models_for") else None
            parts = brain._generate(contents, entries=entries)
            analysis = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
        except Exception as e:
            print(f"[camera_bridge] Brain vision call failed: {e}", flush=True)

    if not analysis:
        # Fallback if brain unavailable or API failed
        analysis = (
            f"**Photo received and saved successfully.**\n\n"
            f"- Image Size: {len(image_bytes) // 1024} KB\n"
            f"- Mode: `{mode}`\n"
            f"- Prompt: *{prompt or 'None specified'}*\n\n"
            f"*(Vision backend was busy or unreachable; image stored locally for further queries.)*"
        )

    # Index into unified memory if available
    try:
        import memory_unified
        clean_summary = analysis.split("\n")[0][:180]
        if hasattr(memory_unified, "remember"):
            memory_unified.remember(
                f"Mobile Camera Scan: {user_query[:60]} -> {clean_summary}",
                category="camera_scan",
                tags=["vision", "mobile", mode]
            )
    except Exception:
        pass

    return analysis


def process_camera_scan(
    image_data: str,
    prompt: str = "",
    mode: str = "auto",
    brain = None,
    emitter = None
) -> Dict[str, Any]:
    """Coordinates decoding, saving, UI notification, vision analysis, and desktop chat rendering."""
    # Strip data URL prefix if sent from web/canvas
    if "," in image_data and "base64" in image_data[:40]:
        image_data = image_data.split(",", 1)[1]

    raw_bytes = base64.b64decode(image_data)
    file_path = save_scan(raw_bytes, ext="jpg")

    # 1. Notify Desktop Chat with the image thumbnail immediately
    if emitter:
        try:
            emitter("log", who="image", text=file_path)
        except Exception as e:
            print(f"[camera_bridge] Failed to emit image bubble: {e}", flush=True)

    # 2. Update notch & system toast
    try:
        import jarvis
        jarvis.notch_line[:] = ["📷 Mobile Lens: Analyzing scan…", time.time()]
    except Exception:
        pass

    prompt_label = f": {prompt[:40]}…" if prompt else ""
    system.notify("Jarvis Mobile Lens", f"Received photo scan{prompt_label}")

    # 3. Perform Vision Analysis
    analysis = analyze_scan(raw_bytes, prompt=prompt, mode=mode, brain=brain)

    # 4. Notify Desktop Chat with analysis response card
    if emitter:
        try:
            report = f"📷 **Mobile Camera Teleport**\n\n{analysis}"
            emitter("log", who="jarvis", text=report)
        except Exception as e:
            print(f"[camera_bridge] Failed to emit vision analysis: {e}", flush=True)

    # 5. Update notch on completion
    try:
        import jarvis
        jarvis.notch_line[:] = ["📷 Scan analysis ready", time.time()]
    except Exception:
        pass

    return {
        "ok": True,
        "file_path": file_path,
        "analysis": analysis,
        "timestamp": time.time(),
        "prompt": prompt,
        "mode": mode
    }
