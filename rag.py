"""Jarvis Hybrid RAG Memory Subsystem.
Combines SQLite FTS5 (BM25 keyword search) + Dense Vector Embeddings with Reciprocal Rank Fusion (RRF).
Indexes local GDDs, Minecraft codebases, notes, and documentation for autonomous context injection.
"""
import glob
import hashlib
import json
import os
import re
import sqlite3
import struct
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests

import system

DB_PATH = os.path.join(system.DATA, "memory.db")
OLLAMA_HOST = (os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
EMBED_MODEL = "nomic-embed-text"
_lock = threading.Lock()


def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS docs (
                path TEXT PRIMARY KEY,
                sha256 TEXT,
                category TEXT,
                indexed_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT,
                doc_id TEXT,
                chunk_index INTEGER,
                category TEXT,
                heading TEXT,
                content TEXT,
                embedding BLOB,
                updated_at REAL
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                chunk_id UNINDEXED,
                content,
                heading,
                file_path
            )
        """)
    return conn


def _hash_vector(text: str, dim: int = 768) -> np.ndarray:
    """Deterministic hashing vectorizer fallback when no embedding server is running."""
    vec = np.zeros(dim, dtype=np.float32)
    words = re.findall(r"\w+", text.lower())
    if not words:
        return vec
    for w in words:
        h = int(hashlib.md5(w.encode()).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 8) & 1) else -1.0
        vec[idx] += sign
    norm = np.linalg.norm(vec)
    if norm > 1e-6:
        vec /= norm
    return vec


def get_embedding(text: str) -> np.ndarray:
    """Generates embedding via Ollama nomic-embed-text, or falls back to hash vectorizer."""
    try:
        url = f"{OLLAMA_HOST}/api/embeddings"
        res = requests.post(url, json={"model": EMBED_MODEL, "prompt": text}, timeout=3)
        if res.ok:
            data = res.json()
            emb = data.get("embedding")
            if emb:
                arr = np.array(emb, dtype=np.float32)
                norm = np.linalg.norm(arr)
                if norm > 1e-6:
                    arr /= norm
                return arr
    except Exception:
        pass
    return _hash_vector(text)


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> List[Tuple[str, str]]:
    """Splits document into chunks with section headers if present."""
    lines = text.splitlines()
    sections = []
    current_heading = "General"
    current_lines = []

    for line in lines:
        header_match = re.match(r"^(#{1,4}\s+|class\s+|public\s+class\s+|interface\s+|def\s+)(.+)", line)
        if header_match and current_lines:
            sections.append((current_heading, "\n".join(current_lines)))
            current_heading = header_match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, "\n".join(current_lines)))

    chunks = []
    for heading, sec_text in sections:
        if len(sec_text) <= max_chars:
            if sec_text.strip():
                chunks.append((heading, sec_text.strip()))
        else:
            start = 0
            while start < len(sec_text):
                end = min(start + max_chars, len(sec_text))
                chunk = sec_text[start:end].strip()
                if chunk:
                    chunks.append((heading, chunk))
                start += max_chars - overlap

    return chunks or [("General", text)]


def index_document(file_path: str, content: Optional[str] = None, category: str = "general") -> int:
    """Indexes a single file into SQLite FTS5 + dense vector store."""
    if not os.path.exists(file_path) and content is None:
        return 0

    if content is None:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            return 0

    content_hash = hashlib.sha256(content.encode()).hexdigest()

    with _lock:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT sha256 FROM docs WHERE path = ?", (file_path,))
        row = cur.fetchone()
        if row and row[0] == content_hash:
            return 0  # Unchanged

        # Remove old chunks for this file
        cur.execute("SELECT id FROM chunks WHERE file_path = ?", (file_path,))
        old_ids = [r[0] for r in cur.fetchall()]
        if old_ids:
            cur.execute("DELETE FROM chunks WHERE file_path = ?", (file_path,))
            cur.executemany("DELETE FROM chunks_fts WHERE chunk_id = ?", [(str(i),) for i in old_ids])

        # Generate new chunks
        raw_chunks = chunk_text(content)
        inserted = 0
        now = time.time()

        for idx, (heading, chunk_body) in enumerate(raw_chunks):
            emb = get_embedding(f"{heading}\n{chunk_body}")
            emb_blob = emb.tobytes()
            cur.execute("""
                INSERT INTO chunks (file_path, doc_id, chunk_index, category, heading, content, embedding, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (file_path, os.path.basename(file_path), idx, category, heading, chunk_body, emb_blob, now))
            chunk_id = cur.lastrowid
            cur.execute("""
                INSERT INTO chunks_fts (chunk_id, content, heading, file_path)
                VALUES (?, ?, ?, ?)
            """, (str(chunk_id), chunk_body, heading, file_path))
            inserted += 1

        cur.execute("""
            INSERT OR REPLACE INTO docs (path, sha256, category, indexed_at)
            VALUES (?, ?, ?, ?)
        """, (file_path, content_hash, category, now))
        conn.commit()
        return inserted


def index_directory(directory_path: str, extensions: Optional[List[str]] = None, category: str = "project") -> Dict[str, int]:
    """Indexes all source files, GDDs, and markdown notes within a directory."""
    if not os.path.isdir(directory_path):
        return {"indexed_files": 0, "indexed_chunks": 0}

    exts = extensions or [".md", ".txt", ".java", ".py", ".json", ".yml", ".yaml", ".gdd", ".cs", ".cpp", ".c", ".h"]
    total_files = 0
    total_chunks = 0

    for root, dirs, files in os.walk(directory_path):
        # Skip node_modules, build caches, git
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", "node_modules", "target", "build", "dist", "__pycache__", ".idea"}]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in exts:
                path = os.path.join(root, f)
                chunks = index_document(path, category=category)
                if chunks > 0:
                    total_files += 1
                    total_chunks += chunks

    return {"indexed_files": total_files, "indexed_chunks": total_chunks}


def search(query: str, top_k: int = 4, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Hybrid RAG Search using Reciprocal Rank Fusion (RRF) between FTS5 BM25 and Vector Cosine Similarity."""
    conn = get_db()
    cur = conn.cursor()

    # 1. BM25 Keyword Search
    clean_query = re.sub(r"[^\w\s]", " ", query).strip()
    words = [w for w in clean_query.split() if len(w) > 2]
    fts_ranks: Dict[int, int] = {}

    if words:
        fts_match_expr = " OR ".join(words)
        try:
            if category:
                cur.execute("""
                    SELECT c.id, bm25(chunks_fts) as score
                    FROM chunks_fts f
                    JOIN chunks c ON c.id = CAST(f.chunk_id AS INTEGER)
                    WHERE chunks_fts MATCH ? AND c.category = ?
                    ORDER BY score ASC LIMIT 30
                """, (fts_match_expr, category))
            else:
                cur.execute("""
                    SELECT CAST(chunk_id AS INTEGER), bm25(chunks_fts) as score
                    FROM chunks_fts
                    WHERE chunks_fts MATCH ?
                    ORDER BY score ASC LIMIT 30
                """, (fts_match_expr,))
            for rank, (cid, _) in enumerate(cur.fetchall()):
                fts_ranks[cid] = rank
        except Exception:
            pass

    # 2. Dense Vector Search
    q_emb = get_embedding(query)
    if category:
        cur.execute("SELECT id, embedding FROM chunks WHERE category = ?", (category,))
    else:
        cur.execute("SELECT id, embedding FROM chunks")
    rows = cur.fetchall()

    vec_ranks: Dict[int, int] = {}
    if rows:
        sims = []
        for cid, blob in rows:
            if blob:
                emb = np.frombuffer(blob, dtype=np.float32)
                sim = float(np.dot(q_emb, emb))
                sims.append((cid, sim))
        sims.sort(key=lambda x: x[1], reverse=True)
        for rank, (cid, _) in enumerate(sims[:30]):
            vec_ranks[cid] = rank

    # 3. Reciprocal Rank Fusion (RRF)
    all_cids = set(fts_ranks.keys()) | set(vec_ranks.keys())
    if not all_cids:
        return []

    scored_cids = []
    for cid in all_cids:
        score = 0.0
        if cid in fts_ranks:
            score += 0.5 * (1.0 / (60 + fts_ranks[cid]))
        if cid in vec_ranks:
            score += 0.5 * (1.0 / (60 + vec_ranks[cid]))
        scored_cids.append((cid, score))

    scored_cids.sort(key=lambda x: x[1], reverse=True)
    top_cids = [cid for cid, _ in scored_cids[:top_k]]

    # 4. Fetch chunk records
    results = []
    placeholders = ",".join("?" for _ in top_cids)
    cur.execute(f"""
        SELECT id, file_path, doc_id, category, heading, content
        FROM chunks WHERE id IN ({placeholders})
    """, top_cids)
    chunk_map = {r[0]: r for r in cur.fetchall()}

    for cid, score in scored_cids[:top_k]:
        if cid in chunk_map:
            _, path, doc_id, cat, heading, content = chunk_map[cid]
            results.append({
                "chunk_id": cid,
                "score": round(score, 5),
                "file_path": path,
                "doc_id": doc_id,
                "category": cat,
                "heading": heading,
                "content": content,
            })

    return results


def get_relevant_context(prompt: str, max_tokens: int = 800) -> str:
    """Retrieves top relevant memory chunks formatted for LLM system prompt injection."""
    matches = search(prompt, top_k=3)
    if not matches:
        return ""

    context_lines = ["\n[Retrieved Project & Knowledge Context (Hybrid RAG)]"]
    total_len = 0
    char_limit = max_tokens * 4

    for m in matches:
        snippet = f"- Source: {m['doc_id']} ({m['heading']}):\n  {m['content']}"
        if total_len + len(snippet) > char_limit:
            break
        context_lines.append(snippet)
        total_len += len(snippet)

    return "\n".join(context_lines) + "\n"


def stats() -> Dict[str, Any]:
    """Returns total docs, chunks, and database disk size."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM docs")
        doc_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cur.fetchone()[0]
        size_bytes = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
        return {
            "documents": doc_count,
            "chunks": chunk_count,
            "size_kb": round(size_bytes / 1024, 1),
            "embed_model": EMBED_MODEL,
        }
    except Exception as e:
        return {"error": str(e)}
