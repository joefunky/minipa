"""Fonte E: Google Places API (New), Text Search. SOLO USO INTERNO, SOLO SUL PC DI GIOVANNI.

Regole (§2, §7, §9 e termini Google Maps Platform):
- costo zero: tetto Google di 30 richieste/giorno sul progetto `minipa`, più un tetto
  interno qui (30/giorno, 900/mese) contato in data/raw/places_uso.json;
- niente nel workflow pubblico: i dati Google non finiscono sulla mappa né su OSM;
- cache al massimo 30 giorni (data/raw/places/, ignorata da git), poi si cancella;
- dei risultati si usano solo orari, stato e tipo; i nomi servono solo all'abbinamento.

Strategia: griglia di celle da ~1 km sulle zone con candidati; per cella una ricerca
"minimarket alimentari" limitata al rettangolo, fino a 3 pagine da 20 risultati.
Ogni pagina è una richiesta (SKU Text Search Enterprise, perché chiede gli orari).

Uso:
    python -m src.fetch_places --stima      # quante richieste servono, nessuna chiamata
    python -m src.fetch_places --vai        # esegue fino al tetto del giorno, riprende da dove era
"""
import json
import os
import sys
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests

from .common import OUTPUT, RAW, ROOT, to_utm

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ("places.id,places.displayName,places.location,places.regularOpeningHours,"
          "places.businessStatus,places.primaryType,nextPageToken")
QUERY = "minimarket alimentari"
CELLA_GRADI = (0.013, 0.009)  # ~1 km in longitudine e latitudine a Milano
DUOMO = (9.1900, 45.4642)
MAX_PAGINE = 3
TETTO_GIORNO, TETTO_MESE = 30, 900
CACHE = RAW / "places"
USO = RAW / "places_uso.json"


def _key():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GOOGLE_PLACES_KEY="):
                os.environ.setdefault("GOOGLE_PLACES_KEY", line.split("=", 1)[1].strip())
    k = os.environ.get("GOOGLE_PLACES_KEY", "")
    if not k:
        sys.exit("Manca GOOGLE_PLACES_KEY nel file .env")
    return k


def celle():
    """Celle della griglia con almeno un candidato, dal centro (Duomo) verso l'esterno."""
    d = pd.read_csv(OUTPUT / "minipa_milano.csv", usecols=["lon", "lat", "candidato"])
    d = d[d.candidato]
    cells = set(zip(np.floor(d.lon / CELLA_GRADI[0]).astype(int), np.floor(d.lat / CELLA_GRADI[1]).astype(int)))
    duomo = to_utm([DUOMO[0]], [DUOMO[1]])[0]

    def dist(c):
        centro = to_utm([(c[0] + 0.5) * CELLA_GRADI[0]], [(c[1] + 0.5) * CELLA_GRADI[1]])[0]
        return float(np.hypot(*(centro - duomo)))
    return sorted(cells, key=dist)


def _uso():
    u = json.loads(USO.read_text(encoding="utf-8")) if USO.exists() else {}
    oggi, mese = date.today().isoformat(), date.today().isoformat()[:7]
    return u, u.get("giorni", {}).get(oggi, 0), sum(v for k, v in u.get("giorni", {}).items() if k.startswith(mese))


def _conta(u):
    oggi = date.today().isoformat()
    u.setdefault("giorni", {})[oggi] = u.get("giorni", {}).get(oggi, 0) + 1
    USO.write_text(json.dumps(u, indent=1), encoding="utf-8")


def pulisci_cache():
    """Termini Google: niente cache oltre 30 giorni."""
    limite = datetime.now() - timedelta(days=30)
    for f in CACHE.glob("*.json") if CACHE.exists() else []:
        if datetime.fromtimestamp(f.stat().st_mtime) < limite:
            f.unlink()


def stima():
    c = celle()
    print(f"celle da ~1 km con candidati: {len(c)}")
    print(f"richieste: da {len(c)} (1 pagina per cella) a {len(c) * MAX_PAGINE} (3 pagine ovunque)")
    print(f"giorni necessari al tetto di {TETTO_GIORNO}/giorno: da {len(c) // TETTO_GIORNO + 1} "
          f"a {len(c) * MAX_PAGINE // TETTO_GIORNO + 1}")
    print(f"soglia gratuita Text Search Enterprise: 1.000/mese; tetto interno {TETTO_MESE}/mese -> costo 0 €")


def vai(extra=0):
    """extra: richieste in più solo per questo giro (eccezione decisa da Giovanni)."""
    key = _key()
    CACHE.mkdir(parents=True, exist_ok=True)
    pulisci_cache()
    u, oggi, mese = _uso()
    fatte = set(u.get("celle_fatte", []))
    for ix, iy in celle():
        cid = f"{ix}_{iy}"
        if cid in fatte:
            continue
        rect = {"low": {"latitude": iy * CELLA_GRADI[1], "longitude": ix * CELLA_GRADI[0]},
                "high": {"latitude": (iy + 1) * CELLA_GRADI[1], "longitude": (ix + 1) * CELLA_GRADI[0]}}
        body, risultati = {"textQuery": QUERY, "pageSize": 20, "languageCode": "it",
                           "locationRestriction": {"rectangle": rect}}, []
        for _ in range(MAX_PAGINE):
            u, oggi, mese = _uso()
            if oggi >= TETTO_GIORNO + extra or mese >= TETTO_MESE:
                if risultati:  # tetto a metà zona: salvo le pagine già pagate (zona segnata come parziale)
                    (CACHE / f"{cid}.json").write_text(json.dumps(risultati, ensure_ascii=False), encoding="utf-8")
                    u.setdefault("celle_fatte", []).append(cid)
                    u.setdefault("celle_parziali", []).append(cid)
                    USO.write_text(json.dumps(u, indent=1), encoding="utf-8")
                print(f"tetto raggiunto (oggi {oggi}, mese {mese}): riprendo domani")
                return
            r = requests.post(URL, json=body, timeout=60, headers={
                "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS, "Content-Type": "application/json"})
            if r.status_code != 429:  # le richieste rifiutate per quota non si pagano
                _conta(u)
            if r.status_code != 200:
                print(f"errore {r.status_code}: {r.text[:200]}")
                return
            j = r.json()
            risultati += j.get("places", [])
            if not j.get("nextPageToken"):
                break
            body = {**body, "pageToken": j["nextPageToken"]}
            time.sleep(2)
        (CACHE / f"{cid}.json").write_text(json.dumps(risultati, ensure_ascii=False), encoding="utf-8")
        u, _, _ = _uso()
        u.setdefault("celle_fatte", []).append(cid)
        USO.write_text(json.dumps(u, indent=1), encoding="utf-8")
        print(f"  cella {cid}: {len(risultati)} luoghi")


def run(*_, **__):
    """Chiamato dalla pipeline: non fa mai chiamate a Google."""
    print("  Google Places: solo a mano sul PC (python -m src.fetch_places --vai)")
    return None


if __name__ == "__main__":
    if "--vai" in sys.argv:
        vai(int(sys.argv[sys.argv.index("--extra") + 1]) if "--extra" in sys.argv else 0)
    else:
        stima()
