#!/usr/bin/env python3
"""PDF-паспорта рекламных мест (Ташкент, Департамент цифрового развития) -> data.json + фото + схемы.

    python3 _tools/passports_to_data.py <slug> file1.pdf file2.pdf ...   [--title ... --subtitle ...]

Из каждого PDF (1 страница A4): № паспорта (CH-xxxxx), адрес (п.7), номер места (п.8), площадь (п.9),
место размещения (п.10), формат (п.11), тип (п.12), стороны (п.13), размеры (п.14), владелец (п.5), даты (п.1-2).
Фото/эскиз (п.15) вырезается в <slug>/photos/<номер>.jpg, схема на OSM-тайлах (п.16) в <slug>/schemes/<номер>.png
(схему смотреть глазами при сверке: точка = центр схемы). Координат в паспорте нет: пишет _needs_geocoding.csv.
Требует poppler-utils (pdftotext, pdftoppm) и Pillow.
"""
import csv, json, os, re, subprocess, sys
from PIL import Image
import numpy as np


def text(pdf):
    return subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True).stdout


def grab(t, pat, flags=re.S):
    m = re.search(pat, t, flags); return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def parse(pdf):
    t = text(pdf)
    num = grab(t, r"№\s*(CH-\d+)")
    # адрес: блок между "Адрес рекламного места" и "3. Chiqarish usuli" в правой колонке — берём строки после заголовка
    seg = t.split("Адрес рекламного места", 1)[1] if "Адрес рекламного места" in t else ""
    addr_lines = []
    for line in seg.splitlines()[1:8]:
        right = line[70:].strip() if len(line) > 70 else ""
        if right and not right.startswith(("8.", "Номер")) and "Reklama joyining raqami" not in right:
            addr_lines.append(right)
        if "8. Reklama joyining raqami" in line or "Номер рекламного места" in line:
            break
    address = re.sub(r"\s+", " ", " ".join(addr_lines)).strip(" ,")
    issued = grab(t, r"Дата выдачи\s+Срок действия.*?(\d{2}\.\d{2}\.\d{4})")
    valid = grab(t, r"Дата выдачи\s+Срок действия.*?\d{2}\.\d{2}\.\d{4}\s+(\d{2}\.\d{2}\.\d{4})")
    place = grab(t, r"([A-Z]-\d{7}-\d{5})")
    area = grab(t, r"(\d+(?:[.,]\d+)?)\s*kv\.m")
    fmt = grab(t, r"Формат конструкции.*?\n.*?\n\s*.*?\s{2,}([А-ЯЁа-яё\- ]+формат)")
    fmt = fmt or ("Сверхбольшой формат" if "Juda katta" in t else "Большой формат" if "Katta format" in t else "")
    kind = "Крышная конструкция (буквы)" if "Tom usti konstruksiya" in t else grab(t, r"Тип конструкции\s+Количество сторон\s+(.+?)\s{2,}")
    sides = grab(t, r"Количество сторон.*?\n.*?\s(\d)\s*$", re.S | re.M)
    size = grab(t, r"Statik\s+([\d.,]+\s*[xх×]\s*[\d.,]+)")
    tech = "Статическая" if "Statik" in t else grab(t, r"Размеры сторон конструкции и технологии\s+(\S+)")
    owner = grab(t, r"ИНН или ПИНФЛ\s+(.+?)\s{2,}")
    owner = re.sub(r"\s+Tom ustida.*", "", owner)
    district = grab(address, r"(\w+)\s+tumani")
    return {
        "id": num, "name": num, "address": address, "issued": issued, "valid": valid, "place": place, "area": area,
        "format": fmt.strip(), "kind": kind, "sides": sides, "size": size.replace("х", "×").replace("x", "×").replace(" ", ""), "tech": tech,
        "owner": owner, "district": district,
    }


