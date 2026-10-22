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
    """Корневая страница (микросайт) со списком карт из maps.json.

    maps.json: {"title", "subtitle", "maps": [{"slug", "title", "subtitle", "tags": [...], "updated": "ГГГГ-ММ-ДД"}]}
    Для каждой карты читается <slug>/data.json: число точек и координаты для мини-карты в карточке.
    На странице: поиск по названию/описанию/тегам, фильтр по тегам, карточки с мини-картой (OSM), числом точек и датой.
    """
    reg = json.load(open(os.path.join(root, "maps.json"), encoding="utf-8"))
    items = []
    for m in reg["maps"]:
        slug = m["slug"]
        pts = []
        try:
            d = json.load(open(os.path.join(root, slug, "data.json"), encoding="utf-8"))
            pts = [[round(float(p["lat"]), 5), round(float(p["lon"]), 5)] for p in d.get("points", []) if p.get("lat") not in (None, "") and p.get("lon") not in (None, "")]
        except (OSError, ValueError, KeyError):
            pass
        n = len(pts)
        step = max(1, n // 300)  # в превью не больше ~300 точек
        items.append({"slug": slug, "title": m["title"], "subtitle": m.get("subtitle", ""), "tags": m.get("tags", []),
                      "updated": m.get("updated", ""), "n": n, "pts": pts[::step]})
    tags = []
    for it in items:
        for t in it["tags"]:
            if t not in tags: tags.append(t)
    data = json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":"))
    title, sub = html.escape(reg.get("title", "Карты")), html.escape(reg.get("subtitle", ""))
    total = sum(i["n"] for i in items)
    page = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<meta name="robots" content="noindex, nofollow">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{--uz:#7000FF;--uz2:#5A00CC;--bg:#F4F4F8;--ink:#1B1B1F;--soft:#6E6E80;--line:#E6E6EE;--card:#fff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;padding:24px 16px 48px}
.wrap{max-width:1080px;margin:0 auto}
.hero{background:linear-gradient(135deg,var(--uz),var(--uz2));color:#fff;border-radius:20px;padding:24px 24px 20px;margin-bottom:16px;box-shadow:0 8px 24px rgba(112,0,255,.18)}
h1{margin:0 0 4px;font-size:26px;letter-spacing:-.01em}
.hero p{margin:0 0 14px;opacity:.85;font-size:13.5px;max-width:640px}
.stats{display:flex;gap:14px;font-size:12.5px;opacity:.9;margin-bottom:14px}
.stats b{font-size:18px;display:block;line-height:1.1}
.search{display:flex;align-items:center;gap:8px;background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.28);border-radius:12px;padding:0 12px}
.search input{flex:1;background:none;border:0;outline:0;color:#fff;font:inherit;font-size:14px;padding:11px 0}
.search input::placeholder{color:rgba(255,255,255,.7)}
.search svg{flex:none;opacity:.8}
.tags{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 16px}
.tag{border:1.5px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:6px 12px;font:inherit;font-size:12.5px;font-weight:500;cursor:pointer}
.tag.on{background:var(--uz);border-color:var(--uz);color:#fff}
.g{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.m{display:flex;flex-direction:column;background:var(--card);border-radius:16px;overflow:hidden;text-decoration:none;color:inherit;box-shadow:0 1px 2px rgba(27,27,31,.05);border:1.5px solid transparent;transition:transform .15s,border-color .15s,box-shadow .15s}
.m:hover{border-color:var(--uz);transform:translateY(-2px);box-shadow:0 10px 24px rgba(27,27,31,.08)}
.mini{height:170px;background:linear-gradient(135deg,#ece6ff,#f7f4ff);position:relative;pointer-events:none}
.mini .leaflet-container{background:#ece6ff;font:inherit}
.mini .cnt{position:absolute;right:10px;top:10px;z-index:500;background:var(--uz);color:#fff;font-size:12px;font-weight:600;border-radius:999px;padding:3px 9px;box-shadow:0 2px 6px rgba(0,0,0,.18)}
.body{padding:12px 14px 14px;display:flex;flex-direction:column;gap:6px}
.m b{font-size:15.5px;line-height:1.25}
.m span.sub{color:var(--soft);font-size:12.5px;line-height:1.4}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;align-items:center}
.chip{font-size:11px;font-weight:500;border-radius:999px;padding:3px 8px;background:#F0EAFF;color:var(--uz2)}
.date{margin-left:auto;color:var(--soft);font-size:11.5px}
.empty{display:none;color:var(--soft);text-align:center;padding:40px 0}
.empty.show{display:block}
.foot{color:var(--soft);font-size:11.5px;margin-top:28px;text-align:center}
.foot a{color:var(--uz)}
@media(max-width:600px){body{padding:12px 12px 32px}.hero{padding:18px 16px 16px;border-radius:16px}h1{font-size:22px}.g{grid-template-columns:1fr}}
</style></head>
<body><div class="wrap">
<div class="hero"><h1>__TITLE__</h1><p>__SUB__</p>
<div class="stats"><div><b id="nMaps">0</b><span id="lMaps">карт</span></div><div><b id="nPts">0</b><span id="lPts">точек</span></div></div>
<label class="search"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><input id="q" type="search" placeholder="Поиск по картам: название, описание, тег" autocomplete="off"></label></div>
<div class="tags" id="tags"></div>
<div class="g" id="grid"></div>
<div class="empty" id="empty">Ничего не найдено</div>
<div class="foot">Карты на <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>. Данные каждой карты доступны в GeoJSON и CSV на её странице.</div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const D=__DATA__;
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const plural=(n,a,b,c)=>{const m=n%100;if(m>=11&&m<=19)return c;const k=n%10;return k==1?a:(k>=2&&k<=4)?b:c};
const fmtDate=s=>{if(!/^\\d{4}-\\d{2}-\\d{2}$/.test(s))return s||'';const [y,m,d]=s.split('-');return `${d}.${m}.${y}`};
const grid=document.getElementById('grid'),tagsEl=document.getElementById('tags'),q=document.getElementById('q'),empty=document.getElementById('empty');
const allTags=[];D.items.forEach(i=>(i.tags||[]).forEach(t=>{if(!allTags.includes(t))allTags.push(t)}));
let tag='';
if(allTags.length){tagsEl.innerHTML=['<button class="tag on" data-t="">Все</button>'].concat(allTags.map(t=>`<button class="tag" data-t="${esc(t)}">${esc(t)}</button>`)).join('');
 tagsEl.addEventListener('click',e=>{const b=e.target.closest('.tag');if(!b)return;tag=b.dataset.t;tagsEl.querySelectorAll('.tag').forEach(x=>x.classList.toggle('on',x===b));render()});}
const nM=D.items.length,nP=D.items.reduce((s,i)=>s+i.n,0);
document.getElementById('nMaps').textContent=nM;document.getElementById('lMaps').textContent=plural(nM,'карта','карты','карт');
document.getElementById('nPts').textContent=nP;document.getElementById('lPts').textContent=plural(nP,'точка','точки','точек');
function card(i){
 const chips=(i.tags||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join('');
 return `<a class="m" href="${esc(i.slug)}/" data-slug="${esc(i.slug)}"><div class="mini" id="mini-${esc(i.slug)}"><span class="cnt">${i.n} ${plural(i.n,'точка','точки','точек')}</span></div>
 <div class="body"><b>${esc(i.title)}</b><span class="sub">${esc(i.subtitle||'')}</span><div class="meta">${chips}<span class="date">${esc(fmtDate(i.updated))}</span></div></div></a>`;}
function render(){
 const s=q.value.trim().toLowerCase();
 const list=D.items.filter(i=>(!tag||(i.tags||[]).includes(tag))&&(!s||(i.title+' '+(i.subtitle||'')+' '+(i.tags||[]).join(' ')).toLowerCase().includes(s)));
 grid.innerHTML=list.map(card).join('');empty.classList.toggle('show',!list.length);
 if(!window.L)return;
 list.forEach(i=>{if(!i.pts.length)return;const el=document.getElementById('mini-'+i.slug);
  const map=L.map(el,{zoomControl:false,attributionControl:false,dragging:false,scrollWheelZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false,touchZoom:false,tap:false,preferCanvas:true});
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);
  i.pts.forEach(p=>L.circleMarker(p,{radius:i.pts.length>80?3:5,color:'#fff',weight:1.5,fillColor:'#7000FF',fillOpacity:.95}).addTo(map));
  map.fitBounds(L.latLngBounds(i.pts),{padding:[22,22],maxZoom:15});});
}
q.addEventListener('input',render);render();
</script></body></html>"""
    page = page.replace("__TITLE__", title).replace("__SUB__", sub).replace("__DATA__", data)
    with open(os.path.join(root, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"OK: index.html, {len(items)} карт, {total} точек, теги: {', '.join(tags) or 'нет'}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__); sys.exit(1)
    if args[0] == "index":
        build_index(); sys.exit(0)
    if "--check" in sys.argv:
        e = validate(load(args[0])); print("OK" if not e else "\n".join(e)); sys.exit(1 if e else 0)
    build(args[0])
