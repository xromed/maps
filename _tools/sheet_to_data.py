#!/usr/bin/env python3
"""Реестр статики (Google Sheets) -> statika/data.json.

Источник: таблица «Реестр Статики», лист «Норм реестр статика». Таблица только читается.

    python3 _tools/sheet_to_data.py statika --csv export.csv          # из локального CSV (экспорт листа)
    python3 _tools/sheet_to_data.py statika --sa sa.json              # через Google Sheets API, сервисный аккаунт
    GOOGLE_SA_JSON='{...}' python3 _tools/sheet_to_data.py statika    # ключ из переменной окружения (GitHub Actions)

Лист должен быть расшарен на email сервисного аккаунта (просмотр). Деньги (стоимость, простой в $) в карту не попадают.
Координаты берутся из колонки ГЕО (десятичные, DMS, «40.1°N, 65.3°E»); строки без ГЕО ищутся в <slug>/_geocache.json
по ключу «город|локация»; что не нашлось, пишется в <slug>/_needs_geocoding.csv и <slug>/_unmapped.csv.

Метро: листы «МЕТРО» (количество Slimbox/растяжек/путевых по станциям) и «Метро размеры» дают точки
«Метро: Slimbox» / «Метро: растяжка» / «Метро: путевые» на каждой станции; координаты и линии станций
в <slug>/_metro_stations.json (ключи-алиасы для разных написаний), контрагент и даты из строки «Метро» реестра.
Локальный прогон: --csv реестр.csv --metro-csv metro.csv --sizes-csv sizes.csv
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
# центры городов для проверки ГЕО (точка дальше CITY_RADIUS_KM от своего города не публикуется)
CITY_RADIUS_KM = 30
CITIES = {"ташкент": (41.311, 69.280), "бектемир": (41.21, 69.33), "андижан": (40.783, 72.344), "наманган": (41.000, 71.672), "фергана": (40.386, 71.786),
          "маргилан": (40.471, 71.725), "коканд": (40.529, 70.943), "самарканд": (39.655, 66.959), "каттакурган": (39.899, 66.256), "бухара": (39.768, 64.421),
          "каган": (39.722, 64.551), "гиждуван": (40.100, 64.683), "карши": (38.861, 65.789), "шахрисабз": (39.058, 66.834), "термез": (37.224, 67.278),
          "денау": (38.267, 67.897), "нукус": (42.461, 59.617), "ургенч": (41.550, 60.631), "хива": (41.378, 60.364), "навои": (40.103, 65.374),
          "зарафшан": (41.573, 64.207), "джизак": (40.116, 67.842), "гулистан": (40.489, 68.784), "ангрен": (41.016, 70.143), "чирчик": (41.469, 69.582),
          "алмалык": (40.844, 69.598), "янгиюль": (41.112, 69.047), "нурафшон": (41.040, 69.360), "учкудук": (42.157, 63.556), "турткуль": (41.550, 61.000)}
NOT_SET = "Не указан"


def km(a, b, c, d):
    import math
    p = math.pi / 180
    h = math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2
    return 12742 * math.asin(math.sqrt(h))


def city_ok(city, lat, lon):
    """None, если город неизвестен; иначе расстояние до центра города в км."""
    c = CITIES.get(re.sub(r"\s+", " ", city.lower()).strip())
    return None if not c else km(lat, lon, c[0], c[1])


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


def read_values(sa_info, rng):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    from urllib.parse import quote
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s = AuthorizedSession(creds)
    r = s.get(f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{quote(rng, safe='')}", timeout=60)
    if r.status_code != 200:
        sys.exit(f"Sheets API {r.status_code}: {r.text[:1500]}\n(сервисный аккаунт: {sa_info.get('client_email')})")
    return r.json().get("values", [])


def read_sheet(sa_info):
    return rows_from_values(read_values(sa_info, RANGE))


def csv_values(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return list(csv.reader(io.StringIO(raw.decode(enc))))
        except UnicodeDecodeError:
            continue


# ---------- метро (листы «МЕТРО» и «Метро размеры») ----------
METRO_RANGE, METRO_SIZES_RANGE = "'МЕТРО'!A1:G200", "'Метро размеры'!A1:D300"
METRO_TYPES = [("Slimbox", "Метро: Slimbox"), ("Растяжка", "Метро: растяжка"), ("Путевые", "Метро: путевые")]


def skey(name):
    """Ключ станции: без пробелов, точек, дефисов, в нижнем регистре; снимаем типовые приставки."""
    s = re.sub(r"\(.*?\)", "", str(name or "")).lower()
    s = re.sub(r"(чиланзарская|узбекистанская|юнусабадская)\s+линия,?", "", s)
    s = re.sub(r"станция метро|станция|лайтбокс.*|переход.*", "", s)
    s = re.sub(r"[-–]\s*\d+\s*$", "", s.strip())
    return re.sub(r"[\s.\-'’ʻ`]", "", s)


def metro_points(values, size_values, base, stations, unmapped):
    """values: лист МЕТРО (колонки: пусто, станция, Slimbox, Растяжка, Путевые, пусто, заметка).
    size_values: лист «Метро размеры» (Поверхность, Город, Станция, Размер). base: строка «Метро» из реестра (контрагент, даты)."""
    # размеры по типу и станции
    sizes = {}
    cur = ""
    for row in size_values[1:]:
        row = list(row) + [""] * (4 - len(row))
        head = str(row[0]).strip()
        if head:
            cur = "Slimbox" if "slim" in head.lower() else "Растяжка" if "растяж" in head.lower() else "Путевые" if "путев" in head.lower() else ""
        if not cur or not str(row[2]).strip():
            continue
        k = skey(row[2]); sz = str(row[3]).strip()
        if sz:
            sizes.setdefault((cur, k), [])
            if sz not in sizes[(cur, k)]:
                sizes[(cur, k)].append(sz)
    # количество по станциям (одинаковые названия суммируются)
    counts = {}
    order = []
    for row in values[1:]:
        row = list(row) + [""] * (7 - len(row))
        st = str(row[1]).strip()
        if not st:
            continue
        k = skey(st)
        if k not in counts:
            counts[k] = {"name": st, "n": [0, 0, 0]}; order.append(k)
        for i in range(3):
            try:
                counts[k]["n"][i] += int(float(str(row[2 + i]).replace(",", ".") or 0))
            except ValueError:
                pass
    pts = []
    # ближайший по ключу: справочник хранит несколько алиасов на станцию
    alias = {}
    for sid, st in stations.items():
        for a in [st["name"]] + st.get("aliases", []):
            alias[skey(a)] = sid
    for k in order:
        c = counts[k]; sid = alias.get(k)
        if not sid:
            unmapped.append({"строка": "МЕТРО", "Город": "Ташкент", "Тип носителя": "Метро", "Размер": "", "Локация": c["name"], "ГЕО": "", "причина": "станция не найдена в справочнике _metro_stations.json"})
            continue
        st = stations[sid]
        if not st.get("lat"):
            unmapped.append({"строка": "МЕТРО", "Город": "Ташкент", "Тип носителя": "Метро", "Размер": "", "Локация": st["name"], "ГЕО": "", "причина": "нет координат станции в _metro_stations.json"})
            continue
        for i, (short, typ) in enumerate(METRO_TYPES):
            n = c["n"][i]
            if n <= 0:
                continue
            sz = ", ".join(sizes.get((short, k), []) or sizes.get((short, skey(st["name"])), []))
            props = {f: base.get(f, "") for f in FIELDS}
            props["Размер"] = sz
            props["Комментарий"] = f"{short}: {n} шт на станции. " + (base.get("Комментарий", "") or "")
            pts.append({
                "id": hashlib.md5(f"metro|{sid}|{short}".encode()).hexdigest()[:8],
                "name": f"{typ} ×{n}", "address": f"Ташкент, станция метро {st['name']} ({st['line']} линия)",
                "lat": st["lat"], "lon": st["lon"],
                "cat": {"Тип носителя": typ, "Город": "Ташкент", "Статус по износу": base.get("Статус по износу", "").strip() or NOT_SET, "Контрагент": base.get("Контрагент", "").strip() or NOT_SET},
                "props": props, "accuracy": "exact", "photo": "",
            })
    return pts


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


def build(slug, rows, metro_vals=None, sizes_vals=None):
    os.makedirs(slug, exist_ok=True)
    cache_path = os.path.join(slug, "_geocache.json")
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    st_path = os.path.join(slug, "_metro_stations.json")
    stations = json.load(open(st_path, encoding="utf-8")) if os.path.exists(st_path) else {}
    pts, need, unmapped, bad_geo = [], [], [], []
    metro_base = None
    for i, r in enumerate(rows, 2):  # i = номер строки в листе
        city, loc, kind = r.get("Город", "").strip(), r.get("Локация", "").strip(), r.get("Тип носителя", "").strip()
        if kind.lower() == "метро" and metro_vals:
            metro_base = r  # строка-сводка по метро: контрагент и даты пойдут на все станции
            continue
        geo = parse_geo(r.get("ГЕО", ""))
        acc = "exact"
        if geo and not in_uz(*geo):
            bad_geo.append((i, r.get("ГЕО", ""))); geo = None
        if geo:
            dist = city_ok(city, *geo)
            if dist is not None and dist > CITY_RADIUS_KM:
                unmapped.append({"строка": i, "Город": city, "Тип носителя": kind, "Размер": r.get("Размер", ""), "Локация": loc, "ГЕО": r.get("ГЕО", ""), "причина": f"ГЕО не в городе: {dist:.0f} км от {city}, проверить координаты в реестре"})
                continue
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
            "cat": {c: (r.get(c, "").strip() or NOT_SET) for c in CATS},
            "props": props, "accuracy": acc, "photo": "",
        })
    n_metro = 0
    if metro_vals:
        mp = metro_points(metro_vals, sizes_vals or [], metro_base or {}, stations, unmapped)
        n_metro = len(mp); pts.extend(mp)
    # одинаковые координаты у разных адресов (кроме метро и сторон А/Б одного места): пометить «проверить»
    def addr_key(a):
        a = re.sub(r"\(.*?\)", "", a.lower()); a = re.sub(r"\b(еще|ещё|сторона|а|б|a|b)\b", "", a)
        return re.sub(r"[^a-zа-яё0-9]+", "", a)
    groups = {}
    for p in pts:
        if p["cat"]["Тип носителя"].startswith("Метро") or p["accuracy"] != "exact":
            continue  # метро и наши приблизительные геокоды не считаем
        groups.setdefault((round(p["lat"], 5), round(p["lon"], 5)), []).append(p)
    dups = 0
    for g in groups.values():
        if len({addr_key(p["address"]) for p in g}) > 1:
            for p in g:
                p["accuracy"] = "dup"; dups += 1
    today = datetime.date.today().isoformat()
    d = {
        "title": "Реестр статики", "subtitle": f"{len(pts)} носителей из {len(rows)} строк реестра, {len({p['cat']['Город'] for p in pts})} городов",
        "foot": f"Источник: Google-таблица «Реестр Статики», лист «{SHEET_NAME}». Обновляется автоматически каждый день в 12:00. Обновлено {today}. Без координат: {len(unmapped)} строк.",
        "categories": CATS, "fields": FIELDS, "numbered": False, "cluster_from": 60,
        "accuracy_labels": {"exact": "координаты из реестра", "approx": "найдено по адресу, приблизительно", "building": "найдено по адресу", "dup": "координаты совпадают с другой строкой реестра, проверить"},
        "stale_days": 2, "updated": today,
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
    print(f"{slug}: {len(pts)} точек из {len(rows)} строк (метро: {n_metro}, дублей координат: {dups}); не на карте {len(unmapped)} (из них можно геокодировать {len(need)}); ГЕО вне Узбекистана: {bad_geo or 'нет'}")


def main():
    a = sys.argv[1:]
    slug = a[0] if a and not a[0].startswith("--") else "statika"
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    if "--csv" in a:
        rows = read_csv(opt("--csv"))
        metro = csv_values(opt("--metro-csv")) if opt("--metro-csv") else None
        sizes = csv_values(opt("--sizes-csv")) if opt("--sizes-csv") else None
    else:
        info = json.load(open(opt("--sa"))) if opt("--sa") else json.loads(os.environ["GOOGLE_SA_JSON"])
        rows = read_sheet(info)
        metro = read_values(info, METRO_RANGE)
        sizes = read_values(info, METRO_SIZES_RANGE)
    build(slug, rows, metro, sizes)


if __name__ == "__main__":
    main()
