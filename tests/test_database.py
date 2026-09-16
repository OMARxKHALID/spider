import pytest
import threading
import time
from spider.storage.db import DatabaseManager
from spider.core.models import OCRResult

class TestDatabase:


    def test_save_and_retrieve(self, memory_db):
        res = OCRResult(text="Hello World", confidence=0.95, engine_used="eng", timestamp=time.time(), language="eng")
        memory_db.save_result(res)
        items = memory_db.get_history()
        assert len(items) == 1
        assert items[0]['text'] == "Hello World"
        assert abs(items[0]['confidence'] - 0.95) < 0.001

    def test_confidence_zero_not_lost(self, memory_db):
        res = OCRResult(text="Poor OCR", confidence=0.0, engine_used="eng", timestamp=time.time(), language="eng")
        memory_db.save_result(res)
        items = memory_db.get_history()
        assert items[0]['confidence'] == 0.0, \
            "Zero confidence must be stored and returned as 0.0"

    def test_confidence_none_returns_none(self, memory_db):
        res = OCRResult(text="Unknown", confidence=None, engine_used="eng", timestamp=time.time(), language="eng")
        memory_db.save_result(res)
        items = memory_db.get_history()
        assert items[0]['confidence'] is None


    def test_fts_basic_search(self, memory_db):
        memory_db.save_result(OCRResult(text="Hello World from OCR", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        memory_db.save_result(OCRResult(text="Goodbye World", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        results = memory_db.search_history("Hello")
        assert len(results) == 1
        assert "Hello" in results[0]['text']

    def test_fts_trigram_partial_match(self, memory_db):
        memory_db.save_result(OCRResult(text="ecosystem benefits", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        results = memory_db.search_history("system")
        assert len(results) == 1, \
            "Trigram FTS should match 'system' inside 'ecosystem'"

    def test_fts_sync_after_delete(self, memory_db):
        memory_db.save_result(OCRResult(text="Delete me", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        items = memory_db.get_history()
        memory_db.delete_result(items[0]['id'])
        results = memory_db.search_history("Delete me")
        assert len(results) == 0, \
            "FTS index must be updated after DELETE"

    def test_fts_sync_after_clear(self, memory_db):
        for i in range(10):
            memory_db.save_result(OCRResult(text=f"Item number {i}", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        memory_db.clear_history()
        results = memory_db.search_history("Item")
        assert len(results) == 0, \
            "FTS index must be cleared after clear_history()"

    def test_fts_query_injection_blocked(self, memory_db):
        memory_db.save_result(OCRResult(text="sensitive data", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        dangerous_queries = [
            'NOT sensitive',
            'sensitive AND data',
            'sensitive OR nothing',
            '"sensitive"*',
            'NEAR(sensitive data)',
            '{sensitive}',
            'sensitive + data',
        ]
        for q in dangerous_queries:
            assert isinstance(memory_db.search_history(q), list)

    def test_search_keeps_words_containing_operators(self, memory_db):
        memory_db.save_result(OCRResult(text="Note about android in Oregon", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        memory_db.save_result(OCRResult(text="unrelated", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        for q in ["Note", "android", "Oregon", "NOT", "and"]:
            assert [r['text'] for r in memory_db.search_history(q)] == ["Note about android in Oregon"], q

    def test_search_short_terms(self, memory_db):
        memory_db.save_result(OCRResult(text="Hi there", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        memory_db.save_result(OCRResult(text="100% done", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        assert [r['text'] for r in memory_db.search_history("Hi")] == ["Hi there"]
        assert [r['text'] for r in memory_db.search_history("%")] == ["100% done"]

    def test_search_quotes_escaped(self, memory_db):
        memory_db.save_result(OCRResult(text='say "quoted" word', confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        assert len(memory_db.search_history('"quoted"')) == 1

    def test_fts_unicode_search(self, memory_db):
        memory_db.save_result(OCRResult(text="مرحبا بالعالم", confidence=0.9, engine_used="eng", timestamp=time.time(), language="ara"))
        results = memory_db.search_history("مرحبا")
        assert len(results) == 1, "Arabic text must be searchable via FTS"

    def test_restore_after_delete_is_searchable(self, memory_db):
        memory_db.save_result(OCRResult(text="Restore me please", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        item = memory_db.get_history()[0]
        memory_db.delete_result(item['id'])
        memory_db.restore_result(item)
        assert memory_db.get_history() == [item]
        assert len(memory_db.search_history("Restore")) == 1


    def test_fts_update_trigger(self, memory_db):
        memory_db.save_result(OCRResult(text="Original text", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        items = memory_db.get_history()
        item_id = items[0]['id']
        conn = memory_db.connection
        conn.execute("UPDATE history SET text=? WHERE id=?",
                     ("Completely different", item_id))
        conn.commit()
        old_results = memory_db.search_history("Original")
        assert len(old_results) == 0, \
            "After update, old text must not appear in FTS"
        new_results = memory_db.search_history("Completely different")
        assert len(new_results) == 1, \
            "After update, new text must appear in FTS"


    def test_db_directory_permissions(self, tmp_path, monkeypatch):
        import stat
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        db = DatabaseManager()
        db.close()
        mode = stat.S_IMODE((tmp_path / "spider").stat().st_mode)
        assert mode == 0o700

    def test_legacy_db_gets_incremental_vacuum(self, tmp_path):
        import sqlite3
        path = str(tmp_path / "legacy.db")
        legacy = sqlite3.connect(path)
        legacy.execute("CREATE TABLE history (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, text TEXT NOT NULL, image_blob BLOB, engine_used TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'eng', confidence REAL)")
        legacy.execute("INSERT INTO history (timestamp, text, engine_used) VALUES (1, 'legacy row', 'eng')")
        legacy.commit()
        legacy.close()

        db = DatabaseManager(db_path=path)
        assert db.connection.execute("PRAGMA auto_vacuum").fetchone()[0] == 2
        assert len(db.search_history("legacy")) == 1
        db.close()


    def test_concurrent_writes_no_corruption(self, memory_db):
        errors = []
        def worker(n):
            try:
                for i in range(5):
                    memory_db.save_result(OCRResult(text=f"Thread {n} item {i}", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"Thread safety errors: {errors}"
        items = memory_db.get_history(limit=100)
        assert len(items) == 25, \
            f"Expected 25 items from 5 threads × 5 writes, got {len(items)}"


    def test_clear_history_performance(self, memory_db):
        for i in range(1000):
            memory_db.save_result(OCRResult(text=f"Item {i}", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng"))
        start = time.time()
        memory_db.clear_history()
        elapsed = time.time() - start
        assert elapsed < 2.0, \
            f"clear_history took {elapsed:.2f}s — FTS delete-all not working"
        assert len(memory_db.get_history(limit=10)) == 0
        assert memory_db.connection.execute("PRAGMA freelist_count").fetchone()[0] == 0, \
            "incremental_vacuum must release freed pages"
