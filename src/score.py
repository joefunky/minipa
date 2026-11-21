"""Punteggio Pakibo 0-100, fasce e file di output."""
import json

import numpy as np
import pandas as pd

from . import features as F, oh
from scipy.spatial import cKDTree

from .common import INTERIM, OUTPUT, RAW, WEB, to_utm
from .match import load_osm, match
from . import segnalazioni as SEG

WEIGHTS = {"b_identikit": 35, "b_contesto": 25, "b_orari": 40}  # ricalibrare con calibrate.py
CHAIN_CAP = 39  # le catene non sono Pakibo: restano nel dataset, fuori dalla mappa


def load_ds(name):
    d = pd.read_csv(RAW / f"{name}.csv", sep=";", dtype=str)
    d["lon"] = pd.to_numeric(d.LONG_X_4326, errors="coerce")
    d["lat"] = pd.to_numeric(d.LAT_Y_4326, errors="coerce")
    return d.dropna(subset=["lon", "lat"]).reset_index(drop=True)


def fascia(s):
    # "da_scoprire" (30-39): base allargata da far verificare con le segnalazioni
    return np.select([s >= 70, s >= 40, s >= 30], ["probabile", "verifica", "da_scoprire"], "escluso")


def build():
    shops, pe, osm = load_ds("ds49"), load_ds("ds58"), load_osm()
    shops["settore"] = shops.settore_merceologico.map(F.settore)
    kw = shops.insegna.fillna("").str.contains(F.KEYWORDS)
    pre = shops.codice_ateco.fillna("").str.startswith("47.11") | shops.settore.isin(["alimentare", "misto"]) | kw
    m = match(shops[pre], osm)
    shops = shops.join(m)
    osm_cols = osm.reset_index(drop=True)
    for c in ["osm_id", "osm_shop", "osm_name", "osm_brand", "osm_opening_hours"]:
        shops[c] = shops.osm_idx.map(lambda j: osm_cols.at[int(j), c] if pd.notna(j) else None)
    shops["indirizzo"] = (shops.DescrizioneVia.fillna("").str.title() + " " + shops.Civico.fillna("")).str.strip()

    # negozi OSM senza riga DS49 corrispondente: entrano come record "solo OSM"
    used = set(shops.osm_idx.dropna().astype(int))
    extra = osm_cols[~osm_cols.index.isin(used)].copy()
    if len(extra):
        _area(extra, shops, extra.osm_lon, extra.osm_lat)
        extra = extra.assign(Codice="OSM:" + extra.osm_id, insegna=extra.osm_name, lon=extra.osm_lon,
                             lat=extra.osm_lat, indirizzo=extra.osm_addr, match_tipo="solo_osm",
                             settore=np.where(extra.osm_shop == "kiosk", "non alimentare", "alimentare"))
        shops = pd.concat([shops, extra.drop(columns=["osm_lon", "osm_lat", "osm_addr"])], ignore_index=True)
        pre = pd.concat([pre, pd.Series(extra.settore.eq("alimentare").to_numpy() |
                                        extra.insegna.str.contains(F.KEYWORDS).to_numpy())], ignore_index=True)

    # negozi nuovi segnalati dai cittadini (note OSM #pakibo, esito "nuovo")
    notes = SEG.load()
    nuovi = SEG.new_shops(notes)
    if len(nuovi):
        _area(nuovi, shops, nuovi.lon, nuovi.lat)
        shops = pd.concat([shops, nuovi], ignore_index=True)
        pre = pd.concat([pre, pd.Series(True, index=range(len(nuovi)))], ignore_index=True)

    shops["b_identikit"], shops["catena"] = F.block_identikit(shops)
    shops["n_pe_200m"] = F.pe_counts(shops, pe)
    shops["b_contesto"], shops["zona_movida"] = F.block_contesto(shops, shops.n_pe_200m)
    shops["b_orari"], weeks, cmax, shops["dopo_mezzanotte"], shops["h24"] = F.block_orari(shops)
    shops["chiusura_max"] = cmax.map(lambda v: oh.fmt(int(v)) if pd.notna(v) else "")
    shops["fonti_orari"] = np.where(cmax.notna(), "OSM", "")
    shops["orari"] = weeks

    # prove dalle segnalazioni: aperto la sera/notte alza il blocco orari, esclusioni azzerano
    ev = SEG.evidence(notes).reindex(shops.Codice)
    late = ev.seg_aperto_max.to_numpy(dtype=float)
    seg_b = np.select([late >= 1440, late >= 1320], [0.8, 0.5], 0.0)
    shops["b_orari"] = np.maximum(shops.b_orari, seg_b)
    shops["dopo_mezzanotte"] = shops.dopo_mezzanotte | (late > 1440)
    shops["fonti_orari"] = np.where(seg_b > 0, (shops.fonti_orari + " segnalazioni").str.strip(), shops.fonti_orari)
    later = np.nan_to_num(late) > cmax.fillna(0).to_numpy()
    shops["chiusura_max"] = np.where(later & (seg_b > 0), [oh.fmt(int(v)) if v == v else "" for v in late], shops.chiusura_max)
    shops["segnalazioni"] = ev.seg_n.fillna(0).astype(int).to_numpy()
    contro = (ev.seg_chiusi_notte.fillna(0) > ev.seg_aperti_notte.fillna(0)).to_numpy()
    escludi = ev.seg_escludi.fillna(False).astype(bool).to_numpy()

    # i non candidati non hanno identikit alimentare: niente orari né contesto che li promuova
    cand = (shops.b_identikit > 0) | shops.catena & pre
    s = sum(shops[k] * w for k, w in WEIGHTS.items())
    s = np.where(shops.catena | contro, np.minimum(s, CHAIN_CAP), s)
    # due o più conferme notturne e nessuna contraria: probabile anche senza altri segnali
    conferme = (ev.seg_aperti_notte.fillna(0) >= 2).to_numpy() & ~contro
    s = np.where(conferme, np.maximum(s, 70), s)
    s = np.where(escludi, 0, s)
    shops["score"] = np.where(cand, s, 0).round(1)
    shops["fascia"] = fascia(shops.score)
    shops["candidato"] = cand & ~shops.catena
    SEG.write_ground_truth(notes)
    return shops, pre


