# 2026: what waiting for a retest or a small pullback would have changed

Every trade the indicator took in 2026 (default: original rules + the volume check), replayed as if we had waited for a retest of the broken level or a small pullback before entering. Same stop price and exit rules. `research/quant/y2026_retest.py`. Points after costs; rupees at 5 lots (delta 0.5).

## Nifty

| Waiting for | Filled | Missed (were winners / losers) | Stop reached first | Net points | Change | Rs at 5 lots |
|---|---|---|---|---|---|---|
| nothing (as traded) | 70 | - | - | +2,214 | - | +359,697 |
| retest | 45 | 18 (18 / 0) | 2 | +1,460 | -753 | +237,281 |
| pullback 10 pts, 15 min | 37 | 33 (31 / 2) | 0 | +1,459 | -754 | +237,145 |
| pullback 10 pts, 30 min | 45 | 25 (24 / 1) | 0 | +1,293 | -921 | +210,075 |
| pullback 10 pts, 60 min | 48 | 22 (22 / 0) | 0 | +1,446 | -768 | +234,968 |
| pullback 20 pts, 15 min | 30 | 40 (37 / 3) | 0 | +914 | -1,300 | +148,490 |
| pullback 20 pts, 30 min | 37 | 33 (31 / 2) | 0 | +1,127 | -1,087 | +183,109 |
| pullback 20 pts, 60 min | 41 | 29 (29 / 0) | 0 | +1,050 | -1,163 | +170,696 |
| pullback 30 pts, 15 min | 15 | 55 (48 / 7) | 0 | +623 | -1,590 | +101,316 |
| pullback 30 pts, 30 min | 19 | 51 (48 / 3) | 0 | +456 | -1,758 | +74,097 |
| pullback 30 pts, 60 min | 32 | 38 (38 / 0) | 0 | +582 | -1,632 | +94,529 |

### Nifty: trade by trade (retest, and a 20-point pullback within 30 minutes)

