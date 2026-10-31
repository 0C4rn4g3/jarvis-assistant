"""Everything that depends on the operating system, behind one small interface: where files live, the microphone and
speaker, screenshots, mouse and keyboard, windows, apps, the shell, notifications, media and starting at login.
Windows and Linux (X11 or Wayland; KDE Plasma gets faster paths). Each function picks the best tool that's installed."""
import json, os, re, shutil, subprocess, sys, tempfile, threading, time

IS_WINDOWS = sys.platform == "win32"
WAYLAND = not IS_WINDOWS and os.environ.get("XDG_SESSION_TYPE") == "wayland"
KDE = "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "")
GNOME = "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "")
HERE = os.path.dirname(os.path.abspath(__file__))
CALC = "calc" if IS_WINDOWS else "kcalc" if KDE else "gnome-calculator"  # for examples in the prompts

# ---------------------------------------------------------------- where things live
if IS_WINDOWS:
    _root = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Jarvis")
    CONFIG, DATA = _root, os.path.join(_root, "data")
else:
    CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "jarvis")
    DATA = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "jarvis")
PICTURES = os.path.join(os.path.expanduser("~"), "Pictures", "Jarvis")


def have(program):
    return shutil.which(program) is not None


def run(args, timeout=15, env=None):
    """A short command's output (stdout and stderr), '' if it isn't installed."""
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env,
                           creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (r.stdout + r.stderr).strip()


def describe():
    """A few lines for the models: what this computer is and how to do common things on it."""
    if IS_WINDOWS:
        return ("The computer runs Windows. run_command runs PowerShell (e.g. Get-ChildItem $HOME\\Downloads, Get-Clipboard, "
                "Set-Clipboard 'text'). Open apps with act launch (notepad, calc, explorer, msedge, spotify...); "
                "media keys: act([{keys: \"XF86AudioPlay\"}]).")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "Linux")
    return (f"The computer runs Linux ({desktop}, {'Wayland' if WAYLAND else 'X11'}). run_command runs bash (e.g. ls ~/Downloads; "
            "volume: wpctl set-volume @DEFAULT_AUDIO_SINK@ 50% or pactl; clipboard: wl-paste / xclip). Open apps with act "
            "launch (firefox, dolphin, nautilus, kcalc...); media keys: act([{keys: \"XF86AudioPlay\"}]).")


