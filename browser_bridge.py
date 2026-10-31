"""browser_bridge.py - Chrome DevTools Protocol (CDP) Bridge for Jarvis.

Enables Jarvis to interact directly with live Chrome/Edge/Brave sessions
via Chrome DevTools Protocol (CDP) over WebSockets and HTTP on port 9222.
Reads clean DOM trees, fills forms, clicks elements, and navigates deterministically
without brittle OCR or pixel-guessing coordinate hacks.
"""

import asyncio
import json
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

CDP_PORT = 9222
CDP_BASE_URL = f"http://127.0.0.1:{CDP_PORT}"

BROWSER_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

JARVIS_BROWSER_PROFILE = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "Jarvis", "browser_profile"
)


def is_cdp_available() -> bool:
    """Checks if a browser with remote debugging on CDP_PORT is reachable."""
    try:
        req = urllib.request.Request(f"{CDP_BASE_URL}/json/version", headers={"User-Agent": "Jarvis-CDP"})
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_installed_browser_path(preference: Optional[str] = None) -> Optional[str]:
    """Finds path to installed Chrome, Brave, or Edge."""
    if preference:
        for p in BROWSER_PATHS:
            if preference.lower() in p.lower() and os.path.exists(p):
                return p
    for p in BROWSER_PATHS:
        if os.path.exists(p):
            return p
    return None


def launch_browser(url: str = "https://www.google.com", browser_preference: Optional[str] = None) -> Dict[str, Any]:
    """Launches browser with remote debugging port 9222 enabled using dedicated Jarvis profile."""
    if is_cdp_available():
        # Already running, optionally open tab
        if url:
            navigate(url)
        return {"status": "already_running", "cdp_url": CDP_BASE_URL, "url": url}

    exe = get_installed_browser_path(browser_preference)
    if not exe:
        return {"error": "No supported browser (Chrome, Brave, Edge) found on system."}

    os.makedirs(JARVIS_BROWSER_PROFILE, exist_ok=True)
    cmd = [
        exe,
        f"--remote-debugging-port={CDP_PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={JARVIS_BROWSER_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        url
    ]

    try:
        proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0)
        # Wait up to 5s for CDP endpoint to become ready
        for _ in range(25):
            time.sleep(0.2)
            if is_cdp_available():
                return {"status": "launched", "pid": proc.pid, "cdp_url": CDP_BASE_URL, "browser": exe}
        return {"status": "launching_slowly", "pid": proc.pid, "browser": exe}
    except Exception as e:
        return {"error": f"Failed to launch browser: {e}"}


