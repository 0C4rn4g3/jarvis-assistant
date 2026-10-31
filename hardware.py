"""Jarvis Hardware Auto-Profiler: detects CPU, RAM, GPU/VRAM and configures optimal LLM inference tiers."""
import json
import os
import platform
import subprocess
import sys
import psutil
import time

NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
_gpu_cache = {"time": 0.0, "data": None}

try:
    import store
except ImportError:
    store = None


def get_cpu_info():
    """Detects CPU model and physical/logical core counts."""
    name = platform.processor() or "Unknown CPU"
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                text=True, timeout=5, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW
            ).strip()
            if out:
                name = out.splitlines()[0].strip()
        except Exception:
            pass

    cores = psutil.cpu_count(logical=False) or (os.cpu_count() // 2 if os.cpu_count() else 1)
    threads = psutil.cpu_count(logical=True) or os.cpu_count() or 1
    return {
        "name": name,
        "physical_cores": cores,
        "logical_threads": threads,
    }


def get_ram_info():
    """Detects total and available system memory in GB."""
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024 ** 3), 2),
        "available_gb": round(mem.available / (1024 ** 3), 2),
        "used_percent": mem.percent,
    }


def get_gpu_info():
    """Detects GPU brand, name, total VRAM, and free VRAM with 5s caching and hidden window."""
    now = time.time()
    if _gpu_cache["data"] and (now - _gpu_cache["time"] < 5.0):
        return _gpu_cache["data"]

    res = _detect_gpu()
    _gpu_cache["time"] = now
    _gpu_cache["data"] = res
    return res


def _detect_gpu():
    # 1. Try nvidia-smi
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader,nounits"],
            text=True, timeout=5, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW
        ).strip()
        if out:
            parts = [p.strip() for p in out.splitlines()[0].split(",")]
            if len(parts) >= 3:
                return {
                    "vendor": "NVIDIA",
                    "name": parts[0],
                    "vram_total_mb": int(parts[1]),
                    "vram_free_mb": int(parts[2]),
                    "driver_version": parts[3] if len(parts) > 3 else "Unknown",
                    "detected": True,
                }
    except Exception:
        pass

    # 2. Windows fallback via Win32_VideoController
    if sys.platform == "win32":
        try:
            cmd = "(Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM) | ConvertTo-Json -Compress"
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", cmd],
                text=True, timeout=5, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW
            ).strip()
            if out:
                data = json.loads(out)
                if isinstance(data, list) and data:
                    data = data[0]
                name = data.get("Name", "Unknown GPU")
                vram_bytes = data.get("AdapterRAM") or 0
                vram_mb = int(vram_bytes / (1024 * 1024)) if vram_bytes else 0
                vendor = "NVIDIA" if "nvidia" in name.lower() else ("AMD" if "amd" in name.lower() or "radeon" in name.lower() else "Intel")
                return {
                    "vendor": vendor,
                    "name": name,
                    "vram_total_mb": vram_mb,
                    "vram_free_mb": vram_mb,
                    "driver_version": "N/A",
                    "detected": True,
                }
        except Exception:
            pass

    return {
        "vendor": "Unknown",
        "name": "Integrated / Generic Graphics",
        "vram_total_mb": 0,
        "vram_free_mb": 0,
        "driver_version": "N/A",
        "detected": False,
    }


