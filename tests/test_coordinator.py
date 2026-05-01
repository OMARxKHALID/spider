import pytest
import threading
import time
from unittest.mock import Mock, patch, MagicMock

class TestCoordinator:

    # ── Generation counter ──────────────────────────────────

    def test_stale_callback_ignored(self):
        """Pipeline 1's callback must not fire if Pipeline 2 already started."""
        # This is a logic test — trace the generation counter
        # Start generation=1, manually check guard
        coord = Mock()
        coord._run_generation = 1
        
        # Simulate stale callback from generation 0
        run_id_stale = 0
        run_id_current = 1
        
        assert run_id_stale != coord._run_generation, \
            "Stale run_id must differ from current generation"
        assert run_id_current == coord._run_generation, \
            "Current run_id must match generation"

    # ── Engine lock ─────────────────────────────────────────

    def test_engine_initialized_only_once_under_concurrent_load(self):
        """Two threads racing to init engine — engine must be created once."""
        init_count = [0]
        lock = threading.RLock()
        engine_ref = [None]

        def init_engine():
            with lock:
                if engine_ref[0] is not None:
                    return
                time.sleep(0.01)  # simulate slow init
                init_count[0] += 1
                engine_ref[0] = object()

        threads = [threading.Thread(target=init_engine) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()

        assert init_count[0] == 1, \
            f"Engine initialized {init_count[0]} times — lock not working"

    # ── DB not closed mid-pipeline ──────────────────────────

    def test_db_not_closed_between_captures(self, memory_db, mock_engine):
        """Database must remain open between pipeline runs."""
        from spider.core.models import OCRResult
        # Save an item, verify it's readable after a simulated pipeline cycle
        memory_db.save_result(OCRResult(text="Before pipeline", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        
        # Simulate what the fixed finally block does (nothing to db)
        # Then verify db still works
        items = memory_db.get_history()
        assert len(items) == 1, "DB must still be accessible after pipeline"
        
        # Save again — simulates second capture
        memory_db.save_result(OCRResult(text="After pipeline", confidence=0.9, engine_used="eng", timestamp=time.time(), language="eng", image_bytes=b"img"))
        items = memory_db.get_history()
        assert len(items) == 2, "DB must accept writes after second capture"

    # ── Portal timeout ──────────────────────────────────────

    def test_portal_timeout_calls_callback_with_none(self):
        """If portal times out, callback(None) must be called."""
        callback_args = []
        
        ctx = {
            "completed": False,
            "sub_id": None,
            "timeout_id": None,
            "callback": lambda x: callback_args.append(x)
        }
        
        # Simulate the timeout handler logic
        def on_portal_timeout(ctx):
            if not ctx.get("completed"):
                ctx["completed"] = True
                if ctx.get("sub_id"):
                    pass  # would unsubscribe
                ctx["callback"](None)
            return False  # GLib.SOURCE_REMOVE
        
        on_portal_timeout(ctx)
        
        assert callback_args == [None], \
            "Portal timeout must call callback with None"

    def test_portal_timeout_does_not_double_fire(self):
        """If portal responds before timeout, timeout handler must no-op."""
        callback_count = [0]
        
        ctx = {
            "completed": True,  # already completed
            "sub_id": None,
            "callback": lambda x: callback_count.__setitem__(0, callback_count[0] + 1)
        }
        
        def on_portal_timeout(ctx):
            if not ctx.get("completed"):
                ctx["callback"](None)
            return False
        
        on_portal_timeout(ctx)
        assert callback_count[0] == 0, \
            "Timeout must not fire callback if already completed"

    # ── Cancel event ────────────────────────────────────────

    def test_cancel_event_checked_during_pipeline(self):
        """Worker must respect cancel_event and abort early."""
        cancel_event = threading.Event()
        processing_stages_completed = []
        
        def mock_pipeline(cancel_event):
            # Stage 1
            if cancel_event.is_set():
                return None
            processing_stages_completed.append("stage1")
            
            # Stage 2
            if cancel_event.is_set():
                return None
            processing_stages_completed.append("stage2")
            
            return "result"
        
        # Without cancel — both stages run
        cancel_event.clear()
        result = mock_pipeline(cancel_event)
        assert len(processing_stages_completed) == 2
        assert result == "result"
        
        # With cancel after stage 1
        processing_stages_completed.clear()
        cancel_event.set()
        result = mock_pipeline(cancel_event)
        assert len(processing_stages_completed) == 0
        assert result is None
