# Инструменты для карт

Одна папка = одна карта: `<slug>/data.json` (источник истины), `index.html` (собирается), `data.geojson`, `data.csv`, `photos/`.
Корневая `index.html` собирается из `maps.json`. Всё, что собирается, пересобирает GitHub Actions (`build.yml`) при пуше data.json/maps.json/_tools,
поэтому в репозиторий достаточно пушить data.json (+ строку в maps.json).

## Конвейер

1. Входные данные → `data.json`
   - таблица xlsx/csv/geojson/kml/gpx: `python3 _tools/table_to_data.py src.xlsx <slug>/data.json --title "..." --cat "Колонка" --field "Колонка"`
   - PDF-паспорта рекламных мест: `python3 _tools/passports_to_data.py <slug> *.pdf --title "..."`
   - фото с EXIF: `python3 _tools/photos_to_data.py <slug> *.jpg`
   - всё остальное: написать data.json руками по схеме в шапке `build_map.py`
2. Геокодинг (только если нет координат): `<slug>/_needs_geocoding.csv` → во встроенном браузере открыть nominatim.openstreetmap.org и выполнить `_tools/geocode_in_browser.js` → ответ сохранить в `<slug>/_geocoded.json` → `python3 _tools/merge_geocoded.py <slug>`. Всё, что не `exact`, сверить глазами (схема/спутник) и поправить координаты в data.json.
3. Сборка: `python3 _tools/build_map.py <slug>` и `python3 _tools/build_map.py index` (после правки `maps.json`).
4. Проверка: открыть `<slug>/index.html` headless-браузером (Playwright) на 1200px и 390px, убедиться, что ошибок JS нет, попап открывается, фильтры считают. После публикации открыть ссылку во встроенном браузере и проверить тайлы и фото.
5. Публикация в ветку `gh-pages` репозитория `xromed/maps`:
   - текст (data.json, maps.json, csv, txt): коннектор GitHub `push_files` или `git push`, если репозиторий добавлен в источники сессии; сборку сделает Actions;
   - бинарники (фото): `git push` при наличии доступа; иначе `<slug>/_assets.txt` со строками `URL -> photos/x.jpg` (workflow `import-assets` скачает), иначе base64-куски в `<slug>/chunks/` (тот же workflow соберёт `photos/<key>.jpg`; куски по 1600 символов с пробелами каждые 8, каждый сверять по blob-SHA через листинг папки).
   - адрес карты: `https://xromed.github.io/maps/<slug>/`

## Формат data.json

См. docstring в `build_map.py`. Главное: `title`, `categories` (фильтры; первое поле красит маркеры), `fields` (таблица в карточке), `points[]` с `name`, `lat`, `lon`, `address`, `photo`, `cat{}`, `props{}`, `accuracy` (exact | approx | building).

## Дизайн

Повторяет filial-atm-map: Inter, акцент #7000FF, левая панель 340px (hero, поиск, карточки фильтров со свотчами и счётчиками, счётчик точек, список точек, скачивание), круглые маркеры по цвету первой категории или нумерованные метки для малых наборов, кластеры от `cluster_from` точек, карточка с фото сверху, на телефоне панель = нижний лист. Подложки: OSM и спутник Esri. Библиотеки Leaflet 1.9.4 и markercluster 1.5.3 грузятся с unpkg.