# ---------------------------------------------------------------- microphone and speaker
def mic_frames(target=None):
    """16 kHz mono int16 frames of 80 ms (1280 samples): PipeWire's pw-record when there (it can use the echo canceller),
    otherwise PortAudio through sounddevice (Windows, PulseAudio/ALSA systems)."""
    import numpy as np
    if not IS_WINDOWS and have("pw-record"):
        while True:  # pw-record quits when PipeWire restarts (an update, a new device): start it again, or Jarvis goes deaf
            p = subprocess.Popen(["pw-record", *(["--target", target] if target else []), "--rate", "16000", "--channels", "1",
                                  "--format", "s16", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            started = time.time()
            while chunk := p.stdout.read(2560):
                if len(chunk) == 2560:
                    yield np.frombuffer(chunk, np.int16)
            print(f"[voice] the microphone stream stopped (pw-record exit {p.wait()}): starting it again", flush=True)
            time.sleep(1 if time.time() - started > 10 else 10)  # (failing at once: wait longer, don't spin)
    import sounddevice as sd
    with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1280) as stream:
        while True:
            frames, _ = stream.read(1280)
            yield frames[:, 0].copy()


class AudioOut:
    """A stream of 24 kHz mono 16-bit PCM to the speakers that can be cut off at once: pw-play on PipeWire, else
    sounddevice."""

    def __init__(self, target=None):
        self.target, self.proc, self.stream = target, None, None
        self.pipewire = not IS_WINDOWS and have("pw-play")

    def write(self, pcm):
        if self.pipewire:
            proc = self.proc  # (stop() may clear it from another thread meanwhile)
            if not proc or proc.poll() is not None:
                proc = self.proc = subprocess.Popen(["pw-play", *(["--target", self.target] if self.target else []), "--raw", "--rate",
                                                     "24000", "--channels", "1", "--format", "s16", "-"],
                                                    stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
            proc.stdin.write(pcm)
            proc.stdin.flush()
        else:
            import numpy as np
            import sounddevice as sd
            if self.stream is None:
                self.stream = sd.RawOutputStream(samplerate=24000, channels=1, dtype="int16")
                self.stream.start()
            self.stream.write(np.frombuffer(pcm, np.int16).tobytes())

    def stop(self):
        proc, self.proc = self.proc, None  # the speaker thread and the Stop button can both get here at once
        if proc:
            proc.kill()
            try:
                proc.stdin.close()
            except OSError:
                pass
        if self.stream is not None:
            try:
                self.stream.abort()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


def record_audio(path, source="pc"):
    """Start recording to a 16 kHz mono WAV: what the PC is playing ("pc") or the microphone ("room"). The process; end it
    with stop_recording, which finishes the file."""
    if IS_WINDOWS or not have("pw-record"):
        raise RuntimeError("recording needs PipeWire (Linux)")
    what = ["-P", "{ stream.capture.sink=true }"] if source == "pc" else []
    return subprocess.Popen(["pw-record", *what, "--rate", "16000", "--channels", "1", "--format", "s16", path],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_recording(proc):
    import signal
    proc.send_signal(signal.SIGINT)  # (pw-record finishes the WAV header on SIGINT)
    try:
        proc.wait(5)
    except subprocess.TimeoutExpired:
        proc.kill()


def chime():
    """A short, soft two-note chime (generated, so there's no sound file to ship)."""
    def play():
        import numpy as np
        t = np.linspace(0, 0.09, int(24000 * 0.09), False)
        notes = [np.sin(2 * np.pi * f * t) * np.exp(-t * 30) for f in (880, 1320)]
        tone = (np.concatenate(notes) * 0.25 * 32767).astype(np.int16).tobytes()
        out = AudioOut()
        try:
            out.write(tone)
            time.sleep(0.25)
        finally:
            if out.proc:
                out.proc.stdin.close()
            elif out.stream is not None:
                time.sleep(0.05)
                out.stream.close()
    threading.Thread(target=play, daemon=True).start()


# ---------------------------------------------------------------- screenshots
SHOT_HELPER = os.path.join(DATA, "bin", "jarvis-shot")  # KDE: built by install.sh from jarvis-shot.c


def _jpeg(raw, w, h, stride, fmt):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage
    out = QByteArray()
    buf = QBuffer(out)
    buf.open(QIODevice.WriteOnly)
    QImage(raw, w, h, stride, fmt).save(buf, "JPG", 85)
    return bytes(out)


def _from_file(args, suffix=".png", timeout=10):
    path = os.path.join(tempfile.mkdtemp(prefix="jarvis-"), "screen" + suffix)
    run(args + [path] if "{}" not in " ".join(args) else [a.replace("{}", path) for a in args], timeout=timeout)
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QImage
        img = QImage(path)
        if img.isNull():
            return None
        out = QByteArray()
        buf = QBuffer(out)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "JPG", 85)
        return bytes(out)
    finally:
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)


def screenshot():
    """A JPEG of the whole screen, by the fastest way this desktop allows."""
    shot = _screenshot()
    if not shot:
        raise RuntimeError("couldn't take a screenshot: no screenshot tool on this desktop answered")
    return shot


def screen_peek_jpeg(max_w: int = 640, max_h: int = 360, quality: int = 40) -> bytes:
    """Downsamples screen capture to low-resolution JPEG for phone screen peek monitoring."""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
        import sys
        _app = QApplication.instance() or QApplication(sys.argv)
        screen = QGuiApplication.primaryScreen()
        if screen:
            pix = screen.grabWindow(0)
            if not pix.isNull():
                scaled = pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                out = QByteArray()
                buf = QBuffer(out)
                buf.open(QIODevice.WriteOnly)
                scaled.save(buf, "JPG", quality)
                return bytes(out)
    except Exception:
        pass
    try:
        raw_shot = screenshot()
        if raw_shot:
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
            from PySide6.QtGui import QImage
            img = QImage()
            img.loadFromData(raw_shot)
            if not img.isNull():
                scaled = img.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                out = QByteArray()
                buf = QBuffer(out)
                buf.open(QIODevice.WriteOnly)
                scaled.save(buf, "JPG", quality)
                return bytes(out)
            return raw_shot
    except Exception:
        pass
    return b""


def _screenshot():
    if KDE and WAYLAND and os.path.exists(SHOT_HELPER):  # ~30 ms through KWin
        try:
            raw = subprocess.run([SHOT_HELPER], capture_output=True, timeout=5).stdout
            head, pixels = raw.split(b"\n", 1)
            w, h, stride, fmt = map(int, head.split())
            if w and len(pixels) >= stride * h and pixels.strip(b"\0"):  # (all black: KWin refused this caller)
                from PySide6.QtGui import QImage
                return _jpeg(pixels, w, h, stride, QImage.Format(fmt))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    if WAYLAND:
        if KDE and have("spectacle"):
            return _from_file(["spectacle", "-b", "-n", "-f", "-o"])
        if have("grim"):  # wlroots desktops (Sway, Hyprland...)
            return _from_file(["grim"])
        if GNOME and have("gnome-screenshot"):
            return _from_file(["gnome-screenshot", "-f"])
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        import sys
        _app = QApplication.instance() or QApplication(sys.argv)
        screen = QGuiApplication.primaryScreen()
        if screen:
            pix = screen.grabWindow(0)
            if not pix.isNull():
                img = pix.toImage()
                out = QByteArray()
                buf = QBuffer(out)
                buf.open(QIODevice.WriteOnly)
                img.save(buf, "JPG", 85)
                return bytes(out)
    except Exception:
        pass
    try:
        import mss  # Windows and X11
        from PySide6.QtGui import QImage
        with mss.mss() as m:
            shot = m.grab(m.monitors[0])
            return _jpeg(bytes(shot.bgra), shot.width, shot.height, shot.width * 4, QImage.Format_ARGB32)
    except Exception:
        pass
    return None


def capture_region():
    """Let the user drag over part of the screen; that part as a JPEG, or None if they cancelled (or nothing here can)."""
    if WAYLAND and KDE and have("spectacle"):
        return _from_file(["spectacle", "-b", "-n", "-r", "-o"], timeout=120)
    if WAYLAND and have("grim") and have("slurp"):
        area = run(["slurp"], 120)
        return _from_file(["grim", "-g", area]) if re.fullmatch(r"\d+,\d+ \d+x\d+", area) else None
    if not WAYLAND and not IS_WINDOWS and have("maim"):
        return _from_file(["maim", "-s"], timeout=120)
    return None


# ---------------------------------------------------------------- mouse and keyboard
WDOTOOL_ENV = dict(os.environ, XDG_STATE_HOME=os.path.join(DATA, "state"), RUST_LOG="error")
_input_lock = threading.Lock()  # one input action at a time (wdotool's permission token is single-use)
KEY_NAMES = {"enter": "Return", "return": "Return", "esc": "Escape", "escape": "Escape", "del": "Delete", "delete": "Delete",
             "backspace": "BackSpace", "tab": "Tab", "space": "space", "pageup": "Page_Up", "pgup": "Page_Up", "pagedown": "Page_Down",
             "pgdn": "Page_Down", "home": "Home", "end": "End", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
             "arrowup": "Up", "arrowdown": "Down", "arrowleft": "Left", "arrowright": "Right", "pause": "Pause", "ret": "Return",
             "insert": "Insert", "control": "ctrl", "cmd": "super", "win": "super", "windows": "super", "meta": "super"}


def key_chains(keys):
    """'ctrl+a Enter' -> [['ctrl', 'a'], ['Return']] with common names turned into xkb's."""
    return [[KEY_NAMES.get(k.lower(), k) for k in chain.split("+")] for chain in keys.split()]


def _wayland_tool():
    return "wdotool" if have("wdotool") else "ydotool" if have("ydotool") else None


PERMISSION_PENDING = ("timed out: the desktop is still waiting for the user to allow Jarvis's input control in its permission "
                      "prompt (Remote Control)")
_input_blocked_until = [0.0]  # after a timed-out permission prompt, fail fast for a minute instead of waiting again


def _wdo(*args, timeout=15):
    if time.time() < _input_blocked_until[0]:
        return PERMISSION_PENDING
    with _input_lock:
        try:
            r = subprocess.run(["wdotool", *map(str, args)], capture_output=True, text=True, timeout=timeout, env=WDOTOOL_ENV)
            if r.returncode != 0 and "no keyboard device from EIS" in (r.stderr or ""):
                r = subprocess.run(["wdotool", "--backend", "uinput", *map(str, args)], capture_output=True, text=True, timeout=timeout, env=WDOTOOL_ENV)
        except subprocess.TimeoutExpired:
            _input_blocked_until[0] = time.time() + 60
            return PERMISSION_PENDING
        except OSError as e:
            return str(e)
    _input_blocked_until[0] = 0.0
    return (r.stdout + r.stderr).strip()


def _pynput_key(name):
    from pynput.keyboard import Key, KeyCode
    special = {"Return": Key.enter, "Escape": Key.esc, "BackSpace": Key.backspace, "Tab": Key.tab, "space": Key.space,
               "Delete": Key.delete, "Insert": Key.insert, "Home": Key.home, "End": Key.end, "Page_Up": Key.page_up,
               "Page_Down": Key.page_down, "Up": Key.up, "Down": Key.down, "Left": Key.left, "Right": Key.right,
               "ctrl": Key.ctrl, "shift": Key.shift, "alt": Key.alt, "super": Key.cmd, "Pause": Key.pause,
               "XF86AudioPlay": Key.media_play_pause, "XF86AudioNext": Key.media_next, "XF86AudioPrev": Key.media_previous,
               "XF86AudioMute": Key.media_volume_mute, "XF86AudioRaiseVolume": Key.media_volume_up,
               "XF86AudioLowerVolume": Key.media_volume_down}
    if name in special:
        return special[name]
    if len(name) > 1 and name[0] in "Ff" and name[1:].isdigit():
        return getattr(Key, name.lower())
    if len(name) == 1:
        return KeyCode.from_char(name.lower())
    raise ValueError(f"unknown key '{name}'")


def move_pointer(px, py):
    """'' once the pointer is at (px, py) in screen pixels, else what went wrong."""
    if WAYLAND:
        if _wayland_tool() != "wdotool":
            return "moving the pointer on Wayland needs wdotool"
        for _ in range(3):  # wdotool makes a fresh virtual device per call: the first event is occasionally dropped
            out = _wdo("mousemove", px, py, timeout=30)  # (the first call waits while the user answers the permission prompt)
            if out:
                return out
            at = _wdo("getmouselocation")
            if at == f"x:{px} y:{py}":
                return ""
        return f"the pointer ended up at {at}"
    from pynput.mouse import Controller
    Controller().position = (px, py)
    return ""


def click(button="left", double=False):
    if WAYLAND:
        tool = _wayland_tool()
        for _ in range(2 if double else 1):
            out = (_wdo("click", {"left": "1", "middle": "2", "right": "3"}[button]) if tool == "wdotool" else
                   run(["ydotool", "click", {"left": "0xC0", "middle": "0xC2", "right": "0xC1"}[button]]) if tool else "no input tool")
            if out and tool != "ydotool":
                return out
        return ""
    from pynput.mouse import Button, Controller
    Controller().click(getattr(Button, button), 2 if double else 1)
    return ""


def type_text(text):
    if WAYLAND:
        tool = _wayland_tool()
        return _wdo("type", "--", text, timeout=60) if tool == "wdotool" else run(["ydotool", "type", "--", text], 60) and "" if tool else \
            "typing on Wayland needs wdotool or ydotool"
    from pynput.keyboard import Controller
    Controller().type(text)
    return ""


def press_keys(keys):
    """Key chains like 'ctrl+l', 'Return', 'ctrl+a BackSpace'; '' when done, else the problem."""
    for chain in key_chains(keys):
        if WAYLAND:
            if _wayland_tool() != "wdotool":
                return "key presses on Wayland need wdotool"
            out = _wdo("key", "+".join(chain), timeout=40)
            if out:
                return out
            continue
        from pynput.keyboard import Controller
        kb, held = Controller(), []
        try:
            for name in chain:
                k = _pynput_key(name)
                kb.press(k)
                held.append(k)
        except ValueError as e:
            return str(e)
        finally:
            for k in reversed(held):
                kb.release(k)
    return ""


def scroll(amount):
    if WAYLAND:
        return _wdo("scroll", "--", 0, int(amount), timeout=40) if _wayland_tool() == "wdotool" else "scrolling on Wayland needs wdotool"
    from pynput.mouse import Controller
    Controller().scroll(0, -int(amount))
    return ""


def screen_size():
    if IS_WINDOWS or not WAYLAND:
        import mss
        with mss.mss() as m:
            return m.monitors[0]["width"], m.monitors[0]["height"]
    return None  # Wayland: taken from the screenshot instead


# ---------------------------------------------------------------- windows
def _kdo(*args):
    return run(["kdotool", *args])


def window_ids():
    if KDE and WAYLAND and have("kdotool"):
        return set(_kdo("search", ".").split())
    if WAYLAND:
        return set()
    import pywinctl
    return {str(w.getHandle()) for w in pywinctl.getAllWindows()}


def active_window():
    if KDE and WAYLAND and have("kdotool"):
        return _kdo("getactivewindow")
    if WAYLAND:
        return ""
    import pywinctl
    w = pywinctl.getActiveWindow()
    return str(w.getHandle()) if w else ""


def active_app():
    """The focused app's name, as the accessibility interface knows it."""
    if KDE and WAYLAND and have("kdotool"):
        return _kdo("getactivewindow", "getwindowclassname").split(".")[-1]
    if WAYLAND:
        return ""
    import pywinctl
    w = pywinctl.getActiveWindow()
    return (w.getAppName() or "").removesuffix(".exe") if w else ""


def active_window_context():
    """Provides foreground window metadata: app name, window title, and active file/URL hints."""
    try:
        app = active_app()
        title = ""
        if IS_WINDOWS:
            try:
                import ctypes
                u32 = ctypes.windll.user32
                hwnd = u32.GetForegroundWindow()
                if hwnd:
                    buf = ctypes.create_unicode_buffer(512)
                    u32.GetWindowTextW(hwnd, buf, 512)
                    title = buf.value.strip()
            except Exception:
                pass
        if not title:
            try:
                import pywinctl
                w = pywinctl.getActiveWindow()
                if w:
                    title = (w.title or "").strip()
                    if not app:
                        app = (w.getAppName() or "").removesuffix(".exe")
            except Exception:
                pass

        if not app and not title:
            return ""

        file_hint = ""
        if title:
            parts = [p.strip() for p in title.split(" - ")]
            if len(parts) >= 2 and ("." in parts[0] or "Code" in parts[-1] or "IntelliJ" in parts[-1]):
                file_hint = f" | Active File: {parts[0]}"

        return f"[Foreground App: {app or 'Desktop'}{file_hint} | Window: {title[:120]}]"
    except Exception:
        return ""


def list_windows():
    if KDE and WAYLAND and have("kdotool"):  # one call for all of them (each kdotool call costs ~0.3 s)
        out = _kdo("search", ".", "getwindowclassname", "%@", "getwindowname", "%@").splitlines()
        if len(out) % 2 == 0:
            n = len(out) // 2
            return [f"{app}: {title}" for app, title in zip(out[:n], out[n:])]
        return [f"{_kdo('getwindowclassname', wid)}: {_kdo('getwindowname', wid)}" for wid in _kdo("search", ".").split()]  # (a title with a line break)
    if WAYLAND:
        return ["(listing windows isn't possible on this Wayland desktop; look at the screen instead)"]
    import pywinctl
    return [f"{w.getAppName()}: {w.title}" for w in pywinctl.getAllWindows() if w.title]


def _find_windows(name):
    want = name.split(": ", 1)[-1].lower()
    if not want.strip():  # an empty name matches every window (close_window would close them all)
        return []
    import pywinctl
    return [w for w in pywinctl.getAllWindows() if want in w.title.lower() or want in (w.getAppName() or "").lower()]


def _kde_window(name, action):
    """kdotool's action on the first window matching name: '' when done, else the problem. (kdotool says nothing when no
    window matches, so the match's class name is printed first to tell.)"""
    if not name.split(": ", 1)[-1].strip():  # (an empty name matches every window)
        return "no window name given"
    # kdotool pastes the pattern into a KWin script as-is: a quote or backtick there breaks the script (a 5 s timeout
    # and an "Error:" line), so those match any character instead
    pattern = re.sub(r'["`]', ".", re.escape(name.split(": ", 1)[-1]))
    found = _kdo("search", pattern, "getwindowclassname", action)
    return "" if found and not found.startswith("Error") else f"no window matching {name}"


def focus_window(name, wid=None):
    """Bring a window to the front by (part of) its title or app name, or by id; '' when done, else the problem."""
    if KDE and WAYLAND and have("kdotool"):
        return _kdo("windowactivate", wid) if wid else _kde_window(name, "windowactivate")
    if WAYLAND:
        return "switching windows isn't possible on this Wayland desktop; use keyboard shortcuts (alt+tab)"
    import pywinctl
    found = [w for w in pywinctl.getAllWindows() if str(w.getHandle()) == wid] if wid else _find_windows(name)
    if not found:
        return f"no window matching {name}"
    found[0].activate()
    return ""


def close_window(name):
    if KDE and WAYLAND and have("kdotool"):
        return _kde_window(name, "windowclose")
    if WAYLAND:
        return "closing windows by name isn't possible on this Wayland desktop; use alt+F4 on the focused window"
    found = _find_windows(name)
    if not found:
        return f"no window matching {name}"
    for w in found:
        w.close()
    return ""


# ---------------------------------------------------------------- apps, links, the shell
def program_exists(command):
    """Whether a launch command's program can be found (Windows resolves more names itself, so it's always tried)."""
    words = [w for w in command.split() if w not in ("setsid", "-f", "nohup", "env", "exec") and "=" not in w]
    return IS_WINDOWS or not words or have(os.path.expanduser(words[0]))


def launch(command, env=None):
    """Start an app without waiting for it."""
    if IS_WINDOWS:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(f'start "" {command}', shell=True, creationflags=flags, env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["bash", "-lc", command], start_new_session=True, env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def open_target(target):
    """Open a web address or file with the default app."""
    if IS_WINDOWS:
        os.startfile(target)
    else:
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def shell(command, timeout=30):
    """Run a command (bash, or PowerShell on Windows); (exit code, output). Output goes to a file, not a pipe, so an app
    started in the background can't keep the call waiting."""
    args = (["powershell", "-NoProfile", "-NonInteractive", "-Command", command] if IS_WINDOWS else ["bash", "-lc", command])
    with tempfile.TemporaryFile() as log:
        r = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=timeout,
                           creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,
                           **({} if IS_WINDOWS else {"start_new_session": True}))
        log.seek(0)
        return r.returncode, log.read().decode(errors="replace").strip()


def keep_system_awake(enable: bool = True):
    """Prevents system sleep/standby while allowing display power save (Windows Away Mode)."""
    if IS_WINDOWS:
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ES_AWAYMODE_REQUIRED = 0x00000040
        try:
            if enable:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED)
            else:
                ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:
            pass


