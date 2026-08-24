"""Tests for the parts that must not break: quota handling and state.

Run with:  python -m unittest discover -s tests
"""
from __future__ import annotations

import datetime as dt
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoshorts import config as config_mod  # noqa: E402
from autoshorts.db import Store, fingerprint  # noqa: E402
from autoshorts.quota import QuotaGate, classify, seconds_until_daily_reset  # noqa: E402


class FakeError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def make_cfg(tmp: Path) -> config_mod.Config:
    data = config_mod._deep_merge(config_mod.DEFAULTS, {})
    cfg = config_mod.Config(data, tmp / "config.yaml")
    cfg.ensure_dirs()
    return cfg


class QuotaClassification(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_daily_quota_waits_for_reset(self):
        exc = FakeError(
            "429 RESOURCE_EXHAUSTED: quota exceeded for "
            "generate_requests_per_model_per_day",
            code=429,
        )
        verdict = classify(exc, self.cfg)
        self.assertEqual(verdict.kind, "quota")
        # Should be a real wait, not a 60-second retry storm.
        self.assertGreater(verdict.wait_seconds, 600)

    def test_retry_delay_hint_is_honoured(self):
        exc = FakeError("429 rate limit exceeded, retryDelay: '37s'", code=429)
        verdict = classify(exc, self.cfg)
        self.assertEqual(verdict.kind, "quota")
        self.assertAlmostEqual(verdict.wait_seconds, 42, delta=1)

    def test_backoff_grows_with_attempts(self):
        exc = FakeError("429 Too Many Requests", code=429)
        first = classify(exc, self.cfg, attempts=0).wait_seconds
        later = classify(exc, self.cfg, attempts=3).wait_seconds
        self.assertGreater(later, first)
        self.assertLessEqual(later, self.cfg["quota"]["max_backoff_seconds"])

    def test_transient_errors_are_retryable(self):
        verdict = classify(FakeError("503 Service Unavailable", code=503), self.cfg)
        self.assertEqual(verdict.kind, "transient")
        self.assertTrue(verdict.retryable)

    def test_real_bugs_are_not_retried(self):
        verdict = classify(TypeError("prompt must be a string"), self.cfg)
        self.assertEqual(verdict.kind, "fatal")
        self.assertFalse(verdict.retryable)

    def test_daily_reset_is_in_the_future(self):
        now = dt.datetime(2026, 1, 1, 9, 0, tzinfo=dt.timezone.utc)
        # Reset hour already passed today, so it must roll to tomorrow.
        self.assertGreater(seconds_until_daily_reset(8, now), 23 * 3600)
        self.assertLess(seconds_until_daily_reset(10, now), 2 * 3600)


class CooldownSurvivesRestart(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_block_is_persisted_and_reloaded(self):
        store = Store(self.cfg.db_path)
        QuotaGate(store, self.cfg, log=lambda _m: None).block(900, "test")
        store.close()

        # Simulate the process being killed and started again.
        store = Store(self.cfg.db_path)
        remaining = QuotaGate(store, self.cfg, log=lambda _m: None).blocked_for()
        self.assertGreater(remaining, 800)
        store.close()

    def test_longer_block_wins(self):
        store = Store(self.cfg.db_path)
        gate = QuotaGate(store, self.cfg, log=lambda _m: None)
        gate.block(3600, "long")
        gate.block(60, "short")
        self.assertGreater(gate.blocked_for(), 3000)
        gate.clear()
        self.assertEqual(gate.blocked_for(), 0)
        store.close()

    def test_call_sets_cooldown_on_quota_error(self):
        store = Store(self.cfg.db_path)
        gate = QuotaGate(store, self.cfg, log=lambda _m: None)

        def boom():
            raise FakeError("429 RESOURCE_EXHAUSTED", code=429)

        with self.assertRaises(FakeError):
            gate.call(boom, label="test")
        self.assertGreater(gate.blocked_for(), 0)
        store.close()


class StateStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))
        self.store = Store(self.cfg.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_topics_never_repeat(self):
        self.assertIsNotNone(self.store.add_topic("Why viruses are not alive"))
        self.assertIsNone(self.store.add_topic("why  VIRUSES are not   alive"))
        self.assertEqual(self.store.count_topics("new"), 1)

    def test_fingerprint_ignores_case_and_spacing(self):
        self.assertEqual(fingerprint("A  B"), fingerprint("a b"))

    def test_clips_are_handed_out_in_order(self):
        video_id = self.store.create_video(None, "T", "D", ["x"])
        for idx in range(1, 4):
            self.store.add_clip(video_id, idx, f"prompt {idx}", "n", "c")
        first = self.store.next_pending_clip(4)
        self.assertEqual(first["idx"], 1)
        self.store.complete_clip(first["id"], "/tmp/x.mp4")
        self.assertEqual(self.store.next_pending_clip(4)["idx"], 2)

    def test_clip_gives_up_after_max_attempts(self):
        video_id = self.store.create_video(None, "T", "D", [])
        self.store.add_clip(video_id, 1, "p", "n", "c")
        clip = self.store.next_pending_clip(2)
        self.store.fail_clip(clip["id"], "boom", 2)
        self.assertIsNotNone(self.store.next_pending_clip(2))  # one retry left
        self.store.fail_clip(clip["id"], "boom", 2)
        self.assertIsNone(self.store.next_pending_clip(2))     # now given up

    def test_video_completion_is_all_or_nothing(self):
        video_id = self.store.create_video(None, "T", "D", [])
        for idx in (1, 2):
            self.store.add_clip(video_id, idx, "p", "n", "c")
        clips = self.store.clips_for(video_id)
        self.store.complete_clip(clips[0]["id"], "/tmp/a.mp4")
        self.assertFalse(self.store.video_is_complete(video_id))
        self.store.complete_clip(clips[1]["id"], "/tmp/b.mp4")
        self.assertTrue(self.store.video_is_complete(video_id))


class ManualInbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))
        self.store = Store(self.cfg.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _provider(self):
        from autoshorts.video import ManualProvider

        gate = QuotaGate(self.store, self.cfg, log=lambda _m: None)
        return ManualProvider(self.cfg, gate, log=lambda _m: None)

    def test_prompts_are_written_for_pending_clips_only(self):
        video_id = self.store.create_video(None, "T", "D", [])
        self.store.add_clip(video_id, 1, "PROMPT ONE", "n", "c")
        self.store.add_clip(video_id, 2, "PROMPT TWO", "n", "c")
        self.store.complete_clip(self.store.clips_for(video_id)[0]["id"], "/tmp/a.mp4")

        index = self._provider().publish_prompts(self.store)
        text = index.read_text()
        self.assertNotIn("PROMPT ONE", text)
        self.assertIn("PROMPT TWO", text)

    def test_tagged_file_is_matched_to_its_clip(self):
        video_id = self.store.create_video(None, "T", "D", [])
        self.store.add_clip(video_id, 1, "p1", "n", "c")
        self.store.add_clip(video_id, 2, "p2", "n", "c")
        provider = self._provider()

        (self.cfg.inbox_dir / f"v{video_id:04d}_c2.mp4").write_bytes(b"clip-two")
        clip_two = self.store.clips_for(video_id)[1]
        dest = self.cfg.work_dir / "out2.mp4"
        provider.produce(clip_two, dest)
        self.assertEqual(dest.read_bytes(), b"clip-two")

    def test_untagged_drop_goes_to_the_next_clip_in_line(self):
        video_id = self.store.create_video(None, "T", "D", [])
        self.store.add_clip(video_id, 1, "p1", "n", "c")
        provider = self._provider()
        (self.cfg.inbox_dir / "Gemini_download.mp4").write_bytes(b"whatever")
        dest = self.cfg.work_dir / "out1.mp4"
        provider.produce(self.store.clips_for(video_id)[0], dest)
        self.assertEqual(dest.read_bytes(), b"whatever")

    def test_empty_inbox_reports_not_ready(self):
        from autoshorts.video import NotReady

        video_id = self.store.create_video(None, "T", "D", [])
        self.store.add_clip(video_id, 1, "p1", "n", "c")
        with self.assertRaises(NotReady):
            self._provider().produce(
                self.store.clips_for(video_id)[0], self.cfg.work_dir / "x.mp4"
            )


class Subtitles(unittest.TestCase):
    def test_caption_timings_follow_real_clip_durations(self):
        from autoshorts.assemble import build_subtitles

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "c.ass"
            build_subtitles(["first", "second"], [8.0, 12.0], dest)
            text = dest.read_text()
            self.assertIn("0:00:00.15", text)   # first starts at the top
            self.assertIn("0:00:08.15", text)   # second starts when first ends
            self.assertIn("0:00:19.85", text)   # and runs to 20s
            self.assertIn("first", text)
            self.assertIn("second", text)

    def test_braces_cannot_inject_ass_override_tags(self):
        from autoshorts.assemble import build_subtitles

        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "c.ass"
            build_subtitles(["{\\an8}sneaky"], [5.0], dest)
            body = dest.read_text().split("[Events]")[1]
            self.assertNotIn("{\\an8}", body)


if __name__ == "__main__":
    unittest.main()


class ConfigErrorsAreNotRateLimits(unittest.TestCase):
    """A missing API key used to be read as a transient 'unavailable' error,
    which bought a pointless cooldown on every single call."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_api_key_is_fatal_not_transient(self):
        from autoshorts.llm import LLMUnavailable

        verdict = classify(LLMUnavailable("No GEMINI_API_KEY set."), self.cfg)
        self.assertEqual(verdict.kind, "fatal")
        self.assertEqual(verdict.wait_seconds, 0)

    def test_missing_key_sets_no_cooldown(self):
        from autoshorts.llm import LLMUnavailable

        store = Store(self.cfg.db_path)
        gate = QuotaGate(store, self.cfg, log=lambda _m: None)

        def boom():
            raise LLMUnavailable("No GEMINI_API_KEY set.")

        for _ in range(3):
            with self.assertRaises(LLMUnavailable):
                gate.call(boom, label="topics")
        self.assertEqual(gate.blocked_for(), 0)
        store.close()

    def test_provider_misconfiguration_is_fatal(self):
        from autoshorts.video import ProviderError

        self.assertEqual(classify(ProviderError("no key for veo"), self.cfg).kind, "fatal")

    def test_genuine_service_outage_is_still_transient(self):
        verdict = classify(FakeError("503 Service Unavailable"), self.cfg)
        self.assertEqual(verdict.kind, "transient")


class SyncDestination(unittest.TestCase):
    """Pointing sync at the output folder must not try to copy a file onto
    itself and report a failure."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = make_cfg(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_copying_into_the_output_folder_is_a_no_op(self):
        from autoshorts import sync

        self.cfg.data["sync"] = {"enabled": True, "method": "copy",
                                 "dest": str(self.cfg.output_dir)}
        video = self.cfg.output_dir / "0001_x.mp4"
        video.write_bytes(b"video")

        messages: list[str] = []
        self.assertEqual(sync.push(self.cfg, [video], log=messages.append), 1)
        self.assertFalse([m for m in messages if "failed" in m])
        self.assertEqual(video.read_bytes(), b"video")

    def test_copying_to_a_real_destination_works(self):
        from autoshorts import sync

        dest = Path(self.tmp.name) / "phone"
        self.cfg.data["sync"] = {"enabled": True, "method": "copy", "dest": str(dest)}
        video = self.cfg.output_dir / "0001_x.mp4"
        video.write_bytes(b"video")

        self.assertEqual(sync.push(self.cfg, [video], log=lambda _m: None), 1)
        self.assertEqual((dest / "0001_x.mp4").read_bytes(), b"video")

    def test_disabled_sync_moves_nothing(self):
        from autoshorts import sync

        self.cfg.data["sync"] = {"enabled": False, "method": "copy", "dest": "/nope"}
        self.assertEqual(sync.push(self.cfg, [Path("/tmp/x")], log=lambda _m: None), 0)
