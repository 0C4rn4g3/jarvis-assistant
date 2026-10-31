"""Jarvis in its own phone app, through your private relay (relay/worker.js, on your own Cloudflare account). The PC and
the phone both dial out to the relay, so nothing on the PC is open to the internet, and everything between them is
end-to-end encrypted: the relay only ever forwards ciphertext. Pairing is a QR code in Settings carrying the relay's
address, this PC's id and public key (what the phone trusts) and a one-time secret; the phone trades the secret for
its own token, which every later connection shows.

The handshake: the phone sends a fresh P-256 key; the PC answers with its own fresh key and a short sealed proof.
Both sides derive one AES-256-GCM key each way from ECDH(PC's long-term key, phone's fresh key) + ECDH(both fresh
keys), so only the PC holding its private key can answer, and a recorded session can't be read later. Frames are
counted, never sent twice, in order (the relay keeps them in order), and the counter is the nonce."""
import asyncio, base64, hashlib, hmac, json, os, secrets, socket, threading, time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import store
from remote import REMOTE_NOTE

STATE_FILE = os.path.join(store.DATA, "phone.json")  # {"relay": url, "sign"/"enc": PEM keys, "devices": {id: {...}}}
PAIR_SECONDS = 600  # how long a pairing QR code works
HELLO, WELCOME, DATA = 1, 2, 3  # the first byte of every frame between the phone and the PC
INFO = b"jarvis-relay-v1"


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def raw(public_key):
    return public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def point(data):
    return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes(data))


def nonce(n):
    return n.to_bytes(12, "big")


