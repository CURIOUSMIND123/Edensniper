"""Command line interface."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import config as config_mod
from . import planner, sync, upload, video
from .db import Store
from .quota import QuotaGate
from .runner import Runner, log

PKG_DIR = Path(__file__).resolve().parent
ROOT = PKG_DIR.parent


def _open(args) -> tuple[config_mod.Config, Store]:
    cfg = config_mod.load(getattr(args, "config", None))
    cfg.ensure_dirs()
    return cfg, Store(cfg.db_path)


# ------------------------------------------------------------ commands
def cmd_init(args) -> int:
    target = Path(args.config or (Path.cwd() / "config.yaml"))
    example = ROOT / "config.example.yaml"
    if target.exists() and not args.force:
        print(f"{target} already exists (use --force to overwrite)")
    else:
        shutil.copy(example, target)
        print(f"wrote {target}")
    cfg = config_mod.load(str(target))
    cfg.ensure_dirs()
    print(f"work   {cfg.work_dir}\ninbox  {cfg.inbox_dir}\nout    {cfg.output_dir}")
    print("\nNext:\n  1. edit config.yaml (niche, provider, sync.dest)")
    print("  2. export GEMINI_API_KEY=...   (free key: https://aistudio.google.com/apikey)")
    print("  3. python -m autoshorts run")
    return 0


def cmd_doctor(args) -> int:
    cfg, store = _open(args)
    ok = True

    def check(label: str, good: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and good
        print(f"  [{'ok' if good else '--'}] {label}{(' — ' + detail) if detail else ''}")

    print(f"config: {cfg.source or '(defaults only)'}")
    print("checks:")
    check("config file present", cfg.source is not None, "run `init` to create one")
    check("GEMINI_API_KEY set", bool(cfg.api_key), "needed for topics and scripts")
    try:
        import google.genai  # noqa: F401
        check("google-genai installed", True)
    except ImportError:
        check("google-genai installed", False, "pip install -r requirements.txt")
    check("ffmpeg on PATH", bool(shutil.which("ffmpeg")), "needed to stitch clips")
    check("ffprobe on PATH", bool(shutil.which("ffprobe")))
    check("provider valid", str(cfg["provider"]).lower() in ("api", "manual"))
    if str(cfg["provider"]).lower() == "api":
        check("api provider has key", bool(cfg.api_key), "Veo needs a paid-tier key")
    if cfg["sync"].get("enabled") and cfg["sync"].get("method") == "copy":
        dest = Path(str(cfg["sync"].get("dest") or ""))
        check("sync destination writable", dest.parent.exists(), str(dest))
    if cfg["sync"].get("enabled") and cfg["sync"].get("method") == "rclone":
        check("rclone installed", bool(shutil.which("rclone")))
    if cfg["youtube"].get("enabled"):
        check("youtube authorised", (cfg.work_dir / upload.TOKEN_NAME).exists(),
              "run `auth-youtube`")

    print("\nstate:")
    for key, value in store.stats().items():
        print(f"  {key:20s} {value}")
    gate = QuotaGate(store, cfg, log=lambda _m: None)
    blocked = gate.blocked_for()
    print(f"  {'cooldown':20s} {'none' if blocked <= 0 else f'{blocked/60:.1f} min left'}")
    store.close()
    return 0 if ok else 1


def cmd_run(args) -> int:
    cfg, store = _open(args)
    if args.max_videos is not None:
        cfg.data["runner"]["max_videos"] = args.max_videos
    runner = Runner(cfg, store, log=log)
    runner.install_signals()
    try:
        runner.run()
    finally:
        store.close()
    return 0


def cmd_status(args) -> int:
    cfg, store = _open(args)
    stats = store.stats()
    width = max(len(k) for k in stats)
    for key, value in stats.items():
        print(f"{key:{width}s}  {value}")
    print()
    rows = store.conn.execute(
        "SELECT v.id, v.title, v.status, "
        "  (SELECT COUNT(*) FROM clips c WHERE c.video_id=v.id) AS total, "
        "  (SELECT COUNT(*) FROM clips c WHERE c.video_id=v.id AND c.status='done') AS done "
        "FROM videos v ORDER BY v.id DESC LIMIT ?", (args.limit,),
    ).fetchall()
    for row in rows:
        print(f"#{row['id']:<4} {row['done']}/{row['total']} clips  "
              f"{row['status']:<10} {row['title'][:56]}")
    store.close()
    return 0


def cmd_topics(args) -> int:
    cfg, store = _open(args)
    gate = QuotaGate(store, cfg, log=log)
    planner.discover_topics(store, cfg, gate, count=args.count, log=log)
    for row in store.conn.execute(
        "SELECT id, title, status FROM topics ORDER BY id DESC LIMIT 20"
    ):
        print(f"  {row['status']:<9} {row['title']}")
    store.close()
    return 0


def cmd_prompts(args) -> int:
    cfg, store = _open(args)
    gate = QuotaGate(store, cfg, log=log)
    provider = video.ManualProvider(cfg, gate, log)
    index = provider.publish_prompts(store, limit=args.limit)
    print(f"wrote {index}")
    print(f"drop finished clips into {cfg.inbox_dir}")
    if args.show:
        print()
        print(index.read_text())
    store.close()
    return 0


def cmd_assemble(args) -> int:
    """Force-assemble one video whose clips are all present."""
    cfg, store = _open(args)
    row = store.get_video(args.video_id)
    if row is None:
        print(f"no video #{args.video_id}")
        return 1
    clips = [clip for clip in store.clips_for(args.video_id) if clip["status"] == "done"]
    if not clips:
        print("no finished clips for that video")
        return 1
    runner = Runner(cfg, store, log=log)
    runner.ship(row, clips)
    store.close()
    return 0


def cmd_auth_youtube(args) -> int:
    cfg, store = _open(args)
    store.close()
    try:
        upload.authorize(cfg, log=print)
    except upload.YouTubeNotConfigured as exc:
        print(exc)
        return 1
    return 0


def cmd_upload(args) -> int:
    cfg, store = _open(args)
    row = store.get_video(args.video_id)
    if row is None or not row["render_path"]:
        print("that video has not been rendered yet")
        return 1
    runner = Runner(cfg, store, log=log)
    runner.publish(row["id"], row, Path(row["render_path"]))
    store.close()
    return 0


def cmd_sync(args) -> int:
    cfg, store = _open(args)
    paths = [
        Path(row["render_path"])
        for row in store.videos_by_status("assembled", "synced", "uploaded")
        if row["render_path"] and Path(row["render_path"]).exists()
    ]
    sent = sync.push(cfg, paths, log=print)
    print(f"pushed {sent} file(s)")
    store.close()
    return 0


def cmd_export(args) -> int:
    """Dump everything as JSON, for eyeballing or scripting against."""
    cfg, store = _open(args)
    payload = {
        "stats": store.stats(),
        "videos": [
            dict(row) | {"clips": [dict(clip) for clip in store.clips_for(row["id"])]}
            for row in store.conn.execute("SELECT * FROM videos ORDER BY id")
        ],
    }
    print(json.dumps(payload, indent=2, default=str))
    store.close()
    return 0


# --------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoshorts",
        description="Unattended 60-second Shorts pipeline.",
    )
    parser.add_argument("-c", "--config", help="path to config.yaml")
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("init", help="create config.yaml and the working folders")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = subs.add_parser("doctor", help="check the setup and report state")
    p.set_defaults(func=cmd_doctor)

    p = subs.add_parser("run", help="start the pipeline and leave it running")
    p.add_argument("--max-videos", type=int, default=None)
    p.set_defaults(func=cmd_run)

    p = subs.add_parser("status", help="what's queued, made and shipped")
    p.add_argument("--limit", type=int, default=15)
    p.set_defaults(func=cmd_status)

    p = subs.add_parser("topics", help="find new topics now")
    p.add_argument("--count", type=int, default=12)
    p.set_defaults(func=cmd_topics)

    p = subs.add_parser("prompts", help="manual mode: write pending prompts to the inbox")
    p.add_argument("--limit", type=int, default=24)
    p.add_argument("--show", action="store_true")
    p.set_defaults(func=cmd_prompts)

    p = subs.add_parser("assemble", help="stitch one video's clips right now")
    p.add_argument("video_id", type=int)
    p.set_defaults(func=cmd_assemble)

    p = subs.add_parser("auth-youtube", help="one-time YouTube authorisation")
    p.set_defaults(func=cmd_auth_youtube)

    p = subs.add_parser("upload", help="upload one rendered video")
    p.add_argument("video_id", type=int)
    p.set_defaults(func=cmd_upload)

    p = subs.add_parser("sync", help="push rendered videos to the phone")
    p.set_defaults(func=cmd_sync)

    p = subs.add_parser("export", help="dump all state as JSON")
    p.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130
    except BrokenPipeError:
        # Someone piped us into `head`. Not an error.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
