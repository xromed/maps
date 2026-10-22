#!/usr/bin/env python3
"""Реестр статики (Google Sheets) -> statika/data.json.

Источник: таблица «Реестр Статики», лист «Норм реестр статика». Таблица только читается.

    python3 _tools/sheet_to_data.py statika --csv export.csv          # из локального CSV (экспорт листа)
    python3 _tools/sheet_to_data.py statika --sa sa.json              # через Google Sheets API, сервисный аккаунт
    GOOGLE_SA_JSON='{...}' python3 _tools/sheet_to_data.py statika    # ключ из переменной окружения (GitHub Actions)

Лист должен быть расшарен на email сервисного аккаунта (просмотр). Деньги (стоимость, простой в $) в карту не попадают.
Координаты берутся из колонки ГЕО (десятичные, DMS, «40.1°N, 65.3°E»); строки без ГЕО ищутся в <slug>/_geocache.json
по ключу «город|локация»; что не нашлось, пишется в <slug>/_needs_geocoding.csv и <slug>/_unmapped.csv.
"""
import csv, hashlib, io, json, os, re, sys, datetime

SHEET_ID = "1Gpt3qVkAaeASXNBKuO5r4WrbBTse5eYOqj-PnCO8CNI"
SHEET_NAME = "Норм реестр статика"
RANGE = f"'{SHEET_NAME}'!A1:Z2000"

CATS = ["Тип носителя", "Город", "Статус по износу", "Контрагент"]
FIELDS = ["Размер", "Оффер", "Дата начала контракта", "Дата монтажа", "Дата смены имиджа", "Дата осмотра фото", "Комментарий"]
# заголовки листа -> наши названия (в листе есть опечатки и лишние пробелы)
ALIASES = {"Дата Смены Имиджа": "Дата смены имиджа", "Дата осмора фото": "Дата осмотра фото"}
UZ_LAT, UZ_LON = (36.5, 46.0), (55.5, 74.0)


def norm_header(h):
    h = re.sub(r"\s+", " ", str(h or "")).strip()
    return ALIASES.get(h, h)


def rows_from_values(values):
    header = [norm_header(h) for h in values[0]]
    out = []
    for r in values[1:]:
        r = list(r) + [""] * (len(header) - len(r))
        d = {header[i]: (str(r[i]).strip() if r[i] is not None else "") for i in range(len(header)) if header[i]}
        if any(d.get(k) for k in ("Город", "Локация", "ГЕО", "Тип носителя")):
            out.append(d)
    return out


