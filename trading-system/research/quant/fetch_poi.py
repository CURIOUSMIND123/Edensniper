import json, os, time, subprocess, datetime as dt
days = sorted({k[:10] for k in json.load(open('../.cache/nifty_1m.json'))})
out = json.load(open('../.cache/poi.json')) if os.path.exists('../.cache/poi.json') else {}
for d in days:
    if d in out: continue
    y, m, dd = d.split('-'); url = f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{dd}{m}{y}.csv"
    txt = ''
    for k in range(4):
        r = subprocess.run(['curl', '-sS', '-m', '30', '-A', 'Mozilla/5.0', url], capture_output=True, text=True)
        txt = r.stdout
        if 'Client' in txt: break
        time.sleep(2 ** k)
    rows = {}
    for line in txt.splitlines():
        parts = [p.strip() for p in line.split(',')]
        if parts and parts[0] in ('Client', 'DII', 'FII', 'Pro', 'TOTAL'):
            try: rows[parts[0]] = [int(float(x)) for x in parts[1:15] if x != '']
            except ValueError: pass
    out[d] = rows
    if len(out) % 50 == 0: json.dump(out, open('../.cache/poi.json', 'w')); print(d, len(out), flush=True)
    time.sleep(0.15)
json.dump(out, open('../.cache/poi.json', 'w')); print('done', len(out), sum(1 for v in out.values() if 'FII' in v))
