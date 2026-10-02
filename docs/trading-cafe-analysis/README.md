# How @TRADINGCAFEINDIA trades — analysis of the last 30 live streams

I pulled the auto-captions of the channel's last **30 live streams** (5 Aug → 1 Oct 2026, ≈153 hours, 26 trading
days), read them, and logged every trade call: setup, entry, stop-loss, targets, and what happened as he described
it on stream. I then checked every call against **real market data**: Nifty/Sensex intraday bars and the
exchanges' option records for each day. This folder has:

| File | What it is |
|---|---|
| `README.md` | This report: the method, the rules, a scorecard, and a reality check |
| [`market-check.md`](market-check.md) | **His calls checked against what the market actually did**, and what a follower would have made |
| [`verified_calls.csv`](verified_calls.csv) | Every call with the matched strike, the real contract high/low, the market check, and the follower result |
| [`charts/`](charts/) | One chart per day (real index path with his calls marked) plus summary charts |
| [`trade_log.csv`](trade_log.csv) | 138 logged calls (117 from the main host) with entry / SL / targets / outcome |
| [`daily-notes/`](daily-notes/) | One file per trading day: pre-market plan, every trade, what he taught, and a market-check chart and table |
| [`streams.md`](streams.md) | The 30 videos, dates, lengths, and who hosted each one |
| [`../../trading-system/tradingview/`](../../trading-system/tradingview/README.md) | **TCI All-in-One** TradingView indicator: liquidity, sweeps, pin bars, zones, PCR/OI, BUY/SELL with SL and targets |
| [`../../trading-system/`](../../trading-system/README.md) | His setup as fixed rules: TradingView indicator, Groww backtester, and a paper/live bot (with the test results) |

---

## TL;DR

**Checked against the real market** (details in [market-check.md](market-check.md)):
- His quoted prices are real. Of 53 WIN claims I could compare, 44 exits sit inside the option's actual range for
  that day.
- **Copying his calls as given (his entry, his stop, his first target) won only 40% of the time.** That made about
  **+0.28R per call before costs**, and roughly **zero after charges and 1 point of slippage** each way. Nifty calls
  were barely positive after costs; Sensex calls were negative.
- His direction is often right. 37 of the 48 calls that stopped a follower out later moved 2R or more his way. But
  his stops are inside normal 1-minute noise. A follower who gets stopped is out, even when the called move comes later.