def read_csv(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            txt = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    return rows_from_values(list(csv.reader(io.StringIO(txt))))


def read_sheet(sa_info):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s = AuthorizedSession(creds)
    from urllib.parse import quote
    r = s.get(f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(RANGE, safe='')}", timeout=60)
    r.raise_for_status()
    return rows_from_values(r.json().get("values", []))


def dms(d, m, s, hemi):
    v = float(d) + float(m) / 60 + float(s) / 3600
    return -v if hemi in ("S", "W") else v


def parse_geo(txt):
    """Возвращает (lat, lon) или None."""
    t = (txt or "").replace("\n", " ").replace("’", "'").replace("′", "'").replace("″", '"').replace("''", '"').strip()
    t = t.translate(str.maketrans("ЕНСВ", "ENSW"))  # кириллические двойники букв полушарий
    if not t:
        return None
    m = re.findall(r"(\d{1,3})°\s*(\d{1,2})'\s*(\d{1,2}(?:[.,]\d+)?)\"?\s*([NSEW])", t)
    if len(m) >= 2:
        a = dms(m[0][0], m[0][1], m[0][2].replace(",", "."), m[0][3]); b = dms(m[1][0], m[1][1], m[1][2].replace(",", "."), m[1][3])
        lat, lon = (a, b) if m[0][3] in "NS" else (b, a)
        return lat, lon
    m = re.findall(r"(-?\d{1,3}\.\d+)\s*°?\s*([NSEW])?", t)
    if len(m) >= 2:
        a, b = float(m[0][0]), float(m[1][0])
        if m[0][1] in ("E", "W") or (m[1][1] in ("N", "S")):
            a, b = b, a
        if a > 50 and b < 50:  # перепутаны местами
            a, b = b, a
        return a, b
    return None


def in_uz(lat, lon):
    return UZ_LAT[0] <= lat <= UZ_LAT[1] and UZ_LON[0] <= lon <= UZ_LON[1]


def key_of(city, loc):
    return re.sub(r"\s+", " ", f"{city}|{loc}".lower()).strip()


def build(slug, rows):
    os.makedirs(slug, exist_ok=True)
    cache_path = os.path.join(slug, "_geocache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    pts, need, unmapped, bad_geo = [], [], [], []
    for i, r in enumerate(rows, 2):  # i = номер строки в листе
        city, loc, kind = r.get("Город", "").strip(), r.get("Локация", "").strip(), r.get("Тип носителя", "").strip()
        geo = parse_geo(r.get("ГЕО", ""))
        acc = "exact"
        if geo and not in_uz(*geo):
            bad_geo.append((i, r.get("ГЕО", ""))); geo = None
        if not geo:
            c = cache.get(key_of(city, loc))
            if c and c.get("lat"):
                geo, acc = (c["lat"], c["lon"]), c.get("accuracy", "approx")
        if not geo:
            if loc and kind not in ("Автобусы",):
                need.append({"id": key_of(city, loc), "name": f"{kind} {city}", "address": f"{loc}, {city}"})
            unmapped.append({"строка": i, "Город": city, "Тип носителя": kind, "Размер": r.get("Размер", ""), "Локация": loc, "ГЕО": r.get("ГЕО", ""), "причина": "нет локации" if not loc else "адрес не найден"})
            continue
        name = " ".join(x for x in (kind, r.get("Размер", "")) if x) or f"Строка {i}"
        props = {f: r.get(f, "") for f in FIELDS}
        pts.append({
            "id": hashlib.md5(f"{city}|{loc}|{kind}|{r.get('Размер','')}|{i}".encode()).hexdigest()[:8],
            "name": name, "address": ", ".join(x for x in (city, loc) if x),
            "lat": round(geo[0], 6), "lon": round(geo[1], 6),
            "cat": {c: (r.get(c, "").strip() or "—") for c in CATS},
            "props": props, "accuracy": acc, "photo": "",
        })
    today = datetime.date.today().isoformat()
    d = {
        "title": "Реестр статики", "subtitle": f"{len(pts)} носителей из {len(rows)} строк реестра, {len({p['cat']['Город'] for p in pts})} городов",
        "foot": f"Источник: Google-таблица «Реестр Статики», лист «{SHEET_NAME}». Обновляется автоматически каждый день в 12:00. Обновлено {today}. Без координат: {len(unmapped)} строк.",
        "categories": CATS, "fields": FIELDS, "numbered": False, "cluster_from": 60,
        "accuracy_labels": {"exact": "координаты из реестра", "approx": "найдено по адресу, приблизительно", "building": "найдено по адресу"},
        "points": pts,
    }
    json.dump(d, open(os.path.join(slug, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(slug, "_unmapped.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["строка", "Город", "Тип носителя", "Размер", "Локация", "ГЕО", "причина"], delimiter=";"); w.writeheader(); w.writerows(unmapped)
    seen = set(); need = [n for n in need if not (n["id"] in seen or seen.add(n["id"]))]
    with open(os.path.join(slug, "_needs_geocoding.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "address"]); w.writeheader(); w.writerows(need)
    # дата обновления на главной
    try:
        reg = json.load(open("maps.json", encoding="utf-8"))
        for m in reg["maps"]:
            if m["slug"] == slug:
                m["updated"] = today
        json.dump(reg, open("maps.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    except (OSError, ValueError, KeyError):
        pass
    print(f"{slug}: {len(pts)} точек из {len(rows)} строк; без координат {len(unmapped)} (из них можно геокодировать {len(need)}); ГЕО вне Узбекистана: {bad_geo or 'нет'}")


def main():
    a = sys.argv[1:]
    slug = a[0] if a and not a[0].startswith("--") else "statika"
    if "--csv" in a:
        rows = read_csv(a[a.index("--csv") + 1])
    else:
        info = json.load(open(a[a.index("--sa") + 1])) if "--sa" in a else json.loads(os.environ["GOOGLE_SA_JSON"])
        rows = read_sheet(info)
    build(slug, rows)


if __name__ == "__main__":
    main()
