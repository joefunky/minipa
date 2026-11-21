"""Fonte J: guide e articoli sul web che citano minimarket aperti di notte.

data/manual/fonti_web.csv è compilato a mano (oggi: guida ZERO "I minimarket notturni",
aggiornata al 28/11/2019), con coordinate già calcolate una volta sola.
Si usano solo indirizzo e orario di chiusura come prova; i nomi servono solo a chi legge il file.
Le fonti vecchie valgono poco: il blocco orari arriva al massimo a 0,5.
"""
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from .common import MANUAL, to_utm

RAGGIO = 25  # metri
B_ORARI = 0.5
B_IDENTIKIT = 0.6


def load():
    f = MANUAL / "fonti_web.csv"
    if not f.exists():
        return pd.DataFrame()
    return pd.read_csv(f, sep=";").dropna(subset=["lat", "lon"]).reset_index(drop=True)


def attach(shops):
    """-> (indice dei negozi abbinati, righe della fonte), un negozio per voce della fonte.

    Tra i negozi entro 25 m sceglie quello con l'identikit più alto (di solito l'unico alimentare).
    """
    w = load()
    if w.empty:
        return [], w
    food = shops.index[shops.b_identikit > 0]
    tree = cKDTree(to_utm(shops.loc[food, "lon"], shops.loc[food, "lat"]))
    idx, rows = [], []
    for i, p in enumerate(to_utm(w.lon, w.lat)):
        near = [food[j] for j in tree.query_ball_point(p, RAGGIO)]
        if near:
            idx.append(shops.loc[near, "b_identikit"].idxmax())
            rows.append(i)
    return idx, w.iloc[rows].reset_index(drop=True)


def apply(shops):
    idx, w = attach(shops)
    shops["fonte_web"] = None
    if not idx:
        return shops, 0
    for i, r in zip(idx, w.itertuples()):
        shops.at[i, "b_orari"] = max(shops.at[i, "b_orari"], B_ORARI)
        shops.at[i, "b_identikit"] = max(shops.at[i, "b_identikit"], B_IDENTIKIT)
        shops.at[i, "fonte_web"] = f"{r.fonte} {str(r.data_fonte)[:4]}|{r.url}"
        shops.at[i, "fonti_orari"] = (str(shops.at[i, "fonti_orari"] or "") + f" web ({r.fonte} {str(r.data_fonte)[:4]})").strip()
        if not shops.at[i, "chiusura_max"]:
            shops.at[i, "chiusura_max"] = f"{r.chiusura} ({str(r.data_fonte)[:4]})"
        if r.chiusura == "24h" or str(r.chiusura) < "06:00":
            shops.at[i, "dopo_mezzanotte"] = True
    return shops, len(idx)
