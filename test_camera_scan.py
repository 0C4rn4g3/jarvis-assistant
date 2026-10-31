"""Tests for Phone Camera Teleport (Scan to PC) bridge."""
import os
import sys
import unittest
import base64
import json
import time

sys.path.insert(0, r"C:\Users\User\Desktop\jarvis-assistant")
import camera_bridge
import brain
import jarvis

# Minimal valid 1x1 JPEG
TINY_JPEG = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00'
    b'\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13'
    b'\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342'
    b'\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05'
    b'\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08'
    b'\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'
)
B64_JPEG = base64.b64encode(TINY_JPEG).decode("ascii")


class TestCameraScanBridge(unittest.TestCase):
    def test_save_and_list_scans(self):
        filepath = camera_bridge.save_scan(TINY_JPEG, ext="jpg")
        self.assertTrue(os.path.exists(filepath))
        self.assertTrue(filepath.endswith(".jpg"))

        scans = camera_bridge.list_scans(limit=10)
        self.assertGreaterEqual(len(scans), 1)
        self.assertTrue(any(s["path"] == filepath for s in scans))

    def test_process_camera_scan_emits(self):
        events = []
        def test_emitter(kind, **data):
            events.append((kind, data))

        res = camera_bridge.process_camera_scan(
            B64_JPEG,
            prompt="Level 3 boss flowchart",
            mode="sketch",
            emitter=test_emitter
        )
        self.assertTrue(res["ok"])
        self.assertTrue(os.path.exists(res["file_path"]))
        self.assertIn("analysis", res)

        # Confirm image bubble and reply events emitted
        has_img = any(k == "log" and d.get("who") == "image" for k, d in events)
        has_reply = any(k == "log" and d.get("who") == "jarvis" for k, d in events)
        self.assertTrue(has_img)
        self.assertTrue(has_reply)

    def test_brain_tools(self):
        self.assertIn("list_camera_scans", brain.TOOLS)
        self.assertIn("analyze_camera_scan", brain.TOOLS)

        lst = brain.tool_list_camera_scans(limit=5)
        self.assertIn("scans", lst)

    def test_api_routes(self):
        b = brain.Brain() if hasattr(brain, "Brain") else None
        # GET scans
        get_res = jarvis.api_get("/api/phone/camera_scans", brain=b)
        self.assertIn("scans", get_res)

        # POST scan
        post_res = jarvis.api_post(
            "/api/phone/camera_scan",
            {"image": B64_JPEG, "prompt": "Inventory UI diagram", "mode": "sketch"},
            live=None,
            brain=b
        )
        self.assertTrue(post_res["ok"])
        self.assertTrue(os.path.exists(post_res["file_path"]))


if __name__ == "__main__":
    unittest.main()
