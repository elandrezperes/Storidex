"""Empaqueta el Worker para Sites sin instalar dependencias de frontend."""
import json
from pathlib import Path

SITE = Path(__file__).resolve().parent
files = {
    "/": ("text/html; charset=utf-8", SITE / "public/index.html"),
    "/app.js": ("text/javascript; charset=utf-8", SITE / "public/app.js"),
    "/style.css": ("text/css; charset=utf-8", SITE / "public/style.css"),
    "/ubicaciones.json": ("application/json; charset=utf-8", SITE.parent / "core/data/ubicaciones.json"),
}
files["/referencias.json"] = (
    "application/json; charset=utf-8", SITE.parent / "core/data/referencias_creativas.json"
)
assets = {url: (mime, path.read_text(encoding="utf-8")) for url, (mime, path) in files.items()}
target = SITE.parent / "dist/server/index.js"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(
    "const assets = " + json.dumps(assets) + ";\n" + (SITE / "worker.js").read_text(encoding="utf-8"),
    encoding="utf-8",
)
print(target)
