"""Stitch the clips into one finished vertical Short.

Everything here is ffmpeg. Each clip is normalised to the same format
first — mixed resolutions and frame rates are the usual reason a naive
concat produces a video that stutters or loses audio halfway through.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

W, H, FPS = 1080, 1920, 30


class FFmpegMissing(RuntimeError):
    pass


def require_ffmpeg() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        raise FFmpegMissing(
            f"{' and '.join(missing)} not found on PATH. "
            "Install it — Termux: `pkg install ffmpeg`; "
            "Debian/Ubuntu: `sudo apt install ffmpeg`; macOS: `brew install ffmpeg`."
        )


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-12:]
        raise RuntimeError("ffmpeg failed:\n" + "\n".join(tail))


def duration_of(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe could not read {path.name}")
    return float(json.loads(proc.stdout)["format"]["duration"])


def has_audio(path: Path) -> bool:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return False
    return bool(json.loads(proc.stdout).get("streams"))


def normalize(src: Path, dest: Path, max_seconds: float | None = None) -> Path:
    """One clip -> 1080x1920 / 30fps / yuv420p / stereo AAC.

    Scale to cover the frame then centre-crop, so a 16:9 clip becomes a
    proper vertical shot instead of getting letterboxed with black bars.
    """
    video_filter = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},fps={FPS},format=yuv420p,setsar=1"
    )
    args = ["ffmpeg", "-y", "-i", str(src)]
    if not has_audio(src):
        # Silent track, otherwise the concat drops audio from this point on.
        args += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                 "-shortest"]
    if max_seconds:
        args += ["-t", f"{max_seconds:.3f}"]
    args += [
        "-vf", video_filter,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(dest),
    ]
    _run(args)
    return dest


def _ass_time(seconds: float) -> str:
    hours, rem = divmod(max(0.0, seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{int(hours)}:{int(minutes):02d}:{secs:05.2f}"


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_subtitles(captions: list[str], durations: list[float], dest: Path) -> Path:
    """One caption per clip, timed to that clip's real duration."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,74,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    cursor = 0.0
    for caption, length in zip(captions, durations):
        start, end = cursor, cursor + length
        cursor = end
        text = _escape(caption).strip()
        if not text:
            continue
        # Fade in and out so captions don't pop on the cut.
        lines.append(
            f"Dialogue: 0,{_ass_time(start + 0.15)},{_ass_time(end - 0.15)},Cap,,0,0,0,,"
            f"{{\\fad(180,180)}}{text}"
        )
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def assemble(
    clip_paths: list[Path],
    captions: list[str],
    dest: Path,
    work_dir: Path,
    clip_seconds: float | None = None,
    max_total_seconds: float | None = 60.0,
    log=print,
) -> Path:
    """Normalise, caption and concatenate. Returns the finished file."""
    require_ffmpeg()
    if not clip_paths:
        raise ValueError("no clips to assemble")

    staging = work_dir / "staging" / dest.stem
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    normalized: list[Path] = []
    for i, source in enumerate(clip_paths, start=1):
        if not source.exists():
            raise FileNotFoundError(f"missing clip: {source}")
        out = staging / f"n{i:02d}.mp4"
        log(f"  normalising {source.name}")
        normalize(source, out, max_seconds=clip_seconds)
        normalized.append(out)

    durations = [duration_of(path) for path in normalized]
    total = sum(durations)
    log(f"  {len(normalized)} clips, {total:.1f}s total")

    subtitles = build_subtitles(captions, durations, staging / "captions.ass")

    listing = staging / "concat.txt"
    listing.write_text(
        "".join(f"file '{path.resolve().as_posix()}'\n" for path in normalized),
        encoding="utf-8",
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
        "-vf", f"ass={subtitles.resolve().as_posix()}",
    ]
    if max_total_seconds and total > max_total_seconds:
        log(f"  trimming to {max_total_seconds:.0f}s")
        args += ["-t", f"{max_total_seconds:.3f}"]
    args += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        str(dest),
    ]
    _run(args)

    shutil.rmtree(staging, ignore_errors=True)
    log(f"  rendered {dest}")
    return dest
