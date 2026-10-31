"""Price & Gear Watch for Jarvis.
Tracks hardware, Unity assets, and development plugins.
Monitors price drops, tracks discounts, and alerts on sales via Desktop Notch and Phone push.
"""
import json
import os
import random
import re
import time
from typing import Any, Dict, List, Optional

import store
import system

WISHLIST_FILE = os.path.join(store.DATA, "wishlist.json")

DEFAULT_ITEMS = [
    {
        "id": "odin-inspector",
        "name": "Odin Inspector and Serializer",
        "category": "unity_asset",
        "store": "Unity Asset Store",
        "current_price": 55.0,
        "target_price": 40.0,
        "historic_low": 38.5,
        "on_sale": True,
        "discount_pct": 30,
        "url": "https://assetstore.unity.com/packages/tools/utilities/odin-inspector-and-serializer-89049",
        "last_checked": time.time()
    },
    {
        "id": "rtx-5080",
        "name": "NVIDIA GeForce RTX 5080 (16GB GDDR7)",
        "category": "hardware",
        "store": "Newegg / Best Buy",
        "current_price": 999.0,
        "target_price": 899.0,
        "historic_low": 949.0,
        "on_sale": False,
        "discount_pct": 0,
        "url": "https://www.nvidia.com",
        "last_checked": time.time()
    },
    {
        "id": "astar-pathfinding-pro",
        "name": "A* Pathfinding Project Pro",
        "category": "unity_asset",
        "store": "Unity Asset Store",
        "current_price": 100.0,
        "target_price": 70.0,
        "historic_low": 50.0,
        "on_sale": True,
        "discount_pct": 50,
        "url": "https://arongranberg.com/astar/",
        "last_checked": time.time()
    },
    {
        "id": "rewired-unity",
        "name": "Rewired Advanced Input Manager",
        "category": "unity_asset",
        "store": "Unity Asset Store",
        "current_price": 45.0,
        "target_price": 30.0,
        "historic_low": 22.5,
        "on_sale": False,
        "discount_pct": 0,
        "url": "https://guavaman.com/rewired",
        "last_checked": time.time()
    }
]


def _load_wishlist() -> List[Dict[str, Any]]:
    if not os.path.exists(WISHLIST_FILE):
        _save_wishlist(DEFAULT_ITEMS)
        return DEFAULT_ITEMS
    try:
        with open(WISHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_ITEMS


def _save_wishlist(items: List[Dict[str, Any]]):
    try:
        os.makedirs(os.path.dirname(WISHLIST_FILE), exist_ok=True)
        with open(WISHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, indent=2)
    except Exception:
        pass


def add_item(
    name: str,
    category: str = "unity_asset",
    target_price: float = 0.0,
    current_price: float = 0.0,
    url: str = "",
    store_name: str = ""
) -> Dict[str, Any]:
    """Adds a new hardware component, Unity asset, or tool to the price watch wishlist."""
    items = _load_wishlist()
    slug = re.sub(r'[^a-zA-Z0-9]', '-', name.lower().strip())
    
    # Check duplicate
    existing = next((x for x in items if x["id"] == slug or x["name"].lower() == name.lower()), None)
    if existing:
        existing.update({
            "target_price": float(target_price) if target_price > 0 else existing.get("target_price", 0.0),
            "current_price": float(current_price) if current_price > 0 else existing.get("current_price", 0.0),
            "url": url or existing.get("url", ""),
            "last_checked": time.time()
        })
        _save_wishlist(items)
        return {"ok": True, "action": "updated", "item": existing}

    item = {
        "id": slug,
        "name": name.strip(),
        "category": category.strip().lower() or "unity_asset",
        "store": store_name or ("Unity Asset Store" if "unity" in category.lower() else "Hardware Retailer"),
        "current_price": float(current_price) if current_price > 0 else float(target_price) * 1.25,
        "target_price": float(target_price),
        "historic_low": float(current_price) if current_price > 0 else float(target_price),
        "on_sale": False,
        "discount_pct": 0,
        "url": url,
        "last_checked": time.time()
    }
    items.append(item)
    _save_wishlist(items)
    return {"ok": True, "action": "added", "item": item}


def remove_item(item_id_or_name: str) -> bool:
    items = _load_wishlist()
    target = item_id_or_name.strip().lower()
    initial_len = len(items)
    items = [x for x in items if x["id"].lower() != target and x["name"].lower() != target]
    if len(items) < initial_len:
        _save_wishlist(items)
        return True
    return False


def list_items(category: str = "") -> List[Dict[str, Any]]:
    items = _load_wishlist()
    if category:
        c = category.strip().lower()
        items = [x for x in items if c in x.get("category", "").lower()]
    return items


def check_deals() -> Dict[str, Any]:
    """Scans tracked wishlist items for deals, discounts, or target price threshold triggers."""
    items = _load_wishlist()
    deals_found = []

    for it in items:
        it["last_checked"] = time.time()
        # Evaluate deal conditions: price <= target price or on_sale with >= 20% discount
        is_deal = False
        if it.get("target_price", 0) > 0 and it.get("current_price", 0) <= it.get("target_price", 0):
            is_deal = True
        elif it.get("on_sale") and it.get("discount_pct", 0) >= 20:
            is_deal = True

        if is_deal:
            deals_found.append(it)

    _save_wishlist(items)

    # If active deals found, push alert
    if deals_found:
        top_deal = deals_found[0]
        alert_msg = f"🏷️ Deal Alert: {top_deal['name']} is on sale for ${top_deal['current_price']:.2f} ({top_deal['discount_pct']}% OFF)!"
        try:
            import jarvis
            jarvis.notch_line[:] = [alert_msg[:30], time.time()]
            if jarvis.phone_ref[0]:
                jarvis.phone_ref[0].push(f"🏷️ **Price Watch Sale Alert**:\n- **{top_deal['name']}**: ${top_deal['current_price']:.2f} (Target: ${top_deal['target_price']:.2f})\nStore: {top_deal['store']}\n{top_deal['url']}")
        except Exception:
            pass

    return {
        "ok": True,
        "total_tracked": len(items),
        "deals_count": len(deals_found),
        "deals": deals_found,
        "report": wishlist_report()
    }


def wishlist_report() -> str:
    items = _load_wishlist()
    lines = [
        "🛍️ **Price & Gear Wishlist Watch**",
        "| Item | Cat | Current | Target | Deal Status |",
        "| :--- | :--- | :---: | :---: | :--- |"
    ]
    for it in items:
        status = f"🔥 **{it['discount_pct']}% OFF**" if it.get("on_sale") else "Tracking"
        if it.get("target_price", 0) > 0 and it.get("current_price", 0) <= it.get("target_price", 0):
            status += " (🎯 Hit!)"
        lines.append(f"| {it['name']} | `{it['category']}` | ${it['current_price']:.2f} | ${it['target_price']:.2f} | {status} |")
    return "\n".join(lines)
