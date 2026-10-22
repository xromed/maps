#!/usr/bin/env python3
"""Таблица (xlsx/csv/tsv/geojson/kml/gpx) -> канонический data.json.

    python3 _tools/table_to_data.py input.xlsx out/data.json --title "..." --subtitle "..." \
        --name "Название" --address "Адрес" --lat "Широта" --lon "Долгота" \
        --cat "Банк" --cat "Тип" --field "Телефон" --field "Режим" --photo "Фото" --id "ID"

Колонки угадываются по названию, если флаги не заданы (name/название/наименование, адрес/address,
lat/широта/latitude, lon/lng/долгота/longitude, фото/photo/image, категория/тип/type/category).
Точки без координат попадают в out/_needs_geocoding.csv (их геокодирует geocode_in_browser.js),
после чего результат сливается через merge_geocoded.py.
Требует: pip install openpyxl (для xlsx).
"""
import argparse, csv, json, os, re, sys


def read_rows(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(next(it))]
        return [dict(zip(header, [("" if v is None else v) for v in r])) for r in it if any(v not in (None, "") for v in r)]
    if ext in (".csv", ".tsv", ".txt"):
        raw = open(path, "rb").read()
        for enc in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                txt = raw.decode(enc); break
            except UnicodeDecodeError:
                continue
        dialect = csv.Sniffer().sniff(txt[:5000], delimiters=";,\t|")
        return list(csv.DictReader(txt.splitlines(), dialect=dialect))
    if ext == ".geojson" or ext == ".json":
        gj = json.load(open(path, encoding="utf-8"))
        rows = []
        for f in gj.get("features", []):
            g = f.get("geometry") or {}
            if g.get("type") != "Point":
                continue
            r = dict(f.get("properties") or {}); r["lon"], r["lat"] = g["coordinates"][:2]
            rows.append(r)
        return rows
    if ext in (".kml", ".gpx"):
        import xml.etree.ElementTree as ET
        t = ET.parse(path); ns = {"k": "http://www.opengis.net/kml/2.2", "g": "http://www.topografix.com/GPX/1/1"}
        rows = []
        for pm in t.iter("{http://www.opengis.net/kml/2.2}Placemark"):
            c = pm.find(".//k:coordinates", ns)
            if c is None: continue
            lon, lat = [float(x) for x in c.text.strip().split(",")[:2]]
            rows.append({"name": (pm.findtext("k:name", "", ns) or "").strip(), "description": (pm.findtext("k:description", "", ns) or "").strip(), "lat": lat, "lon": lon})
        for wp in t.iter("{http://www.topografix.com/GPX/1/1}wpt"):
            rows.append({"name": wp.findtext("g:name", "", ns), "description": wp.findtext("g:desc", "", ns), "lat": float(wp.get("lat")), "lon": float(wp.get("lon"))})
        return rows
    sys.exit(f"неизвестный формат: {ext}")


GUESS = {
    "name": ["name", "название", "наименование", "объект", "точка", "title"],
    "address": ["address", "адрес", "адреса", "manzil", "местоположение"],
    "lat": ["lat", "latitude", "широта", "y"],
    "lon": ["lon", "lng", "long", "longitude", "долгота", "x"],
    "photo": ["photo", "фото", "image", "картинка", "img"],
    "id": ["id", "код", "номер", "№"],
}


def guess(cols, key):
    low = {c.lower().strip(): c for c in cols}
    for g in GUESS[key]:
        if g in low: return low[g]
    for c in cols:
        if any(g in c.lower() for g in GUESS[key]): return c
    return None


def num(v):
    if v in (None, ""): return None
    s = str(v).strip().replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--title", default="Карта"); ap.add_argument("--subtitle", default=""); ap.add_argument("--foot", default="")
    for k in ("name", "address", "lat", "lon", "photo", "id", "coords"):
        ap.add_argument("--" + k)
    ap.add_argument("--cat", action="append", default=[]); ap.add_argument("--field", action="append", default=[])
    ap.add_argument("--all-fields", action="store_true", help="все остальные колонки в карточку")
    a = ap.parse_args()
    rows = read_rows(a.src)
    if not rows: sys.exit("пустая таблица")
    cols = list(rows[0].keys())
    col = {k: getattr(a, k) or guess(cols, k) for k in ("name", "address", "lat", "lon", "photo", "id")}
    print("колонки:", col, "| категории:", a.cat, "| поля:", a.field or ("все" if a.all_fields else "нет"))
    used = set(v for v in col.values() if v) | set(a.cat) | set(a.field) | ({a.coords} if a.coords else set())
    fields = a.field or ([c for c in cols if c not in used] if a.all_fields else [])
    pts, todo = [], []
    for i, r in enumerate(rows, 1):
        lat = lon = None
        if a.coords and r.get(a.coords):
            mm = re.findall(r"-?\d+(?:[.,]\d+)?", str(r[a.coords]))
            if len(mm) >= 2: lat, lon = num(mm[0]), num(mm[1])
        if lat is None and col["lat"] and col["lon"]:
            lat, lon = num(r.get(col["lat"])), num(r.get(col["lon"]))
        p = {
            "id": str(r.get(col["id"], "") if col["id"] else "").strip() or str(i),
            "name": str(r.get(col["name"], "") if col["name"] else "").strip() or f"Точка {i}",
            "address": str(r.get(col["address"], "") if col["address"] else "").strip(),
            "lat": lat, "lon": lon,
            "photo": str(r.get(col["photo"], "") if col["photo"] else "").strip(),
            "cat": {c: str(r.get(c, "")).strip() or "—" for c in a.cat},
            "props": {f: ("" if r.get(f) in (None, "") else str(r.get(f)).strip()) for f in fields},
            "accuracy": "exact" if lat is not None else "",
        }
        pts.append(p)
        if lat is None or lon is None:
            todo.append({"id": p["id"], "name": p["name"], "address": p["address"]})
    d = {"title": a.title, "subtitle": a.subtitle, "foot": a.foot, "categories": a.cat, "fields": fields,
         "numbered": len(pts) <= 60, "cluster_from": 60, "points": pts}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    json.dump(d, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(pts)} точек -> {a.out}; с координатами: {len(pts)-len(todo)}, нужно геокодировать: {len(todo)}")
    if todo:
        tp = os.path.join(os.path.dirname(a.out) or ".", "_needs_geocoding.csv")
        with open(tp, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "name", "address"]); w.writeheader(); w.writerows(todo)
        print("адреса для геокодинга:", tp)


if __name__ == "__main__":
    main()
