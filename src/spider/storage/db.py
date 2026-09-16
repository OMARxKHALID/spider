import sqlite3
import os
import threading
from typing import List, Optional
from spider.core.models import OCRResult
import logging

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 500
HISTORY_COLUMNS = "id, timestamp, text, engine_used, language, confidence"


def default_db_path() -> str:
    xdg_data = os.getenv('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(xdg_data, 'spider', 'history.db')


class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = default_db_path()
            data_dir = os.path.dirname(db_path)
            os.makedirs(data_dir, exist_ok=True)
            os.chmod(data_dir, 0o700)

        self.db_path = db_path
        self._local = threading.local()
        self._all_connections = []
        self._conn_lock = threading.Lock()
        self._init_db()

    @property
    def connection(self):
        if getattr(self._local, "conn", None) is None:
            with self._conn_lock:
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                self._all_connections.append(conn)
                self._local.conn = conn
        return self._local.conn

    def close(self):
        with self._conn_lock:
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._all_connections.clear()
        self._local.conn = None

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        schema_version = 3
        try:
            if conn.execute("PRAGMA auto_vacuum").fetchone()[0] == 0:
                has_tables = conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
                conn.execute("PRAGMA auto_vacuum = INCREMENTAL")
                if has_tables:
                    logger.info("DB: Enabling incremental auto-vacuum")
                    try:
                        conn.execute("VACUUM")
                    except sqlite3.OperationalError as e:
                        logger.warning("DB: Could not enable auto-vacuum, will retry next start: %s", e)

            if conn.execute("PRAGMA user_version").fetchone()[0] < schema_version:
                logger.info("DB: Initializing database schema (v%d)", schema_version)
                conn.execute("""
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
                conn.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp)")
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS history_fts USING fts5(
                        text,
                        content='history',
                        content_rowid='id',
                        tokenize='trigram'
                    )
                """)
                conn.execute("INSERT INTO history_fts(history_fts) VALUES('rebuild')")
                conn.execute(f"PRAGMA user_version = {schema_version}")
                conn.commit()

            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS history_ai AFTER INSERT ON history BEGIN
                    INSERT INTO history_fts(rowid, text) VALUES (new.id, new.text);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS history_ad AFTER DELETE ON history BEGIN
                    INSERT INTO history_fts(history_fts, rowid, text)
                    VALUES ('delete', old.id, old.text);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS history_au AFTER UPDATE ON history BEGIN
                    INSERT INTO history_fts(history_fts, rowid, text)
                        VALUES ('delete', old.id, old.text);
                    INSERT INTO history_fts(rowid, text)
                        VALUES (new.id, new.text);
                END
            """)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _fts_query(terms: List[str]) -> str:
        return " ".join('"' + t.replace('"', '""') + '"' for t in terms)

    @staticmethod
    def _like_pattern(term: str) -> str:
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    def save_result(self, result: OCRResult):
        logger.info("DB: Saving OCR result (%d characters)", len(result.text))
        conn = self.connection
        with conn:
            cursor = conn.execute(
                "INSERT INTO history (timestamp, text, engine_used, language, confidence) VALUES (?, ?, ?, ?, ?)",
                (result.timestamp, result.text, result.engine_used, result.language, result.confidence)
            )
            pruned = conn.execute(
                "DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY timestamp DESC LIMIT ?)",
                (HISTORY_LIMIT,)
            ).rowcount
        if pruned:
            conn.execute("PRAGMA incremental_vacuum").fetchall()
        return cursor.lastrowid

    def restore_result(self, item: dict):
        with self.connection as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO history ({HISTORY_COLUMNS}) VALUES (:id, :timestamp, :text, :engine_used, :language, :confidence)",
                item
            )

    def get_history(self, limit: int = 50, offset: int = 0) -> List[dict]:
        rows = self.connection.execute(
            f"SELECT {HISTORY_COLUMNS} FROM history ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (min(limit, 200), offset)
        ).fetchall()
        return [dict(row) for row in rows]

    def search_history(self, query: str) -> List[dict]:
        terms = query.split() if query else []
        if not terms:
            return self.get_history()

        if all(len(t) >= 3 for t in terms):
            sql = """
                SELECT h.id, h.timestamp, h.text, h.engine_used, h.language, h.confidence
                FROM history h
                JOIN history_fts f ON h.id = f.rowid
                WHERE history_fts MATCH ?
                ORDER BY rank
                LIMIT 200
            """
            params = (self._fts_query(terms),)
        else:
            where = " AND ".join("text LIKE ? ESCAPE '\\'" for _ in terms)
            sql = f"SELECT {HISTORY_COLUMNS} FROM history WHERE {where} ORDER BY timestamp DESC LIMIT 200"
            params = tuple(self._like_pattern(t) for t in terms)

        return [dict(row) for row in self.connection.execute(sql, params).fetchall()]

    def clear_history(self):
        logger.info("DB: Purging all history")
        conn = self.connection
        with conn:
            conn.execute("DELETE FROM history")
        conn.execute("PRAGMA incremental_vacuum").fetchall()

    def delete_result(self, result_id: int):
        conn = self.connection
        with conn:
            conn.execute("DELETE FROM history WHERE id = ?", (result_id,))
        conn.execute("PRAGMA incremental_vacuum").fetchall()