def similar_programs(name):
    """Installed programs and app-menu entries whose name contains name's first part ("brave-browser" -> brave...)."""
    want, found = os.path.basename(name).lower().split("-")[0], set()
    for d in dict.fromkeys(os.environ.get("PATH", "").split(os.pathsep)):
        if os.path.isdir(d):
            found |= {f for f in os.listdir(d) if want in f.lower()}
    entries = set()
    for apps in ("/usr/share/applications", os.path.expanduser("~/.local/share/applications")):
        if os.path.isdir(apps):
            entries |= {f"gtk-launch {f[:-8]}" for f in os.listdir(apps) if f.endswith(".desktop") and want in f.lower()}
    return (sorted(found, key=len) + sorted(entries, key=len))[:12]


CHROMIUM_BROWSERS = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave", "msedge", "chrome")


def chromium_based(program):
    """Whether a program is a Chromium browser or an Electron app (Discord, VS Code, Spotify...), following launcher
    scripts to what they start. On Linux those only show their controls to accessibility tools when started with
    --force-renderer-accessibility (Windows' UI Automation needs nothing)."""
    path = shutil.which(os.path.expanduser(program))
    if IS_WINDOWS or not path:
        return False
    if os.path.basename(path) in CHROMIUM_BROWSERS:
        return True
    for _ in range(3):  # e.g. a /usr/bin script that runs /usr/lib/app/app, which sits next to Chromium's resources.pak
        path = os.path.realpath(path)
        if os.path.exists(os.path.join(os.path.dirname(path), "resources.pak")):
            return True
        try:
            with open(path, "rb") as f:
                script = f.read(65536)
        except OSError:
            return False
        if not script.startswith(b"#!"):
            return False
        body = script.decode(errors="ignore").split("\n", 1)[-1]  # (not the #! line's interpreter)
        if re.search(r"(?i)\belectron", body):  # runs the system's Electron, or says it's one
            return True
        path = next((p for p in re.findall(r"(?<![\w$}])/[\w.+/-]+", body) if os.path.isfile(p) and os.access(p, os.X_OK)), None)
        if not path:
            return False
    return False