def crop_boxes(pdf, outdir, key):
    """Фото (п.15, слева) и схема (п.16, справа) в нижней трети страницы."""
    os.makedirs(os.path.join(outdir, "photos"), exist_ok=True); os.makedirs(os.path.join(outdir, "schemes"), exist_ok=True)
    tmp = os.path.join(outdir, "_page")
    subprocess.run(["pdftoppm", "-r", "150", "-png", "-f", "1", "-l", "1", pdf, tmp], check=True)
    pagefile = tmp + "-1.png"
    im = Image.open(pagefile).convert("RGB"); W, H = im.size
    def box(x0, x1):
        sub = im.crop((x0, int(H * 0.53), x1, int(H * 0.87)))
        a = np.asarray(sub).astype(int); nonwhite = a.sum(axis=2) < 700
        rows = nonwhite.mean(axis=1); cols = nonwhite.mean(axis=0)
        ys = [y for y in range(a.shape[0]) if rows[y] > 0.6]; xs = [x for x in range(a.shape[1]) if cols[x] > 0.5]
        if not ys or not xs: return sub
        y0 = ys[0] + 3; y1 = min(ys[-1] - 3, y0 + int(0.25 * H)); return sub.crop((xs[0] + 3, y0, xs[-1] - 3, y1))
    photo = box(int(W * 0.02), int(W * 0.5)); scheme = box(int(W * 0.5), int(W * 0.98))
    photo.thumbnail((640, 640)); photo.save(os.path.join(outdir, "photos", f"{key}.jpg"), "JPEG", quality=80, optimize=True, progressive=True)
    scheme.save(os.path.join(outdir, "schemes", f"{key}.png"))
    os.remove(pagefile)


def main():
    args = sys.argv[1:]
    opts = {k: v for k, v in zip(args, args[1:]) if k.startswith("--")}
    pos = [a for i, a in enumerate(args) if not a.startswith("--") and (i == 0 or not args[i - 1].startswith("--"))]
    slug, pdfs = pos[0], pos[1:]
    os.makedirs(slug, exist_ok=True)
    pts, todo = [], []
    for pdf in pdfs:
        r = parse(pdf); key = r["id"].split("-")[-1] or os.path.splitext(os.path.basename(pdf))[0]
        try:
            crop_boxes(pdf, slug, key); photo = f"photos/{key}.jpg"
        except Exception as e:
            print("фото не вырезано:", pdf, e); photo = ""
        pts.append({"id": r["id"], "name": f"СН-{key}", "address": r["address"], "lat": None, "lon": None, "photo": photo,
                    "cat": {"Район": r["district"] or "—", "Формат": r["format"] or "—"},
                    "props": {"Размер": r["size"] + " м" if r["size"] else "", "Площадь": (r["area"] + " м²") if r["area"] else "", "Тип": r["kind"],
                              "Стороны": r["sides"], "Технология": r["tech"], "Номер места": r["place"], "Выдан": r["issued"], "Действует до": r["valid"], "Владелец": r["owner"]},
                    "accuracy": "", "file": os.path.basename(pdf)})
        todo.append({"id": r["id"], "name": pts[-1]["name"], "address": r["address"]})
        print(f"{r['id']}: {r['address']} | {r['size']} | {r['area']} м² | {r['format']}")
    d = {"title": opts.get("--title", "Рекламные конструкции"), "subtitle": opts.get("--subtitle", f"{len(pts)} паспортов"), "foot": opts.get("--foot", ""),
         "categories": ["Район", "Формат"], "fields": ["Размер", "Площадь", "Тип", "Стороны", "Номер места", "Выдан", "Действует до", "Владелец"],
         "numbered": True, "cluster_from": 60, "accuracy_labels": {"exact": "адрес подтверждён по OSM", "approx": "по схеме паспорта, ±30 м", "building": "здание подтверждено, позиция условная"},
         "points": pts}
    json.dump(d, open(os.path.join(slug, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(slug, "_needs_geocoding.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "address"]); w.writeheader(); w.writerows(todo)
    print(f"{len(pts)} паспортов -> {slug}/data.json; геокодировать: {slug}/_needs_geocoding.csv; схемы для сверки: {slug}/schemes/")


if __name__ == "__main__":
    main()
