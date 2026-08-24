"""The orchestrator loop.

Start it and leave it. Every pass it does the most useful thing available:
top up topics, script a video, make the next clip, or finish and ship a
video whose clips are all done. When the API says no, it sleeps and comes
back. Nothing is held in memory, so killing it costs you at most one clip.
"""
from __future__ import annotations

import json
import signal
import time
from datetime import datetime
from pathlib import Path

from . import assemble as asm
from . import planner, sync, upload, video
from .db import Store
from .quota import QuotaGate, classify

TOPIC_LOW_WATER = 4


def log(message: str) -> None:
    print(f"{datetime.now():%H:%M:%S} {message}", flush=True)


class Runner:
    def __init__(self, cfg, store: Store, log=log):
        self.cfg = cfg
        self.store = store
        self.log = log
        self.stop = False
        self.gate = QuotaGate(store, cfg, log=log)
        self.provider = video.build(cfg, self.gate, log)
        self._shipped = 0
        self._waiting_on = None  # so "waiting for a clip" is said once, not every minute

    def request_stop(self, *_args) -> None:
        if self.stop:
            raise KeyboardInterrupt
        self.stop = True
        self.log("stopping after the current step — press Ctrl-C again to force")

    def install_signals(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self.request_stop)
            except (ValueError, OSError):  # not on the main thread
                pass

    # ---------------------------------------------------------- steps
    def top_up_topics(self) -> None:
        if self.store.count_topics("new") >= TOPIC_LOW_WATER:
            return
        planner.discover_topics(self.store, self.cfg, self.gate, count=12, log=self.log)

    def top_up_scripts(self) -> None:
        target = self.cfg["runner"]["target_pending_videos"]
        while not self.stop and self.store.count_videos("scripted", "generating") < target:
            topic = self.store.next_topic()
            if topic is None:
                added = planner.discover_topics(
                    self.store, self.cfg, self.gate, count=12, log=self.log
                )
                topic = self.store.next_topic()
                if topic is None or not added:
                    return
            planner.write_script(self.store, self.cfg, self.gate, topic, log=self.log)

    def make_next_clip(self) -> str:
        """Returns 'made' | 'waiting' | 'idle'."""
        clip = self.store.next_pending_clip(self.cfg["quota"]["max_attempts_per_clip"])
        if clip is None:
            return "idle"

        token = video.clip_token(clip["video_id"], clip["idx"])
        dest = video.clip_path(self.cfg, clip["video_id"], clip["idx"])
        self.store.set_video_status(clip["video_id"], "generating")
        waiting = self._waiting_on == token

        if dest.exists() and dest.stat().st_size > 0:
            # Left over from an interrupted run — reuse it, don't pay twice.
            self.store.complete_clip(clip["id"], str(dest))
            self.log(f"[clip] {token} already on disk")
            return "made"

        if not waiting:
            self.log(f"[clip] {token} — {clip['caption'] or clip['prompt'][:60]}")
        try:
            self.provider.produce(clip, dest, attempts=clip["attempts"])
        except video.NotReady:
            if not waiting:
                self._waiting_on = token
                self.log(
                    f"[wait] waiting for {token}. Paste its prompt into Gemini, then "
                    f"drop the clip into {self.cfg.inbox_dir}"
                )
                self.log(f"[wait] all pending prompts: {self.cfg.inbox_dir / 'PROMPTS.md'}")
            return "waiting"
        except Exception as exc:  # noqa: BLE001
            verdict = classify(exc, self.cfg, clip["attempts"])
            self.store.fail_clip(
                clip["id"], f"{type(exc).__name__}: {exc}",
                self.cfg["quota"]["max_attempts_per_clip"],
            )
            if verdict.kind == "fatal":
                self.log(f"[clip] {token} failed: {exc}")
            else:
                self.log(f"[clip] {token} deferred: {verdict.reason}")
            return "idle"

        self.store.complete_clip(clip["id"], str(dest))
        self._waiting_on = None
        if self.cfg["sync"].get("include_clips"):
            sync.push(self.cfg, [dest], log=self.log)
        self.log(f"[clip] {token} done")
        return "made"

    def finish_ready_videos(self) -> int:
        finished = 0
        for row in self.store.videos_by_status("scripted", "generating"):
            if self.stop:
                break
            video_id = row["id"]
            clips = self.store.clips_for(video_id)
            if not clips:
                continue
            if any(clip["status"] == "pending" for clip in clips):
                continue
            done = [clip for clip in clips if clip["status"] == "done"]
            if len(done) < len(clips):
                self.store.set_video_status(
                    video_id, "failed",
                    error=f"{len(clips) - len(done)} clip(s) could not be generated",
                )
                self.log(f"[video] #{video_id} failed — some clips never generated")
                continue
            self.ship(row, done)
            finished += 1
        return finished

    def ship(self, row, clips) -> None:
        video_id = row["id"]
        safe = "".join(ch if ch.isalnum() or ch in " -_" else "" for ch in row["title"])
        slug = safe.strip().replace(" ", "_")[:50].strip("_")
        stem = f"{video_id:04d}_{slug}" if slug else f"{video_id:04d}"
        dest = self.cfg.output_dir / f"{stem}.mp4"

        self.log(f"[video] #{video_id} assembling {row['title']!r}")
        try:
            asm.assemble(
                clip_paths=[Path(clip["path"]) for clip in clips],
                captions=[clip["caption"] or "" for clip in clips],
                dest=dest,
                work_dir=self.cfg.work_dir,
                clip_seconds=float(self.cfg["clip_seconds"]),
                max_total_seconds=60.0,
                log=self.log,
            )
        except Exception as exc:  # noqa: BLE001
            self.store.set_video_status(video_id, "failed", error=str(exc)[:500])
            self.log(f"[video] #{video_id} assembly failed: {exc}")
            return

        self.store.set_video_status(video_id, "assembled", render_path=str(dest))
        self._write_sidecar(row, dest)

        if sync.push(self.cfg, [dest], log=self.log):
            self.store.set_video_status(video_id, "synced", render_path=str(dest))

        if self.cfg["youtube"].get("enabled"):
            self.publish(video_id, row, dest)

        self._shipped += 1
        self.log(f"[video] #{video_id} ready — {dest}")

    def _write_sidecar(self, row, dest: Path) -> None:
        """Title/description/tags next to the file, for manual uploading."""
        tags = json.loads(row["tags"] or "[]")
        text = (
            f"{row['title']}\n\n{row['description']}\n\n"
            f"{self.cfg['youtube'].get('disclosure', '')}\n\n"
            f"#Shorts {' '.join('#' + t.replace(' ', '') for t in tags[:3])}\n"
        )
        dest.with_suffix(".txt").write_text(text, encoding="utf-8")

    def publish(self, video_id: int, row, dest: Path) -> None:
        try:
            youtube_id = upload.upload(
                self.cfg, dest, row["title"], row["description"] or "",
                json.loads(row["tags"] or "[]"), log=self.log,
            )
        except upload.YouTubeNotConfigured as exc:
            self.log(f"[upload] skipped: {exc}")
        except Exception as exc:  # noqa: BLE001
            verdict = classify(exc, self.cfg)
            if verdict.retryable:
                self.gate.block(verdict.wait_seconds, f"youtube: {verdict.reason}")
                self.log("[upload] quota hit — will retry this video later")
            else:
                self.log(f"[upload] failed: {exc}")
        else:
            self.store.set_video_status(
                video_id, "uploaded", youtube_id=youtube_id, render_path=str(dest)
            )

    def retry_uploads(self) -> None:
        """Videos rendered earlier but never uploaded (quota, or YT off then on)."""
        if not self.cfg["youtube"].get("enabled"):
            return
        for row in self.store.videos_by_status("assembled", "synced"):
            if self.stop or self.gate.blocked_for() > 0:
                return
            path = Path(row["render_path"] or "")
            if path.exists():
                self.publish(row["id"], row, path)

    # ----------------------------------------------------------- loop
    def run(self) -> None:
        cfg = self.cfg
        cfg.ensure_dirs()
        limit = cfg["runner"]["max_videos"]
        idle = cfg["runner"]["idle_seconds"]
        self.log(
            f"runner up — provider={self.provider.name} "
            f"clips/video={cfg['clips_per_video']} out={cfg.output_dir}"
        )

        while not self.stop:
            if limit and self._shipped >= limit:
                self.log(f"reached max_videos={limit}, stopping")
                break

            self.gate.wait_if_blocked(stop_check=lambda: self.stop)
            if self.stop:
                break

            self.top_up_topics()
            self.top_up_scripts()

            if isinstance(self.provider, video.ManualProvider):
                self.provider.publish_prompts(self.store)

            outcome = self.make_next_clip()
            self.finish_ready_videos()
            self.retry_uploads()

            if outcome == "waiting":
                self._nap(idle)
            elif outcome == "idle":
                self._nap(idle)

        self.log("stopped")

    def _nap(self, seconds: float) -> None:
        end = time.time() + seconds
        while not self.stop and time.time() < end:
            time.sleep(min(2.0, end - time.time()))