| Date | Time | Setup | Side | Entry | Result as traded | With a retest | With a pullback |
|---|---|---|---|---|---|---|---|
| 2026-01-02 | 09:32 | breakout | BUY | 26,210.40 | 3:15 time exit: +63 | missed (never came back): -63 | missed (never came back): -63 |
| 2026-01-07 | 09:46 | breakout | SELL | 26,104.30 | stop: -66 | no trade (stop first): +66 | in at 26,124.30: +1 (+67) |
| 2026-01-08 | 09:35 | breakout | SELL | 26,060.80 | 3:15 time exit: +98 | missed (never came back): -98 | in at 26,080.80: +3 (-96) |
| 2026-01-09 | 09:30 | breakout | SELL | 25,839.15 | 3:15 time exit: +83 | missed (never came back): -83 | in at 25,859.15: +6 (-77) |
| 2026-01-20 | 09:35 | breakout | SELL | 25,484.10 | stop at entry: +9 | in at 25,471.36: +10 (+2) | missed (never came back): -9 |
| 2026-01-22 | 09:16 | magnet | SELL | 25,332.45 | stop at entry: +5 | same (no level to retest) | in at 25,352.45: -60 (-65) |
| 2026-01-22 | 10:10 | volume line | SELL | 25,366.15 | target: next line: +135 | in at 25,367.95: +136 (+2) | in at 25,386.15: +155 (+20) |
| 2026-01-22 | 13:55 | volume line | BUY | 25,233.40 | 3:15 time exit: +60 | in at 25,227.50: +66 (+6) | in at 25,213.40: +80 (+20) |
| 2026-01-28 | 13:45 | volume line | SELL | 25,208.35 | stop: -68 | in at 25,213.75: -63 (+5) | in at 25,228.35: -48 (+20) |
| 2026-02-04 | 10:35 | volume line | SELL | 25,726.50 | stop: -70 | in at 25,737.50: -59 (+11) | in at 25,746.50: -50 (+20) |
| 2026-02-05 | 09:39 | breakout | SELL | 25,666.15 | stop at entry: +7 | in at 25,653.32: +9 (+2) | missed (never came back): -7 |
| 2026-02-06 | 09:40 | breakout | SELL | 25,543.45 | stop at entry: +7 | in at 25,540.77: +7 (+0) | in at 25,563.45: +7 (-0) |
| 2026-02-09 | 09:16 | magnet | SELL | 25,832.65 | stop at entry: +6 | same (no level to retest) | missed (never came back): -6 |
| 2026-02-10 | 09:45 | breakout | BUY | 25,949.65 | stop at entry: +6 | in at 25,947.92: +6 (-0) | in at 25,929.65: +4 (-2) |
| 2026-02-13 | 09:40 | breakout | SELL | 25,537.40 | stop at entry: +8 | in at 25,545.52: +7 (-1) | in at 25,557.40: +5 (-2) |
| 2026-02-19 | 11:25 | volume line | SELL | 25,683.25 | target: next line: +147 | in at 25,689.40: +153 (+6) | missed (never came back): -147 |
| 2026-02-20 | 14:30 | volume line | SELL | 25,591.10 | 3:15 time exit: +18 | in at 25,602.50: +29 (+11) | in at 25,611.10: +38 (+20) |
| 2026-02-27 | 09:30 | breakout | SELL | 25,363.40 | 3:15 time exit: +105 | in at 25,350.72: +12 (-93) | in at 25,383.40: +8 (-98) |
| 2026-03-06 | 10:05 | volume line | BUY | 24,635.00 | stop: -52 | in at 24,625.50: -42 (+10) | missed (never came back): +52 |
| 2026-03-06 | 11:05 | volume line | BUY | 24,635.70 | stop: -52 | in at 24,632.50: -49 (+3) | in at 24,615.70: -32 (+20) |
| 2026-03-06 | 12:40 | volume line | SELL | 24,586.15 | target: next line: +125 | in at 24,587.50: +126 (+1) | in at 24,606.15: +145 (+20) |
| 2026-03-11 | 09:55 | volume line | SELL | 24,148.55 | target: next line: +260 | in at 24,157.50: +268 (+9) | in at 24,168.55: +280 (+20) |
| 2026-03-13 | 09:45 | breakout | SELL | 23,415.25 | trailing stop: +24 | in at 23,403.54: +13 (-10) | missed (never came back): -24 |
| 2026-03-23 | 09:54 | breakout | SELL | 22,634.55 | stop at entry: +23 | in at 22,623.23: +25 (+1) | missed (never came back): -23 |
| 2026-03-24 | 11:20 | volume line | BUY | 22,730.45 | 3:15 time exit: +149 | in at 22,702.50: +177 (+28) | in at 22,710.45: +169 (+20) |
| 2026-03-25 | 09:44 | breakout | BUY | 23,268.65 | 3:15 time exit: +39 | missed (never came back): -39 | in at 23,248.65: +47 (+8) |
| 2026-04-01 | 13:25 | volume line | SELL | 22,810.60 | 3:15 time exit: +131 | missed (never came back): -131 | missed (never came back): -131 |
| 2026-04-08 | 09:46 | breakout | BUY | 23,938.85 | stop at entry: +10 | missed (never came back): -10 | in at 23,918.85: +10 (-0) |
| 2026-04-17 | 09:35 | volume line | SELL | 24,196.55 | stop: -105 | in at 24,222.50: -79 (+26) | in at 24,216.55: -85 (+20) |
| 2026-04-21 | 09:45 | breakout | BUY | 24,486.00 | 3:15 time exit: +59 | in at 24,498.24: +55 (-5) | missed (never came back): -59 |
| 2026-04-24 | 09:30 | breakout | SELL | 24,056.60 | 3:15 time exit: +90 | missed (never came back): -90 | missed (never came back): -90 |
| 2026-04-28 | 14:30 | volume line | SELL | 23,997.40 | 3:15 time exit: +24 | in at 24,021.20: +48 (+24) | in at 24,017.40: +44 (+20) |
| 2026-04-29 | 09:50 | breakout | BUY | 24,165.90 | trailing stop: +41 | missed (never came back): -41 | missed (never came back): -41 |
| 2026-05-06 | 12:45 | volume line | SELL | 24,022.30 | stop: -54 | in at 24,032.50: -44 (+10) | in at 24,042.30: -34 (+20) |
| 2026-05-08 | 09:16 | magnet | BUY | 24,198.25 | stop at entry: +5 | same (no level to retest) | in at 24,178.25: +3 (-2) |
| 2026-05-11 | 09:38 | breakout | SELL | 23,895.55 | stop at entry: +7 | in at 23,883.60: +9 (+1) | missed (never came back): -7 |
| 2026-05-12 | 09:30 | breakout | SELL | 23,633.10 | stop at entry: +12 | missed (never came back): -12 | in at 23,653.10: +9 (-2) |
| 2026-05-13 | 09:31 | breakout | SELL | 23,362.45 | stop at entry: +14 | in at 23,350.77: -157 (-171) | in at 23,382.45: +11 (-2) |
| 2026-05-13 | 13:20 | volume line | SELL | 23,505.10 | 3:15 time exit: +79 | in at 23,522.50: +96 (+17) | in at 23,525.10: +99 (+20) |
| 2026-05-14 | 11:35 | volume line | BUY | 23,604.65 | 3:15 time exit: +68 | missed (never came back): -68 | missed (never came back): -68 |
| 2026-05-18 | 11:10 | volume line | BUY | 23,476.40 | target: next line: +167 | in at 23,470.00: +174 (+6) | missed (never came back): -167 |
| 2026-05-19 | 09:16 | magnet | SELL | 23,716.90 | stop at entry: +5 | same (no level to retest) | in at 23,736.90: +2 (-2) |
| 2026-05-26 | 13:05 | volume line | SELL | 23,971.25 | 3:15 time exit: +56 | in at 23,975.05: +60 (+4) | in at 23,991.25: +76 (+20) |
| 2026-06-03 | 09:54 | breakout | SELL | 23,265.25 | stop at entry: +19 | in at 23,253.62: +20 (+1) | in at 23,285.25: +16 (-2) |
| 2026-06-09 | 12:15 | volume line | BUY | 23,187.65 | 3:15 time exit: +46 | in at 23,186.25: +48 (+1) | missed (never came back): -46 |
| 2026-06-17 | 09:38 | breakout | BUY | 24,048.05 | stop at entry: +6 | missed (never came back): -6 | missed (never came back): -6 |
| 2026-06-24 | 11:10 | volume line | BUY | 23,987.55 | 3:15 time exit: +40 | in at 23,967.50: +60 (+20) | in at 23,967.55: +60 (+20) |
| 2026-06-25 | 09:50 | breakout | BUY | 24,169.70 | stop at entry: +4 | missed (never came back): -4 | missed (never came back): -4 |
| 2026-07-01 | 09:50 | volume line | BUY | 23,949.70 | 3:15 time exit: +53 | in at 23,946.35: +56 (+3) | missed (never came back): -53 |
| 2026-07-02 | 09:33 | breakout | BUY | 24,127.60 | stop at entry: +5 | in at 24,139.66: +24 (+19) | in at 24,107.60: +2 (-2) |
| 2026-07-06 | 09:35 | breakout | BUY | 24,370.05 | stop at entry: +6 | in at 24,372.33: +37 (+31) | missed (never came back): -6 |
| 2026-07-10 | 09:34 | breakout | BUY | 24,187.90 | stop at entry: +4 | in at 24,199.99: +6 (+2) | missed (never came back): -4 |
| 2026-07-13 | 12:40 | volume line | BUY | 24,212.10 | stop: -49 | in at 24,209.75: -46 (+2) | missed (never came back): +49 |
| 2026-07-17 | 09:30 | breakout | BUY | 24,211.70 | stop at entry: +10 | in at 24,223.81: +12 (+2) | missed (never came back): -10 |
| 2026-07-22 | 09:31 | breakout | SELL | 24,046.95 | stop at entry: +11 | in at 24,035.75: +12 (+1) | missed (never came back): -11 |
| 2026-07-29 | 09:39 | breakout | BUY | 24,203.20 | stop at entry: +4 | missed (never came back): -4 | missed (never came back): -4 |
| 2026-07-30 | 10:30 | volume line | SELL | 24,232.10 | stop: -44 | in at 24,232.50: -44 (+0) | in at 24,252.10: -24 (+20) |
| 2026-08-04 | 11:50 | volume line | SELL | 24,532.80 | 3:15 time exit: +65 | missed (never came back): -65 | missed (never came back): -65 |
| 2026-08-06 | 09:31 | breakout | BUY | 24,648.20 | stop at entry: +2 | missed (never came back): -2 | in at 24,628.20: -1 (-2) |
| 2026-08-19 | 09:30 | breakout | SELL | 24,093.05 | stop at entry: +6 | in at 24,081.00: +7 (+2) | missed (never came back): -6 |
| 2026-08-20 | 10:20 | volume line | SELL | 24,219.60 | 3:15 time exit: +4 | in at 24,220.00: +4 (+0) | missed (never came back): -4 |
| 2026-08-26 | 09:40 | breakout | BUY | 24,363.20 | stop at entry: +3 | missed (never came back): -3 | in at 24,343.20: -38 (-40) |
| 2026-08-31 | 09:42 | breakout | SELL | 24,036.20 | stop at entry: +8 | in at 24,024.95: +9 (+1) | missed (never came back): -8 |
| 2026-09-01 | 09:44 | breakout | SELL | 24,027.80 | stop at entry: +3 | no trade (stop first): -3 | missed (never came back): -3 |
| 2026-09-07 | 09:54 | breakout | SELL | 23,818.50 | 3:15 time exit: +34 | in at 23,806.59: +30 (-4) | missed (never came back): -34 |
| 2026-09-08 | 09:30 | breakout | SELL | 23,669.20 | stop at entry: +7 | missed (never came back): -7 | in at 23,689.20: +5 (-2) |
| 2026-09-15 | 09:16 | magnet | SELL | 23,492.10 | target: CPR edge: +62 | same (no level to retest) | in at 23,512.10: +69 (+8) |
| 2026-09-28 | 09:30 | breakout | SELL | 22,905.25 | 3:15 time exit: +76 | missed (never came back): -76 | missed (never came back): -76 |
| 2026-09-29 | 09:30 | breakout | SELL | 22,624.20 | stop at entry: +12 | in at 22,612.89: +14 (+1) | missed (never came back): -12 |
| 2026-10-08 | 09:43 | breakout | SELL | 22,475.75 | 3:15 time exit: +141 | in at 22,464.51: +137 (-4) | in at 22,495.75: +149 (+8) |

