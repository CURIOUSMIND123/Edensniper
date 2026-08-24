"""Clip production. Two providers, same interface.

ApiProvider    — Veo via the Google GenAI API. Fully unattended.
ManualProvider — you generate the clip in the Gemini app and drop the file
                 into the inbox folder. The pipeline waits, picks it up and
                 carries on. Nothing else changes.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".m4v", ".mkv"}


def clip_token(video_id: int, idx: int) -> str:
    return f"v{video_id:04d}_c{idx}"


def clip_path(cfg, video_id: int, idx: int) -> Path:
    folder = cfg.work_dir / "clips" / f"v{video_id:04d}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{clip_token(video_id, idx)}.mp4"


class ProviderError(RuntimeError):
    pass


class NotReady(RuntimeError):
    """Manual mode: the clip hasn't been dropped in the inbox yet."""


# ---------------------------------------------------------------- API mode
class ApiProvider:
    name = "api"

    def __init__(self, cfg, gate, log=print):
        self.cfg = cfg
        self.gate = gate
        self.log = log

    def _client(self):
        from google import genai

        if not self.cfg.api_key:
            raise ProviderError(
                "provider is 'api' but no GEMINI_API_KEY is set. "
                "Get a key at https://aistudio.google.com/apikey, or switch "
                "provider to 'manual' in config.yaml."
            )
        return genai.Client(api_key=self.cfg.api_key)

    def produce(self, clip, dest: Path, attempts: int = 0) -> Path:
        from google.genai import types

        client = self._client()

        def start():
            return client.models.generate_videos(
                model=self.cfg["models"]["video"],
                prompt=clip["prompt"],
                config=types.GenerateVideosConfig(
                    aspect_ratio=self.cfg["aspect_ratio"],
                    number_of_videos=1,
                ),
            )

        operation = self.gate.call(start, attempts=attempts, label="veo")

        # Video generation is long-running; poll until it resolves.
        waited = 0.0
        while not operation.done:
            time.sleep(10)
            waited += 10
            if waited > 1800:
                raise ProviderError("video generation timed out after 30 minutes")
            operation = self.gate.call(
                client.operations.get, operation, attempts=attempts, label="veo-poll"
            )

        if getattr(operation, "error", None):
            raise ProviderError(f"generation failed: {operation.error}")

        generated = (getattr(operation.response, "generated_videos", None) or [])
        if not generated:
            raise ProviderError("generation returned no video (prompt may have been filtered)")

        video_file = generated[0].video
        self.gate.call(client.files.download, file=video_file, attempts=attempts, label="download")
        video_file.save(str(dest))
        if not dest.exists() or dest.stat().st_size == 0:
            raise ProviderError("downloaded clip is empty")
        return dest


# ------------------------------------------------------------- manual mode
class ManualProvider:
    """Watches the inbox folder for clips you made by hand."""

    name = "manual"

    def __init__(self, cfg, gate, log=print):
        self.cfg = cfg
        self.log = log
        self.inbox = cfg.inbox_dir
        self.inbox.mkdir(parents=True, exist_ok=True)
        (self.inbox / "prompts").mkdir(exist_ok=True)

    # -- prompt hand-off -------------------------------------------
    def publish_prompts(self, store, limit: int = 24) -> Path:
        """Write every pending prompt to the inbox so you can batch them.

        One file per clip, plus a single PROMPTS.md you can read on a phone.
        Regenerated on every pass, so finished clips drop off the list.
        """
        pending = store.conn.execute(
            "SELECT c.*, v.title AS video_title FROM clips c "
            "JOIN videos v ON v.id = c.video_id "
            "WHERE c.status='pending' AND v.status IN ('scripted','generating') "
            "ORDER BY c.video_id, c.idx LIMIT ?",
            (limit,),
        ).fetchall()

        folder = self.inbox / "prompts"
        for stale in folder.glob("*.txt"):
            stale.unlink()

        lines = [
            "# Clips to generate",
            "",
            "Paste a prompt into the Gemini app, download the clip, and drop the",
            f"file into:  {self.inbox}",
            "",
            "Name the file with the tag shown (e.g. `v0001_c3.mp4`) — or just drop",
            "the file as-is and it will be matched to the next clip in line.",
            "",
        ]
        for row in pending:
            token = clip_token(row["video_id"], row["idx"])
            (folder / f"{token}.txt").write_text(row["prompt"] + "\n", encoding="utf-8")
            lines += [
                f"## {token}  —  {row['video_title']}  (shot {row['idx']})",
                "",
                "```",
                row["prompt"],
                "```",
                "",
            ]
        if not pending:
            lines.append("_Nothing pending. Every queued clip is done._")

        index = self.inbox / "PROMPTS.md"
        index.write_text("\n".join(lines), encoding="utf-8")
        return index

    # -- ingestion --------------------------------------------------
    def _loose_videos(self) -> list[Path]:
        found = [
            path
            for path in self.inbox.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES
        ]
        return sorted(found, key=lambda p: p.stat().st_mtime)

    def _match(self, clip) -> Path | None:
        token = clip_token(clip["video_id"], clip["idx"])
        candidates = self._loose_videos()
        for path in candidates:
            if token in path.stem:
                return path
        # No tagged file: take the oldest untagged drop. The runner always
        # asks for the lowest pending clip, so order is preserved.
        for path in candidates:
            if not any(part.startswith("v0") and "_c" in part for part in [path.stem]):
                return path
        return None

    def produce(self, clip, dest: Path, attempts: int = 0) -> Path:
        source = self._match(clip)
        if source is None:
            raise NotReady(clip_token(clip["video_id"], clip["idx"]))
        # Wait for the copy to finish before claiming it.
        size = -1
        for _ in range(30):
            current = source.stat().st_size
            if current == size and current > 0:
                break
            size = current
            time.sleep(1)
        shutil.move(str(source), str(dest))
        self.log(f"  picked up {source.name} -> {dest.name}")
        return dest


def build(cfg, gate, log=print):
    provider = str(cfg["provider"]).lower()
    if provider == "api":
        return ApiProvider(cfg, gate, log)
    if provider == "manual":
        return ManualProvider(cfg, gate, log)
    raise ProviderError(f"unknown provider {provider!r} (expected 'api' or 'manual')")
