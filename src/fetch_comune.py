"""Fonti A (DS49) e B (DS58) dal portale CKAN del Comune di Milano."""
import requests

from .common import RAW, save_meta

CKAN = "https://dati.comune.milano.it/api/3/action/package_show"
DATASETS = {
    "ds49": "f6764e63-4a8c-46f0-9dc8-7a671e0a3950",       # esercizi di vicinato in sede fissa
    "ds58": "ds58_economia_pubblici_esercizi_in_piano",    # pubblici esercizi in piano
}


def fetch(name, refresh=False):
    out = RAW / f"{name}.csv"
    if out.exists() and not refresh:
        return out
    pkg = requests.get(CKAN, params={"id": DATASETS[name]}, timeout=60).json()["result"]
    res = next(r for r in pkg["resources"] if r.get("format", "").upper() == "CSV")
    r = requests.get(res["url"], timeout=300)
    r.raise_for_status()
    out.write_bytes(r.content)
    save_meta(name, dataset=pkg["name"], titolo=pkg.get("title"), licenza=pkg.get("license_id"),
              url=res["url"], aggiornato_il=res.get("last_modified") or pkg.get("metadata_modified"))
    print(f"  {name}: {len(r.content)/1e6:.1f} MB")
    return out


def run(refresh=False):
    return {n: fetch(n, refresh) for n in DATASETS}


if __name__ == "__main__":
    run(refresh=True)
