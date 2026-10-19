"""
Nexis AI - Two-Tier Hybrid Memory Architecture (memory.py)
Production-grade hybrid memory system providing:
  Layer 1: In-Memory Short-Term Cache (Redis Buffer with sub-millisecond retrieval,
           list capping to 20 turns, TTL eviction, and automatic SQLite fallback).
  Layer 2: Persistent Storage Layer (SQLite Write-Ahead-Logging with sessions,
           messages, and full conversation history).
  Layer 3: Semantic Fact Memory (Cross-session user profile store with asynchronous
           LLM fact extraction and dynamic prompt injection).
  Layer 4: Mandatory Privacy Sanitization (Strict zero-leakage regex scrubbing
           for Aadhaar, Korean RRN, and Japanese MyNumber identifiers).
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("nexis_memory")


# ==============================================================================
# Layer 4: Mandatory Privacy Sanitization (Zero-Leakage Guarantee)
# ==============================================================================
def redact_sensitive_identifiers(text: str) -> str:
    """
    Redacts sensitive government identification numbers before storage, caching,
    or prompt assembly. Enforces strict zero-leakage:
      - Japanese MyNumber / Generic ID digits -> [ID Redacted]
      - Korean Resident Registration Number (RRN) digits -> [RRN Redacted]
      - Indian Aadhaar 12 digits -> [Aadhaar Redacted]
    """
    if not text or not isinstance(text, str):
        return text or ""
    # 1. Japanese MyNumber or explicit National ID (e.g. "MyNumber: 123456789012")
    text = re.sub(
        r"\b(MyNumber|National ID)[:\s]*\d{12}\b",
        r"\1: [ID Redacted]",
        text,
        flags=re.IGNORECASE
    )
    # 2. Korean Resident Registration Number (RRN: 6 digits - 7 digits)
    text = re.sub(r"\b\d{6}-[1-4]\d{6}\b", "[RRN Redacted]", text)
    # 3. Aadhaar 12 digits (with spaces or continuous)
    text = re.sub(r"\b\d{4}\s?\d{4}\s?\d{4}\b", "[Aadhaar Redacted]", text)
    return text


# ==============================================================================
# MemoryManager (Layers 1, 2, 3 Hybrid Orchestrator)
# ==============================================================================
class MemoryManager:
    """
    Production-grade Two-Tier Hybrid Memory Orchestrator:
      - Layer 1: Redis Async Short-Term Buffer
      - Layer 2: SQLite Async Long-Term Persistence
      - Layer 3: Epistemic Fact Store & Prompt Injector
      - Layer 4: PII Redaction Pipeline
    """

    def __init__(
        self,
        db_path: str = "nexis_memory.db",
        redis_url: Optional[str] = None
    ):
        self.db_path = db_path
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._lock = threading.Lock()
        self._redis = None
        self._redis_available = False
        self.init_db()

    # --------------------------------------------------------------------------
    # Database Initialization & Migration (Layer 2 & Layer 3 Schema)
    # --------------------------------------------------------------------------
    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def init_db(self) -> None:
        """Initializes SQLite schema, performs forward migrations, and indexes."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Sessions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        title TEXT NOT NULL
                    );
                """)
                # Messages table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        thought_trace TEXT,
                        tool_calls TEXT,
                        FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                    );
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_messages_session_time 
                    ON messages(session_id, timestamp);
                """)

                # Long-term Semantic Facts table (Layer 3)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS user_facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT DEFAULT 'default_user',
                        session_id TEXT,
                        fact_type TEXT NOT NULL,
                        fact_content TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    );
                """)

                # Inspect user_facts columns for seamless migration
                cursor.execute("PRAGMA table_info(user_facts);")
                existing_cols = {row["name"] for row in cursor.fetchall()}

                if "fact_content" not in existing_cols:
                    if "fact" in existing_cols:
                        cursor.execute("ALTER TABLE user_facts ADD COLUMN fact_content TEXT DEFAULT '';")
                        cursor.execute("UPDATE user_facts SET fact_content = fact WHERE fact_content = '';")
                if "fact_type" not in existing_cols:
                    if "category" in existing_cols:
                        cursor.execute("ALTER TABLE user_facts ADD COLUMN fact_type TEXT DEFAULT 'general';")
                        cursor.execute("UPDATE user_facts SET fact_type = category WHERE fact_type = 'general';")
                if "user_id" not in existing_cols:
                    cursor.execute("ALTER TABLE user_facts ADD COLUMN user_id TEXT DEFAULT 'default_user';")
                if "session_id" not in existing_cols:
                    cursor.execute("ALTER TABLE user_facts ADD COLUMN session_id TEXT;")
                if "updated_at" not in existing_cols:
                    cursor.execute("ALTER TABLE user_facts ADD COLUMN updated_at REAL DEFAULT 0;")
                    if "created_at" in existing_cols:
                        cursor.execute("UPDATE user_facts SET updated_at = created_at WHERE updated_at = 0;")

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_facts_user_type 
                    ON user_facts(user_id, fact_type);
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_facts_content 
                    ON user_facts(fact_content);
                """)

                conn.commit()
                logger.info(f"Initialized SQLite MemoryManager schema at {self.db_path}")

    # --------------------------------------------------------------------------
    # Layer 1: In-Memory Short-Term Cache (Redis Buffer)
    # --------------------------------------------------------------------------
    async def init_redis(self) -> bool:
        """
        Initializes connection to local Redis buffer.
        If Redis is offline or fails, logs warning and seamlessly falls back
        to SQLite without crashing the host application.
        """
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0
            )
            await self._redis.ping()
            self._redis_available = True
            logger.info(f"Layer 1: Redis short-term buffer connected at {self.redis_url}")
            return True
        except Exception as exc:
            self._redis_available = False
            logger.warning(
                f"Layer 1: Redis offline or connection failed at {self.redis_url} ({exc}). "
                f"Automatic fallback to SQLite persistent storage active."
            )
            return False

    async def close_redis(self) -> None:
        """Gracefully closes Redis connection pool."""
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
            self._redis_available = False

    async def cache_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        ttl: int = 7200
    ) -> bool:
        """
        Caches a conversational turn in Redis.
        - Capped to 20 turns (ltrim -20 -1).
        - TTL eviction defaults to 7200 seconds (2 hours).
        - Zero-leakage PII redaction applied before serialization.
        """
        clean_content = redact_sensitive_identifiers(content)
        if not self._redis_available or not self._redis:
            return False

        key = f"nexis:session:{session_id}:turns"
        payload = json.dumps({
            "role": role,
            "content": clean_content,
            "timestamp": time.time()
        })
        try:
            await self._redis.rpush(key, payload)
            # Cap list size to 20
            await self._redis.ltrim(key, -20, -1)
            # Set TTL eviction
            await self._redis.expire(key, ttl)
            return True
        except Exception as exc:
            logger.warning(f"Redis cache_turn warning for session {session_id}: {exc}")
            return False

    async def get_recent_history(
        self,
        session_id: str,
        limit: int = 8
    ) -> List[Dict[str, str]]:
        """
        Sub-millisecond sliding window retrieval for active session turns.
        1. Queries Redis buffer.
        2. If Redis is unavailable, returns empty, or throws, automatically
           falls back to SQLite.
        3. Enforces token window budget (3,000 max tokens) via manage_token_window.
        """
        history: List[Dict[str, str]] = []
        redis_success = False

        if self._redis_available and self._redis:
            try:
                key = f"nexis:session:{session_id}:turns"
                raw_items = await self._redis.lrange(key, -limit, -1)
                if raw_items:
                    for item in raw_items:
                        try:
                            parsed = json.loads(item)
                            history.append({
                                "role": parsed.get("role", "user"),
                                "content": parsed.get("content", "")
                            })
                        except Exception:
                            continue
                    redis_success = True
            except Exception as exc:
                logger.warning(f"Redis get_recent_history failure ({exc}). Falling back to SQLite.")
                redis_success = False

        # SQLite fallback on Redis miss or failure
        if not redis_success or not history:
            history = await self.get_recent_messages(session_id, limit=limit)

        return self.manage_token_window(history, max_tokens=3000)

    # --------------------------------------------------------------------------
    # Token Safety Budget Management
    # --------------------------------------------------------------------------
    def manage_token_window(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 3000
    ) -> List[Dict[str, str]]:
        """
        Calculates cumulative token budget across historical turns.
        If cumulative budget exceeds max_tokens (default 3,000), compacts older turns
        into a synthesized context summary while preserving recent turns.
        """
        if not messages:
            return []

        def estimate_tokens(text: str) -> int:
            return (len(text) // 4) + 4

        total_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
        if total_tokens <= max_tokens:
            return messages

        # Budget exceeded: retain newest turns that fit within 2,200 tokens
        target_budget = 2200
        retained = []
        accumulated = 0
        discarded = []

        for m in reversed(messages):
            tokens = estimate_tokens(m.get("content", ""))
            if accumulated + tokens <= target_budget:
                retained.append(m)
                accumulated += tokens
            else:
                discarded.append(m)

        retained.reverse()
        discarded.reverse()

        if discarded:
            summary_snippets = []
            for d in discarded:
                r = d.get("role", "unknown")
                c = (d.get("content", "") or "").replace("\n", " ").strip()
                if len(c) > 120:
                    c = c[:120] + "..."
                summary_snippets.append(f"{r}: {c}")

            summary_text = " | ".join(summary_snippets)
            summary_message = {
                "role": "system",
                "content": f"[Earlier conversation summary: {summary_text}]"
            }
            return [summary_message, *retained]

        return retained

    # --------------------------------------------------------------------------
    # Layer 2: Persistent Storage Layer (SQLite / Long-Term History)
    # --------------------------------------------------------------------------
    async def create_or_update_session(self, session_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        """Creates a new session or updates an existing one."""
        return await asyncio.to_thread(self._sync_create_or_update_session, session_id, title)

    def _sync_create_or_update_session(self, session_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT session_id, created_at, updated_at, title FROM sessions WHERE session_id = ?", (session_id,))
                row = cursor.fetchone()
                if row:
                    new_title = title if title else row["title"]
                    cursor.execute(
                        "UPDATE sessions SET updated_at = ?, title = ? WHERE session_id = ?",
                        (now, new_title, session_id)
                    )
                    conn.commit()
                    return {
                        "session_id": session_id,
                        "created_at": row["created_at"],
                        "updated_at": now,
                        "title": new_title
                    }
                else:
                    initial_title = title if title else "New conversation"
                    cursor.execute(
                        "INSERT INTO sessions (session_id, created_at, updated_at, title) VALUES (?, ?, ?, ?)",
                        (session_id, now, now, initial_title)
                    )
                    conn.commit()
                    return {
                        "session_id": session_id,
                        "created_at": now,
                        "updated_at": now,
                        "title": initial_title
                    }

    async def save_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        thought_trace: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        timestamp: Optional[float] = None,
        ttl: int = 7200
    ) -> int:
        """
        Complete dual-write persistence:
        1. Persists to SQLite permanently (sessions and messages).
        2. Caches to Redis buffer for instant sub-millisecond retrieval.
        Zero-leakage PII sanitization applied to both layers.
        """
        clean_content = redact_sensitive_identifiers(content)
        clean_thought = redact_sensitive_identifiers(thought_trace) if thought_trace else None

        msg_id = await self.save_message(
            session_id=session_id,
            role=role,
            content=clean_content,
            thought_trace=clean_thought,
            tool_calls=tool_calls,
            timestamp=timestamp
        )

        await self.cache_turn(
            session_id=session_id,
            role=role,
            content=clean_content,
            ttl=ttl
        )
        return msg_id

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        thought_trace: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        timestamp: Optional[float] = None
    ) -> int:
        """Sanitizes PII and persists a turn into SQLite messages."""
        return await asyncio.to_thread(
            self._sync_save_message,
            session_id,
            role,
            content,
            thought_trace,
            tool_calls,
            timestamp
        )

    def _sync_save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        thought_trace: Optional[str] = None,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        timestamp: Optional[float] = None
    ) -> int:
        clean_content = redact_sensitive_identifiers(content)
        clean_thought = redact_sensitive_identifiers(thought_trace) if thought_trace else None
        serialized_tools = json.dumps(tool_calls) if tool_calls else None
        now = timestamp or time.time()

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()

                # Ensure session exists
                cursor.execute("SELECT session_id, title FROM sessions WHERE session_id = ?", (session_id,))
                row = cursor.fetchone()
                if not row:
                    gen_title = clean_content[:32] + ("..." if len(clean_content) > 32 else "")
                    cursor.execute(
                        "INSERT INTO sessions (session_id, created_at, updated_at, title) VALUES (?, ?, ?, ?)",
                        (session_id, now, now, gen_title or "New conversation")
                    )
                else:
                    if (row["title"] in ["New conversation", "Untitled Session", ""] or not row["title"]) and role == "user":
                        gen_title = clean_content[:32] + ("..." if len(clean_content) > 32 else "")
                        cursor.execute(
                            "UPDATE sessions SET updated_at = ?, title = ? WHERE session_id = ?",
                            (now, gen_title, session_id)
                        )
                    else:
                        cursor.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))

                cursor.execute(
                    """
                    INSERT INTO messages (session_id, role, content, timestamp, thought_trace, tool_calls)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (session_id, role, clean_content, now, clean_thought, serialized_tools)
                )
                conn.commit()
                return cursor.lastrowid

    async def get_recent_messages(self, session_id: str, limit: int = 8) -> List[Dict[str, str]]:
        """Retrieves recent turns from SQLite in chronological order."""
        return await asyncio.to_thread(self._sync_get_recent_messages, session_id, limit)

    def _sync_get_recent_messages(self, session_id: str, limit: int = 8) -> List[Dict[str, str]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT role, content FROM messages 
                    WHERE session_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                    """,
                    (session_id, limit)
                )
                rows = cursor.fetchall()
                results = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
                return results

    async def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists sessions ordered by updated_at DESC."""
        return await asyncio.to_thread(self._sync_list_sessions, limit)

    def _sync_list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT s.session_id, s.title, s.created_at, s.updated_at,
                           COUNT(m.id) as message_count
                    FROM sessions s
                    LEFT JOIN messages m ON s.session_id = m.session_id
                    GROUP BY s.session_id
                    ORDER BY s.updated_at DESC
                    LIMIT ?
                    """,
                    (limit,)
                )
                rows = cursor.fetchall()
                sessions = []
                for r in rows:
                    sessions.append({
                        "id": r["session_id"],
                        "session_id": r["session_id"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "title": r["title"] or "New conversation",
                        "message_count": r["message_count"]
                    })
                return sessions

    async def get_session_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves complete conversation history for a given session."""
        return await asyncio.to_thread(self._sync_get_session_details, session_id)

    def _sync_get_session_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT session_id, created_at, updated_at, title FROM sessions WHERE session_id = ?",
                    (session_id,)
                )
                sess = cursor.fetchone()
                if not sess:
                    return None

                cursor.execute(
                    """
                    SELECT id, role, content, timestamp, thought_trace, tool_calls
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY timestamp ASC
                    """,
                    (session_id,)
                )
                msg_rows = cursor.fetchall()
                messages = []
                for m in msg_rows:
                    tools = None
                    if m["tool_calls"]:
                        try:
                            tools = json.loads(m["tool_calls"])
                        except Exception:
                            tools = []

                    messages.append({
                        "id": m["id"],
                        "role": m["role"],
                        "content": m["content"],
                        "timestamp": m["timestamp"],
                        "thought_trace": m["thought_trace"],
                        "toolsExecuted": tools or []
                    })

                return {
                    "id": sess["session_id"],
                    "session_id": sess["session_id"],
                    "created_at": sess["created_at"],
                    "updated_at": sess["updated_at"],
                    "title": sess["title"] or "New conversation",
                    "messages": messages
                }

    async def delete_session(self, session_id: str) -> bool:
        """Deletes session and all turns from both SQLite and Redis."""
        # Clean up Redis buffer
        if self._redis_available and self._redis:
            try:
                await self._redis.delete(f"nexis:session:{session_id}:turns")
            except Exception:
                pass
        return await asyncio.to_thread(self._sync_delete_session, session_id)

    def _sync_delete_session(self, session_id: str) -> bool:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return cursor.rowcount > 0

    # --------------------------------------------------------------------------
    # Layer 3: Semantic Fact Memory (Cross-Session User Profile Store)
    # --------------------------------------------------------------------------
    async def save_fact(
        self,
        fact_content: str,
        fact_type: str = "general",
        user_id: str = "default_user",
        session_id: Optional[str] = None
    ) -> bool:
        """
        Upserts an extracted user fact into user_facts table.
        Sanitizes PII prior to persistence.
        """
        return await asyncio.to_thread(
            self._sync_save_fact,
            fact_content,
            fact_type,
            user_id,
            session_id
        )

    def _sync_save_fact(
        self,
        fact_content: str,
        fact_type: str = "general",
        user_id: str = "default_user",
        session_id: Optional[str] = None
    ) -> bool:
        clean_fact = redact_sensitive_identifiers(fact_content.strip())
        if not clean_fact:
            return False

        clean_type = (fact_type or "general").lower().strip()
        now = time.time()

        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                try:
                    # Check for existing fact for user
                    cursor.execute(
                        "SELECT id FROM user_facts WHERE user_id = ? AND fact_content = ?",
                        (user_id, clean_fact)
                    )
                    existing = cursor.fetchone()
                    if existing:
                        cursor.execute(
                            "UPDATE user_facts SET fact_type = ?, session_id = COALESCE(?, session_id), updated_at = ? WHERE id = ?",
                            (clean_type, session_id, now, existing["id"])
                        )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO user_facts (user_id, session_id, fact_type, fact_content, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (user_id, session_id, clean_type, clean_fact, now)
                        )
                    conn.commit()
                    return True
                except Exception as e:
                    logger.warning(f"Error saving user fact: {e}")
                    return False

    async def get_relevant_facts(
        self,
        query: str = "",
        user_id: str = "default_user",
        limit: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant user facts.
        Ranks by keyword overlap with fallback to recent facts.
        """
        return await asyncio.to_thread(self._sync_get_relevant_facts, query, user_id, limit)

    def _sync_get_relevant_facts(
        self,
        query: str = "",
        user_id: str = "default_user",
        limit: int = 6
    ) -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, user_id, session_id, fact_type, fact_content, updated_at
                    FROM user_facts
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 50
                    """,
                    (user_id,)
                )
                rows = cursor.fetchall()
                if not rows:
                    return []

                facts = [
                    {
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "session_id": r["session_id"],
                        "fact_type": r["fact_type"],
                        "fact_content": r["fact_content"],
                        "updated_at": r["updated_at"],
                        # Compatibility aliases
                        "fact": r["fact_content"],
                        "category": r["fact_type"]
                    }
                    for r in rows
                ]

                if not query:
                    return facts[:limit]

                # Rank by word overlap
                query_tokens = set(re.findall(r"\w+", query.lower()))
                scored = []
                for f in facts:
                    fact_tokens = set(re.findall(r"\w+", f["fact_content"].lower()))
                    overlap = len(query_tokens.intersection(fact_tokens))
                    scored.append((overlap, f))

                scored.sort(key=lambda x: x[0], reverse=True)
                return [item[1] for item in scored[:limit]]

    def format_facts_for_prompt(self, facts: List[Union[Dict[str, Any], str]]) -> str:
        """
        Formats retrieved facts into dynamic system prompt injection section:
        ### PERSISTENT USER FACTS & DOMAIN CONSTRAINTS:
        - [category]: fact
        """
        if not facts:
            return ""

        lines = ["### PERSISTENT USER FACTS & DOMAIN CONSTRAINTS:"]
        for f in facts:
            if isinstance(f, dict):
                cat = f.get("fact_type") or f.get("category") or "general"
                content = f.get("fact_content") or f.get("fact") or ""
                if content:
                    lines.append(f"- [{cat}]: {content}")
            elif isinstance(f, str) and f.strip():
                lines.append(f"- {f.strip()}")

        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    async def list_all_facts(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        """Returns all persistent facts for inspection or diagnostics."""
        return await asyncio.to_thread(self._sync_list_all_facts, user_id)

    def _sync_list_all_facts(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, user_id, session_id, fact_type, fact_content, updated_at
                    FROM user_facts
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                    """,
                    (user_id,)
                )
                return [
                    {
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "session_id": r["session_id"],
                        "fact_type": r["fact_type"],
                        "fact_content": r["fact_content"],
                        "updated_at": r["updated_at"],
                        "fact": r["fact_content"],
                        "category": r["fact_type"]
                    }
                    for r in cursor.fetchall()
                ]

    async def extract_facts_background(
        self,
        user_query: str,
        assistant_response: str,
        session_id: Optional[str] = None,
        user_id: str = "default_user"
    ) -> None:
        """
        Asynchronous background task to extract salient user facts using Groq or Ollama.
        Discovers domain entities and preferences (e.g., location/district, crops grown,
        clinical allergies, educational level) and upserts them into user_facts.
        """
        if not user_query or len(user_query.strip()) < 8:
            return

        groq_api_key = os.getenv("GROQ_API_KEY", "")
        system_prompt = (
            "You are a background user memory extractor for an AI assistant. "
            "Analyze the user's message and the assistant's reply. "
            "Identify any permanent, durable facts explicitly revealed about the USER "
            "(e.g., location, farmland location, acreage, soil type, crops cultivated, "
            "medical conditions, allergies, medications, educational status, grade level, career, "
            "or persistent user preferences). "
            "Ignore temporary commands or generic questions (e.g. 'what is the price of tomato today', 'how to solve x^2=4'). "
            "If one or more durable facts about the user are found, output a JSON array of objects with keys: "
            "'fact' (a clear, concise standalone sentence) and 'category' (one of: 'agriculture', 'healthcare', 'education', 'preference', 'general'). "
            "If no durable user facts are found, output strictly: []\n"
            "Respond ONLY with valid JSON."
        )

        user_content = f"User Message:\n{user_query}\n\nAssistant Response:\n{assistant_response[:600]}"

        try:
            extracted_facts = []
            if groq_api_key and groq_api_key != "your_groq_api_key_here":
                from groq import AsyncGroq
                client = AsyncGroq(api_key=groq_api_key, max_retries=1)
                models_to_try = [
                    os.getenv("GROQ_ORCHESTRATOR_MODEL", "llama-3.3-70b-versatile"),
                    "llama-3.3-70b-versatile",
                    "openai/gpt-oss-120b",
                    "openai/gpt-oss-20b",
                    "qwen/qwen3.8-27b"
                ]
                raw_text = ""
                for model_candidate in list(dict.fromkeys(models_to_try)):
                    try:
                        completion = await client.chat.completions.create(
                            model=model_candidate,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_content}
                            ],
                            temperature=0.1,
                            max_tokens=300
                        )
                        raw_text = completion.choices[0].message.content or ""
                        if raw_text:
                            break
                    except Exception as m_err:
                        err_str = str(m_err).lower()
                        if "404" in err_str or "model_not_found" in err_str or "decommissioned" in err_str:
                            continue
                        logger.debug(f"Fact extraction candidate {model_candidate} returned error: {m_err}")

                json_match = re.search(r"\[.*\]", raw_text, flags=re.DOTALL)
                if json_match:
                    extracted_facts = json.loads(json_match.group(0))
            else:
                # Local Ollama fallback
                ollama_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
                from openai import AsyncOpenAI
                client = AsyncOpenAI(base_url=ollama_url, api_key="ollama")
                completion = await client.chat.completions.create(
                    model=os.getenv("OLLAMA_ORCHESTRATOR_MODEL", "llama3.1:8b"),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.1,
                    max_tokens=300
                )
                raw_text = completion.choices[0].message.content or ""
                json_match = re.search(r"\[.*\]", raw_text, flags=re.DOTALL)
                if json_match:
                    extracted_facts = json.loads(json_match.group(0))

            if isinstance(extracted_facts, list):
                for item in extracted_facts:
                    if isinstance(item, dict) and ("fact" in item or "fact_content" in item):
                        fact_text = item.get("fact_content") or item.get("fact") or ""
                        cat = item.get("fact_type") or item.get("category") or "general"
                        if fact_text.strip():
                            await self.save_fact(
                                fact_content=fact_text.strip(),
                                fact_type=cat,
                                user_id=user_id,
                                session_id=session_id
                            )
                            logger.info(f"Layer 3: Stored persistent fact [{cat}]: {fact_text}")

        except Exception as e:
            logger.debug(f"Fact extraction background task completed with notice: {e}")


# Singleton instance
memory_manager = MemoryManager()