- **A wider stop helped.** Keeping his entry and first target but using about 2× his stop raised the follower win
  rate to 60% and net P&L (1 lot per call, after costs) from about ₹5,800 to ₹19,100. Each trade risked twice as
  much, and this is one sample
  ([details](market-check.md#what-if-you-used-a-wider-stop)).
- **This is not a "big money from tomorrow" method.** Paper-trade it first. The worst run in this sample was 7
  losses in a row, and about −18R after costs.

**From his narration** (what he said on stream):
- **He doesn't predict direction.** Every morning he marks a few price "zones" and writes conditional plans for
  *both* a call (CE) and a put (PE): "CE only above X, PE only above Y". He then waits for price to prove itself at
  a zone and trades whichever side triggers. The "always right" impression mostly comes from this.
- **The edge is a small stop-loss, not accuracy.** Median stop was about **8 premium points on Nifty options** and
  **25 on Sensex options**. He skips trades where reward isn't at least about 2× the risk, and he trails stops hard.
- **The 1:3 / 1:4 targets are the plan. What actually happened was closer to 1:2.** On trades where the stop is
  known, the median result was **~1.9R**. Only **22%** reached 3R or more.
- **He is not always right.** In his own narration, 17 calls hit stop-loss, 13 went nowhere (break-even), and for
  13 he never said how they ended. Some days opened with 2–3 losses in a row (23 Sep, 25 Aug).
- **His results track market volatility.** Big days came on big-range days (15, 28, 30 Sep; 1 Oct). On narrow days
  he roughly broke even. Nifty fell ~9% over this period, so put-buying produced most of the big wins.
- **His own co-host said their win rate is about 40%.** That's well below the ~80% his narration suggests, and it
  points to narration bias: wins get celebrated on stream, losses get a single line.
- **There is a business behind the stream:** broker referral links (the "VIP" Telegram unlocks when you open an
  account through their link and place one F&O trade), a crypto app referral, an indicator, and a course. He says he
  is a SEBI-registered Research Analyst (since ~2021-22). I couldn't verify that from here; check it yourself.

---

## 1. Who is on the stream

- **Main host** (chat calls him "Chinmay sir"). Hosts most days, 9:05 am to about 3:15 pm. Everything below
  describes his method unless marked otherwise.
- **Associate** ("Swapnil", runs a channel called *Trade Circuit*). Hosts when the main host is away: all of 10 Sep
  and 25 Sep, the mornings of 24 Sep, and the afternoons of 11, 16 and 29 Sep. His method differs a little: he
  enters on a 15-minute candle close beyond a drawn line, uses standard-deviation and fair-value-gap targets, and
  puts stops on the index ("spot") level rather than on the option.

## 2. His daily routine

| Time (IST) | What he does |
|---|---|
| 9:05–9:15 | **Global cues**: US close (Dow/S&P/Nasdaq), Asia live (Nikkei, Hang Seng, China, Kospi), crude, gold, sometimes rupee or FII flows. Then a **higher-timeframe chart** of Nifty and Sensex: yesterday's key zones, where the open will land, and how many points of room there are up and down. |
| 9:15–9:20 | **Never trades the first tick.** Lets the opening premium settle ("market ko setal hone do", "pehle 1–2 minute rukenge"). Picks strikes: Nifty around ₹150 premium, Sensex around ₹300, usually slightly in-the-money. Plots levels on the **option chart**. |
| 9:20–11:00 | **Main window** ("arli morning sniper entries"). Most of his best trades start here. Fast scalps, tiny stops, quick move to break-even. |
| 11:00–1:30 | "Mid-day market": choppy. Smaller quantity, bigger stops, quick part-booking. Often waits ("vet end voch"). |
| ~1:30–2:30 | On volatile days, especially **expiry days**, he may build a **"jori"** (buy a cheap CE and a cheap PE together). Directional trades continue if a trend is running. |
| 2:30–3:15 | Trails runners and books profits. For overnight (BTST) trades he decides only after 3:15, and only if price is beyond a stated level. |

He focuses on the index that **expires soonest**: Sensex on Thursdays and the days before, Nifty on Tuesdays. Cheap
options near expiry move fast.

## 3. How he marks levels ("zones")

He uses price action only. RSI and other indicators don't enter his decisions; open interest and PCR come up only
as background when someone asks. The zones he draws:

1. **Previous-day key zones.** Where yesterday reversed, where it consolidated and broke, the day high/low, and
   where the "last distribution" (a selling cluster) began.
2. **Demand/supply zones.** The base a strong rally started from ("proven support") and the area a sharp fall came
   from (a supply or "drop" zone, where earlier buyers are trapped).
3. **Distribution zones as targets.** "Where the previous selling started is where price will go": the earlier
   swing, the start of the previous range, or a gap zone.
4. **Round numbers** (Nifty 23,000 / 23,400; Sensex 73,000 / 74,500) and the strikes carrying very large open
   interest.
5. **Fibonacci extensions** for targets in "untraded territory" (for example, the 194/238/267 put targets on 29 Sep).
6. **Liquidity.** Stops sit above highs and below lows. He waits for those to be taken ("liquidity lene do",
   "stop-loss hunting hone do") before he enters.

He plots levels on the index for context, but **entry, stop and target are always set on the option chart**: "always
follow option price action first, not the index".

## 4. The entry setups

All entries are on the **1-minute** option chart. Occasionally he gives a 5-minute version with a bigger stop and
target.

### A. Breakout plus follow-up candle (his most common)
- Price compresses near a zone ("cluster", "barcode", tight range, inside candles).
- **He doesn't buy the breakout candle itself.** He waits for it to close and enters only when the *next* candle
  takes out its high. Stop goes below that breakout or follow-up candle, or below the consolidation low.
  > "Fols brekaaut avoyad karne ka ek hi tarika hai: kaindal klojing ke baad uske folo-ap men kaam karo."
  > (The only way to avoid a false breakout is to trade the follow-up after the candle closes.)
- Accepts a worse price in exchange for not getting trapped.
- *Example (28 Sep):* the 23100PE broke the prior day's distribution zone. Entry above 166 on the follow-up, stop
  147–151, targets 198 / 224. It ran to about 222.

### B. Pullback ("first bounce") into a zone
- After a strong move breaks a level, he waits for the first pullback into the breakout zone or base. He enters on
  the **first green candle or pin bar** there, with the stop below that candle or the zone.
- *Example (1 Oct):* 72000CE. He waited for price to come back to 264–268, a "proven support where the last
  strong rally started", with a stop about 30 pts away. Targets 351 then 408. It moved about 100 points.
- Rule: **take the first bounce, avoid the second.** "Doosra tappa men utna dam nahin rahta" (the second bounce has
  less power).

### C. Reversal, only after confirmation
- He never buys the exact bottom: "Bottom nahin pakarna, bottom ka confirmation pakarna" (don't catch the bottom,
  catch the confirmation of the bottom).
- Needs a **stop-hunt or liquidity sweep** below a low, then a **W / double-bottom / rounding bottom**, a pin bar or
  engulfing candle, and a close back above the level. He also wants to know *who is getting trapped*.
- Counter-trend reversals were where he lost most often, for example the CE reversal attempts on 15 Sep and 8 Sep.

### D. Continuation and "higher-high" adds
- In a trend, he adds above the latest high with a stop under the latest small consolidation, but warns: "higher-high
  entry hai to badi quantity mat lena" (don't use big quantity on a higher-high entry).
- Mid-day continuation trades get smaller size and faster trailing.

### E. Dead-cat bounce scalp
- After a big fall, a quick counter-trend scalp off a base with a 4–6 point stop, small size, and break-even as soon
  as possible (28 Sep, 29 Sep).

## 5. Stop-loss, targets, trailing, sizing

| Rule | What he says or does |
|---|---|
| Where the stop goes | Below the zone, the swing low, the consolidation low, or the entry candle's low. Price-action based, not a fixed %. |
| Stop size (median across 30 streams) | **Nifty option ≈ 8 pts** (range 4–15). **Sensex option ≈ 25 pts** (range 10–40). He calls a 40–50 pt Sensex stop "too big" and skips or downsizes. |
| Rough rule by premium | ₹300 option → ₹20–30 risk. ₹150 option → ₹15–20 risk. ₹100 option with a ₹15 stop is "too big". |
| Minimum reward:risk | Skips 1:1 trades (29 Sep 9:15, 21 Aug 9:20). Wants at least ~1:2, ideally 30-pt stop for 80–90 pt target. |
| First action after entry | Once the option moves about the stop distance in his favour, move the stop to entry ("₹1 bhi wapas nahi dena"). |
| Part booking | With 2+ lots: book one lot near 1:1 or the primary target, and trail the rest from entry. With large quantity (associate's version): 40% at T1, 20% at T2, 20% at T3, hold 20%. |
| Trailing | Trail below the base of each big candle or each new higher-low. Never exit 100% at a target. "Don't sit for a huge target; trail." |
| Sizing | Size by **rupee risk**: e.g. ₹20k capital, ₹900 risk per trade. Lot sizes he quoted: Nifty 65, Sensex 20. ₹12–15k minimum to trade 2 lots of ~₹300 options. Keep quantity the same after losses (don't shrink after a loss streak, or the wins can't cover it). |
| When to stop | After 1–2 failed attempts at the same setup, stop and wait ("do baar haath jal gaye to shant ho jao"). No third entry in the same zone. |
| Holding | No hoping: "₹300 ka call ₹100 tak pakad ke baithna trading nahi, tukkebaazi hai" (holding a ₹300 call down to ₹100 isn't trading, it's gambling). Exit when the stop hits. |

## 6. Strike selection

- Nifty: about **₹150** premium. Sensex: about **₹300**. Usually slightly **in-the-money**, because "intrinsic value"
  decays less than OTM premium.
- He switches strikes whenever premium drifts (to ₹100 or ₹500) and tells viewers to "update the watchlist".
- Avoids options under ~₹100 and calls ₹20–30 "zero-hero" options gambling ("bhagwan bharose").
- He stopped trading futures after the STT hike (break-even costs ~16 Nifty points).

## 7. No-trade rules (things he repeatedly refused)

- The first 1–2 minutes after the open.
- Buying a running breakout candle ("bhagti hui kaindal men andar mat aana").
- Trading inside a tight cluster or range.
- R:R below ~1:2, or a stop he considers too big for the day's volatility.
- Taking a second or third entry in the same zone after it failed.
- Trading news headlines. He watches how price reacts instead.
- Deep OTM options, especially on expiry day.

## 8. The "jori" (long strangle) play

On volatile days, often expiry, when directional stops would be 60–80 Sensex points, he buys **one cheap CE and one
cheap PE** (about ₹100–120 each on Sensex, ₹30–60 on Nifty), usually between 12:30 and 2:30.
- Risk is **about half the combined premium**. Targets are roughly +50% to +100% of the combined premium.
- Exit by **booking whichever leg doubles first**, then holding or trailing the other leg as a free ride. Or exit
  once there's any net profit.
- Results in the log: wins on 1 Oct, 22 Sep and 17 Sep (first jori). Losses: 17 Sep (second jori, "complete fail")
  and earlier ones he mentioned in passing. Several ended around cost.

---

## 9. Scorecard: what happened in these 30 streams

All numbers are **option-premium points as he stated or showed them on stream**. This is his narrated record. For the
check against real prices, and a 40% win rate for followers, see [market-check.md](market-check.md). "SCRATCH" means break-even or within a few points.

### Main host: 117 logged calls

| Outcome | Count |
|---|---|
| WIN | 72 |
| LOSS (stop hit) | 17 |
| SCRATCH (≈ break-even) | 13 |
| UNCLEAR (he never said how it ended) | 13 |
| SKIPPED (setup there but R:R too poor) | 2 |

| Metric | Value |
|---|---|
| Win rate, wins ÷ (wins + losses) | **81%**, as narrated |
| Win rate counting scratches as non-wins | 71% |
| Stress test: treat every "unclear" as a loss | **63%** (including scratches) |
| Average / median win | +39 / +35 pts |
| Average / median loss | −20 / −13 pts |
| Realised reward in R (94 calls where the stop is known) | **median 1.9R**, mean 1.7R |
| Calls that reached ≥3R | 22% |
| Calls that lost ≥1R | 13% |
| Nifty options | 37 W / 9 L; avg win +26, avg loss −10; median stop 8 |
| Sensex options | 33 W / 8 L; avg win +55, avg loss −32; median stop 25 |

### Results by how much the market moved

| Nifty day range | Days | Avg narrated net per day | Examples |
|---|---|---|---|
| ≥ 200 pts (volatile) | 7 | **+165 pts** | 30 Sep +430, 1 Oct +300, 28 Sep +168, 15 Sep +135 (but 25 Aug only +7) |
| 120–200 pts | 8 | +120 pts | 17 Sep +300, 5 Aug +245, 21 Sep only +19 |
| < 120 pts (narrow) | 8 | **+49 pts** | 7 Aug +3, 18 Sep +16, 4 Sep +30, 23 Sep +32 (3 losses that morning) |

Over the period, Nifty fell from 24,573 to 22,422 (**−8.8%**). The best days were large down days
(15 Sep −457 pts, 28 Sep −285 pts open-to-close), and most of the biggest wins were **puts**.

### The co-host's numbers
- On 29 Sep the associate said: "**win ratio ~40%**, but we play risk-reward. When we win it's ~137 pts, when we lose
  it's ~15 pts." He also showed a sheet of recent stops: 12, 12, 10, 19, 7, 10, 3, 1, 7, 4, 6 points.
- That 40% is about half the ~80% the narration suggests. The likely reasons: wins get celebrated with viewer
  shout-outs, losses get one line ("kat do, koi baat nahi"), and the unclear trades are probably mostly scratches
  or losses.

---

## 10. Reality check: does he "always predict the right move"?

**No, and he says so himself.** A few things he repeated on stream:
- "Kisi se bhi bahut higher accuracy ki ummeed karke kaam mat karo" (don't trade expecting very high accuracy from
  anyone). Focus on R:R and consistency.
- "Random buy/sell bhi 50% sahi hota hai — edge chhota risk aur achha reward hai" (even random buys and sells are
  right 50% of the time; the edge is small risk with good reward).
- "Hamesha ek-do chhote stop-loss hote hain din men, mayus nahin hona" (there are always one or two small stop-losses
  in a day; don't be disheartened).

Why it **looks** like he's always right:
1. **Plans on both sides.** He calls "CE above X, PE above Y". Whichever triggers becomes "the call".
2. **Small, fast stops.** Losers are cut at 5–15 points and mentioned once. Winners run for 50–100 points with
   viewer P&L shout-outs.
3. **Targets are levels, not promises.** "Target 1:3–1:4" is the distance to the next zone. The realised median was
   about 1:2.
4. **Selective display.** The Telegram calls and "verified P&L" he shows are chosen by him: 38 lakh, 78 lakh,
   95 lakh days. He also runs a much bigger book of delta-neutral and spread strategies, so those P&L figures are
   not from 1-lot option buying like his viewers do.
5. **Market regime.** This was a falling, volatile market, which suits put buyers and momentum entries.
6. **Stream delay.** He says himself that YouTube runs 3–4 seconds late, and entries are given as zones. A viewer's
   fill is usually worse than his.

## 11. The business around the stream (be aware)

- **Broker referral.** The "VIP" Telegram group is free but unlocks only after you open an account through their link
  (Lemon / a "Trading Duniya" page) and place one F&O trade. It auto-renews monthly the same way.
- **Crypto and gold.** He pushes CoinSwitch account opening and a "TCI Crypto Premium" group (~2,000 members).
- **Products.** A zone indicator (sent via WhatsApp) and an "Option Scalping Pro" course, which he describes as free.
- **Channel.** He says it's demonetised and tells viewers not to Super Chat; he asks for likes. The Telegram common
  group has ~76,000 subscribers.
- **Registration.** He says he is a **SEBI-registered Research Analyst** (registered ~2021-22) and stresses he's an
  RA, not an Investment Adviser. The associate claimed RAs can't trade what they recommend. **Verify the registration
  number on SEBI's website** (Intermediaries → Research Analysts) before trusting any "SEBI registered" label.
- Context: SEBI's Sept 2024 study found about **9 in 10 individual F&O traders lost money** over FY22–FY24.

## 12. If you want to use this method: a checklist

Pre-market:
- [ ] Mark yesterday's key zones on Nifty/Sensex: reversal points, consolidation breaks, distribution start, day high/low.
- [ ] Note where the open lands relative to those zones, and the room (points) to the next zone up and down.
- [ ] Pick one CE and one PE near ₹150 (Nifty) or ₹300 (Sensex), slightly ITM. Plot levels on their **option charts**.
- [ ] Write the conditional plan: "CE only above __, stop __, T1 __" and "PE only above __, stop __, T1 __".

Entry (1-min chart):
- [ ] Skip the first 1–2 minutes.
- [ ] Breakout: wait for the breakout candle to close, then enter on the follow-up candle. Never buy the breakout candle itself.
- [ ] Pullback: first green candle or pin bar back at the breakout zone or base.
- [ ] Reversal: only after a liquidity sweep plus W/pin-bar/engulfing and a reclaim of the level.
- [ ] R:R to the next zone is at least 1:2. Stop is about 5–10 pts (Nifty) or 15–25 (Sensex). Otherwise skip.

Management:
- [ ] Stop goes in the system, not in your head.
- [ ] Move to break-even once price has moved about one stop-distance in your favour.
- [ ] Book one lot at T1 and trail the rest under each big candle's base.
- [ ] Two failed attempts on a setup means you're done with it. No third entry.
- [ ] Mid-day: half size. Expiry chop: consider a small strangle with risk capped at half the premium, or nothing.

Before trading real money: **paper-trade this for 30+ sessions** and track *your own* win rate and R per trade. Your
fills will be worse than what's narrated. Risk ~1% of capital per trade. In the market check, copying every call
mechanically roughly broke even after costs. Only Nifty calls stayed slightly positive. See
[market-check.md](market-check.md#can-you-follow-this-from-tomorrow).

## 13. Method and limitations

- **Data.** YouTube auto-generated Hindi captions (`hi-orig`) for the 30 most recent live streams, converted to
  timestamped text, transliterated to Latin script, and filtered to the trade-relevant lines. The 30 Sep and 1 Oct
  streams were read in full; the others were read through trade-related filters plus the full pre-market segment.
- **Prices.** Index bars came from Yahoo Finance (^NSEI, ^BSESN): 1-minute from 4 Sep, 5-minute before that. Option
  contract day OHLC came from the NSE and BSE F&O bhavcopy files. Minute-level option prices were reconstructed by
  fitting a Black-Scholes model to each contract's real day range ([market-check.md](market-check.md)).
- **Limits.** Auto-captions mishear some numbers (for example "2830" for "28–30"), so entries, stops and targets are
  as close as the captions allowed. Outcomes in the scorecard are **as he narrated them**. The market check uses
  reconstructed option prices, not recorded ticks, and there was no broker data on his fills. "Points" are
  option-premium points, which differ between Nifty and Sensex. Trades marked UNCLEAR had no stated outcome.
- I deliberately did **not** commit the raw transcripts. Only summaries and short quotes are here.

*This is research, not investment advice.*
