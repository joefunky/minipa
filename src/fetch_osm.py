"""Fonte D: negozi OSM nel Comune di Milano via Overpass."""
import json
import time

import requests

from .common import RAW, save_meta

ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
QUERY = """
[out:json][timeout:180];
area["boundary"="administrative"]["admin_level"="8"]["name"="Milano"]->.a;
nwr(area.a)["shop"~"^(convenience|supermarket|kiosk|alcohol)$"];
out center tags;
"""


def run(refresh=False):
    out = RAW / "osm_shops.json"
    if out.exists() and not refresh:
        return out
    last = None
    for url in ENDPOINTS:
        for _ in range(2):
            try:
                r = requests.post(url, data={"data": QUERY}, timeout=240,
                                  headers={"User-Agent": "pakibo-milano/0.1"})
                r.raise_for_status()
                data = r.json()
                out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                save_meta("osm_shops", fonte="OpenStreetMap via Overpass", endpoint=url,
                          licenza="ODbL", elementi=len(data["elements"]),
                          osm_base=data.get("osm3s", {}).get("timestamp_osm_base"))
                print(f"  osm: {len(data['elements'])} elementi")
                return out
            except Exception as e:  # rete o server occupato: riprova
                last = e
                time.sleep(10)
    raise RuntimeError(f"Overpass non raggiungibile: {last}")


if __name__ == "__main__":
    run(refresh=True)
