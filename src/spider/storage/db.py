import sqlite3
import os
import time
from typing import List, Optional
from spider.core.models import OCRResult
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            data_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "spider")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "history.db")
        
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp   REAL    NOT NULL,
                    text        TEXT    NOT NULL,
                    image_blob  BLOB,
                    engine_used TEXT    NOT NULL,
                    language    TEXT    NOT NULL DEFAULT 'eng',
                    confidence  REAL
                )
            """)
            
            try:
                cursor.execute("SELECT compile_options FROM pragma_compile_options WHERE compile_options LIKE 'ENABLE_FTS5%'")
                
                cursor.execute("SELECT sql FROM sqlite_master WHERE name='history_fts'")
                existing_sql = cursor.fetchone()
                if existing_sql and 'trigram' not in existing_sql[0].lower():
                    logger.info("Upgrading search engine to Trigram Fuzzy mode...")
                    cursor.execute("DROP TABLE IF EXISTS history_fts")

                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS history_fts USING fts5(
                        text,
                        content='history',
                        content_rowid='id',
                        tokenize='trigram'
                    )
                """)
                
                cursor.execute("INSERT OR IGNORE INTO history_fts(rowid, text) SELECT id, text FROM history")
                
                cursor.execute("DROP TRIGGER IF EXISTS history_ai")
                cursor.execute("""
                    CREATE TRIGGER history_ai AFTER INSERT ON history BEGIN
                        INSERT INTO history_fts(rowid, text) VALUES (new.id, new.text);
                    END
                """)
                
                cursor.execute("DROP TRIGGER IF EXISTS history_ad")
                cursor.execute("""
                    CREATE TRIGGER history_ad AFTER DELETE ON history BEGIN
                        INSERT INTO history_fts(history_fts, rowid, text)
                        VALUES ('delete', old.id, old.text);
                    END
                """)
                logger.info("Database initialized with FTS5 support")
            except sqlite3.OperationalError as e:
                logger.error("FTS5 not available: %s", e)

    def save_result(self, result: OCRResult):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO history (timestamp, text, image_blob, engine_used, language, confidence) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (result.timestamp, result.text, result.image_bytes, result.engine_used, result.language, result.confidence)
            )
            return cursor.lastrowid

    def get_history(self, limit: int = 50, offset: int = 0) -> List[dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, timestamp, text, engine_used, language, confidence FROM history ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            return [dict(row) for row in cursor.fetchall()]

    def search_history(self, query: str) -> List[dict]:
        if not query:
            return self.get_history()
            
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT h.id, h.timestamp, h.text, h.engine_used, h.language, h.confidence 
                FROM history h
                JOIN history_fts f ON h.id = f.rowid
                WHERE history_fts MATCH ?
                ORDER BY rank
            """, (query,))
            return [dict(row) for row in cursor.fetchall()]

    def clear_history(self):
        logger.info("Clearing all history from database")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM history")
            conn.commit()

    def delete_result(self, result_id: int):
        logger.info("Deleting history item: %d", result_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM history WHERE id = ?", (result_id,))
            conn.commit()
