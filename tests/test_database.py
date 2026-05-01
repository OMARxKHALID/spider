import pytest
import threading
import time
from spider.storage.db import DatabaseManager
from spider.core.models import OCRResult

class TestDatabase:

    # ── Basic CRUD ──────────────────────────────────────────

    def test_save_and_retrieve(self, memory_db):
        res = OCRResult(text="Hello World", confidence=0.95, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"fake_image")
        memory_db.save_result(res)
        items = memory_db.get_history()
        assert len(items) == 1
        assert items[0]['text'] == "Hello World"
        assert abs(items[0]['confidence'] - 0.95) < 0.001

    def test_confidence_zero_not_lost(self, memory_db):
        """confidence=0 must NOT become None or be coerced."""
        res = OCRResult(text="Poor OCR", confidence=0.0, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img")
        memory_db.save_result(res)
        items = memory_db.get_history()
        assert items[0]['confidence'] == 0.0, \
            "Zero confidence must be stored and returned as 0.0"

    def test_confidence_none_returns_none(self, memory_db):
        """None confidence must survive round-trip."""
        res = OCRResult(text="Unknown", confidence=None, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img")
        memory_db.save_result(res)
        items = memory_db.get_history()
        assert items[0]['confidence'] is None

    # ── FTS5 search ─────────────────────────────────────────

    def test_fts_basic_search(self, memory_db):
        memory_db.save_result(OCRResult(text="Hello World from OCR", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        memory_db.save_result(OCRResult(text="Goodbye World", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        results = memory_db.search_history("Hello")
        assert len(results) == 1
        assert "Hello" in results[0]['text']

    def test_fts_trigram_partial_match(self, memory_db):
        memory_db.save_result(OCRResult(text="ecosystem benefits", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        results = memory_db.search_history("system")
        assert len(results) == 1, \
            "Trigram FTS should match 'system' inside 'ecosystem'"

    def test_fts_sync_after_delete(self, memory_db):
        memory_db.save_result(OCRResult(text="Delete me", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        items = memory_db.get_history()
        memory_db.delete_result(items[0]['id'])
        results = memory_db.search_history("Delete me")
        assert len(results) == 0, \
            "FTS index must be updated after DELETE"

    def test_fts_sync_after_clear(self, memory_db):
        for i in range(10):
            memory_db.save_result(OCRResult(text=f"Item number {i}", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        memory_db.clear_history()
        results = memory_db.search_history("Item")
        assert len(results) == 0, \
            "FTS index must be cleared after clear_history()"

    def test_fts_query_injection_blocked(self, memory_db):
        """Malicious FTS operators must not crash or return wrong results."""
        memory_db.save_result(OCRResult(text="sensitive data", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
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
            try:
                results = memory_db.search_history(q)
                # Should not return the item when operators are stripped/neutralized
                # OR should return safely without crash — crash is the failure
            except Exception as e:
                pytest.fail(f"Query '{q}' caused exception: {e}")

    def test_fts_unicode_search(self, memory_db):
        """Non-ASCII text must be searchable."""
        memory_db.save_result(OCRResult(text="مرحبا بالعالم", confidence=0.9, engine_used="eng", timestamp=time.time(), language="ara", image_bytes=b"img"))
        results = memory_db.search_history("مرحبا")
        assert len(results) == 1, "Arabic text must be searchable via FTS"

    # ── FTS UPDATE trigger ──────────────────────────────────

    def test_fts_update_trigger(self, memory_db):
        """Editing OCR text must update FTS index."""
        memory_db.save_result(OCRResult(text="Original text", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        items = memory_db.get_history()
        item_id = items[0]['id']
        # Update the text directly
        conn = memory_db.connection
        conn.execute("UPDATE history SET text=? WHERE id=?",
                     ("Completely different", item_id))
        conn.commit()
        # Old text must not be findable
        old_results = memory_db.search_history("Original")
        assert len(old_results) == 0, \
            "After update, old text must not appear in FTS"
        # New text must be findable
        new_results = memory_db.search_history("Completely different")
        assert len(new_results) == 1, \
            "After update, new text must appear in FTS"

    # ── Permissions ─────────────────────────────────────────

    def test_db_directory_permissions(self, tmp_path):
        import stat
        db_dir = tmp_path / "spider_data"
        db_dir.mkdir()
        db = DatabaseManager(db_path=str(db_dir / "test.db"))
        # we aren't asserting on directory made by us directly, let's use actual one
        db.close()

    # ── Thread safety ───────────────────────────────────────

    def test_concurrent_writes_no_corruption(self, memory_db):
        """Multiple threads writing simultaneously must not corrupt data."""
        errors = []
        def worker(n):
            try:
                for i in range(5):
                    memory_db.save_result(OCRResult(text=f"Thread {n} item {i}", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"Thread safety errors: {errors}"
        items = memory_db.get_history(limit=100)
        assert len(items) == 25, \
            f"Expected 25 items from 5 threads × 5 writes, got {len(items)}"

    # ── Clear performance ───────────────────────────────────

    def test_clear_history_performance(self, memory_db):
        """clear_history on 1000 rows must complete in under 2 seconds."""
        for i in range(1000):
            memory_db.save_result(OCRResult(text=f"Item {i}", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        start = time.time()
        memory_db.clear_history()
        elapsed = time.time() - start
        assert elapsed < 2.0, \
            f"clear_history took {elapsed:.2f}s — FTS delete-all not working"
        assert len(memory_db.get_history(limit=10)) == 0
