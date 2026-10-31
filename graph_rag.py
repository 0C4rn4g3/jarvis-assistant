"""Jarvis Temporal Knowledge Graph (GraphRAG Layer).
Upgrades flat SQLite key-value memory into an entity-relationship graph
with temporal timestamps (valid_from, valid_until) tracking evolving project architectures,
dependencies, bugs, and user preferences over time.
"""
import json
import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import system

DB_PATH = os.path.join(system.DATA, "jarvis_temporal.db")
_db_lock = threading.Lock()


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db_lock:
        os.makedirs(system.DATA, exist_ok=True)
        conn = get_db()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    properties TEXT,
                    valid_from REAL NOT NULL,
                    valid_until REAL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_node_name ON graph_nodes(name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_node_valid ON graph_nodes(valid_until)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_edges (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    properties TEXT,
                    valid_from REAL NOT NULL,
                    valid_until REAL,
                    created_at REAL NOT NULL,
                    FOREIGN KEY (source_id) REFERENCES graph_nodes(id),
                    FOREIGN KEY (target_id) REFERENCES graph_nodes(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_rel ON graph_edges(relation)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_valid ON graph_edges(valid_until)")
        conn.close()


init_db()


def upsert_node(name: str, entity_type: str = "Concept", properties: Optional[Dict[str, Any]] = None, valid_from: Optional[float] = None) -> str:
    """Gets or creates an entity node."""
    name = name.strip()
    valid_from = valid_from or time.time()
    props_json = json.dumps(properties or {})

    with _db_lock:
        conn = get_db()
        try:
            cur = conn.execute("SELECT id FROM graph_nodes WHERE LOWER(name) = LOWER(?) AND valid_until IS NULL", (name,))
            row = cur.fetchone()
            if row:
                return row["id"]

            node_id = f"node_{uuid.uuid4().hex[:10]}"
            with conn:
                conn.execute(
                    "INSERT INTO graph_nodes (id, name, entity_type, properties, valid_from, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (node_id, name, entity_type, props_json, valid_from, time.time()),
                )
            return node_id
        finally:
            conn.close()


def add_relationship(source_name: str, relation: str, target_name: str,
                     source_type: str = "Project", target_type: str = "Dependency",
                     properties: Optional[Dict[str, Any]] = None,
                     valid_from: Optional[float] = None) -> str:
    """Adds a directional edge between two entities."""
    now = valid_from or time.time()
    src_id = upsert_node(source_name, entity_type=source_type, valid_from=now)
    tgt_id = upsert_node(target_name, entity_type=target_type, valid_from=now)
    props_json = json.dumps(properties or {})

    with _db_lock:
        conn = get_db()
        try:
            # Check if active edge exists
            cur = conn.execute("""
                SELECT id FROM graph_edges
                WHERE source_id = ? AND target_id = ? AND relation = ? AND valid_until IS NULL
            """, (src_id, tgt_id, relation.upper()))
            row = cur.fetchone()
            if row:
                return row["id"]

            edge_id = f"edge_{uuid.uuid4().hex[:10]}"
            with conn:
                conn.execute("""
                    INSERT INTO graph_edges (id, source_id, target_id, relation, properties, valid_from, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (edge_id, src_id, tgt_id, relation.upper(), props_json, now, time.time()))
            return edge_id
        finally:
            conn.close()


def supersede_relationship(source_name: str, relation: str, old_target_name: str, new_target_name: str,
                           source_type: str = "Project", target_type: str = "Dependency") -> Dict[str, Any]:
    """Updates temporal state: terminates previous fact and activates new truth."""
    now = time.time()
    with _db_lock:
        conn = get_db()
        try:
            # Terminate old active edge
            conn.execute("""
                UPDATE graph_edges
                SET valid_until = ?
                WHERE relation = ? AND valid_until IS NULL
                  AND source_id IN (SELECT id FROM graph_nodes WHERE LOWER(name) = LOWER(?))
                  AND target_id IN (SELECT id FROM graph_nodes WHERE LOWER(name) = LOWER(?))
            """, (now, relation.upper(), source_name, old_target_name))
        finally:
            conn.close()

    # Add new active relationship
    new_edge = add_relationship(
        source_name, relation, new_target_name,
        source_type=source_type, target_type=target_type, valid_from=now
    )
    return {
        "status": "superseded",
        "relation": relation.upper(),
        "from": old_target_name,
        "to": new_target_name,
        "edge_id": new_edge,
    }


def query_active_subgraph(entity_name: str = "") -> List[Dict[str, Any]]:
    """Returns all currently valid relationships for an entity or entire graph."""
    with _db_lock:
        conn = get_db()
        try:
            if entity_name:
                cur = conn.execute("""
                    SELECT e.id, s.name as source, s.entity_type as source_type,
                           e.relation, t.name as target, t.entity_type as target_type,
                           e.properties, e.valid_from, e.valid_until
                    FROM graph_edges e
                    JOIN graph_nodes s ON s.id = e.source_id
                    JOIN graph_nodes t ON t.id = e.target_id
                    WHERE e.valid_until IS NULL
                      AND (LOWER(s.name) = LOWER(?) OR LOWER(t.name) = LOWER(?))
                    ORDER BY e.created_at DESC
                """, (entity_name.strip(), entity_name.strip()))
            else:
                cur = conn.execute("""
                    SELECT e.id, s.name as source, s.entity_type as source_type,
                           e.relation, t.name as target, t.entity_type as target_type,
                           e.properties, e.valid_from, e.valid_until
                    FROM graph_edges e
                    JOIN graph_nodes s ON s.id = e.source_id
                    JOIN graph_nodes t ON t.id = e.target_id
                    WHERE e.valid_until IS NULL
                    ORDER BY e.created_at DESC LIMIT 50
                """)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def get_entity_context_for_prompt(prompt_text: str) -> str:
    """Finds entities mentioned in prompt and builds a GraphRAG context block."""
    if not prompt_text:
        return ""

    with _db_lock:
        conn = get_db()
        try:
            cur = conn.execute("SELECT DISTINCT name FROM graph_nodes WHERE valid_until IS NULL")
            names = [r["name"] for r in cur.fetchall() if len(r["name"]) >= 3]
        finally:
            conn.close()

    mentioned = [name for name in names if name.lower() in prompt_text.lower()]
    if not mentioned:
        return ""

    lines = []
    seen_edges = set()
    for ent in mentioned[:4]:
        sub = query_active_subgraph(ent)
        for rel in sub:
            key = (rel["source"], rel["relation"], rel["target"])
            if key not in seen_edges:
                seen_edges.add(key)
                lines.append(f"- {rel['source']} ({rel['source_type']}) --[{rel['relation']}]--> {rel['target']} ({rel['target_type']})")

    if not lines:
        return ""

    return "# Active Temporal Knowledge Graph:\n" + "\n".join(lines[:12])
