# AutoShorts

An unattended pipeline that turns a niche into finished 60-second vertical
Shorts: it finds topics, writes the script, produces six ~10-second clips,
stitches them with captions, copies the result to your phone, and (if you
let it) uploads to YouTube.

It is built to survive quota limits. When the model says "you're done for
today", it records the deadline, sleeps, wakes up and carries on. You can
close the laptop, kill the process, reboot — it resumes from the last
finished clip.

---

## Read this first

Three things that decide how you should use this.

**1. It makes original clips. It does not remix other people's videos.**
Re-cutting reels you found online is exactly what YouTube's *reused
content* policy rejects for monetisation, and it collects copyright
strikes. This tool generates new footage on the same subjects instead.

**2. Your Gemini Pro subscription is the Gemini *app*, which has no API.**
No script can legally drive it — automating that interface breaks Google's
terms and gets accounts banned. So there are two modes:

| mode | video comes from | how much you do |
|---|---|---|
| `manual` | you, in the Gemini app | paste a prompt, drop the download into a folder |
| `api` | Veo, via a Google AI Studio key | nothing |

`manual` is the mode that fits a Gemini Pro subscription. Everything
except the paste-and-download is still automatic: topics, scripts,
prompts, stitching, captions, phone sync, upload. When the app's session
limit stops you after a couple of clips, you just walk away — your place
is saved, and the remaining prompts are waiting in `inbox/PROMPTS.md`.

`api` mode is fully hands-off but Veo generation is paid per clip. Text
(topics, scripts, titles) runs on the **free** tier either way.

**3. Monetisation has a bar this tool cannot jump for you.** YouTube
requires 1,000 subscribers plus 10 million Shorts views in 90 days. This
gets you consistent output; it does not skip that requirement. AI-made
visuals are allowed, but they must be disclosed and the video needs to add
something of its own — which is why every video here is a written
explainer, not a montage.

---

## Setup

### On a PC or laptop

```bash
cd shorts
pip install -r requirements.txt
sudo apt install ffmpeg          # macOS: brew install ffmpeg

python -m autoshorts init
export GEMINI_API_KEY=...        # free key: https://aistudio.google.com/apikey
python -m autoshorts doctor      # tells you what's still missing
```

### On the phone, with Termux

Works fine — this is all Python and ffmpeg.

```bash
pkg install python ffmpeg git
termux-setup-storage              # lets it write to /sdcard
pip install -r requirements.txt
python -m autoshorts init
```

Then set `sync.dest` in `config.yaml` to `/sdcard/Movies/AutoShorts` so
finished videos land in your gallery.

### Configure

Open `config.yaml` and set:

- `niche` — what the channel is about. Be specific; this is the single
  biggest lever on quality.
- `provider` — `manual` or `api`.
- `sync.dest` — where finished videos should land on the phone.

---

## Running it

```bash
python -m autoshorts run
```

Leave it running. It picks whatever is most useful each pass: find topics,
write a script, make the next clip, ship a finished video.

### The manual-mode loop

1. Start the runner. It scripts a few videos and writes every pending
   prompt to `inbox/PROMPTS.md`, one file each under `inbox/prompts/`.
2. Open the Gemini app. Paste a prompt. Download the clip.
3. Drop the file into the `inbox/` folder. Name it with the tag from the
   prompt (`v0001_c3.mp4`) — or just drop it as-is and it will be matched
   to the next clip in line.
4. Session limit hits after two clips? Close the app. The runner keeps
   waiting and the remaining prompts stay in `PROMPTS.md`. Come back
   whenever.
5. The moment all six clips of a video are in, it stitches them, burns
   captions, copies the result to your phone and — if enabled — uploads.

To make step 3 effortless from the phone, point a sync app at the inbox:
Syncthing, or `rclone` against a Drive folder your phone saves into.

---

## Commands

| command | what it does |
|---|---|
| `init` | write `config.yaml` and create the folders |
| `doctor` | check the setup, show what's missing and what's queued |
| `run` | the main loop; `--max-videos 3` to stop after three |
| `status` | topics, clips and videos at a glance |
| `topics` | find new topics right now |
| `prompts` | rewrite `inbox/PROMPTS.md` (`--show` to print it) |
| `assemble <id>` | stitch one video's clips immediately |
| `auth-youtube` | one-time YouTube authorisation |
| `upload <id>` | upload one finished video |
| `sync` | push finished videos to the phone |
| `export` | dump all state as JSON |

---

## Uploading to YouTube

Off by default, and the first uploads should be **private** until you have
watched a few yourself.

1. Google Cloud Console → enable **YouTube Data API v3**.
2. Credentials → **OAuth client ID** → *Desktop app* → download the JSON.
3. Save it as `work/client_secret.json`.
4. `python -m autoshorts auth-youtube`
5. Set `youtube.enabled: true` in `config.yaml`.

YouTube's own API quota allows roughly six uploads a day. Hitting it is
treated like any other quota wall: the runner waits and retries the video
later, rather than losing it.

---

## How the quota waiting works

Everything that touches an API goes through a single gate.

- A **daily limit** (`per day`, `RESOURCE_EXHAUSTED`) → sleeps until the
  configured reset hour.
- A **rate limit with a hint** (`retryDelay: '37s'`) → waits exactly that
  long, plus a small margin.
- A **rate limit with no hint** → doubles the wait each attempt, inside
  `min_backoff_seconds`…`max_backoff_seconds`.
- A **transient error** (503, timeout, dropped connection) → short backoff
  and retry.
- A **real bug** (bad argument, bad config) → not retried; the clip is
  marked and the runner moves on to the next one.

The deadline is written to SQLite, not held in memory. Kill the process
mid-wait and restart it: it reads the deadline back and keeps waiting
instead of hammering the API and getting the key throttled harder.

A clip is retried `max_attempts_per_clip` times before it is given up on.
If a video ends up with a clip that can never be made, the video is marked
failed rather than sitting in the queue forever.

---

## Where things end up

```
work/
  autoshorts.db          all state; delete it to start over
  clips/v0001/           the raw 10-second clips
  client_secret.json     YouTube OAuth (you provide)
inbox/
  PROMPTS.md             manual mode: what to paste next
  prompts/v0001_c3.txt   one file per pending clip
out/
  0001_Title.mp4         the finished Short
  0001_Title.txt         title, description and tags for it
```

Individual clips are pushed to the phone too when
`sync.include_clips` is on, so you always have the raw material.

---

## Tests

```bash
cd shorts
python -m unittest discover -s tests
```

Twenty tests covering quota classification, cooldowns surviving a
restart, clip ordering and retry limits, inbox matching, and caption
timing.

---

## Troubleshooting

**"ffmpeg not found"** — `pkg install ffmpeg` (Termux) or
`sudo apt install ffmpeg`.

**"No GEMINI_API_KEY set"** — topics and scripts fall back to a built-in
list and a template, so it still runs, but the writing will be generic.
The key is free: <https://aistudio.google.com/apikey>.

**Clips are never picked up** — check the file actually landed in `inbox/`
at the top level, not in a subfolder, and that its extension is one of
`.mp4 .mov .webm .m4v .mkv`.

**The video is shorter than 60 seconds** — most models return 8-second
clips, so six of them is about 48s. Raise `clips_per_video` to 7 or 8 if
you want to fill the minute.

**Everything is stuck waiting** — `python -m autoshorts doctor` prints the
remaining cooldown at the bottom.
