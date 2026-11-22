"""Abbina i luoghi Google (cache locale, max 30 giorni) ai negozi MiniPa. SOLO USO INTERNO.

Produce data/output/coda_google.csv (cartella ignorata da git): i negozi che Google dà
aperti la sera, da far verificare per primi. Niente nomi Google nel file: solo place_id
(che i termini permettono di conservare) e il link per aprirlo su Google Maps.
I dati Google non entrano nel punteggio pubblico né nella mappa.

    python -m src.places_match
"""
import json
from datetime import date

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from . import oh
from .common import MANUAL, OUTPUT, RAW, to_utm
from .fetch_places import CACHE, pulisci_cache

RAGGIO = 30
# solo negozi di alimentari generici: in centro la ricerca restituisce anche gelaterie, bar, ristoranti
TIPI_OK = {"grocery_store", "supermarket", "convenience_store", "food_store", "market", "store", "liquor_store"}


def week(periods):
    """periods Google (day 0 = domenica) -> 7 liste lun..dom di [inizio, fine] in minuti."""
    w = [[] for _ in range(7)]
    for p in periods or []:
        o, c = p.get("open", {}), p.get("close")
        if c is None:  # aperto 24 ore
            return [[[0, 1440]] for _ in range(7)]
        d = (o["day"] + 6) % 7
        a = o["hour"] * 60 + o.get("minute", 0)
        b = c["hour"] * 60 + c.get("minute", 0) + (1440 if c["day"] != o["day"] else 0)
        w[d].append([a, b])
    return w


def run():
    pulisci_cache()
    rows = []
    for f in CACHE.glob("*.json"):
        for p in json.loads(f.read_text(encoding="utf-8")):
            cmax, dopo, h24 = oh.summary(week(p.get("regularOpeningHours", {}).get("periods")))
            scaricato = date.fromtimestamp(f.stat().st_mtime).isoformat()
            rows.append({"place_id": p["id"], "scaricato_il": scaricato, "lat": p["location"]["latitude"], "lon": p["location"]["longitude"],
                         "tipo": p.get("primaryType", ""), "stato": p.get("businessStatus", ""),
                         "g_chiusura": oh.fmt(int(cmax)) if cmax else "", "g_cmax": cmax or 0,
                         "g_dopo_mezzanotte": dopo, "g_h24": h24})
    g = pd.DataFrame(rows).drop_duplicates("place_id")
    shops = pd.read_csv(OUTPUT / "minipa_milano.csv", dtype={"Codice": str})
    shops = shops[shops.candidato].reset_index(drop=True)
    d, j = cKDTree(to_utm(shops.lon, shops.lat)).query(to_utm(g.lon, g.lat), distance_upper_bound=RAGGIO)
    ok = np.isfinite(d)
    g["Codice"] = np.where(ok, shops.Codice.reindex(np.where(ok, j, 0)).to_numpy(), "")
    g["dist_m"] = np.where(ok, d.round(1), np.nan)
    m = g.merge(shops[["Codice", "indirizzo", "MUNICIPIO", "score", "fascia"]], on="Codice", how="left")
    m["maps"] = "https://www.google.com/maps/place/?q=place_id:" + m.place_id
    sera = m[(m.g_cmax >= 22 * 60) & m.tipo.isin(TIPI_OK)].sort_values("g_cmax", ascending=False)
    sera.drop(columns=["g_cmax"]).to_csv(OUTPUT / "coda_google.csv", index=False, encoding="utf-8-sig")
    # per la mappa pubblica: SOLO place_id e coordinate (consentiti dai termini EEA), con data di download
    sera[["place_id", "lat", "lon", "scaricato_il"]].to_csv(MANUAL / "google_da_confermare.csv", index=False)
    print(f"luoghi Google: {len(g)}, abbinati a negozi MiniPa: {ok.sum()}")
    print(f"aperti dopo le 22 (alimentari generici): {len(sera)}; dopo mezzanotte: {int(sera.g_dopo_mezzanotte.sum())}; "
          f"senza corrispondenza in MiniPa: {int((sera.Codice == '').sum())}")
    return sera


if __name__ == "__main__":
    s = run()
    print(s[["indirizzo", "fascia", "score", "g_chiusura", "tipo", "dist_m"]].head(25).to_string())