## Sensex

| Waiting for | Filled | Missed (were winners / losers) | Stop reached first | Net points | Change | Rs at 5 lots |
|---|---|---|---|---|---|---|
| nothing (as traded) | 68 | - | - | +8,001 | - | +400,026 |
| retest | 42 | 19 (18 / 1) | 0 | +4,902 | -3,098 | +245,104 |
| pullback 30 pts, 15 min | 49 | 19 (18 / 1) | 0 | +5,571 | -2,429 | +278,575 |
| pullback 30 pts, 30 min | 55 | 13 (13 / 0) | 0 | +5,083 | -2,917 | +254,154 |
| pullback 30 pts, 60 min | 57 | 11 (11 / 0) | 0 | +5,371 | -2,630 | +268,527 |
| pullback 60 pts, 15 min | 28 | 40 (34 / 6) | 0 | +4,185 | -3,815 | +209,263 |
| pullback 60 pts, 30 min | 37 | 31 (28 / 3) | 0 | +3,796 | -4,204 | +189,823 |
| pullback 60 pts, 60 min | 40 | 28 (27 / 1) | 0 | +3,725 | -4,275 | +186,273 |
| pullback 100 pts, 15 min | 10 | 58 (50 / 8) | 0 | +1,160 | -6,841 | +57,999 |
| pullback 100 pts, 30 min | 21 | 47 (41 / 6) | 0 | +2,310 | -5,690 | +115,502 |
| pullback 100 pts, 60 min | 28 | 40 (36 / 4) | 0 | +3,216 | -4,784 | +160,804 |

