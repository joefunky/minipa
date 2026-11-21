"""Abbinamento negozi DS49 <-> OSM (raggio + similarità dell'insegna).

Regole:
- insegna presente: candidati OSM entro 30 m con token_set_ratio >= 70;
  vince la similarità più alta, a parità il più vicino.
- insegna vuota (circa 4 negozi su 5 nel DS49): solo distanza, entro 30 m,
  e un elemento OSM va al massimo a un negozio (il più vicino).
"""
import json
import re
import unicodedata

import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from scipy.spatial import cKDTree

from .common import RAW, to_utm

R_NAME, R_DIST, MIN_SIM = 30, 30, 70
_GENERIC = r"\b(srl|snc|sas|spa|s\.r\.l\.?|di|e|&|the)\b"


def norm(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(_GENERIC, " ", s)
    return re.sub(r"[^a-z0-9/ ]+", " ", s).strip()


def load_osm():
    els = json.loads((RAW / "osm_shops.json").read_text(encoding="utf-8"))["elements"]
    rows = []
    for e in els:
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if lat is None:
            continue
        t = e.get("tags", {})
        rows.append({"osm_id": f"{e['type']}/{e['id']}", "osm_lat": lat, "osm_lon": lon,
                     "osm_shop": t.get("shop"), "osm_name": t.get("name") or "",
                     "osm_brand": t.get("brand") or "", "osm_opening_hours": t.get("opening_hours") or "",
                     "osm_addr": f"{t.get('addr:street', '')} {t.get('addr:housenumber', '')}".strip()})
    return pd.DataFrame(rows)


def match(shops, osm):
    """shops: DataFrame con lon, lat, insegna. Restituisce colonne di match allineate a shops."""
    res = pd.DataFrame(index=shops.index, columns=["osm_idx", "match_tipo", "match_dist_m", "match_sim"])
    if osm.empty or shops.empty:
        return res
    tree = cKDTree(to_utm(osm.osm_lon, osm.osm_lat))
    pts = to_utm(shops.lon, shops.lat)
    osm_names = [norm(f"{n} {b}") for n, b in zip(osm.osm_name, osm.osm_brand)]
    dist_claims = {}  # osm_idx -> (dist, shop_index)
    for (idx, ins), p in zip(shops.insegna.items(), pts):
        q = norm(ins)
        if q:
            best = None
            for j in tree.query_ball_point(p, R_NAME):
                sim = fuzz.token_set_ratio(q, osm_names[j]) if osm_names[j] else 0
                if sim >= MIN_SIM:
                    d = float(np.hypot(*(tree.data[j] - p)))
                    if best is None or (sim, -d) > (best[1], -best[2]):
                        best = (j, sim, d)
            if best:
                res.loc[idx] = [best[0], "insegna+distanza", round(best[2], 1), best[1]]
        else:
            d, j = tree.query(p, distance_upper_bound=R_DIST)
            if np.isfinite(d) and (j not in dist_claims or d < dist_claims[j][0]):
                dist_claims[j] = (float(d), idx)
    for j, (d, idx) in dist_claims.items():
        res.loc[idx] = [j, "solo_distanza", round(d, 1), np.nan]
    return res
