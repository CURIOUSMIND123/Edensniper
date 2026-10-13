"""The phone app's history: every call of 2026 (default settings, as the alert program takes them) on both indices,
and whether it succeeded: the index went at least 50 Nifty / 150 Sensex points the call's way before the stop loss.

    python y2026_apphistory.py nifty     (and sensex), then: python y2026_apphistory.py
writes ../../alerts/history-2026.json (the app server reads it as the history before it started).
"""
import collections, json, sys

def dump(nm):
    sys.argv = [sys.argv[0], nm]
    import y2026 as Y
    sys.path.insert(0, '../../alerts')
    import cprb_alerts as A
    spec = A.SPEC[nm]; sess = {d: Y.one[d] for d in Y.days}
    vol = collections.defaultdict(dict)
    for k, v in Y.bees.items(): vol[k[:10]][int(k[11:13]) * 60 + int(k[14:16])] = v[4]
    daily = {d: Y.DAY[d] for d in Y.days}
    A.RULES, A.SWEEP = 'classic', False
    out = []
    for d in Y.D26:
        cx = A.context(spec, sess, vol, d, daily); cx['tvol'] = vol.get(d, {})
        for t in A.day_trades(cx, Y.one[d], 929, True, False, 'classic'):
            if t['taken'] and t['exit']:
                ci = A.call_info(cx, t, Y.one[d])
                out.append(dict(d=d, index=cx['name'], time=ci['time'], side=ci['side'], setup=ci['setup'], entry=ci['entry'],
                                stop=ci['stop'], pts=ci['pts'], mfe=ci['mfe'], mae=ci['mae'], success=ci['success'],
                                targets=ci['targets'], hit=ci['hit']))
    json.dump(out, open(f'../.cache/apphist_{nm}.json', 'w'))
    w = sum(r['success'] for r in out)
    print(nm, len(out), 'calls,', w, f'reached the success move ({100 * w / len(out):.0f}%)')

if __name__ == '__main__':
    if len(sys.argv) > 1:
        dump(sys.argv[1]); sys.exit()
    rows = [r for nm in ('nifty', 'sensex') for r in json.load(open(f'../.cache/apphist_{nm}.json'))]
    rows.sort(key=lambda r: (r['d'], r['time'], r['index']))
    json.dump(rows, open('../../alerts/history-2026.json', 'w'), separators=(',', ':'))
    print(len(rows), 'calls written to alerts/history-2026.json')
