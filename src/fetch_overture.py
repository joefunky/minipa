"""Fonte I: Overture Maps Places (licenza CDLA Permissive 2.0 / ODbL per alcune fonti).

Dà il nome che l'attività usa online (es. pagine social), la categoria,
siti e social: proprio ciò che manca al DS49 (insegna presente solo 1 volta su 6).
Si legge con DuckDB solo la porzione del parquet mondiale che cade su Milano.
"""
import re

import duckdb
import requests

from .common import RAW, save_meta

BUCKET = "https://overturemaps-us-west-2.s3.amazonaws.com"
BBOX = (9.04, 45.38, 9.28, 45.54)


def latest_release():
    xml = requests.get(BUCKET, params={"list-type": 2, "prefix": "release/", "delimiter": "/"}, timeout=60).text
    return sorted(re.findall(r"<Prefix>release/([^<]+)/</Prefix>", xml))[-1]


def run(refresh=False):
    out = RAW / "overture_places.parquet"
    if out.exists() and not refresh:
        return out
    rel = latest_release()
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    x0, y0, x1, y1 = BBOX
    con.execute(f"""
    COPY (SELECT id, names."primary" AS nome, basic_category, taxonomy."primary" AS categoria,
            array_to_string(taxonomy.alternates, ';') AS categorie_alt, confidence, operating_status,
            array_to_string(websites, ' ') AS siti, array_to_string(socials, ' ') AS social,
            brand.names."primary" AS marchio, addresses[1].freeform AS indirizzo,
            array_to_string(list_distinct([s.dataset for s in sources]), ';') AS fonti,
            ST_X(geometry) AS lon, ST_Y(geometry) AS lat
          FROM read_parquet('s3://overturemaps-us-west-2/release/{rel}/theme=places/type=place/*', hive_partitioning=1)
          WHERE bbox.xmin BETWEEN {x0} AND {x1} AND bbox.ymin BETWEEN {y0} AND {y1})
    TO '{out.as_posix()}' (FORMAT parquet)""")
    n = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()[0]
    save_meta("overture_places", fonte="Overture Maps Places", release=rel, licenza="CDLA-Permissive-2.0 (+ODbL)",
              elementi=n)
    print(f"  overture: {n} luoghi (release {rel})")
    return out


if __name__ == "__main__":
    run(refresh=True)


FOOD = ("basic_category IN ('food_and_beverage_store','convenience_store') OR categoria ILIKE '%grocer%' "
        "OR categoria IN ('convenience_store','liquor_store','market')")


def load_food():
    """Negozi alimentari Overture, con colonne nello stesso formato di match.load_osm().

    Nota etica (§2): le categorie con una provenienza (es. 'korean_grocery_store')
    vengono ridotte a 'grocery_store'. La provenienza non è mai un segnale.
    """
    f = RAW / "overture_places.parquet"
    if not f.exists():
        return None
    d = duckdb.connect().execute(f"SELECT * FROM '{f.as_posix()}' WHERE {FOOD}").df()
    # nomi che vengono solo da BrightQuery (registri delle imprese): possono contenere nomi
    # di persone fisiche (§2), quindi si tengono solo categoria e posizione, senza nome
    solo_bq = d.fonti.str.contains("BrightQuery") & ~d.fonti.str.contains("meta|Foursquare|Microsoft|AllThePlaces|Uberall|PinMeTo")
    d["nome"] = d.nome.where(~solo_bq, None)
    d["marchio"] = d.marchio.where(~solo_bq, None)
    cat = d.categoria.fillna("").where(~d.categoria.fillna("").str.endswith("grocery_store"), "grocery_store")
    return d.assign(osm_lon=d.lon, osm_lat=d.lat, osm_name=d.nome.fillna(""), osm_brand=d.marchio.fillna(""),
                    ov_id=d.id, ov_nome=d.nome, ov_categoria=cat, ov_stato=d.operating_status.fillna(""),
                    ov_indirizzo=d.indirizzo.fillna(""))[
        ["osm_lon", "osm_lat", "osm_name", "osm_brand", "ov_id", "ov_nome", "ov_categoria", "ov_stato", "ov_indirizzo"]
    ].reset_index(drop=True)
