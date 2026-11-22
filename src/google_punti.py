"""Punti "da confermare" suggeriti da Google Places (termini EEA di Google Maps Platform).

Sulla mappa pubblica si usano SOLO latitudine, longitudine e place_id, più il link alla
scheda Google Maps: è ciò che i termini EEA consentono "With any Map". Niente nomi, orari,
tipi o indirizzi Google, né nel repository né sulla mappa.

- places_match.py (locale) scrive data/manual/google_da_confermare.csv con i luoghi che
  Google dà aperti dopo le 22: place_id, lat, lon, scaricato_il.
- Qui la pipeline li legge, scarta quelli più vecchi di 30 giorni, li aggancia ai negozi
  MiniPa entro 30 m (solo link) o li aggiunge come record "GGL:<place_id>".
- Un record GGL senza segnalazioni resta in fascia "da_confermare" (viola); con una
  segnalazione sul posto entra nel punteggio come ogni altro negozio.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .common import MANUAL, to_utm

FILE = MANUAL / "google_da_confermare.csv"
RAGGIO = 30
SCADENZA_GIORNI = 30


def link(place_id):
    return f"https://www.google.com/maps/place/?q=place_id:{place_id}"


def load():
    if not FILE.exists():
        return pd.DataFrame(columns=["place_id", "lat", "lon", "scaricato_il"])
    g = pd.read_csv(FILE)
    limite = (date.today() - timedelta(days=SCADENZA_GIORNI)).isoformat()
    return g[g.scaricato_il >= limite].drop_duplicates("place_id").reset_index(drop=True)


def add(shops, pre, area):
    """Aggancia i punti Google ai negozi esistenti o li aggiunge come record GGL."""
    shops["google_link"] = None
    g = load()
    if g.empty:
        return shops, pre
    cand = shops.index[pre.to_numpy()]
    d, j = cKDTree(to_utm(shops.loc[cand, "lon"], shops.loc[cand, "lat"])).query(
        to_utm(g.lon, g.lat), distance_upper_bound=RAGGIO)
    ok = np.isfinite(d)
    for k in np.flatnonzero(ok):
        shops.at[cand[j[k]], "google_link"] = link(g.place_id[k])
    nuovi = g[~ok]
    if len(nuovi):
        rec = pd.DataFrame({"Codice": "GGL:" + nuovi.place_id, "insegna": None, "indirizzo": "",
                            "lon": nuovi.lon.to_numpy(), "lat": nuovi.lat.to_numpy(), "settore": "alimentare",
                            "match_tipo": "google", "google_link": nuovi.place_id.map(link).to_numpy()})
        area(rec, shops, rec.lon, rec.lat)
        shops = pd.concat([shops, rec], ignore_index=True)
        pre = pd.concat([pre, pd.Series(True, index=range(len(rec)))], ignore_index=True)
    return shops, pre


def mark(shops):
    """Record GGL non ancora confermati da nessuno: fascia 'da_confermare'."""
    ggl = shops.Codice.str.startswith("GGL:") & (shops.segnalazioni.fillna(0) == 0)
    shops.loc[ggl, "fascia"] = "da_confermare"
    shops.loc[ggl, "candidato"] = True
    return shops
