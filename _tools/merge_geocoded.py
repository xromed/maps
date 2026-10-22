#!/usr/bin/env python3
"""Сливает результат геокодинга (<slug>/_geocoded.json из geocode_in_browser.js) в <slug>/data.json по id.
    python3 _tools/merge_geocoded.py <slug>
Печатает список approx/не найденных для ручной сверки."""
import json, os, sys

slug = sys.argv[1]
dp = os.path.join(slug, "data.json"); gp = os.path.join(slug, "_geocoded.json")
d = json.load(open(dp, encoding="utf-8")); g = {str(x["id"]): x for x in json.load(open(gp, encoding="utf-8"))}
upd = miss = appr = 0
for p in d["points"]:
    r = g.get(str(p.get("id")))
    if not r: continue
    if r.get("lat") is None:
        miss += 1; print(f"НЕ НАЙДЕНО: {p['id']} | {p.get('address')}"); continue
    if p.get("lat") in (None, ""):
        p["lat"], p["lon"], p["accuracy"] = r["lat"], r["lon"], r.get("accuracy", "approx"); upd += 1
        if p["accuracy"] != "exact":
            appr += 1; print(f"ПРОВЕРИТЬ ({r.get('osm_class')}/{r.get('osm_type')}): {p['id']} | {p.get('address')} -> {r['lat']:.5f},{r['lon']:.5f} | {r.get('display','')[:80]}")
json.dump(d, open(dp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"обновлено {upd}, приблизительных {appr}, не найдено {miss}")