def headless_browser():
    """A Chromium-family browser for rendering JavaScript-heavy pages, or None."""
    for name in CHROMIUM_BROWSERS:
        if have(name):
            return shutil.which(name)
    if IS_WINDOWS:
        for path in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
            if os.path.exists(path):
                return path
    return None


# ---------------------------------------------------------------- notifications, media, stats, login
notifier = [None]  # set by the tray app: shows a balloon from the tray icon


def notify(title, text):
    if not IS_WINDOWS and have("notify-send"):
        subprocess.Popen(["notify-send", "-a", "Jarvis", "-i", os.path.join(HERE, "icon.svg"), title, text], stderr=subprocess.DEVNULL)
    elif notifier[0]:
        notifier[0](title, text)


def selected_text():
    """(the text selected right now, the clipboard): Linux has both; Windows has only the clipboard, so selected is ''."""
    if IS_WINDOWS:
        return "", run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"], 5)
    if WAYLAND and have("wl-paste"):
        get = lambda *flags: run(["wl-paste", "--no-newline", *flags], 3)
        return get("--primary"), get()
    if have("xclip"):
        get = lambda which: run(["xclip", "-o", "-selection", which], 3)
        return get("primary"), get("clipboard")
    return "", ""


def paste_text(text):
    """Puts text in the clipboard, presses ctrl+v, then puts back what the clipboard held: '' when done, else the
    problem; None where there's no clipboard tool (Windows, or Linux without wl-copy/xclip), so it's typed instead."""
    if WAYLAND and have("wl-copy"):
        copy, paste = ["wl-copy"], ["wl-paste", "--no-newline"]
    elif not IS_WINDOWS and have("xclip"):
        copy, paste = ["xclip", "-selection", "clipboard"], ["xclip", "-o", "-selection", "clipboard"]
    else:
        return None
    before = subprocess.run(paste, capture_output=True, timeout=3)  # (stdout only: an empty clipboard's error isn't text to keep)
    subprocess.run(copy, input=text.encode(), timeout=5)
    problem = press_keys("ctrl+v")
    time.sleep(0.5)  # (the app reads the clipboard after the key press)
    if before.returncode == 0 and before.stdout:
        subprocess.run(copy, input=before.stdout, timeout=5)
    return problem


