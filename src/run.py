"""Pipeline completa: python -m src.run [--refresh]"""
import json
import sys

from . import calibrate, fetch_comune, fetch_osm, fetch_places, ordinanze, score, segnalazioni
from .common import OUTPUT


def main():
    refresh = "--refresh" in sys.argv
    print("1. download fonti open")
    fetch_comune.run(refresh)
    fetch_osm.run(refresh)
    fetch_places.run()
    segnalazioni.fetch(refresh=True)  # sempre: sono le novità più frequenti
    print("2. zone movida")
    _, tipo = ordinanze.load_zones()
    print(f"  zone: {tipo}")
    print("3. abbinamento, feature, punteggio")
    shops, pre = score.build()
    out = score.write(shops, pre)
    score.sample(out)
    cand = out[out.candidato]
    matched = cand.osm_id.notna()
    stats = {
        "negozi_ds49": int((~shops.Codice.str.startswith("OSM:")).sum()),
        "negozi_solo_osm": int(shops.Codice.str.startswith("OSM:").sum()),
        "candidati": int(len(cand)),
        "catene": int(out.catena.sum()),
        "tentati_abbinamento_pct": 100.0,
        "abbinati_osm": int(matched.sum()),
        "tasso_match_pct": round(100 * matched.mean(), 1),
        "match_per_tipo": cand.match_tipo.value_counts().to_dict(),
        "con_orari": int((cand.fonti_orari == "OSM").sum()),
        "dopo_mezzanotte": int(cand.dopo_mezzanotte.sum()),
        "fasce": cand.fascia.value_counts().to_dict(),
        "segnalazioni_lette": int(len(segnalazioni.load())),
    }
    (OUTPUT / "stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print("4. calibrazione")
    calibrate.run()


if __name__ == "__main__":
    main()
