# MiniPa Milano — v1

Mappa dei minimarket indipendenti aperti la sera e la notte a Milano. Parte dai dati aperti e cresce con le segnalazioni di chi è a Milano. La specifica (`HANDOFF_pakibo_milano.md`) resta solo in locale, fuori dal repository.

**Cartella:** il progetto sta nella radice di `20261121_MINIPA/`, senza la sottocartella `minipa/`, perché la cartella è dedicata solo a questo.

## Come si lancia

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m src.run            # usa i file già scaricati in data/raw/
.venv\Scripts\python -m src.run --refresh  # scarica di nuovo DS49, DS58 e OSM
```

Poi apri `web/index.html` con doppio clic. Non serve nessuna build. Serve la connessione a internet per Leaflet e per le tile della mappa.

## Fonti e licenze

| Fonte | Uso | Licenza | Data dei dati |
|---|---|---|---|
| A. DS49 – Esercizi di vicinato in sede fissa (Comune di Milano, CKAN) | universo dei negozi, identikit | CC BY 4.0 | risorsa aggiornata il 31/08/2026 |
| B. DS58 – Pubblici esercizi in piano (Comune di Milano, CKAN) | densità di bar e ristoranti entro 200 m | CC BY 4.0 | 31/08/2026 |
| C. Ordinanze movida 2026 | zone movida | atti del Comune | estiva 11/06–02/11/2026, Duomo/Arco 31/07–29/08/2026 |
| D. OpenStreetMap (Overpass) | orari (`opening_hours`), tipo di negozio | ODbL | snapshot del 21/11/2026 |
| I. Overture Maps Places (release mensile, letta con DuckDB) | nome usato online, categoria (minimarket/alimentari/specializzato), stato "chiuso per sempre", negozi assenti dal DS49 | CDLA Permissive 2.0 (+ODbL) | release 2026-11-18 |
| J. Guide sul web (`data/manual/fonti_web.csv`, compilato a mano) | oggi la guida [ZERO "I minimarket notturni"](https://zero.eu/it/guide/i-minimarket-notturni/), 14 negozi | si usano solo indirizzo e ora di chiusura, con link alla fonte | guida del 28/11/2019: prova datata, quindi blocco orari al massimo 0,5 |
| E. Google Places (API New, Text Search) | solo sul PC: zone da ~1 km dal centro verso l'esterno, 30 richieste/giorno (tetto Google + tetto interno 900/mese), costo 0 € | termini Google Maps Platform EEA | cache locale max 30 giorni |
| F, G, H (Open Wifi, Mapillary, storico DS49) | non usate nella v1 | — | — |

La data di download e l'URL di ogni fonte sono nei file `data/raw/*.meta.json`.

**Nota sul DS49:** l'ID della risorsa CSV è cambiato rispetto all'handoff (ora `95ef10f2-…`). La pipeline ricava l'URL a ogni download con `package_show`, quindi il cambio non la rompe.

## Risultati (run del 21/11/2026)

- Negozi DS49 con coordinate: 27.886, più 430 negozi OSM senza riga DS49 (record `OSM:…`).
- **Candidati** (con un segnale alimentare, catene escluse): 7.519. Tutti tentati in abbinamento con OSM (100%).
- **Tasso di match OSM: 6,0%** (448 candidati): 355 solo per distanza, 8 per insegna più distanza, 85 record solo OSM.
- Candidati con orari noti: 68, di cui 13 aperti dopo mezzanotte.
- **Fasce:** 5 probabili (≥70), 80 da verificare (40–69), 1.038 da scoprire (30–39), il resto escluso.

Le statistiche aggiornate stanno in `data/output/stats.json`.

**Il limite principale è OSM.** A Milano ci sono solo circa 920 negozi mappati come convenience, supermarket, kiosk o alcohol, e appena 283 hanno gli orari. Inoltre il DS49 ha l'insegna solo in 1 caso su 6 e l'ATECO in 1 caso su 14, quindi quasi tutti gli abbinamenti sono per sola distanza. Senza Google, la fascia ≥70 resterà piccola finché non si aggiunge altra prova degli orari: verifica sul campo o orari aggiunti su OSM.

## Modello di punteggio

Punteggio = 35·identikit + 25·contesto + 40·orari. Ogni blocco vale da 0 a 1. I pesi sono quelli dell'handoff, da ricalibrare con `src/calibrate.py`.

- **Identikit:** ATECO 47.11 +0,45; settore alimentare +0,15; misto +0,25, con +0,15 in più se misto e superficie ≤ 40 m². È la firma che emerge dai negozi della guida ZERO: 7 su 9 contro il 20% dei candidati; parole chiave merceologiche o di orario nell'insegna +0,25; OSM `convenience` +0,25 (`alcohol`/`supermarket` +0,10); superficie < 100 m² +0,15 (100–250 m² +0,05).
  - Senza almeno un segnale alimentare il blocco vale 0.
  - Una catena (blacklist in `src/features.py`) porta il blocco a 0 e il punteggio a non più di 39: resta nel dataset con `catena=true`, ma fuori dalla mappa.
- **Contesto:** 0,7 × percentile dei pubblici esercizi entro 200 m, più 0,3 se il negozio è in una zona movida.
- **Orari (da OSM):** 24h = 1; chiusura dopo le 00:00 = 0,8; dopo le 22:00 = 0,5; orari non noti = 0.

**Fasce:**
- ≥70 probabile;
- 40–69 coda di verifica;
- 30–39 da scoprire: la base allargata che chi è a Milano può confermare o scartare;
- sotto 30 escluso dalla mappa, ma conservato nel dataset.

**Abbinamento DS49 ↔ OSM** (`src/match.py`):
- se c'è l'insegna: raggio 30 m e `token_set_ratio` ≥ 70;
- se l'insegna manca: l'elemento OSM più vicino entro 30 m, assegnato a un solo negozio.

## Segnalazioni (note OpenStreetMap)

Chi apre la mappa può toccare un negozio e segnalare:
- ✅ aperto adesso / ❌ chiuso adesso, con l'ora di chiusura se la conosce e gli orari esposti;
- 🏪 è un minimarket: conferma che il negozio è davvero un minimarket;
- chiuso per sempre;
- non è un minimarket.

Con "＋ Nuovo negozio" si aggiunge un punto che non è in mappa.

**Come funziona:**
- Ogni segnalazione diventa una **nota OSM anonima** con il tag `#minipa`, inviata dal browser alle API di OSM. Non serve un server, non serve un account e non costa niente. Le note sono pubbliche, e i mappatori OSM possono usarle per aggiungere `opening_hours`.
- `src/segnalazioni.py` rilegge le note a ogni run e le trasforma in prove:
  - "aperto" visto dopo le 22 alza il blocco orari (0,5, oppure 0,8 se dopo mezzanotte);
  - 2 o più conferme notturne, senza segnalazioni contrarie, portano il negozio almeno a 70;
  - più "chiuso" che "aperto" di notte limitano il punteggio a 39;
  - "è un minimarket" porta il blocco identikit almeno a 0,8;
  - "chiuso per sempre" lo azzera; "non è un minimarket" lo azzera solo se le smentite superano le conferme;
  - i negozi nuovi entrano come record `SEG:<id nota>`.
- Le segnalazioni aperto/chiuso finiscono anche in `data/ground_truth_segnalazioni.csv`, che `calibrate.py` usa insieme a `data/ground_truth.csv`.
- **Per provare senza scrivere su OSM vero:** apri `index.html?osm=dev`. Le note vanno al server di prova `master.apis.dev.openstreetmap.org`.

## Google Places: punti "da confermare"

`python -m src.fetch_places --vai` (solo sul PC, mai nel workflow) cerca "minimarket alimentari" zona per zona. `python -m src.places_match` abbina i risultati ai negozi MiniPa e scrive due file:
- `data/output/coda_google.csv`: privato, ignorato da git. Contiene orari e tipi Google e serve per decidere dove mandare chi verifica.
- `data/manual/google_da_confermare.csv`: pubblico. Contiene **solo** place_id, coordinate e data, per i luoghi che Google dà aperti dopo le 22.

**In mappa:**
- I punti che non abbiamo diventano **segnaposti viola "da confermare"**. Il popup ha il link a Google Maps e i pulsanti di segnalazione, senza nessun altro dato Google.
- I negozi che abbiamo già ricevono solo il link a Google Maps.

**Termini EEA di Google Maps Platform:** con una mappa qualsiasi si possono usare solo latitudine, longitudine e place_id ([Places API adjustments for EEA customers](https://developers.google.com/maps/comms/eea/places)). Resta da verificare nel documento "EEA Places API Permitted Uses" se sia lecito scegliere i punti in base agli orari: è una decisione presa da Giovanni il 22/11/2026.

**Regole dei punti viola:**
- scadono dopo 30 giorni se non vengono riscaricati;
- con la prima segnalazione sul posto diventano negozi MiniPa normali;
- i dati Google non finiscono mai nelle note OSM.

## Pubblicazione (GitHub Pages)

`.github/workflows/pages.yml` ogni notte alle 05:00 fa tre cose:
1. riscarica DS49, DS58, OSM e le segnalazioni;
2. ricalcola i punteggi;
3. pubblica `web/` su GitHub Pages.

Si può anche lanciare a mano dalla scheda Actions. `data/raw`, `data/output` e `web/data.js` non stanno nel repository: li rigenera il workflow.

**Se una fonte non risponde** (es. il portale del Comune, giù il 22/11/2026), la pipeline usa l'ultima copia: prima la cache del workflow, poi `data/seed/`, che è una copia di DS49 e DS58 nel repository (CC BY 4.0). Nel log compare un avviso `ATTENZIONE`.

GitHub sospende i workflow pianificati dopo 60 giorni senza commit. In quel caso basta riattivarlo dalla scheda Actions.

## Vincolo etico

Regole aggiunte con Overture (22/11/2026):
- I nomi che vengono **solo da BrightQuery**, cioè da registri delle imprese, non si usano: possono contenere nomi di persone fisiche. Di quei negozi si tengono solo categoria e posizione.
- Le categorie Overture che indicano una provenienza (es. `korean_grocery_store`) diventano `grocery_store`.
- I marchi di catena corti o ambigui (MD, Pam, Coop, U2…) contano solo a inizio nome. Prima "MD" intercettava l'abbreviazione di un nome proprio e "coop" le cooperative.
- Sulla mappa pubblica non compaiono nomi con forme societarie (srl, snc, "di Nome Cognome"…).

Tutti i segnali descrivono il negozio: merce, dimensione, orari, posizione e contesto. L'insegna serve solo a tre cose: cercare parole chiave merceologiche o di orario, riconoscere le catene e fare l'abbinamento con OSM. Nessuna feature usa nomi di persone, nazionalità, etnia o dati del Registro Imprese.

## Zone movida: approssimazione

Il file `data/manual/zone_movida.csv` descrive ogni zona con un cerchio (centro e raggio), ricavato dall'elenco delle zone delle ordinanze 2026. Non sono le planimetrie ufficiali.

- **Per migliorare:** digitalizzare le planimetrie in `data/manual/zone_movida.geojson`. `src/ordinanze.py` per ora disegna sulla mappa i poligoni di quel file, ma per il punteggio usa ancora i cerchi: va adattato prima di sostituire i cerchi.
- Oggi (21/11) nessuna delle due ordinanze è in vigore. Le uso come indicazione del Comune su dove si vende la sera.

## Output

- `data/output/minipa_milano.geojson` e `.csv`: tutti i candidati e le catene, con `score`, `fascia`, `chiusura_max`, `dopo_mezzanotte`, `fonti_orari`, `catena`, i tre blocchi e i dati del match.
- `data/output/coda_verifica.csv`: la fascia 40–69, ordinata per punteggio.
- `data/output/campione_verifica.csv`: 29 negozi da verificare, stratificati per fascia e municipio. Una volta compilato va copiato in `data/ground_truth.csv`; con almeno 20 righe `calibrate.py` stima i pesi, precision@≥70, recall e matrice di confusione.
- `web/data.js`: i dati della mappa (fasce ≥40). È un file `.js` e non un GeoJSON, così `index.html` funziona anche aperto da disco.

## Struttura

```
src/  fetch_comune.py  fetch_osm.py  fetch_places.py (disattivato)  ordinanze.py
      match.py  features.py  oh.py (parser opening_hours)  score.py  calibrate.py  run.py
data/ raw/  interim/  manual/zone_movida.csv  ground_truth.csv  output/
web/  index.html  data.js
```