_art_cache = {"key": None, "art": ""}


def _clean_windows_app_name(app_id):
    lower = app_id.lower()
    for m in ("spotify", "opera", "chrome", "brave", "edge", "firefox", "vlc", "applemusic", "tidal", "deezer"):
        if m in lower:
            return m.capitalize() if m != "edge" else "Edge"
    part = app_id.split("!")[-1].split(".exe")[0].split(".")[-1]
    return part.strip().title() or "Media"


def _windows_now_playing():
    try:
        import winsdk.windows.media.control as wmc
        import winsdk.windows.storage.streams as streams
    except ImportError:
        return {}

    async def _fetch():
        try:
            mgr = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
            sessions = list(mgr.get_sessions())
            if not sessions:
                return {}
            music_apps = ("spotify", "applemusic", "tidal", "deezer", "foobar", "musicbee")
            scored = []
            for s in sessions:
                pb = s.get_playback_info()
                st = pb.playback_status if pb else 0
                app_id = s.source_app_user_model_id or ""
                is_music = any(m in app_id.lower() for m in music_apps)
                if st == 4:
                    score = 100 if is_music else 80
                elif st == 5:
                    score = 50 if is_music else 20
                else:
                    score = 0
                scored.append((score, s, st, app_id))
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_session, pb_status, app_id = scored[0]
            if best_score == 0 and not (best_session and app_id):
                return {}
            props = await best_session.try_get_media_properties_async()
            title = props.title or ""
            artist = props.artist or props.album_artist or ""
            if not title and not artist:
                return {}
            status = "Playing" if pb_status == 4 else "Paused" if pb_status == 5 else "Stopped"
            art_key = f"{title}:{artist}"
            if _art_cache.get("key") == art_key and _art_cache.get("art"):
                art = _art_cache["art"]
            else:
                art = ""
                if props.thumbnail:
                    try:
                        stream = await props.thumbnail.open_read_async()
                        if stream and stream.size > 0:
                            reader = streams.DataReader(stream)
                            await reader.load_async(stream.size)
                            buf = bytearray(stream.size)
                            reader.read_bytes(buf)
                            import base64
                            art = "data:image/jpeg;base64," + base64.b64encode(buf).decode()
                            _art_cache["key"] = art_key
                            _art_cache["art"] = art
                    except Exception:
                        pass
            tl = best_session.get_timeline_properties()
            length = tl.end_time.total_seconds() if tl and hasattr(tl.end_time, "total_seconds") else 0
            return {
                "player": app_id,
                "app": _clean_windows_app_name(app_id),
                "status": status,
                "title": title,
                "artist": artist,
                "art": art,
                "length": length
            }
        except Exception:
            return {}

    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                return pool.submit(asyncio.run, _fetch()).result()
        return asyncio.run(_fetch())
    except Exception:
        return {}


