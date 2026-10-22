#!/usr/bin/env python3
"""Выполняется в GitHub Actions. Два канала доставки бинарников:
1) <slug>/_assets.txt: строки `https://... -> photos/name.jpg` (пути относительно папки карты). Скачивает (до 20 МБ), удаляет строку после успеха.
2) <slug>/chunks/<key>.NN: base64-куски (пробелы/переносы игнорируются) -> <slug>/photos/<key>.jpg (+ .svg-обёртка). Для случая, когда файл негде разместить публично.
"""
import base64, glob, os, struct, urllib.request

for af in glob.glob("*/_assets.txt"):
    slug = os.path.dirname(af); keep = []
    for line in open(af, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"): continue
        try:
            url, dst = [x.strip() for x in line.split("->", 1)]
            out = os.path.normpath(os.path.join(slug, dst)); assert out.startswith(slug + os.sep)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "maps-import/1.0"})
            data = urllib.request.urlopen(req, timeout=60).read(20 * 1024 * 1024)
            open(out, "wb").write(data); print(f"OK {url} -> {out} ({len(data)} b)")
        except Exception as e:
            print(f"FAIL {line}: {e}"); keep.append(line)
    open(af, "w", encoding="utf-8").write("\n".join(keep) + ("\n" if keep else ""))

for cdir in glob.glob("*/chunks"):
    slug = os.path.dirname(cdir); os.makedirs(os.path.join(slug, "photos"), exist_ok=True)
    keys = sorted({os.path.basename(p).split(".")[0] for p in glob.glob(cdir + "/*")})
    for key in keys:
        parts = sorted(glob.glob(f"{cdir}/{key}.*"))
        b64 = "".join("".join(open(p).read().split()) for p in parts)
        try:
            data = base64.b64decode(b64, validate=True)
        except Exception as e:
            print(f"{key}: BAD BASE64 {e}"); continue
        if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
            print(f"{key}: не полный JPEG, пропуск"); continue
        w = h = 0; i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF: break
            m = data[i + 1]; L = struct.unpack(">H", data[i + 2:i + 4])[0]
            if m in (0xC0, 0xC1, 0xC2): h, w = struct.unpack(">HH", data[i + 5:i + 9]); break
            i += 2 + L
        open(os.path.join(slug, "photos", key + ".jpg"), "wb").write(data)
        open(os.path.join(slug, "photos", key + ".svg"), "w").write(
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><image width="{w}" height="{h}" xlink:href="data:image/jpeg;base64,{b64}"/></svg>')
        print(f"{key}: {w}x{h}, {len(data)} b из {len(parts)} кусков")
