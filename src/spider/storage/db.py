import sqlite3
import os
import threading
from typing import List, Optional
from spider.core.models import OCRResult
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            xdg_data = os.getenv('XDG_DATA_HOME', 
                                 os.path.join(os.path.expanduser('~'), '.local', 'share'))
            data_dir = os.path.join(xdg_data, 'spider')
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "history.db")
        
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    @property
    def connection(self):
        if not hasattr(self._local, "conn") or self._local.conn is None:
            logger.debug("Creating new database connection for thread: %s", threading.current_thread().name)
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    def close(self):
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
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
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp)")
            
            cursor.execute("SELECT sql FROM sqlite_master WHERE name='history_fts'")
            existing_sql = cursor.fetchone()
            if existing_sql and 'trigram' not in existing_sql[0].lower():
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
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def _sanitize_fts_query(self, query: str) -> str:
        query = query.strip()
        for char in '"*:^()':
            query = query.replace(char, ' ')
        terms = [f'"{term}"' for term in query.split() if term]
        return " ".join(terms)

    def save_result(self, result: OCRResult):
        conn = self.connection
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO history (timestamp, text, image_blob, engine_used, language, confidence) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (result.timestamp, result.text, result.image_bytes, result.engine_used, result.language, result.confidence)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            cursor.close()

    def get_history(self, limit: int = 50, offset: int = 0) -> List[dict]:
        safe_limit = min(limit, 200)
        conn = self.connection
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT id, timestamp, text, engine_used, language, confidence FROM history ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (safe_limit, offset)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def search_history(self, query: str) -> List[dict]:
        if not query:
            return self.get_history()
            
        clean_query = self._sanitize_fts_query(query)
        if not clean_query:
            return []

        conn = self.connection
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT h.id, h.timestamp, h.text, h.engine_used, h.language, h.confidence 
                FROM history h
                JOIN history_fts f ON h.id = f.rowid
                WHERE history_fts MATCH ?
                ORDER BY rank
                LIMIT 200
            """, (clean_query,))
            return [dict(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def clear_history(self):
        conn = self.connection
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM history")
            conn.commit()
        finally:
            cursor.close()

    def delete_result(self, result_id: int):
        conn = self.connection
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM history WHERE id = ?", (result_id,))
            conn.commit()
        finally:
            cursor.close()
