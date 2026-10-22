#!/usr/bin/env python3
"""Собирает папку карты из канонического data.json.

Использование:
    python3 _tools/build_map.py <slug>            # читает <slug>/data.json, пишет index.html, data.geojson, data.csv
    python3 _tools/build_map.py <slug> --check    # только валидация

Формат data.json (все строки в UTF-8):
{
  "title": "Накрышные буквы",                       # заголовок (hero)
  "subtitle": "9 конструкций, Ташкент",             # подзаголовок
  "foot": "Источник: паспорта ... Обновлено 2026-09-30.",  # мелкий текст внизу панели (HTML допустим)
  "categories": ["Район", "Формат"],                # поля-фильтры по порядку; первое красит маркеры
  "fields": ["Размер", "Площадь", "Выдан"],         # поля, показываемые таблицей в карточке
  "numbered": true,                                 # нумерованные метки + список точек (для < ~60 точек); false = круглые маркеры + кластеры
  "cluster_from": 60,                               # кластеризовать, если точек больше
  "accuracy_labels": {"exact": "адрес подтверждён", "approx": "по схеме, ±30 м"},
  "points": [
    {"name": "CH-16766", "address": "Чиланзар-1, 11", "lat": 41.28652, "lon": 69.22918,
     "photo": "photos/16766.jpg",                     # относительный путь или URL, необязательно
     "cat": {"Район": "Чиланзарский", "Формат": "Большой"},
     "props": {"Размер": "1.3 × 12 м", "Площадь": "15.6 м²", "Выдан": "14.02.2025"},
     "accuracy": "exact",                              # exact | approx | "" (необязательно)
     "id": "CH-16766"}                                 # необязательно, идёт в экспорт
  ]
}
"""
import csv, json, os, sys, html

HERE = os.path.dirname(os.path.abspath(__file__))
V = os.path.join(HERE, "vendor")


def load(slug):
    path = os.path.join(slug, "data.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate(d):
    errs = []
    for k in ("title", "points"):
        if k not in d:
            errs.append(f"нет поля {k}")
    cats = d.get("categories", [])
    for i, p in enumerate(d.get("points", [])):
        for k in ("name", "lat", "lon"):
            if k not in p or p[k] in (None, ""):
                errs.append(f"точка #{i+1} ({p.get('name','?')}): нет {k}")
        try:
            lat, lon = float(p.get("lat", 0)), float(p.get("lon", 0))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                errs.append(f"точка #{i+1}: координаты вне диапазона {lat},{lon}")
            if abs(lat) < 1 and abs(lon) < 1:
                errs.append(f"точка #{i+1}: нулевые координаты")
        except (TypeError, ValueError):
            errs.append(f"точка #{i+1}: координаты не числа")
        for c in cats:
            if not p.get("cat", {}).get(c):
                errs.append(f"точка #{i+1}: пустая категория «{c}»")
    return errs


def compact(d):
    cats = d.get("categories", [])
    fields = d.get("fields", [])
    values = {c: [] for c in cats}
    pts = []
    for p in d["points"]:
        idx = []
        for c in cats:
            v = str(p.get("cat", {}).get(c, "")).strip() or "—"
            if v not in values[c]:
                values[c].append(v)
            idx.append(values[c].index(v))
        pts.append({
            "n": p["name"], "ad": p.get("address", ""), "y": round(float(p["lat"]), 6), "x": round(float(p["lon"]), 6),
            "c": idx, "v": [p.get("props", {}).get(f, "") for f in fields], "ph": p.get("photo", "") or "", "a": p.get("accuracy", "") or "",
        })
    return {
        "cats": [{"name": c, "values": values[c]} for c in cats],
        "fields": fields,
        "points": pts,
        "numbered": bool(d.get("numbered", len(pts) <= 60)),
        "showList": bool(d.get("show_list", len(pts) <= 300)),
        "clusterFrom": int(d.get("cluster_from", 60)),
        "accLabels": d.get("accuracy_labels", {"exact": "адрес подтверждён по OSM", "approx": "координата приблизительная"}),
    }


def build(slug):
    d = load(slug)
    errs = validate(d)
    if errs:
        print("ОШИБКИ:\n  " + "\n  ".join(errs))
        sys.exit(1)
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    page = (tpl.replace("__TITLE__", html.escape(d["title"]))
            .replace("__SUBTITLE__", html.escape(d.get("subtitle", "")))
            .replace("__FOOT__", d.get("foot", ""))
            .replace("__DATA__", json.dumps(compact(d), ensure_ascii=False, separators=(",", ":"))))
    with open(os.path.join(slug, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    # exports
    cats, fields = d.get("categories", []), d.get("fields", [])
    feats = []
    rows = []
    for i, p in enumerate(d["points"], 1):
        props = {"n": i, "id": p.get("id", ""), "name": p["name"], "address": p.get("address", "")}
        props.update({c: p.get("cat", {}).get(c, "") for c in cats})
        props.update({f: p.get("props", {}).get(f, "") for f in fields})
        props.update({"photo": p.get("photo", ""), "accuracy": p.get("accuracy", "")})
        feats.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(p["lon"]), float(p["lat"])]}, "properties": props})
        rows.append({**props, "lat": p["lat"], "lon": p["lon"]})
    with open(os.path.join(slug, "data.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(slug, "data.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["name"], delimiter=";")
        w.writeheader(); w.writerows(rows)
    print(f"OK: {slug}/index.html ({os.path.getsize(os.path.join(slug,'index.html'))//1024} КБ), {len(feats)} точек, data.geojson, data.csv")


def build_index(root="."):
    """Корневая страница со списком карт из maps.json."""
    reg = json.load(open(os.path.join(root, "maps.json"), encoding="utf-8"))
    cards = "".join(
        f'<a class="m" href="{html.escape(m["slug"])}/"><b>{html.escape(m["title"])}</b><span>{html.escape(m.get("subtitle",""))}</span><small>{html.escape(m.get("updated",""))}</small></a>'
        for m in reg["maps"])
    page = f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(reg.get("title","Карты"))}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<style>:root{{--uz:#7000FF;--uz2:#5A00CC;--bg:#F4F4F8;--ink:#1B1B1F;--soft:#6E6E80;--line:#E6E6EE}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;padding:24px 16px}}
.wrap{{max-width:900px;margin:0 auto}} .hero{{background:linear-gradient(135deg,var(--uz),var(--uz2));color:#fff;border-radius:16px;padding:20px 22px;margin-bottom:18px}}
h1{{margin:0 0 4px;font-size:22px}} .hero p{{margin:0;opacity:.85;font-size:13px}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}}
.m{{display:flex;flex-direction:column;gap:4px;background:#fff;border-radius:16px;padding:14px 16px;text-decoration:none;color:inherit;box-shadow:0 1px 2px rgba(27,27,31,.04);border:1.5px solid transparent}}
.m:hover{{border-color:var(--uz)}} .m b{{font-size:15px}} .m span{{color:var(--soft);font-size:12.5px}} .m small{{color:var(--soft);font-size:11px;margin-top:4px}}</style></head>
<body><div class="wrap"><div class="hero"><h1>{html.escape(reg.get("title","Карты"))}</h1><p>{html.escape(reg.get("subtitle",""))}</p></div><div class="g">{cards}</div></div></body></html>"""
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"OK: index.html, {len(reg['maps'])} карт")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__); sys.exit(1)
    if args[0] == "index":
        build_index(); sys.exit(0)
    if "--check" in sys.argv:
        e = validate(load(args[0])); print("OK" if not e else "\n".join(e)); sys.exit(1 if e else 0)
    build(args[0])
