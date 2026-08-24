"""Topic discovery and scripting.

Two jobs:
  1. Keep a queue of fresh, non-repeating topics in the niche.
  2. Turn one topic into a 6-beat script — one beat per 10s clip — with a
     video prompt, a narration line and an on-screen caption for each.
"""
from __future__ import annotations

import random
import textwrap

from .db import Store
from .llm import generate_json
from .quota import QuotaGate

WORDS_PER_CLIP = 25  # ~10 seconds of unhurried narration

TOPIC_PROMPT = """\
You are the researcher for a short-form video channel about: {niche}
Audience: {audience}
Tone: {tone}

Propose {count} NEW video topics. Each must be:
- a single concrete idea that can be explained in 60 seconds
- surprising or counter-intuitive enough that someone stops scrolling
- factually solid; no pseudoscience, no medical advice, no scare-mongering
- different from every topic in the "already covered" list below

Already covered (do NOT repeat or rephrase these):
{covered}

Return JSON: a list of objects with keys "title" and "angle".
"title" is the hook, max 70 characters, no hashtags, no clickbait punctuation.
"angle" is one sentence on what makes this specific take interesting.
"""

SCRIPT_PROMPT = """\
Write a {clips}-shot vertical short video about: {title}
Angle: {angle}
Niche: {niche}
Audience: {audience}
Tone: {tone}

Structure it as exactly {clips} shots of {seconds} seconds each.
Shot 1 must open with a hook that earns the next 5 seconds.
The final shot must land a satisfying payoff, not a call to action.

For each shot give:
- "video_prompt": a self-contained prompt for a text-to-video model.
  Describe camera, subject, lighting, motion, and style in one dense
  paragraph. It must stand alone — the model does not see the other shots,
  so restate the visual style every time to keep the video coherent.
  Absolutely no on-screen text, no logos, no real or recognisable people,
  no named brands, no gore, no medical procedures on humans.
- "narration": one or two sentences, about {words} words, that a voice
  would read over this shot. Plain spoken English. No stage directions.
- "caption": under 8 words, the on-screen text for this shot.

Also give, for the video as a whole:
- "title": under 70 characters, ends without a hashtag
- "description": 2 or 3 sentences
- "tags": 8 to 12 lowercase keyword strings, no "#"

Return one JSON object with keys "title", "description", "tags", "shots".
"shots" is a list of exactly {clips} objects.
"""

# Used only when there is no API key at all, so the pipeline still runs.
# Note these are fixed virology topics: they do NOT follow your `niche`
# setting. Without a key there is no model to think up topics for you.
FALLBACK_TOPICS = [
    ("Why viruses are not technically alive", "they borrow every function of life"),
    ("The virus that only infects other viruses", "virophages hijack the hijackers"),
    ("How a virus decides which cell to enter", "receptor keys and molecular locks"),
    ("Your DNA is 8% ancient virus", "endogenous retroviruses in the human genome"),
    ("The virus that made the placenta possible", "syncytin came from a retrovirus"),
    ("Why flu seasons move around the planet", "antigenic drift and global circulation"),
    ("The largest virus ever found", "pandoravirus and the size boundary"),
    ("How mRNA vaccines actually work", "instructions, not ingredients"),
    ("Why some viruses stay with you forever", "latency in nerve cells"),
    ("The 1918 flu virus was rebuilt from a frozen body", "reverse genetics and permafrost"),
    ("Bacteriophages look engineered", "the lunar-lander shape and why it works"),
    ("Why a virus needs a cell to copy itself", "no ribosomes of its own"),
    ("How viruses jump between species", "spillover and receptor compatibility"),
    ("Why we eradicated smallpox but not polio", "no animal reservoir"),
    ("The immune memory that lasts a lifetime", "long-lived plasma cells"),
]


def _covered_block(store: Store) -> str:
    titles = store.known_topic_titles(120)
    if not titles:
        return "(nothing yet)"
    return "\n".join(f"- {title}" for title in titles)