### Sensex: trade by trade (retest, and a 60-point pullback within 30 minutes)

| Date | Time | Setup | Side | Entry | Result as traded | With a retest | With a pullback |
|---|---|---|---|---|---|---|---|
| 2026-01-02 | 09:45 | breakout | BUY | 85,525.18 | 3:15 time exit: +153 | missed (never came back): -153 | missed (never came back): -153 |
| 2026-01-13 | 13:00 | volume line | SELL | 83,415.82 | stop: -156 | in at 83,416.00: -156 (+0) | in at 83,475.82: -96 (+60) |
| 2026-01-20 | 09:40 | breakout | SELL | 82,884.17 | 3:15 time exit: +361 | in at 82,893.30: +364 (+3) | in at 82,944.17: +27 (-334) |
| 2026-01-22 | 09:16 | magnet | SELL | 82,488.15 | stop at entry: +19 | same (no level to retest) | in at 82,548.15: -199 (-218) |
| 2026-01-23 | 11:50 | volume line | SELL | 81,991.66 | target: next line: +420 | in at 82,018.00: +446 (+26) | in at 82,051.66: +480 (+60) |
| 2026-02-04 | 14:05 | volume line | SELL | 83,765.34 | 3:15 time exit: -121 | in at 83,784.00: -102 (+19) | in at 83,825.34: -61 (+60) |
| 2026-02-05 | 09:37 | breakout | SELL | 83,502.77 | stop at entry: +23 | in at 83,461.02: +28 (+5) | missed (never came back): -23 |
| 2026-02-06 | 11:50 | volume line | BUY | 83,386.88 | stop: -175 | in at 83,368.00: -156 (+19) | in at 83,326.88: -115 (+60) |
| 2026-02-09 | 09:16 | magnet | SELL | 84,045.02 | stop at entry: +20 | same (no level to retest) | missed (never came back): -20 |
| 2026-02-10 | 09:34 | breakout | BUY | 84,301.52 | stop at entry: +18 | in at 84,343.67: +23 (+5) | missed (never came back): -18 |
| 2026-02-11 | 12:10 | volume line | SELL | 84,239.76 | 3:15 time exit: -19 | in at 84,264.00: +5 (+24) | in at 84,299.76: +41 (+60) |
| 2026-02-12 | 09:30 | breakout | SELL | 83,817.31 | stop at entry: +19 | missed (never came back): -19 | in at 83,877.31: +11 (-8) |
| 2026-02-16 | 13:40 | volume line | BUY | 82,973.10 | 3:15 time exit: +301 | in at 82,959.02: +315 (+14) | in at 82,913.10: +361 (+60) |
| 2026-02-19 | 11:25 | volume line | SELL | 83,262.20 | target: next line: +458 | in at 83,275.36: +471 (+13) | missed (never came back): -458 |
| 2026-02-20 | 14:25 | volume line | SELL | 82,943.50 | 3:15 time exit: +132 | in at 82,968.00: +156 (+24) | in at 83,003.50: +192 (+60) |
| 2026-02-27 | 09:55 | breakout | SELL | 81,812.87 | stop at entry: +42 | in at 81,826.64: +40 (-2) | missed (never came back): -42 |
| 2026-03-06 | 10:50 | volume line | SELL | 79,423.82 | 3:15 time exit: +554 | in at 79,496.00: +626 (+72) | in at 79,483.82: +614 (+60) |
| 2026-03-11 | 09:55 | volume line | SELL | 77,809.40 | target: next line: +701 | missed (never came back): -701 | in at 77,869.40: +761 (+60) |
| 2026-03-13 | 09:47 | breakout | SELL | 75,316.86 | trailing stop: +27 | missed (never came back): -27 | missed (never came back): -27 |
| 2026-03-17 | 09:40 | volume line | BUY | 75,597.11 | stop: -257 | missed (never came back): +257 | missed (never came back): +257 |
| 2026-03-17 | 11:55 | volume line | BUY | 75,516.43 | target: next line: +512 | in at 75,466.32: +562 (+50) | in at 75,456.43: +572 (+60) |
| 2026-03-23 | 09:56 | breakout | SELL | 72,977.34 | stop at entry: +82 | in at 72,940.85: +87 (+5) | missed (never came back): -82 |
| 2026-03-24 | 09:16 | magnet | SELL | 73,760.09 | stop at entry: +16 | same (no level to retest) | missed (never came back): -16 |
| 2026-03-25 | 09:30 | breakout | BUY | 75,002.74 | trailing stop: +242 | missed (never came back): -242 | missed (never came back): -242 |
| 2026-03-27 | 11:25 | volume line | SELL | 74,062.94 | 3:15 time exit: +488 | in at 74,072.00: +497 (+9) | missed (never came back): -488 |
| 2026-04-01 | 09:16 | magnet | SELL | 73,646.16 | stop at entry: +16 | same (no level to retest) | in at 73,706.16: -173 (-189) |
| 2026-04-01 | 13:35 | volume line | SELL | 73,492.65 | 3:15 time exit: +352 | missed (never came back): -352 | missed (never came back): -352 |
| 2026-04-02 | 13:30 | volume line | BUY | 72,494.30 | target: next line: +622 | in at 72,424.00: +692 (+70) | in at 72,434.30: +682 (+60) |
| 2026-04-06 | 12:15 | volume line | SELL | 73,114.44 | stop: -266 | in at 73,128.00: -252 (+14) | in at 73,174.44: -206 (+60) |
| 2026-04-09 | 09:35 | volume line | SELL | 77,071.93 | 3:15 time exit: +434 | missed (never came back): -434 | in at 77,131.93: +494 (+60) |
| 2026-04-17 | 09:35 | volume line | SELL | 78,035.64 | stop: -336 | in at 78,080.00: -292 (+44) | in at 78,095.64: -276 (+60) |
| 2026-04-21 | 09:50 | breakout | BUY | 79,028.18 | 3:15 time exit: +179 | in at 79,005.60: +187 (+8) | missed (never came back): -179 |
| 2026-04-28 | 13:15 | volume line | SELL | 76,979.07 | 3:15 time exit: +179 | in at 76,984.00: +184 (+5) | in at 77,039.07: +239 (+60) |
| 2026-04-29 | 09:50 | breakout | BUY | 77,449.93 | trailing stop: +137 | missed (never came back): -137 | missed (never came back): -137 |
| 2026-05-11 | 09:37 | breakout | SELL | 76,363.74 | stop at entry: +27 | in at 76,325.56: +32 (+5) | missed (never came back): -27 |
| 2026-05-12 | 09:30 | breakout | SELL | 75,328.14 | 3:15 time exit: +441 | missed (never came back): -441 | in at 75,388.14: +32 (-408) |
| 2026-05-13 | 09:31 | breakout | SELL | 74,439.34 | stop at entry: +56 | in at 74,402.12: -591 (-647) | in at 74,499.34: -494 (-550) |
| 2026-05-14 | 11:40 | volume line | BUY | 75,239.70 | 3:15 time exit: +77 | missed (never came back): -77 | missed (never came back): -77 |
| 2026-05-18 | 11:35 | volume line | BUY | 74,906.77 | 3:15 time exit: +336 | in at 74,856.00: +387 (+51) | in at 74,846.77: +396 (+60) |
| 2026-05-19 | 09:16 | magnet | SELL | 75,604.00 | stop at entry: +16 | same (no level to retest) | in at 75,664.00: +9 (-7) |
| 2026-05-19 | 09:35 | volume line | SELL | 75,486.42 | stop: -150 | in at 75,504.00: -132 (+18) | in at 75,546.42: -90 (+60) |
| 2026-05-19 | 13:55 | volume line | SELL | 75,485.55 | target: next line: +206 | in at 75,504.00: +224 (+18) | in at 75,545.55: +266 (+60) |
| 2026-05-21 | 12:40 | volume line | SELL | 75,116.19 | stop: -216 | in at 75,192.00: -140 (+76) | missed (never came back): +216 |
| 2026-05-26 | 12:50 | volume line | SELL | 76,284.83 | 3:15 time exit: +278 | missed (never came back): -278 | missed (never came back): -278 |
| 2026-06-03 | 09:54 | breakout | SELL | 73,833.75 | stop at entry: +72 | in at 73,796.83: +77 (+5) | in at 73,893.75: +65 (-8) |
| 2026-06-19 | 09:16 | magnet | BUY | 76,655.62 | stop at entry: +17 | same (no level to retest) | in at 76,595.62: +9 (-8) |
| 2026-06-23 | 10:25 | volume line | SELL | 77,166.21 | target: next line: +474 | in at 77,168.00: +476 (+2) | missed (never came back): -474 |
| 2026-06-29 | 09:35 | volume line | SELL | 76,892.80 | stop: -215 | in at 76,896.00: -212 (+3) | in at 76,952.80: -155 (+60) |
| 2026-06-29 | 12:05 | volume line | SELL | 76,894.12 | 3:15 time exit: +196 | in at 76,896.00: +198 (+2) | missed (never came back): -196 |
| 2026-07-01 | 09:45 | volume line | BUY | 76,733.15 | target: next line: +335 | in at 76,728.00: +340 (+5) | missed (never came back): -335 |
| 2026-07-02 | 09:33 | breakout | BUY | 77,351.29 | stop at entry: +24 | in at 77,389.97: +73 (+49) | in at 77,291.29: +16 (-8) |
| 2026-07-06 | 09:32 | breakout | BUY | 78,092.21 | stop at entry: +15 | in at 78,131.26: +27 (+13) | missed (never came back): -15 |
| 2026-07-10 | 09:40 | breakout | BUY | 77,526.85 | stop at entry: +14 | missed (never came back): -14 | missed (never came back): -14 |
| 2026-07-17 | 09:30 | breakout | BUY | 77,705.40 | 3:15 time exit: +247 | in at 77,737.59: +235 (-12) | in at 77,645.40: +270 (+22) |
| 2026-07-22 | 09:31 | breakout | SELL | 76,960.68 | stop at entry: +41 | in at 76,922.20: +46 (+5) | missed (never came back): -41 |
| 2026-07-29 | 09:39 | breakout | BUY | 77,559.48 | stop at entry: +16 | in at 77,598.26: +48 (+32) | in at 77,499.48: +85 (+69) |
| 2026-08-06 | 09:30 | breakout | BUY | 78,787.72 | stop at entry: +7 | missed (never came back): -7 | in at 78,727.72: -0 (-8) |
| 2026-08-19 | 09:30 | breakout | SELL | 77,047.45 | stop at entry: +26 | missed (never came back): -26 | missed (never came back): -26 |
| 2026-08-20 | 09:45 | volume line | BUY | 77,480.26 | 3:15 time exit: -7 | in at 77,480.00: -7 (+0) | missed (never came back): +7 |
| 2026-08-26 | 09:41 | breakout | BUY | 77,949.55 | stop at entry: +6 | missed (never came back): -6 | in at 77,889.55: -96 (-102) |
| 2026-08-31 | 09:43 | breakout | SELL | 76,896.93 | stop at entry: +23 | in at 76,858.48: +28 (+5) | missed (never came back): -23 |
| 2026-09-08 | 09:30 | breakout | SELL | 75,720.94 | 3:15 time exit: +88 | missed (never came back): -88 | in at 75,780.94: +17 (-71) |
| 2026-09-10 | 09:31 | breakout | SELL | 74,709.86 | 3:15 time exit: +53 | missed (never came back): -53 | in at 74,769.86: +6 (-48) |
| 2026-09-15 | 09:16 | magnet | SELL | 75,144.24 | target: CPR edge: +238 | same (no level to retest) | in at 75,204.24: +260 (+22) |
| 2026-09-28 | 09:30 | breakout | SELL | 73,155.40 | 3:15 time exit: +236 | missed (never came back): -236 | missed (never came back): -236 |
| 2026-09-29 | 09:31 | breakout | SELL | 72,245.20 | stop at entry: +43 | in at 72,209.08: -283 (-326) | missed (never came back): -43 |
| 2026-09-30 | 12:50 | volume line | BUY | 73,019.12 | stop: -207 | in at 72,980.00: -168 (+39) | in at 72,959.12: -147 (+60) |
| 2026-10-06 | 09:40 | breakout | BUY | 72,594.21 | stop at entry: +14 | in at 72,630.51: +175 (+161) | missed (never came back): -14 |

