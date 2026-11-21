"""Segnalazioni dei cittadini, salvate come note OpenStreetMap con tag #minipa.

La mappa web crea una nota anonima con un testo strutturato, per esempio:

    #minipa segnalazione
    esito: aperto            (aperto | chiuso | minimarket | chiuso_definitivo | non_minimarket | nuovo)
    visto_il: 2026-11-22T01:30
    chiude_alle: 02:00       (facoltativo)
    negozio: Minimarket, Via Esempio 3
    codice: C-EV/123         (assente per "nuovo")

Qui le rileggiamo, le trasformiamo in prove per il punteggio e in ground truth (§5).
"""
import json
import re

import pandas as pd
import requests

from .common import RAW, ROOT, save_meta

API = "https://api.openstreetmap.org/api/0.6/notes/search.json"
BBOX = (9.04, 45.38, 9.28, 45.54)  # lon_min, lat_min, lon_max, lat_max (Comune di Milano)
GT_AUTO = ROOT / "data" / "ground_truth_segnalazioni.csv"
_FIELD = re.compile(r"^\s*([a-z_]+)\s*:\s*(.+?)\s*$", re.M)


def fetch(refresh=False):
    out = RAW / "segnalazioni_osm.json"
    if out.exists() and not refresh:
        return out
    r = requests.get(API, params={"q": "#minipa", "closed": -1, "limit": 10000}, timeout=120,
                     headers={"User-Agent": "minipa/0.1"})
    r.raise_for_status()
    out.write_text(r.text, encoding="utf-8")
    save_meta("segnalazioni_osm", fonte="OSM Notes API, testo #minipa", licenza="ODbL",
              note=len(r.json().get("features", [])))
    return out


def load():
    f = RAW / "segnalazioni_osm.json"
    cols = ["note_id", "lon", "lat", "esito", "visto_il", "chiude_alle", "codice", "negozio"]
    if not f.exists():
        return pd.DataFrame(columns=cols)
    rows = []
    for ft in json.loads(f.read_text(encoding="utf-8")).get("features", []):
        lon, lat = ft["geometry"]["coordinates"]
        if not (BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]):
            continue
        first = (ft["properties"].get("comments") or [{}])[0]
        text = first.get("text", "")
        if "#minipa" not in text.lower():
            continue
        kv = dict(_FIELD.findall(text))
        rows.append({"note_id": ft["properties"]["id"], "lon": lon, "lat": lat,
                     "esito": kv.get("esito", "").lower(), "visto_il": kv.get("visto_il", first.get("date", "")[:16]),
                     "chiude_alle": kv.get("chiude_alle", ""), "codice": kv.get("codice", ""),
                     "negozio": kv.get("negozio", "")})
    return pd.DataFrame(rows, columns=cols)


def _minutes(hhmm):
    m = re.match(r"(\d{1,2})[:.](\d{2})", str(hhmm or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _night(minutes):
    """Minuti dall'inizio del giorno -> minuti 'di serata' (00:00-05:59 diventa 24:00-29:59)."""
    if minutes is None:
        return None
    return minutes + 1440 if minutes < 360 else minutes


def new_shops(notes):
    """Esito 'nuovo' -> righe da aggiungere all'universo dei negozi."""
    n = notes[notes.esito == "nuovo"]
    return pd.DataFrame({"Codice": "SEG:" + n.note_id.astype(str), "insegna": n.negozio, "indirizzo": "",
                         "lon": n.lon, "lat": n.lat, "settore": "alimentare", "match_tipo": "segnalazione",
                         "osm_shop": "convenience"})


def evidence(notes):
    """-> DataFrame per Codice con prove serali/notturne e flag di esclusione."""
    if notes.empty:
        return pd.DataFrame(columns=["Codice", "seg_n", "seg_aperto_max", "seg_chiusi_notte", "seg_aperti_notte", "seg_minimarket",
                                     "seg_escludi"]).set_index("Codice")
    n = notes.copy()
    n["Codice"] = n.codice.where(n.codice != "", "SEG:" + n.note_id.astype(str))
    seen = n.visto_il.str[11:16].map(_minutes).map(_night)
    until = n.chiude_alle.map(_minutes).map(_night)
    n["late"] = pd.concat([seen.where(n.esito.isin(["aperto", "nuovo"])), until], axis=1).max(axis=1)
    n["notte"] = seen >= 22 * 60
    g = n.groupby("Codice")
    return pd.DataFrame({
        "seg_n": g.size(),
        "seg_aperto_max": g.late.max(),
        "seg_aperti_notte": g.apply(lambda x: (x.notte & x.esito.isin(["aperto", "nuovo"])).sum(), include_groups=False),
        "seg_chiusi_notte": g.apply(lambda x: (x.notte & (x.esito == "chiuso")).sum(), include_groups=False),
        # "è un minimarket" e "non è un minimarket" si bilanciano: esclude solo la maggioranza contraria
        "seg_minimarket": g.apply(lambda x: x.esito.isin(["minimarket", "nuovo"]).sum(), include_groups=False),
        "seg_escludi": g.apply(lambda x: (x.esito == "chiuso_definitivo").any()
                               or (x.esito == "non_minimarket").sum() > x.esito.isin(["minimarket", "nuovo"]).sum(),
                               include_groups=False),
    })


def write_ground_truth(notes):
    """Esiti aperto/chiuso -> ground truth per calibrate.py (§5)."""
    v = notes[notes.esito.isin(["aperto", "chiuso"]) & (notes.codice != "")]
    pd.DataFrame({"Codice": v.codice, "verificato_il": v.visto_il.str[:10], "ora_verifica": v.visto_il.str[11:16],
                  "aperto": v.esito.map({"aperto": "si", "chiuso": "no"}), "note": "osm_note/" + v.note_id.astype(str)}
                 ).to_csv(GT_AUTO, index=False)