def token_hash(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def get_active_thread_context() -> dict:
    """Gathers desktop/Unity state, active game project, and recent conversation so phone can pick up mid-sentence."""
    import system
    app = system.active_app() or "Desktop"
    is_gaming = False
    try:
        import hardware
        is_gaming = hardware.is_gaming_active()
    except Exception:
        pass

    game_info = {}
    try:
        import game_design
        game_info = game_design.get_active_project() or {}
    except Exception:
        pass

    recent_dialogue = []
    try:
        import jarvis
        for m in reversed(jarvis.sessions.messages):
            if m.get("who") in ("you", "jarvis") and m.get("text"):
                who_label = "User" if m["who"] == "you" else "Jarvis"
                recent_dialogue.insert(0, f"{who_label}: {m['text']}")
                if len(recent_dialogue) >= 6:
                    break
    except Exception:
        pass

    clipboard_snippet = ""
    try:
        import clipboard_daemon
        entries = clipboard_daemon.list_clipboard_history(limit=1)
        if entries:
            clipboard_snippet = entries[0]["text"][:160]
    except Exception:
        pass

    return {
        "ok": True,
        "active_app": app,
        "is_gaming": is_gaming,
        "active_game": game_info.get("name", "Unknown Game"),
        "game_engine": game_info.get("engine", "Unity"),
        "game_genre": game_info.get("genre", ""),
        "game_summary": game_info.get("summary", ""),
        "recent_thread": recent_dialogue,
        "clipboard_snippet": clipboard_snippet,
        "synced_at": time.time()
    }


class Channel:
    """One encrypted conversation: a key and a frame counter each way."""

    def __init__(self, send_key, receive_key, sent=0, got=0):
        self.out, self.into, self.sent, self.got = AESGCM(send_key), AESGCM(receive_key), sent, got

    def seal(self, message):
        frame = bytes([DATA]) + self.out.encrypt(nonce(self.sent), json.dumps(message).encode(), None)
        self.sent += 1
        return frame

    def open(self, frame):
        if frame[:1] != bytes([DATA]):
            raise ValueError("not a data frame")
        message = json.loads(self.into.decrypt(nonce(self.got), bytes(frame[1:]), None))
        self.got += 1
        return message


def derive(long_term, fresh, phone_key, pc_key):
    keys = HKDF(hashes.SHA256(), 64, phone_key + pc_key, INFO).derive(long_term + fresh)
    return keys[:32], keys[32:]  # (phone to PC, PC to phone)


def accept(enc_key, hello):
    """The PC's side of the handshake: (the welcome frame to send back, the Channel)."""
    if len(hello) != 66 or hello[0] != HELLO:
        raise ValueError("not a hello")
    phone_key, fresh = bytes(hello[1:]), ec.generate_private_key(ec.SECP256R1())
    to_pc, to_phone = derive(enc_key.exchange(ec.ECDH(), point(phone_key)), fresh.exchange(ec.ECDH(), point(phone_key)),
                             phone_key, raw(fresh.public_key()))
    return bytes([WELCOME]) + raw(fresh.public_key()) + AESGCM(to_phone).encrypt(nonce(0), b"jarvis", None), \
        Channel(to_phone, to_pc, sent=1)


def connect(pc_key):
    """The phone's side, as the app does it in Kotlin (tests use this one): (hello frame, finish(welcome) -> Channel)."""
    fresh = ec.generate_private_key(ec.SECP256R1())

    def finish(welcome):
        if len(welcome) < 66 or welcome[0] != WELCOME:
            raise ValueError("not a welcome")
        to_pc, to_phone = derive(fresh.exchange(ec.ECDH(), point(pc_key)), fresh.exchange(ec.ECDH(), point(welcome[1:66])),
                                 raw(fresh.public_key()), bytes(welcome[1:66]))
        if AESGCM(to_phone).decrypt(nonce(0), bytes(welcome[66:]), None) != b"jarvis":
            raise ValueError("the PC didn't prove who it is")
        return Channel(to_pc, to_phone, got=1)
    return bytes([HELLO]) + raw(fresh.public_key()), finish


class PhoneLink:
    def __init__(self, brain, notify=print, emitter=None):
        self.brain, self.notify, self.emitter = brain, notify, emitter
        self.state = store.read_json(STATE_FILE, {})
        if not self.state.get("sign"):
            pem = lambda: ec.generate_private_key(ec.SECP256R1()).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
            self.state.update(sign=pem(), enc=pem(), devices={})
            self.save()
        load = lambda name: serialization.load_pem_private_key(self.state[name].encode(), None)
        self.sign_key, self.enc_key = load("sign"), load("enc")
        self.id = b64url(hashlib.sha256(raw(self.sign_key.public_key())).digest())  # what the relay knows this PC by
        self.pairing = None  # {"secret": the QR code's one-time secret, "until": when it stops working}
        self.error, self.connected = "", False
        self.loop = self.ws = self.changed = None
        self.phones = {}  # relay connection id -> {"channel": Channel, "device": paired device id or None, "tries": n}
        self.pending = {}  # device -> replies it hasn't received yet (the app was closed when they came)

    def save(self):
        store.write_json(STATE_FILE, self.state, private=True)

    # ---- the Settings page
    def status(self):
        pairing = None
        if self.pairing and time.time() < self.pairing["until"]:
            import segno
            link = self.pair_link()
            pairing = {"link": link, "qr": segno.make(link, error="m").png_data_uri(scale=6, border=2)}
        return {"relay": self.state.get("relay", ""), "connected": self.connected, "error": self.error, "pairing": pairing,
                "devices": [{"id": d, "name": v["name"]} for d, v in self.state["devices"].items()]}

    def set_relay(self, url):
        url = url.strip().rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        if url and not url.startswith(("wss://", "ws://")):
            raise ValueError("paste your relay's address, like https://jarvis-relay.you.workers.dev")
        self.state["relay"], self.error, self.connected = url, "", False
        self.save()
        self._kick()

    def start_pairing(self):
        if not self.state.get("relay"):
            raise ValueError("add your relay's address first")
        self.pairing = {"secret": b64url(secrets.token_bytes(16)), "until": time.time() + PAIR_SECONDS}
        return self.status()

    def pair_link(self):
        payload = {"v": 1, "r": self.state["relay"], "s": self.id, "k": b64url(raw(self.enc_key.public_key())),
                   "p": self.pairing["secret"]}
        return "jarvis://pair#" + b64url(json.dumps(payload, separators=(",", ":")).encode())  # (a fragment: never sent on)

    def unpair(self, device):
        self.state["devices"].pop(device, None)
        self.pending.pop(device, None)
        self.save()
        for c, phone in list(self.phones.items()):
            if phone["device"] == device:
                self._call(self._drop(c))

    # ---- the connection to the relay
    def run(self):
        asyncio.run(self._main())

    async def _main(self):
        import websockets
        self.loop, self.changed, wait = asyncio.get_running_loop(), asyncio.Event(), 2
        while True:
            relay = self.state.get("relay")
            if relay:
                started = time.time()
                try:
                    async with websockets.connect(self.host_url(relay), max_size=2 ** 20, ping_interval=20, open_timeout=15) as ws:
                        self.ws, self.connected, self.error, self.phones = ws, True, "", {}
                        async for frame in ws:
                            await self._frame(frame)
                except Exception as e:
                    self.error = "another Jarvis with this identity took over" if getattr(getattr(e, "rcvd", None), "code", 0) == 4001 \
                        else f"can't reach the relay ({str(e)[:120] or type(e).__name__})"
                    print(f"[phone] {self.error}", flush=True)
                self.ws, self.connected, self.phones = None, False, {}
                wait = 2 if time.time() - started > 60 else min(wait * 2, 60)
            try:
                await asyncio.wait_for(self.changed.wait(), wait if relay else None)
            except asyncio.TimeoutError:
                pass
            self.changed.clear()

    def host_url(self, relay):
        ts = str(int(time.time() * 1000))
        r, s = decode_dss_signature(self.sign_key.sign(f"jarvis-relay:{self.id}:{ts}".encode(), ec.ECDSA(hashes.SHA256())))
        sig = b64url(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return f"{relay}/host?id={self.id}&pub={b64url(raw(self.sign_key.public_key()))}&ts={ts}&sig={sig}"

    def _kick(self):
        """Reconnect with the new settings."""
        if self.loop:
            self.loop.call_soon_threadsafe(self.changed.set)
            if self.ws:
                self._call(self.ws.close())

    def _call(self, coro):
        if self.loop:
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            coro.close()

    async def _frame(self, frame):
        if isinstance(frame, str):  # the relay: a phone came or went
            m = json.loads(frame)
            if m.get("t") in ("open", "close"):
                self.phones.pop(m.get("c"), None)
            return
        c, data = frame[:36].decode(errors="replace"), frame[36:]
        phone = self.phones.setdefault(c, {"channel": None, "device": None, "tries": 0})
        try:
            if data[:1] == bytes([HELLO]):  # (a new handshake starts the conversation over)
                welcome, phone["channel"] = accept(self.enc_key, data)
                phone["device"] = None
                return await self.ws.send(c.encode() + welcome)
            message = phone["channel"].open(data)
        except Exception:  # not from a phone that did the handshake: it gets nothing
            return await self._drop(c)
        await self._handle(c, phone, message)

    async def _send(self, c, message):
        phone = self.phones.get(c)
        if phone and phone["channel"] and self.ws:
            await self.ws.send(c.encode() + phone["channel"].seal(message))

    async def _drop(self, c):
        self.phones.pop(c, None)
        if self.ws:
            await self.ws.send(json.dumps({"t": "close", "c": c}))

    async def _refuse(self, c, phone, error, unpaired=False):
        phone["tries"] += 1  # (five wrong secrets or tokens and that connection is cut: no guessing)
        await self._send(c, {"op": "error", "error": error, "unpaired": unpaired})
        if phone["tries"] >= 5:
            await self._drop(c)

    async def _handle(self, c, phone, m):
        op, devices = m.get("op"), self.state["devices"]
        if op == "pair":
            p = self.pairing
            if not (p and time.time() < p["until"] and hmac.compare_digest(str(m.get("secret", "")), p["secret"])):
                return await self._refuse(c, phone, "That pairing code has expired: show a new one in Jarvis's Settings.")
            self.pairing, token, device = None, secrets.token_urlsafe(32), secrets.token_hex(8)
            devices[device] = {"name": str(m.get("name") or "Phone")[:60], "hash": token_hash(token), "paired": time.time()}
            self.save()
            phone["device"] = device
            self.notify(f"📱 Paired with {devices[device]['name']}: the Jarvis app reaches this PC now.")
            return await self._send(c, {"op": "paired", "token": token, "name": socket.gethostname()})
        if op == "hello":
            device = next((d for d, v in devices.items() if hmac.compare_digest(v["hash"], token_hash(m.get("token", "")))), None)
            if not device:
                return await self._refuse(c, phone, "This phone isn't paired with Jarvis any more: pair it again.", unpaired=True)
            phone["device"] = device
            await self._send(c, {"op": "ready", "name": socket.gethostname(), "busy": self.brain.ask_lock.locked()})
            for reply in self.pending.pop(device, []):
                await self._send(c, reply)
            return
        if not phone["device"] or phone["device"] not in devices:
            return await self._refuse(c, phone, "This phone isn't paired with Jarvis any more: pair it again.", unpaired=True)
        if op == "ask" and str(m.get("text", "")).strip():
            text = str(m["text"]).strip()
            self.notify(f"📱 From your phone: {text}")
            await self._send(c, {"op": "working", "id": m.get("id"), "queued": self.brain.ask_lock.locked()})
            threading.Thread(target=self._task, args=(phone["device"], m.get("id"), text), daemon=True).start()
        elif op == "stop":
            self.brain.interrupt()
            await self._send(c, {"op": "stopped"})
        elif op == "clipboard_push":
            clip_text = str(m.get("text", "")).strip()
            if clip_text:
                try:
                    import clipboard_daemon
                    clipboard_daemon.record_clipboard_entry(clip_text, app_source="PhoneLink")
                    import win32clipboard, win32con
                    win32clipboard.OpenClipboard()
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardText(clip_text, win32con.CF_UNICODETEXT)
                    win32clipboard.CloseClipboard()
                    self.notify(f"📋 Synced from Phone: {clip_text[:40]}...")
                except Exception as e:
                    print(f"[phone] clipboard_push failed: {e}", flush=True)
            return await self._send(c, {"op": "clipboard_ack"})
        elif op == "clipboard_pull":
            import clipboard_daemon
            entries = clipboard_daemon.list_clipboard_history(limit=1)
            text = entries[0]["text"] if entries else ""
            return await self._send(c, {"op": "clipboard_sync", "text": text})
        elif op == "continue_session":
            curr = self.brain.sessions.current if hasattr(self.brain, "sessions") else {}
            return await self._send(c, {"op": "session_handoff", "conversation": curr})
        elif op == "get_today":
            import system, store, hardware, lead_hunter, jev
            media = system.now_playing() or {}
            reminders = store.reminders()
            stats = system.system_stats() if hasattr(system, "system_stats") else {}
            vram = hardware.arbitrate_vram()
            checks_stamp = os.path.join(store.DATA, "checks.json")
            stamp = store.read_json(checks_stamp, {}) if hasattr(store, "read_json") else {}
            jobs = {"text": stamp.get("latest", ""), "time": stamp.get("time", "")}
            raw_leads = lead_hunter.get_saved_leads()[:15]
            leads_data = [{
                "name": l.get("name", ""),
                "url": l.get("url", ""),
                "maps_url": l.get("maps_url", ""),
                "score": l.get("traction_score", 0),
                "issues": l.get("issues", [])[:2],
                "phone": l.get("phone", "")
            } for l in raw_leads]
            today_data = {
                "op": "today_sync",
                "thread_context": get_active_thread_context(),
                "media": media,
                "reminders": [{
                    "text": r.get("text", ""),
                    "at": r.get("at", 0),
                    "when": time.strftime("%H:%M", time.localtime(r.get("at", time.time())))
                } for r in reminders[:5]],
                "stats": {
                    "cpu": stats.get("cpu", 0),
                    "ram_used_gb": round(stats.get("ram_used", 0) / 1073741824, 1),
                    "ram_total_gb": round(stats.get("ram_total", 0) / 1073741824, 1),
                    "gaming": vram.get("gaming_active", False)
                },
                "jobs": jobs,
                "leads": leads_data,
                "jev": jev.status(),
                "subagents": (lambda: (__import__("subagents").get_subagent_manager().get_status_summary()))()
            }
            return await self._send(c, today_data)
        elif op == "scan_leads":
            import lead_hunter
            niche = str(m.get("niche", "dental clinic")).strip()
            location = str(m.get("location", "")).strip()
            def run_scan():
                res = lead_hunter.scan_leads(niche=niche, location=location, limit=15, send_phone=True)
                raw_leads = res.get("leads", [])
                leads_data = [{
                    "name": l.get("name", ""),
                    "url": l.get("url", ""),
                    "maps_url": l.get("maps_url", ""),
                    "score": l.get("traction_score", 0),
                    "issues": l.get("issues", [])[:2],
                    "phone": l.get("phone", "")
                } for l in raw_leads]
                self._call(self._send(c, {"op": "today_sync", "leads": leads_data}))
            threading.Thread(target=run_scan, daemon=True).start()
            return await self._send(c, {"op": "working", "queued": False})
        elif op == "media_action":
            import system
            action = m.get("action", "PlayPause")
            try:
                system.media(action)
            except Exception:
                pass
            media = system.now_playing() or {}
            return await self._send(c, {"op": "today_sync", "media": media})
        elif op == "geofence_trigger":
            event = str(m.get("event", "enter")).lower()
            if event in ("enter", "near_home", "home"):
                self.notify("📍 Phone entered Home Geofence: Welcome home!")
                system.keep_system_awake(False)
                try:
                    import jarvis
                    jarvis.notch_line[:] = ["📍 Phone near home: Session active", time.time()]
                except Exception:
                    pass
                return await self._send(c, {"op": "geofence_ack", "action": "home_active", "status": "PC Awake"})
            elif event in ("exit", "leaving", "away"):
                if store.settings().get("keep_awake_when_away", True):
                    system.keep_system_awake(True)
                if store.settings().get("lock_on_away", False) and system.IS_WINDOWS:
                    import ctypes
                    try:
                        ctypes.windll.user32.LockWorkStation()
                    except Exception:
                        pass
                import operators
                op_count = len(operators.get_operator_manager().list_operators())
                self.notify("📍 Away from Home: PC awake & ready for remote phone access.")
                try:
                    import jarvis
                    jarvis.notch_line[:] = ["📱 Remote Phone Active: Standby & Listening", time.time()]
                except Exception:
                    pass
                return await self._send(c, {
                    "op": "geofence_ack",
                    "action": "remote_active",
                    "status": f"PC awake & ready for phone control. {op_count} operators running."
                })
        elif op == "spawn_subagent":
            import subagents
            task = str(m.get("task", "")).strip()
            cat = str(m.get("category", "general")).strip()
            if not task:
                return await self._send(c, {"op": "error", "message": "task is required"})
            sub = subagents.get_subagent_manager(brain=self.brain).spawn(task, category=cat, brain=self.brain)
            return await self._send(c, {"op": "subagent_spawned", "id": sub.id, "task": sub.task, "category": sub.category})
        elif op == "cancel_subagent":
            import subagents
            sub_id = str(m.get("id", "")).strip()
            ok = subagents.get_subagent_manager().cancel(sub_id)
            return await self._send(c, {"op": "subagent_cancelled", "id": sub_id, "ok": ok})
        elif op == "list_subagents":
            import subagents
            return await self._send(c, {"op": "subagents_list", "subagents": subagents.get_subagent_manager().list_subagents()})
        elif op == "screen_peek":
            try:
                jpeg = system.screen_peek_jpeg()
                if jpeg:
                    b64_frame = base64.b64encode(jpeg).decode()
                    return await self._send(c, {
                        "op": "screen_frame",
                        "frame": b64_frame,
                        "timestamp": time.time()
                    })
            except Exception as e:
                return await self._send(c, {"op": "screen_frame", "error": str(e)})
        elif op == "thread_context":
            return await self._send(c, {
                "op": "thread_context",
                "context": get_active_thread_context()
            })
        elif op == "camera_scan":
            import camera_bridge
            img_b64 = str(m.get("image", "")).strip()
            prompt = str(m.get("prompt", "")).strip()
            mode = str(m.get("mode", "auto")).strip()
            req_id = m.get("id")
            if not img_b64:
                return await self._send(c, {"op": "error", "error": "image is required"})
            await self._send(c, {"op": "working", "id": req_id, "queued": False})

            def _process():
                try:
                    emitter_fn = self.emitter or (lambda k, **d: self.notify(d.get("text", "")))
                    res = camera_bridge.process_camera_scan(
                        img_b64, prompt=prompt, mode=mode,
                        brain=self.brain, emitter=emitter_fn
                    )
                    reply_text = res.get("analysis", "Camera scan received.")
                    self._call(self._send(c, {
                        "op": "reply",
                        "id": req_id,
                        "text": reply_text,
                        "file_path": res.get("file_path", "")
                    }))
                except Exception as e:
                    print(f"[phone] camera_scan error: {e}", flush=True)
                    self._call(self._send(c, {
                        "op": "error",
                        "id": req_id,
                        "error": f"Camera scan failed: {e}"
                    }))
            threading.Thread(target=_process, daemon=True).start()
            return

    def _task(self, device, request, text):
        try:
            ctx = get_active_thread_context()
            app = ctx.get("active_app", "PC")
            game = ctx.get("active_game", "")
            engine = ctx.get("game_engine", "Unity")
            thread_lines = "\n".join(ctx.get("recent_thread", []))
            clip = ctx.get("clipboard_snippet", "")

            # Keep thread context compact for low mobile latency
            compact_threads = ctx.get("recent_thread", [])[-3:]
            thread_str = "\n".join(compact_threads)
            carry_prompt = [
                f"[MOBILE REMOTE] Foreground: {app} | Game: {game} ({engine})"
            ]
            if thread_str:
                carry_prompt.append(f"Recent Dialogue:\n{thread_str}")
            if clip and len(clip) < 100:
                carry_prompt.append(f"PC Clipboard: \"{clip}\"")
            carry_prompt.append(
                f"User: {text}\n"
                "Reply directly and concisely in 1-2 short sentences as plain text."
            )
            prompt = "\n".join(carry_prompt)
            reply = self.brain.ask(prompt, remote=True)

            # Bidirectional sync: record phone dialogue into desktop sessions
            try:
                import jarvis
                jarvis.sessions.add({"who": "you", "text": f"[📱 Phone] {text}"})
                jarvis.sessions.add({"who": "jarvis", "text": reply})
            except Exception:
                pass
        except Exception as e:
            reply = f"The task failed: {e}"
        self._call(self._deliver(device, {"op": "reply", "id": request, "text": reply}))

    def push(self, text):
        """Something Jarvis did or found on its own (a scheduled task, a check), sent to every paired phone."""
        for device in self.state["devices"]:
            self._call(self._deliver(device, {"op": "reply", "text": text}))

    def push_clipboard(self, text: str):
        """Beams PC clipboard content to all paired phone devices."""
        for device in self.state["devices"]:
            self._call(self._deliver(device, {"op": "clipboard_sync", "text": text}))

    def beam_file_to_phone(self, file_path: str):
        """Notifies paired phones about a file ready for transfer."""
        if os.path.exists(file_path):
            name = os.path.basename(file_path)
            size = os.path.getsize(file_path)
            for device in self.state["devices"]:
                self._call(self._deliver(device, {
                    "op": "file_beam",
                    "filename": name,
                    "size": size,
                    "path": file_path
                }))

    async def _deliver(self, device, message):
        c = next((c for c, p in self.phones.items() if p["device"] == device and p["channel"]), None)
        if c:
            await self._send(c, message)
        else:
            self.pending.setdefault(device, []).append(message)
            del self.pending[device][:-20]