def _area(df, shops, lon, lat):
    """CAP, municipio e NIL presi dal negozio DS49 più vicino."""
    near = cKDTree(to_utm(shops.lon, shops.lat)).query(to_utm(lon, lat))[1]
    for c in ["CAP", "MUNICIPIO", "ID_NIL", "NIL"]:
        df[c] = shops[c].to_numpy()[near]


COLS = ["Codice", "insegna", "indirizzo", "CAP", "MUNICIPIO", "NIL", "lat", "lon", "settore",
        "superficie_vendita", "codice_ateco", "score", "fascia", "b_identikit", "b_contesto", "b_orari",
        "catena", "candidato", "chiusura_max", "dopo_mezzanotte", "h24", "fonti_orari", "n_pe_200m",
        "zona_movida", "osm_id", "osm_shop", "osm_name", "osm_opening_hours", "match_tipo", "match_dist_m", "segnalazioni"]


def write(shops, pre):
    out = shops[pre | shops.catena].copy()
    out[COLS].to_csv(OUTPUT / "pakibo_milano.csv", index=False, encoding="utf-8-sig")
    out[out.fascia == "verifica"].sort_values("score", ascending=False)[COLS].to_csv(
        OUTPUT / "coda_verifica.csv", index=False, encoding="utf-8-sig")

    def feat(r):
        props = {c: (None if (isinstance(r[c], float) and np.isnan(r[c])) else r[c]) for c in COLS if c not in ("lat", "lon")}
        props = {k: (v.item() if hasattr(v, "item") else v) for k, v in props.items()}
        props["orari"] = r.orari
        return {"type": "Feature", "properties": props,
                "geometry": {"type": "Point", "coordinates": [r.lon, r.lat]}}

    fc = {"type": "FeatureCollection", "features": [feat(r) for _, r in out.iterrows()]}
    (OUTPUT / "pakibo_milano.geojson").write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")

    # per la mappa: solo fasce >= 40, in un .js così index.html si apre anche da file://
    keep = ["Codice", "insegna", "osm_name", "indirizzo", "MUNICIPIO", "NIL", "score", "fascia", "chiusura_max",
            "dopo_mezzanotte", "fonti_orari", "osm_id", "zona_movida", "segnalazioni", "orari"]
    web = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(c, 6) for c in f["geometry"]["coordinates"]]},
         "properties": {k: f["properties"].get(k) for k in keep}}
        for f in fc["features"] if f["properties"]["score"] >= 30 and f["properties"]["candidato"]]}
    zones = json.loads((INTERIM / "zone_movida.geojson").read_text(encoding="utf-8"))
    meta = {k: json.loads((RAW / f"{k}.meta.json").read_text(encoding="utf-8")) for k in ("ds49", "ds58", "osm_shops")}
    (WEB / "data.js").write_text("window.PAKIBO=" + json.dumps({"negozi": web, "zone": zones, "meta": meta},
                                 ensure_ascii=False) + ";", encoding="utf-8")
    return out


def sample(out, n=40, seed=1):
    """Campione stratificato per fascia e municipio, per la verifica §5."""
    c = out[out.candidato & (out.score > 0)]
    quota = {"probabile": 0.4, "verifica": 0.4, "escluso": 0.2}
    parts = []
    for f, q in quota.items():
        g = c[c.fascia == f]
        k = min(len(g), round(n * q))
        if k:
            # giro tra i municipi: un negozio a testa finché non si raggiunge la quota
            g = g.sample(frac=1, random_state=seed)
            g = g.assign(_r=g.groupby("MUNICIPIO").cumcount()).sort_values("_r")
            parts.append(g.head(k).drop(columns="_r"))
    s = pd.concat(parts) if parts else c.head(0)
    s[["Codice", "insegna", "indirizzo", "MUNICIPIO", "score", "fascia", "chiusura_max"]].assign(
        verificato_il="", ora_verifica="", aperto="", note="").to_csv(
        OUTPUT / "campione_verifica.csv", index=False, encoding="utf-8-sig")
    return s