def _windows_media(action):
    try:
        import winsdk.windows.media.control as wmc
    except ImportError:
        return False

    async def _act():
        try:
            mgr = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
            sessions = list(mgr.get_sessions())
            if not sessions:
                return False
            music_apps = ("spotify", "applemusic", "tidal", "deezer", "foobar", "musicbee")
            scored = []
            for s in sessions:
                pb = s.get_playback_info()
                st = pb.playback_status if pb else 0
                app_id = s.source_app_user_model_id or ""
                is_music = any(m in app_id.lower() for m in music_apps)
                if st == 4:
                    score = 100 if is_music else 80
                elif st == 5:
                    score = 50 if is_music else 20
                else:
                    score = 0
                scored.append((score, s))
            scored.sort(key=lambda x: x[0], reverse=True)
            target = scored[0][1]
            if action == "PlayPause":
                await target.try_toggle_play_pause_async()
                return True
            elif action == "Next":
                await target.try_skip_next_async()
                return True
            elif action == "Previous":
                await target.try_skip_previous_async()
                return True
        except Exception:
            return False
        return False

    try:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                return pool.submit(asyncio.run, _act()).result()
        return asyncio.run(_act())
    except Exception:
        return False


def now_playing():
    """The media player that's playing (or the first one): {player, app, status, title, artist, art}."""
    if IS_WINDOWS:
        return _windows_now_playing()
    if not have("busctl"):
        return {}
    out = run(["busctl", "--user", "--json=short", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames"], 5)
    try:
        players = [n for n in json.loads(out)["data"][0] if n.startswith("org.mpris.MediaPlayer2.")]
    except (ValueError, KeyError, IndexError):
        return {}
    best = {}
    for name in players:
        def prop(p):
            try:
                return json.loads(run(["busctl", "--user", "--json=short", "get-property", name, "/org/mpris/MediaPlayer2",
                                       "org.mpris.MediaPlayer2.Player", p], 5))["data"]
            except ValueError:
                return None
        status, meta = prop("PlaybackStatus"), prop("Metadata") or {}
        get = lambda k: (meta.get(k) or {}).get("data")
        info = {"player": name, "app": name.split(".")[-1].split("_")[0].title(), "status": status, "title": get("xesam:title") or "",
                "artist": ", ".join(get("xesam:artist") or []), "art": get("mpris:artUrl") or "",
                "length": (get("mpris:length") or 0) / 1e6}
        if not best or status == "Playing":
            best = info
        if status == "Playing":
            break
    return best


def media(action):
    """PlayPause, Next or Previous for the current player (media keys where MPRIS isn't available)."""
    if IS_WINDOWS:
        if _windows_media(action):
            return
        press_keys({"PlayPause": "XF86AudioPlay", "Next": "XF86AudioNext", "Previous": "XF86AudioPrev"}[action])
        return
    player = now_playing().get("player")
    if player:
        run(["busctl", "--user", "call", player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", action], 5)
    else:
        press_keys({"PlayPause": "XF86AudioPlay", "Next": "XF86AudioNext", "Previous": "XF86AudioPrev"}[action])


def system_stats():
    import psutil
    mem, disk = psutil.virtual_memory(), psutil.disk_usage(os.path.expanduser("~"))
    stats = {"cpu": round(psutil.cpu_percent(interval=None), 1), "mem_used": mem.total - mem.available, "mem_total": mem.total,
            "disk_used": disk.used, "disk_total": disk.total, "uptime": time.time() - psutil.boot_time()}
    try:
        import hardware
        gpu = hardware.get_gpu_info()
        if gpu.get("detected"):
            stats["gpu_name"] = gpu.get("name", "")
            stats["gpu_vendor"] = gpu.get("vendor", "")
            stats["gpu_vram_total"] = gpu.get("vram_total_mb", 0)
            stats["gpu_vram_used"] = gpu.get("vram_total_mb", 0) - gpu.get("vram_free_mb", 0)
    except Exception:
        pass
    return stats


def set_autostart(enabled, command):
    """Start Jarvis at login: a .desktop file in ~/.config/autostart, or a shortcut script in the Windows Startup folder."""
    if IS_WINDOWS:
        path = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup", "Jarvis.bat")
        body = f'@echo off\r\nstart "" {command}\r\n'
    else:
        path = os.path.expanduser("~/.config/autostart/jarvis.desktop")
        body = (f"[Desktop Entry]\nType=Application\nName=Jarvis\nExec={command}\nIcon={os.path.join(HERE, 'icon.svg')}\n"
                "X-KDE-autostart-phase=2\nTerminal=false\n")
    if enabled:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(body)
    elif os.path.exists(path):
        os.remove(path)


# ---------------------------------------------------------------- pressing app controls by name (accessibility)
class LinuxAccessibility:
    """AT-SPI through atspi_helper.py, which runs under the system Python (it needs the gi bindings)."""

    def __init__(self):
        self.proc, self.lock = None, threading.Lock()

    def ask(self, cmd, timeout=20):
        import select
        python = "/usr/bin/python3"
        if not os.path.exists(python):
            return {"error": "pressing controls by name needs the system Python with gi (python-gobject) for AT-SPI"}
        with self.lock:
            if not self.proc or self.proc.poll() is not None:
                self.proc = subprocess.Popen([python, os.path.join(HERE, "atspi_helper.py")], text=True,
                                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.proc.stdin.write(json.dumps(cmd) + "\n")
            self.proc.stdin.flush()
            if not select.select([self.proc.stdout], [], [], timeout)[0]:
                self.proc.kill()  # stuck on an unresponsive app: start fresh next time
                return {"error": "the app didn't answer the accessibility request"}
            return json.loads(self.proc.stdout.readline() or '{"error": "accessibility helper exited"}')


class WindowsAccessibility:
    """UI Automation through pywinauto: the same commands as the Linux helper (controls, press, set_text)."""

    INTERACTIVE = {"Button", "CheckBox", "RadioButton", "MenuItem", "Edit", "ComboBox", "Hyperlink", "ListItem", "TabItem",
                   "TreeItem", "Spinner", "Slider", "Document", "SplitButton"}

    def ask(self, cmd, timeout=20):
        try:
            from pywinauto import Desktop
        except ImportError:
            return {"error": "pressing controls by name needs pywinauto (pip install pywinauto)"}
        want = cmd["app"].lower().removesuffix(".exe").split(".")[-1]
        end = time.time() + float(cmd.get("wait", 0))
        while True:
            wins = [w for w in Desktop(backend="uia").windows() if want in (w.window_text() or "").lower()
                    or want in (getattr(w.element_info, "name", "") or "").lower()
                    or want in _process_name(w.element_info.process_id)]
            if wins or time.time() >= end:
                break
            time.sleep(0.2)
        if not wins:
            return {"error": f"no window for '{cmd['app']}'"}
        depth = 4 if any(b in want for b in ("chrome", "msedge", "brave", "firefox", "discord", "electron")) else None
        kwargs = {"depth": depth} if depth else {}
        controls = [c for c in wins[0].descendants(**kwargs) if c.element_info.control_type in self.INTERACTIVE and c.window_text()]
        names = [f"{c.element_info.control_type}: {c.window_text()}" for c in controls]

        def lookup(name):
            low = name.lower().strip()
            return next((c for c in controls if c.window_text().lower() == low), None) or \
                next((c for c in controls if low in c.window_text().lower()), None)
        if cmd["cmd"] == "controls":
            return {"app": wins[0].window_text(), "controls": names[:400]}
        if cmd["cmd"] == "press":
            pressed = []
            for name in cmd["names"]:
                c = lookup(name)
                if c is None:
                    return {"error": f"no control named '{name}'", "pressed": pressed, "available": names[:200]}
                try:
                    c.invoke()
                except Exception:
                    c.click_input()
                pressed.append(name)
                time.sleep(0.1)
            return {"pressed": pressed}
        if cmd["cmd"] == "set_text":
            c = lookup(cmd["field"]) if cmd.get("field") else next((x for x in controls if x.element_info.control_type == "Edit"), None)
            if c is None:
                return {"error": f"no text field '{cmd.get('field', '')}'", "available": names[:200]}
            c.set_edit_text(cmd["text"])
            return {"set": cmd.get("field") or "first text field"}
        return {"error": f"unknown command {cmd['cmd']}"}


def _process_name(pid):
    try:
        import psutil
        return psutil.Process(pid).name().lower()
    except Exception:
        return ""


accessibility = WindowsAccessibility() if IS_WINDOWS else LinuxAccessibility()


# ---------------------------------------------------------------- audio ducking & device switching
_ducked_sessions = {}
_duck_lock = threading.Lock()


def duck_media(duck=True):
    """Lower volume of playing media/apps by ~75% while speaking/listening, or restore it."""
    if not IS_WINDOWS:
        return
    def _run():
        with _duck_lock:
            try:
                import comtypes
                comtypes.CoInitialize()
                from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
                my_pid = os.getpid()
                if duck:
                    sessions = AudioUtilities.GetAllSessions()
                    for s in sessions:
                        if s.Process and s.Process.pid != my_pid and s.Process.name().lower() not in ("python.exe", "pythonw.exe", "audiodg.exe"):
                            try:
                                v = s._ctl.QueryInterface(ISimpleAudioVolume)
                                cur = v.GetMasterVolume()
                                if s.Process.pid not in _ducked_sessions and cur > 0.1:
                                    _ducked_sessions[s.Process.pid] = (v, cur)
                                    v.SetMasterVolume(max(0.05, cur * 0.25), None)
                            except Exception:
                                pass
                else:
                    for pid, (v, orig) in list(_ducked_sessions.items()):
                        try:
                            v.SetMasterVolume(orig, None)
                        except Exception:
                            pass
                    _ducked_sessions.clear()
            except Exception:
                pass
    threading.Thread(target=_run, daemon=True).start()


def list_audio_devices():
    """List active audio output (playback) devices."""
    if not IS_WINDOWS:
        return []
    try:
        import comtypes
        comtypes.CoInitialize()
        from pycaw.pycaw import AudioUtilities, AudioDeviceState
        devices = [d for d in AudioUtilities.GetAllDevices() if d.state == AudioDeviceState.Active and "{0.0.0." in d.id]
        curr_id = AudioUtilities.GetSpeakers().id
        return [{"name": d.FriendlyName, "id": d.id, "default": d.id == curr_id} for d in devices]
    except Exception as e:
        return [{"error": str(e)}]


def switch_audio_device(name=""):
    """Switch default audio playback device to the one matching `name` (e.g. 'headphones', 'speakers')."""
    if not IS_WINDOWS:
        return {"error": "audio device switching is only supported on Windows"}
    try:
        import comtypes, comtypes.client
        from comtypes import GUID, COMMETHOD, HRESULT
        from ctypes import c_wchar_p, c_int, c_void_p
        from pycaw.pycaw import AudioUtilities, AudioDeviceState
        comtypes.CoInitialize()

        class IPolicyConfig(comtypes.IUnknown):
            _iid_ = GUID('{f8679f50-850a-41cf-9c72-430f290290c8}')
            _methods_ = [
                COMMETHOD([], HRESULT, 'GetMixFormat', (['in'], c_wchar_p, 'devId'), (['out'], c_void_p, 'pFormat')),
                COMMETHOD([], HRESULT, 'GetDeviceFormat', (['in'], c_wchar_p, 'devId'), (['in'], c_int, 'bDefault'), (['out'], c_void_p, 'pFormat')),
                COMMETHOD([], HRESULT, 'ResetDeviceFormat', (['in'], c_wchar_p, 'devId')),
                COMMETHOD([], HRESULT, 'SetDeviceFormat', (['in'], c_wchar_p, 'devId'), (['in'], c_void_p, 'p1'), (['in'], c_void_p, 'p2')),
                COMMETHOD([], HRESULT, 'GetProcessingPeriod', (['in'], c_wchar_p, 'devId'), (['in'], c_int, 'bDefault'), (['out'], c_void_p, 'p1'), (['out'], c_void_p, 'p2')),
                COMMETHOD([], HRESULT, 'SetProcessingPeriod', (['in'], c_wchar_p, 'devId'), (['in'], c_void_p, 'p1')),
                COMMETHOD([], HRESULT, 'GetShareMode', (['in'], c_wchar_p, 'devId'), (['out'], c_void_p, 'pMode')),
                COMMETHOD([], HRESULT, 'SetShareMode', (['in'], c_wchar_p, 'devId'), (['in'], c_void_p, 'mode')),
                COMMETHOD([], HRESULT, 'GetPropertyValue', (['in'], c_wchar_p, 'devId'), (['in'], c_void_p, 'key'), (['out'], c_void_p, 'pv')),
                COMMETHOD([], HRESULT, 'SetPropertyValue', (['in'], c_wchar_p, 'devId'), (['in'], c_void_p, 'key'), (['in'], c_void_p, 'pv')),
                COMMETHOD([], HRESULT, 'SetDefaultEndpoint', (['in'], c_wchar_p, 'devId'), (['in'], c_int, 'role')),
                COMMETHOD([], HRESULT, 'SetEndpointVisibility', (['in'], c_wchar_p, 'devId'), (['in'], c_int, 'bVisible')),
            ]

        devices = [d for d in AudioUtilities.GetAllDevices() if d.state == AudioDeviceState.Active and "{0.0.0." in d.id]
        curr_id = AudioUtilities.GetSpeakers().id
        if not name or name.strip().lower() == "list":
            return {"devices": [{"name": d.FriendlyName, "default": d.id == curr_id} for d in devices]}
        target = name.strip().lower()
        matched = next((d for d in devices if target in d.FriendlyName.lower()), None)
        if not matched:
            names = [d.FriendlyName for d in devices]
            return {"error": f"No audio device matching '{name}'. Available: {', '.join(names)}"}
        policy = comtypes.client.CreateObject(GUID('{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}'), interface=IPolicyConfig)
        for role in (0, 1, 2):
            policy.SetDefaultEndpoint(matched.id, role)
        return {"result": f"Default audio switched to {matched.FriendlyName}"}
    except Exception as e:
        return {"error": f"Failed to switch audio device: {e}"}