def get_local_models():
    """Queries running local Ollama engine for installed models."""
    import urllib.request
    ollama_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if "://" not in ollama_host:
        ollama_host = "http://" + ollama_host
    try:
        req = urllib.request.Request(f"{ollama_host}/api/tags", headers={"User-Agent": "Jarvis-HardwareProfiler"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def profile_hardware():
    """Full hardware audit and LLM tier sizing."""
    cpu = get_cpu_info()
    ram = get_ram_info()
    gpu = get_gpu_info()
    models = get_local_models()
    vram_mb = gpu.get("vram_total_mb", 0)

    # Compute recommendations
    if vram_mb >= 15000:
        recommended_tier = "14B-32B Q4"
        recommended_model = "qwen2.5:14b"
        num_ctx = 32768
    elif vram_mb >= 7000:  # e.g. RTX 3070 8GB
        recommended_tier = "7B-9B Q4"
        recommended_model = "qwen2.5:7b"
        num_ctx = 16384
    elif vram_mb >= 3500:
        recommended_tier = "3B-4B Q4"
        recommended_model = "llama3.2:3b"
        num_ctx = 8192
    else:
        # Fall back to CPU inference sizing by RAM
        if ram["total_gb"] >= 32:
            recommended_tier = "CPU 7B Q4"
            recommended_model = "qwen2.5:7b"
            num_ctx = 8192
        else:
            recommended_tier = "CPU 1.5B-3B Q4"
            recommended_model = "llama3.2:3b"
            num_ctx = 4096

    # Select best installed model matching tier if available
    installed_best = None
    priority_models = [recommended_model, "qwen2.5:7b", "qwen3.5:latest", "mistral:latest", "llama3.1:latest", "llama3.2:3b"]
    for pm in priority_models:
        if pm in models:
            installed_best = pm
            break
    if not installed_best and models:
        installed_best = models[0]

    return {
        "cpu": cpu,
        "ram": ram,
        "gpu": gpu,
        "ollama_online": len(models) > 0,
        "installed_local_models": models,
        "recommended_tier": recommended_tier,
        "recommended_model": recommended_model,
        "active_best_local_model": installed_best or recommended_model,
        "recommended_num_ctx": num_ctx,
    }


def print_audit_report(profile):
    """Outputs a clean CLI diagnostic report."""
    print("=" * 60)
    print("  JARVIS SYSTEM HARDWARE & LOCAL INFERENCE PROFILE")
    print("=" * 60)
    print(f" CPU:         {profile['cpu']['name']}")
    print(f" Cores:       {profile['cpu']['physical_cores']} Physical / {profile['cpu']['logical_threads']} Threads")
    print(f" RAM:         {profile['ram']['total_gb']} GB Total ({profile['ram']['available_gb']} GB Free, {profile['ram']['used_percent']}% Used)")
    print(f" GPU:         {profile['gpu']['name']} ({profile['gpu']['vendor']})")
    print(f" VRAM:        {profile['gpu']['vram_total_mb']} MB Total ({profile['gpu']['vram_free_mb']} MB Free)")
    print("-" * 60)
    print(f" Ollama:      {'Online (Port 11434)' if profile['ollama_online'] else 'Offline / Not Detected'}")
    if profile["installed_local_models"]:
        print(f" Local Models: {', '.join(profile['installed_local_models'])}")
    else:
        print(" Local Models: None found in Ollama library")
    print("-" * 60)
    print(f" Sizing Tier: {profile['recommended_tier']}")
    print(f" Rec. Model:  {profile['recommended_model']} (Active: {profile['active_best_local_model']})")
    print(f" Context Win: {profile['recommended_num_ctx']} tokens (JARVIS_NUM_CTX)")
    print("=" * 60)


def apply_profile(profile=None):
    """Updates settings.json and environment to ensure local fallback and context size are calibrated."""
    if profile is None:
        profile = profile_hardware()

    best_model = profile["active_best_local_model"]
    os.environ["JARVIS_NUM_CTX"] = str(profile["recommended_num_ctx"])

    if store:
        s = store.settings()
        agent_models = list(s.get("agent_models", []))
        local_entry = f"ollama {best_model} minimal"
        
        # Ensure optimal local fallback is registered in chain
        clean_chain = [e for e in agent_models if not e.startswith("ollama ")]
        clean_chain.append(local_entry)
        
        try:
            store.update_settings({"agent_models": clean_chain})
            print(f"[Hardware] Saved local fallback '{local_entry}' into agent_models chain.")
        except Exception as e:
            print(f"[Hardware] Warning: could not update settings: {e}")

    return profile


GAME_PROCESS_NAMES = {
    "javaw.exe", "java.exe", "minecraft.windows.exe", "lunarclient.exe", "badlion.exe",
    "unity.exe", "unrealeditor.exe", "unrealpak.exe",
    "cs2.exe", "csgo.exe", "dota2.exe", "valorant.exe", "overwatch.exe",
    "r5apex.exe", "gta5.exe", "cyberpunk2077.exe", "witcher3.exe",
    "eldenring.exe", "fortniteclient-win64-shipping.exe", "fortnite.exe",
    "leagueclientux.exe", "riotclientux.exe", "tarkov.exe"
}

_vram_gaming_active = False
_gaming_cache = {"time": 0.0, "result": False}


def is_gaming_active() -> bool:
    """Checks if high-workload 3D gaming or engine process is running (cached for 10s to eliminate CPU waste)."""
    now = time.time()
    if now - _gaming_cache["time"] < 10.0:
        return _gaming_cache["result"]

    result = False
    try:
        for p in psutil.process_iter(['name']):
            name = (p.info.get('name') or '').lower()
            if name in GAME_PROCESS_NAMES:
                result = True
                break
    except Exception:
        pass

    _gaming_cache["time"] = now
    _gaming_cache["result"] = result
    return result


def arbitrate_vram() -> dict:
    """If 3D game is detected, evicts Ollama models from RTX 3070 VRAM immediately."""
    global _vram_gaming_active
    gaming = is_gaming_active()
    _vram_gaming_active = gaming
    evicted = []

    if gaming:
        import requests
        try:
            r = requests.get("http://localhost:11434/api/ps", timeout=1.5)
            if r.ok:
                models = r.json().get("models", [])
                for m in models:
                    m_name = m.get("name")
                    if m_name:
                        requests.post("http://localhost:11434/api/generate",
                                      json={"model": m_name, "keep_alive": 0}, timeout=1.5)
                        evicted.append(m_name)
                        print(f"[Hardware/VRAM] Evicted {m_name} from VRAM for gaming performance.", flush=True)
        except Exception:
            pass

    return {
        "gaming_active": gaming,
        "evicted_models": evicted,
        "vram_protection_active": gaming
    }


def is_system_idle(cpu_threshold: float = 35.0, require_no_gaming: bool = True) -> bool:
    """Bandwidth / Hardware Scheduler check: returns True only if GPU/CPU is idle and no 3D game is active."""
    if require_no_gaming and is_gaming_active():
        return False
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        if cpu > cpu_threshold:
            return False
        mem = psutil.virtual_memory()
        if mem.percent > 90.0:
            return False
    except Exception:
        pass
    return True



if __name__ == "__main__":
    prof = profile_hardware()
    print_audit_report(prof)
    if "--apply" in sys.argv or "--init" in sys.argv:
        apply_profile(prof)
        print("[Hardware] Recommended parameters applied successfully.")
