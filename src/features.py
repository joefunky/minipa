"""Blocchi di feature 4.1-4.3 (4.4 Mapillary non attivo nella v1).

Vincolo etico (§2): l'insegna si usa SOLO per parole chiave merceologiche/orarie
e per riconoscere le catene. Nessuna feature su nomi, nazionalità o etnia.
"""
import re

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from . import oh
from .common import to_utm
from .ordinanze import in_zone

KEYWORDS = re.compile(r"\b(?:mini ?market|market|food|drinks?|h ?24|24 ?h|24/7|alimentari|"
                      r"frutta e verdura|bazar|express)\b", re.I)
# Catene. I marchi corti o ambigui (MD, Pam, U2, Coop...) valgono solo a inizio nome:
# altrimenti "MD" intercetterebbe abbreviazioni di nomi propri e "coop" le cooperative.
CHAINS_ANY = re.compile(r"\b(?:carrefour|conad|esselunga|lidl|eurospin|il gigante|tigros|despar|eurospar|interspar|"
                        r"bennet|penny|natura ?s[iì]|aldi|basko|sapori ?& ?dintorni|viaggiator goloso|tuod[iì])\b", re.I)
CHAINS_START = re.compile(r"^\s*(?:ok\s+)?(?:md|pam|u2|prix|metro|sigma|simply|crai|coop|unes|iper|in'?s|a&o|"
                          r"il centro|todis|ekom|dimar|famila)\b(?![.'])", re.I)


def is_chain(*names):
    return any(isinstance(n, str) and (CHAINS_ANY.search(n) or CHAINS_START.search(n)) for n in names)


def settore(s):
    s = (s if isinstance(s, str) else "").lower().replace(" ", "")
    if s.startswith("alimentarenon") or s == "misto":
        return "misto"
    if s.startswith("alimentare"):
        return "alimentare"
    if "monopolio" in s:
        return "monopolio"
    return "non alimentare"


def block_identikit(df):
    ateco = df.codice_ateco.fillna("").str.startswith("47.11")
    sett = df.settore.isin(["alimentare", "misto"])
    names = df.insegna.fillna("") + " " + df.osm_name.fillna("") + " " + df.ov_nome.fillna("")
    kw = names.str.contains(KEYWORDS)
    sup = pd.to_numeric(df.superficie_vendita, errors="coerce")
    osm_conv = df.osm_shop.isin(["convenience"]) | df.ov_categoria.eq("convenience_store")
    osm_alc = df.osm_shop.isin(["alcohol", "supermarket"]) | df.ov_categoria.isin(["grocery_store", "liquor_store"])
    # Overture dice negozio specializzato (forno, macelleria, enoteca...): non è un minimarket
    specialist = df.ov_categoria.notna() & df.ov_categoria.ne("") & ~df.ov_categoria.isin(
        ["convenience_store", "grocery_store", "liquor_store", "market", "food_and_beverage_store"])
    b = (0.45 * ateco + 0.15 * (df.settore == "alimentare") + 0.10 * (df.settore == "misto")
         + 0.25 * kw + 0.25 * osm_conv + 0.10 * osm_alc
         + np.where(sup < 100, 0.15, np.where(sup <= 250, 0.05, 0)))
    # serve almeno un segnale alimentare: senza, il negozio non è candidato
    b = np.where(ateco | sett | kw, b, 0).clip(0, 1)
    b = np.where(specialist & ~kw & ~osm_conv, b * 0.5, b)
    catena = pd.Series([is_chain(*r) for r in zip(df.insegna, df.osm_name, df.osm_brand, df.ov_nome)], index=df.index)
    return pd.Series(np.where(catena, 0, b), index=df.index), catena


def pe_counts(df, pe):
    tree = cKDTree(to_utm(pe.lon, pe.lat))
    return np.array([len(x) for x in tree.query_ball_point(to_utm(df.lon, df.lat), 200)])


def block_contesto(df, n_pe):
    pct = pd.Series(n_pe).rank(pct=True).to_numpy()
    zona = in_zone(df.lon, df.lat)
    return pd.Series(0.7 * pct + 0.3 * (zona != ""), index=df.index), zona


def block_orari(df):
    weeks = df.osm_opening_hours.map(lambda s: oh.parse(s) if s else None)
    summ = weeks.map(oh.summary)
    cmax = summ.map(lambda x: x[0]).astype(float)
    dopo = summ.map(lambda x: x[1]).astype(bool)
    h24 = summ.map(lambda x: x[2]).astype(bool)
    b = np.select([h24, cmax >= 1440, cmax >= 1320], [1.0, 0.8, 0.5], 0.0)
    b = np.where(cmax.isna(), 0.0, b)
    return pd.Series(b, index=df.index), weeks, cmax, dopo, h24
