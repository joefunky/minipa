"""Percorsi e utilità condivise."""
import json
from datetime import date
from pathlib import Path

import numpy as np
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
OUTPUT = ROOT / "data" / "output"
MANUAL = ROOT / "data" / "manual"
WEB = ROOT / "web"
for p in (RAW, INTERIM, OUTPUT):
    p.mkdir(parents=True, exist_ok=True)

_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)


def to_utm(lon, lat):
    """lon/lat (EPSG:4326) -> array Nx2 in metri (EPSG:32632)."""
    x, y = _to_utm.transform(np.asarray(lon, float), np.asarray(lat, float))
    return np.column_stack([x, y])


def save_meta(name, **info):
    """Salva accanto al file raw la data di download e la sorgente."""
    info.setdefault("scaricato_il", date.today().isoformat())
    (RAW / f"{name}.meta.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")


def load_meta(name):
    f = RAW / f"{name}.meta.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
