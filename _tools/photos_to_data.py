#!/usr/bin/env python3
"""Фото с геометками (EXIF GPS) -> data.json. Снимки сжимаются в <slug>/photos/.

    python3 _tools/photos_to_data.py <slug> IMG_*.jpg [--title ... --cat-from-folder]

Без EXIF-координат точка попадает в _needs_geocoding.csv с пустым адресом: для таких снимков
(например, TimeMark с наложенным адресом в кадре) адрес читается с картинки глазами и дописывается в data.json.
Требует Pillow.
"""
import csv, json, os, sys
from PIL import Image, ExifTags


def gps(im):
    ex = im.getexif()
    g = ex.get_ifd(0x8825) if hasattr(ex, "get_ifd") else None
    if not g: return None, None
    def dec(v, ref):
        d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
        return -d if ref in ("S", "W") else d
    try:
        return dec(g[2], g[1]), dec(g[4], g[3])
    except Exception:
        return None, None


def main():
    args = sys.argv[1:]; opts = {k: v for k, v in zip(args, args[1:]) if k.startswith("--")}
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--"))]
    slug, files = pos[0], pos[1:]
    os.makedirs(os.path.join(slug, "photos"), exist_ok=True)
    pts, todo = [], []
    for i, f in enumerate(files, 1):
        im = Image.open(f); lat, lon = gps(im)
        ex = im.getexif(); dt = str(ex.get(306, ""))
        key = os.path.splitext(os.path.basename(f))[0]
        from PIL import ImageOps
        im = ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((900, 900))
        im.save(os.path.join(slug, "photos", key + ".jpg"), "JPEG", quality=80, optimize=True, progressive=True)
        cat = os.path.basename(os.path.dirname(os.path.abspath(f))) if "--cat-from-folder" in args else "Фото"
        p = {"id": key, "name": key, "address": "", "lat": lat, "lon": lon, "photo": f"photos/{key}.jpg", "cat": {"Группа": cat},
             "props": {"Снято": dt}, "accuracy": "exact" if lat else ""}
        pts.append(p)
        if lat is None: todo.append({"id": key, "name": key, "address": ""})
        print(f"{key}: {lat}, {lon} {dt}")
    d = {"title": opts.get("--title", "Фото на карте"), "subtitle": opts.get("--subtitle", f"{len(pts)} снимков"), "foot": opts.get("--foot", ""),
         "categories": ["Группа"], "fields": ["Снято"], "numbered": len(pts) <= 60, "cluster_from": 60, "points": pts}
    json.dump(d, open(os.path.join(slug, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if todo:
        with open(os.path.join(slug, "_needs_geocoding.csv"), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id", "name", "address"]); w.writeheader(); w.writerows(todo)
    print(f"{len(pts)} фото, без GPS: {len(todo)}")


if __name__ == "__main__":
    main()
