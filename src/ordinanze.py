"""Fonte C: zone delle ordinanze movida/asporto -> GeoJSON.

La v1 usa data/manual/zone_movida.csv: un punto centrale e un raggio per zona,
ricavati dall'elenco delle zone dell'ordinanza estiva 2026 (11/06-02/11/2026)
e di quella Duomo/Arco della Pace (31/07-29/08/2026). È un'approssimazione:
le planimetrie ufficiali allegate alle ordinanze non sono state digitalizzate.
Per migliorare: sostituire il CSV con data/manual/zone_movida.geojson
(poligoni veri); questo modulo lo usa per primo se esiste.
"""
import json

import numpy as np
import pandas as pd

from .common import INTERIM, MANUAL, to_utm


def load_zones():
    gj = MANUAL / "zone_movida.geojson"
    if gj.exists():
        return json.loads(gj.read_text(encoding="utf-8")), "poligoni"
    z = pd.read_csv(MANUAL / "zone_movida.csv")
    feats = []
    for r in z.itertuples():
        # cerchio come poligono a 32 lati (approssimato in gradi, solo per la mappa)
        t = np.linspace(0, 2 * np.pi, 33)
        dlat = r.raggio_m / 111_320
        dlon = r.raggio_m / (111_320 * np.cos(np.radians(r.lat)))
        ring = [[float(r.lon + dlon * np.cos(a)), float(r.lat + dlat * np.sin(a))] for a in t]
        feats.append({"type": "Feature", "properties": {"zona": r.zona, "ordinanza": r.ordinanza,
                      "raggio_m": int(r.raggio_m)}, "geometry": {"type": "Polygon", "coordinates": [ring]}})
    fc = {"type": "FeatureCollection", "features": feats}
    (INTERIM / "zone_movida.geojson").write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    return fc, "cerchi"


def in_zone(lon, lat):
    """-> array di nomi zona ('' se fuori)."""
    z = pd.read_csv(MANUAL / "zone_movida.csv")
    pts = to_utm(lon, lat)
    cen = to_utm(z.lon, z.lat)
    out = np.full(len(pts), "", dtype=object)
    for c, r, name in zip(cen, z.raggio_m, z.zona):
        d = np.hypot(*(pts - c).T)
        out[(d <= r) & (out == "")] = name
    return out