def discover_topics(store: Store, cfg, gate: QuotaGate, count: int = 12, log=print) -> int:
    """Add new topics to the queue. Returns how many were actually new."""
    prompt = TOPIC_PROMPT.format(
        niche=cfg["niche"],
        audience=cfg["audience"],
        tone=cfg["tone"],
        count=count,
        covered=_covered_block(store),
    )
    try:
        items = gate.call(
            generate_json,
            cfg.api_key,
            cfg["models"]["text"],
            prompt,
            label="topics",
        )
    except Exception as exc:  # noqa: BLE001
        if not cfg.api_key:
            log("[topics] no GEMINI_API_KEY, so there is no model to think up "
                "topics — falling back to a fixed virology list")
            log(f"[topics] this IGNORES your niche ({cfg['niche']!r}). "
                "A free key at https://aistudio.google.com/apikey fixes it.")
        else:
            log(f"[topics] model call failed ({type(exc).__name__}: {exc}), "
                "using built-in list")
        items = [
            {"title": title, "angle": angle}
            for title, angle in random.sample(FALLBACK_TOPICS, k=min(count, len(FALLBACK_TOPICS)))
        ]

    added = 0
    for item in items if isinstance(items, list) else []:
        title = str(item.get("title", "")).strip()
        if not title:
            continue
        if store.add_topic(title, str(item.get("angle", "")).strip()):
            added += 1
    log(f"[topics] {added} new topic(s) queued")
    return added


def _fallback_script(cfg, title: str, angle: str) -> dict:
    """Template script so a missing API key never hard-stops the pipeline."""
    style = (
        "Cinematic macro science documentary look, shallow depth of field, "
        "cool teal and amber lighting, slow deliberate camera motion, "
        "photoreal 3D render, vertical 9:16 framing, no text on screen"
    )
    beats = [
        ("Slow push in on an abstract microscopic structure suspended in dark fluid", f"{title}."),
        ("Orbiting shot revealing intricate geometric detail on the same structure", f"Here is the part that surprises people: {angle}."),
        ("The structure drifts toward a vast translucent cell surface", "Getting inside is the whole problem, and the solution is shape."),
        ("Close macro of the structure docking against the surface, faint glow at contact", "Fit the lock, and the door opens. Miss it, and nothing happens at all."),
        ("Interior view, luminous machinery replicating in the cell's depths", "Once inside, the instructions take over the machinery already there."),
        ("Slow pull back to thousands of identical structures drifting away", "That is the whole trick. Borrow everything, build nothing, and still spread."),
    ]
    clips = cfg["clips_per_video"]
    shots = []
    for i in range(clips):
        visual, narration = beats[i % len(beats)]
        shots.append(
            {
                "video_prompt": f"{visual}. {style}.",
                "narration": narration,
                "caption": " ".join(narration.split()[:6]),
            }
        )
    return {
        "title": title[:70],
        "description": f"{angle}\n\n{title}",
        "tags": ["science", "virology", "biology", "explained", "shorts", "education"],
        "shots": shots,
    }


def write_script(store: Store, cfg, gate: QuotaGate, topic, log=print) -> int | None:
    """Script one topic into a video row plus its clip rows. Returns video id."""
    title = topic["title"]
    angle = topic["angle"] or ""
    prompt = SCRIPT_PROMPT.format(
        clips=cfg["clips_per_video"],
        seconds=cfg["clip_seconds"],
        words=WORDS_PER_CLIP,
        title=title,
        angle=angle,
        niche=cfg["niche"],
        audience=cfg["audience"],
        tone=cfg["tone"],
    )
    try:
        data = gate.call(
            generate_json, cfg.api_key, cfg["models"]["text"], prompt, label="script"
        )
    except Exception as exc:  # noqa: BLE001
        detail = "no GEMINI_API_KEY" if not cfg.api_key else f"{type(exc).__name__}: {exc}"
        log(f"[script] writing from a generic template ({detail})")
        data = _fallback_script(cfg, title, angle)

    shots = data.get("shots") or []
    if len(shots) < cfg["clips_per_video"]:
        log(f"[script] only {len(shots)} shots returned, padding from template")
        data = _fallback_script(cfg, title, angle)
        shots = data["shots"]
    shots = shots[: cfg["clips_per_video"]]

    video_id = store.create_video(
        topic_id=topic["id"],
        title=str(data.get("title") or title)[:100],
        description=str(data.get("description") or angle),
        tags=[str(t).lstrip("#") for t in (data.get("tags") or [])][:12],
    )
    for idx, shot in enumerate(shots, start=1):
        store.add_clip(
            video_id=video_id,
            idx=idx,
            prompt=textwrap.shorten(str(shot.get("video_prompt", "")), 1800, placeholder=""),
            narration=str(shot.get("narration", "")).strip(),
            caption=str(shot.get("caption", "")).strip()[:60],
        )
    store.mark_topic(topic["id"], "used")
    log(f"[script] video #{video_id}: {data.get('title', title)!r} ({len(shots)} shots)")
    return video_id