def list_tabs() -> List[Dict[str, Any]]:
    """Returns list of open inspectable tabs from CDP."""
    if not is_cdp_available():
        return []
    try:
        req = urllib.request.Request(f"{CDP_BASE_URL}/json", headers={"User-Agent": "Jarvis-CDP"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
            return [
                {
                    "id": t.get("id"),
                    "title": t.get("title", ""),
                    "url": t.get("url", ""),
                    "type": t.get("type", ""),
                    "ws_url": t.get("webSocketDebuggerUrl", "")
                }
                for t in targets
                if t.get("type") in ("page", "app") and not t.get("url", "").startswith("chrome-extension://")
            ]
    except Exception:
        return []


def get_active_tab() -> Optional[Dict[str, Any]]:
    """Returns primary active page tab."""
    tabs = list_tabs()
    if not tabs:
        return None
    # Prefer non-blank tabs
    for t in tabs:
        if t["url"] and not t["url"].startswith("about:") and not t["url"].startswith("chrome://"):
            return t
    return tabs[0]


async def _cdp_call_ws(ws_url: str, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 5.0) -> Dict[str, Any]:
    """Sends a single CDP method call over WebSocket and awaits response."""
    import websockets
    params = params or {}
    msg_id = int(time.time() * 1000) % 1000000
    payload = {"id": msg_id, "method": method, "params": params}

    async with websockets.connect(ws_url, max_size=10_000_000) as ws:
        await ws.send(json.dumps(payload))
        start = time.time()
        while time.time() - start < timeout:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            resp = json.loads(raw)
            if resp.get("id") == msg_id:
                if "error" in resp:
                    return {"error": resp["error"].get("message", "CDP error")}
                return resp.get("result", {})
    return {"error": "Timeout waiting for CDP response"}


def call_cdp(method: str, params: Optional[Dict[str, Any]] = None, tab_id: Optional[str] = None, timeout: float = 5.0) -> Dict[str, Any]:
    """Synchronous wrapper for CDP method call on specified or active tab."""
    tabs = list_tabs()
    if not tabs:
        return {"error": "No browser tabs open on CDP port 9222. Use launch_browser() first."}

    target_tab = None
    if tab_id:
        for t in tabs:
            if t["id"] == tab_id:
                target_tab = t
                break
    if not target_tab:
        target_tab = get_active_tab() or tabs[0]

    ws_url = target_tab.get("ws_url")
    if not ws_url:
        return {"error": "Selected tab has no WebSocket debugger URL."}

    try:
        return asyncio.run(_cdp_call_ws(ws_url, method, params, timeout=timeout))
    except Exception as e:
        return {"error": f"CDP call failed: {e}"}


def evaluate_script(js_expression: str, tab_id: Optional[str] = None) -> Any:
    """Executes a JavaScript expression in the browser tab and returns result."""
    res = call_cdp("Runtime.evaluate", {
        "expression": js_expression,
        "returnByValue": True,
        "awaitPromise": True
    }, tab_id=tab_id)
    if "error" in res:
        return res
    val_wrap = res.get("result", {})
    return val_wrap.get("value", val_wrap.get("description"))


DOM_EXTRACT_JS = r"""(() => {
    const title = document.title || '';
    const url = window.location.href;
    
    // Extract headings
    const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
        .filter(el => el.offsetParent !== null)
        .map(h => `${'#'.repeat(parseInt(h.tagName[1]))} ${h.innerText.trim()}`)
        .slice(0, 15);

    // Extract interactive elements (buttons, links, inputs)
    const interactives = [];
    
    // Buttons
    document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]').forEach(btn => {
        if (btn.offsetParent !== null) {
            const txt = (btn.innerText || btn.value || btn.getAttribute('aria-label') || '').trim();
            if (txt) {
                const id = btn.id ? `#${btn.id}` : '';
                const cls = btn.className && typeof btn.className === 'string' ? `.${btn.className.trim().split(/\s+/).slice(0,2).join('.')}` : '';
                interactives.push(`[BUTTON] "${txt}" (Selector: ${id || cls || btn.tagName.toLowerCase()})`);
            }
        }
    });

    // Inputs
    document.querySelectorAll('input:not([type="hidden"]):not([type="button"]):not([type="submit"]), textarea, select').forEach(inp => {
        if (inp.offsetParent !== null) {
            const name = inp.name || inp.id || inp.placeholder || inp.getAttribute('aria-label') || 'input';
            const sel = inp.id ? `#${inp.id}` : (inp.name ? `[name="${inp.name}"]` : inp.tagName.toLowerCase());
            interactives.push(`[INPUT:${inp.type || 'text'}] "${name}" (Selector: ${sel}) value="${(inp.value || '').slice(0, 40)}"`);
        }
    });

    // Top Links
    const links = Array.from(document.querySelectorAll('a[href]'))
        .filter(a => a.offsetParent !== null && a.innerText.trim().length > 1)
        .slice(0, 20)
        .map(a => `[LINK] "${a.innerText.trim()}" -> ${a.href}`);

    // Main text content (condensed)
    const bodyText = (document.body ? document.body.innerText : '')
        .split('\n')
        .map(l => l.trim())
        .filter(l => l.length > 20)
        .slice(0, 30)
        .join('\n');

    return {
        title,
        url,
        headings,
        interactives: interactives.slice(0, 25),
        links,
        body_sample: bodyText.slice(0, 2500)
    };
})()"""


def get_dom_summary(tab_id: Optional[str] = None) -> Dict[str, Any]:
    """Extracts a structured, clean DOM tree without taking screenshots or using OCR."""
    data = evaluate_script(DOM_EXTRACT_JS, tab_id=tab_id)
    if isinstance(data, dict) and "error" in data:
        return data
    return data or {"error": "Failed to extract DOM summary"}


def click_element(selector: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
    """Clicks a DOM element matching CSS selector deterministically."""
    js = f"""(() => {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) return {{success: false, error: "Element not found for selector: " + {json.dumps(selector)}}};
        el.scrollIntoView({{behavior: 'instant', block: 'center'}});
        el.click();
        return {{success: true, tag: el.tagName, text: el.innerText || el.value || ''}};
    }})()"""
    res = evaluate_script(js, tab_id=tab_id)
    return res if isinstance(res, dict) else {"result": res}


def fill_input(selector: str, text: str, submit: bool = False, tab_id: Optional[str] = None) -> Dict[str, Any]:
    """Fills an input/textarea with text and fires standard input/change events."""
    js = f"""(() => {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) return {{success: false, error: "Input not found: " + {json.dumps(selector)}}};
        el.focus();
        el.value = {json.dumps(text)};
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        if ({json.dumps(submit)}) {{
            if (el.form) el.form.submit();
            else {{
                el.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }}));
            }}
        }}
        return {{success: true, selector: {json.dumps(selector)}, text: {json.dumps(text)}}};
    }})()"""
    res = evaluate_script(js, tab_id=tab_id)
    return res if isinstance(res, dict) else {"result": res}


def navigate(url: str, tab_id: Optional[str] = None) -> Dict[str, Any]:
    """Navigates current or specified tab to URL."""
    if not url.startswith("http://") and not url.startswith("https://") and not url.startswith("file://"):
        url = "https://" + url
    return call_cdp("Page.navigate", {"url": url}, tab_id=tab_id)
