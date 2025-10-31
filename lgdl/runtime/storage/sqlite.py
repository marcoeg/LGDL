"""
SQLite storage backend for conversation state.

Provides persistent storage for multi-turn conversations using SQLite.

Copyright (c) 2025 Graziano Labs Corp.
"""

import aiosqlite
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

from ..state import PersistentState, Turn, StorageBackend

logger = logging.getLogger(__name__)


class SQLiteStateStorage(StorageBackend):
    """SQLite-based persistent storage for conversation state"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SQLite storage.

        Args:
            db_path: Path to SQLite database file. If None, uses ~/.lgdl/conversations.db
        """
        if db_path is None:
            home = Path.home()
            lgdl_dir = home / ".lgdl"
            lgdl_dir.mkdir(exist_ok=True)
            db_path = str(lgdl_dir / "conversations.db")

        self.db_path = db_path
        self._initialized = False

    async def _init_db(self):
        """Initialize database schema"""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            # Conversations table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    current_move_state TEXT,
                    awaiting_response INTEGER DEFAULT 0,
                    last_question TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            """)

            # Turns table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    turn_num INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_input TEXT NOT NULL,
                    sanitized_input TEXT NOT NULL,
                    matched_move TEXT,
                    confidence REAL NOT NULL,
                    response TEXT NOT NULL,
                    extracted_params TEXT DEFAULT '{}',
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)

            # Extracted context table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS extracted_context (
                    conversation_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (conversation_id, key),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                )
            """)

            # Indexes for performance
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_turns_conversation
                ON turns(conversation_id, turn_num)
            """)

            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversations_updated
                ON conversations(updated_at)
            """)

            await db.commit()

        self._initialized = True
        logger.info(f"Initialized SQLite storage at {self.db_path}")

    async def create_conversation(self, conversation_id: str) -> PersistentState:
        """Create a new conversation"""
        await self._init_db()

        now = datetime.utcnow()
        state = PersistentState(
            conversation_id=conversation_id,
            created_at=now,
            updated_at=now,
            turns_history=[],
            extracted_context={},
            current_move_state=None,
            awaiting_response=False,
            last_question=None,
            metadata={}
        )

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO conversations (id, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    now.isoformat(),
                    now.isoformat(),
                    json.dumps(state.metadata)
                )
            )
            await db.commit()

        logger.info(f"Created conversation {conversation_id}")
        return state

    async def load_conversation(self, conversation_id: str) -> Optional[PersistentState]:
        """Load conversation state"""
        await self._init_db()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Load conversation metadata
            async with db.execute(
                """
                SELECT id, created_at, updated_at, current_move_state,
                       awaiting_response, last_question, metadata
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                return None

            # Load turns
            turns = []
            async with db.execute(
                """
                SELECT turn_num, timestamp, user_input, sanitized_input,
                       matched_move, confidence, response, extracted_params, metadata
                FROM turns
                WHERE conversation_id = ?
                ORDER BY turn_num ASC
                """,
                (conversation_id,)
            ) as cursor:
                async for turn_row in cursor:
                    turns.append(Turn(
                        turn_num=turn_row["turn_num"],
                        timestamp=datetime.fromisoformat(turn_row["timestamp"]),
                        user_input=turn_row["user_input"],
                        sanitized_input=turn_row["sanitized_input"],
                        matched_move=turn_row["matched_move"],
                        confidence=turn_row["confidence"],
                        response=turn_row["response"],
                        extracted_params=json.loads(turn_row["extracted_params"]),
                        metadata=json.loads(turn_row["metadata"])
                    ))

            # Load extracted context
            extracted_context = {}
            async with db.execute(
                "SELECT key, value FROM extracted_context WHERE conversation_id = ?",
                (conversation_id,)
            ) as cursor:
                async for ctx_row in cursor:
                    extracted_context[ctx_row["key"]] = json.loads(ctx_row["value"])

            state = PersistentState(
                conversation_id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                turns_history=turns,
                extracted_context=extracted_context,
                current_move_state=row["current_move_state"],
                awaiting_response=bool(row["awaiting_response"]),
                last_question=row["last_question"],
                metadata=json.loads(row["metadata"])
            )

            logger.debug(f"Loaded conversation {conversation_id} with {len(turns)} turns")
            return state

    async def save_conversation(self, state: PersistentState) -> None:
        """Save conversation state"""
        await self._init_db()

        async with aiosqlite.connect(self.db_path) as db:
            # Update conversation metadata
            await db.execute(
                """
                UPDATE conversations
                SET updated_at = ?,
                    current_move_state = ?,
                    awaiting_response = ?,
                    last_question = ?,
                    metadata = ?
                WHERE id = ?
                """,
                (
                    state.updated_at.isoformat(),
                    state.current_move_state,
                    1 if state.awaiting_response else 0,
                    state.last_question,
                    json.dumps(state.metadata),
                    state.conversation_id
                )
            )

            # Get existing turn count
            async with db.execute(
                "SELECT MAX(turn_num) as max_turn FROM turns WHERE conversation_id = ?",
                (state.conversation_id,)
            ) as cursor:
                row = await cursor.fetchone()
                existing_turns = row[0] if row and row[0] else 0

            # Insert new turns only
            for turn in state.turns_history[existing_turns:]:
                await db.execute(
                    """
                    INSERT INTO turns (
                        conversation_id, turn_num, timestamp, user_input,
                        sanitized_input, matched_move, confidence, response,
                        extracted_params, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        state.conversation_id,
                        turn.turn_num,
                        turn.timestamp.isoformat(),
                        turn.user_input,
                        turn.sanitized_input,
                        turn.matched_move,
                        turn.confidence,
                        turn.response,
                        json.dumps(turn.extracted_params),
                        json.dumps(turn.metadata)
                    )
                )

            # Update extracted context (upsert)
            for key, value in state.extracted_context.items():
                await db.execute(
                    """
                    INSERT OR REPLACE INTO extracted_context (conversation_id, key, value)
                    VALUES (?, ?, ?)
                    """,
                    (state.conversation_id, key, json.dumps(value))
                )

            await db.commit()

        logger.debug(f"Saved conversation {state.conversation_id}")

    async def delete_conversation(self, conversation_id: str) -> None:
        """Delete conversation permanently"""
        await self._init_db()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,)
            )
            await db.commit()

        logger.info(f"Deleted conversation {conversation_id}")

    async def cleanup_old_conversations(self, older_than: timedelta) -> int:
        """Remove old conversations from storage"""
        await self._init_db()

        cutoff = datetime.utcnow() - older_than
        cutoff_iso = cutoff.isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            # Get count of conversations to delete
            async with db.execute(
                "SELECT COUNT(*) FROM conversations WHERE updated_at < ?",
                (cutoff_iso,)
            ) as cursor:
                row = await cursor.fetchone()
                count = row[0] if row else 0

            # Delete old conversations (cascade will handle related records)
            await db.execute(
                "DELETE FROM conversations WHERE updated_at < ?",
                (cutoff_iso,)
            )
            await db.commit()

        logger.info(f"Cleaned up {count} conversations older than {older_than}")
        return count

    async def get_stats(self) -> dict:
        """Get storage statistics"""
        await self._init_db()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM conversations") as cursor:
                row = await cursor.fetchone()
                total_conversations = row[0] if row else 0

            async with db.execute("SELECT COUNT(*) FROM turns") as cursor:
                row = await cursor.fetchone()
                total_turns = row[0] if row else 0

            async with db.execute(
                "SELECT AVG(turn_count) FROM (SELECT COUNT(*) as turn_count FROM turns GROUP BY conversation_id)"
            ) as cursor:
                row = await cursor.fetchone()
                avg_turns = row[0] if row and row[0] else 0.0

        return {
            "total_conversations": total_conversations,
            "total_turns": total_turns,
            "avg_turns_per_conversation": round(avg_turns, 2),
            "db_path": self.db_path
        }
