// Пакетный геокодинг через Nominatim из ВСТРОЕННОГО БРАУЗЕРА Claude (из облачной среды Nominatim закрыт).
// 1) Открыть вкладку https://nominatim.openstreetmap.org/search?q=Tashkent&format=json  (любая страница этого домена).
// 2) Выполнить этот код через javascript_tool, подставив массив ITEMS: [{id, address}, ...]  (до ~150 за раз, 1.1 с на адрес).
// 3) Результат (JSON) сохранить в <slug>/_geocoded.json и слить: python3 _tools/merge_geocoded.py <slug>
//
// Стратегия на адрес: полный адрес -> без номера дома -> только улица+город. Возвращает class/type и bbox,
// чтобы отличить дом (building, exact) от улицы/района (approx). Всё, что не building, помечается approx
// и подлежит ручной сверке (схема в паспорте, спутник, Google).
const ITEMS = __ITEMS__;           // например [{"id":"1","address":"Toshkent shahri, Chilonzor tumani, Chilonzor-I, 11"}]
const CITY = "Tashkent";           // подставляется, если в адресе нет города
const sleep = ms => new Promise(r => setTimeout(r, ms));
const norm = s => s.replace(/Toshkent shahri,?/i, "Tashkent,").replace(/\btumani\b/gi, "district").replace(/\bmahallasi\b|\bmahalla\b|\bMFY\b/gi, "").replace(/\bko'chasi\b|\bko‘chasi\b|\bkoʻchasi\b/gi, "street").replace(/\bmavzesi\b/gi, "").replace(/\s+,/g, ",").replace(/,\s*,/g, ",").trim();
async function q(s) {
  const r = await fetch("/search?" + new URLSearchParams({ q: s, format: "json", limit: 3, addressdetails: 1 }), { headers: { "Accept-Language": "ru" } });
  if (!r.ok) return [];
  return r.json();
}
const out = [];
for (const it of ITEMS) {
  const a0 = it.address || "";
  const withCity = /tashkent|toshkent|ташкент/i.test(a0) ? a0 : a0 + ", " + CITY;
  const variants = [withCity, norm(withCity), norm(withCity).replace(/,\s*\d+[a-zA-Zа-я/]*\s*$/, ""), norm(withCity).split(",").slice(-3).join(",")];
  let hit = null, used = null;
  for (const v of variants) {
    const res = await q(v); await sleep(1100);
    if (res.length) { hit = res[0]; used = v; break; }
  }
  out.push(hit ? { id: it.id, address: a0, lat: +hit.lat, lon: +hit.lon, osm_class: hit.class, osm_type: hit.type, display: hit.display_name, query: used,
                   accuracy: (hit.class === "building" || hit.type === "house" || hit.addresstype === "building") ? "exact" : "approx" }
                : { id: it.id, address: a0, lat: null, lon: null, accuracy: "", display: "НЕ НАЙДЕНО" });
}
JSON.stringify(out);
