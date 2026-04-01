"""
SCRAPER QUOTE ANOMALE — LuckSport 1x2
Scrapa quote medie apertura + live da https://1x2.lucksport.com/default_en.shtml
Salva in collection MongoDB `quote_anomale`.
Quote apertura scritte una sola volta ($setOnInsert), live aggiornate ad ogni run.
"""
import os
import sys
import time
import re
import atexit
from datetime import datetime, timezone

# --- Cleanup Chrome ---
_active_driver = None
def _cleanup():
    global _active_driver
    if _active_driver:
        try: _active_driver.quit()
        except: pass
        _active_driver = None
atexit.register(_cleanup)

# --- Fix percorsi ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)
if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend")
    try:
        from config import db
    except:
        print("❌ Impossibile connettersi al DB.")
        sys.exit(1)

from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    print("❌ Selenium non installato.")
    sys.exit(1)

# --- Configurazione ---
URL = "https://1x2.lucksport.com/default_en.shtml"
COLLECTION = "quote_anomale"

# Mappa codici LuckSport → nomi campionato nel nostro DB
# Solo i campionati mappati vengono scrapeati, gli altri ignorati
LEAGUE_MAP = {
    # ITALIA
    "ITA D1": "Serie A",
    "ITA D2": "Serie B",
    "ITA C1-A": "Serie C - Girone A",
    "ITA C1-B": "Serie C - Girone B",
    "Italy C1C": "Serie C - Girone C",
    # INGHILTERRA
    "ENG PR": "Premier League",
    "ENG LCH": "Championship",
    "ENG D1": "League One",
    "ENG D2": "League Two",             # TODO: verificare — potrebbe essere ENG D2 o altro
    # SPAGNA
    "SPA D1": "La Liga",
    "SPA D2": "LaLiga 2",
    # GERMANIA
    "GER D1": "Bundesliga",
    "GER D2": "2. Bundesliga",
    "GER D3": "3. Liga",
    # FRANCIA
    "FRA D1": "Ligue 1",
    "FRA D2": "Ligue 2",
    # OLANDA
    "HOL D1": "Eredivisie",
    "HOL D2": "Eerste Divisie",
    # PORTOGALLO
    "POR D1": "Liga Portugal",
    "POR D2": "Liga Portugal 2",
    # SCOZIA
    "SCO PR": "Scottish Premiership",
    "SCO LCH": "Scottish Championship",
    # BELGIO
    "BEL D1": "Jupiler Pro League",
    # TURCHIA
    "TUR D1": "Süper Lig",
    "TFF 1. Lig": "1. Lig",
    # ARABIA SAUDITA
    "KSA PR": "Saudi Pro League",
    # AMERICHE
    "BRA D1": "Brasileirão Serie A",
    "ARG D1": "Primera División",
    "USA MLS": "Major League Soccer",
    "MEX D1": "Liga MX",
    # ASIA
    "JPN D1": "J1 League",
    # SCANDINAVIA
    "SWE D1": "Allsvenskan",
    "FIN D1": "Veikkausliiga",
    "DEN D1": "Superligaen",
    "DEN SASL": "Superligaen",          # Potrebbe essere questo il codice, teniamo entrambi
    "NOR PR": "Eliteserien",
    "NOR D1": "Eliteserien",
    # IRLANDA
    "IRE PR": "League of Ireland Premier Division",
    # COPPE EUROPEE
    "UEFA CL": "Champions League",
    "UEFA EL": "Europa League",
}

# Modalità: "apertura" (pipeline notturna) o "live" (pre-match -2h)
# In modalità apertura: salva solo quote_apertura ($setOnInsert)
# In modalità live: aggiorna quote_chiusura ($set) + calcola indicatori
MODE = os.environ.get("QA_MODE", "apertura")  # default: apertura


def _crea_driver(headless=True):
    """Crea Chrome driver."""
    global _active_driver
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    # Disabilita immagini per velocità
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    _active_driver = driver
    return driver


def _parse_float(text):
    """Converte testo in float, ritorna None se non valido."""
    try:
        val = float(text.strip())
        return val if val > 0 else None
    except (ValueError, AttributeError):
        return None


def _normalize_match_key(home, away):
    """Crea match_key normalizzato: lowercase, senza caratteri speciali."""
    def _clean(name):
        name = name.lower().strip()
        name = re.sub(r'[^a-z0-9\s]', '', name)
        name = re.sub(r'\s+', '_', name)
        return name
    return f"{_clean(home)}_vs_{_clean(away)}"


def _parse_date(date_text):
    """Converte '31/03/2026 (Tuesday)' in '2026-03-31'."""
    match = re.match(r'(\d{2})/(\d{2})/(\d{4})', date_text.strip())
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    return None


def scrape_lucksport(driver, target_date=None):
    """
    Scrapa tutte le partite da LuckSport.

    Args:
        driver: Selenium WebDriver
        target_date: stringa 'YYYY-MM-DD' per filtrare solo una data specifica.
                     Se None, scrapa tutte le date disponibili.

    Returns:
        list of dict con i dati grezzi delle partite
    """
    print(f"📡 Navigazione a {URL}...")
    driver.get(URL)

    # Attendi rendering JS
    print("⏳ Attendo rendering pagina...")
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.t1"))
        )
        time.sleep(3)  # Extra wait per rendering completo
    except Exception:
        print("⚠️ Timeout attesa tabella, provo comunque...")
        time.sleep(5)

    # Parse HTML
    soup = BeautifulSoup(driver.page_source, "html.parser")
    table = soup.find("table", class_="t1")
    if not table:
        print("❌ Tabella t1 non trovata!")
        return []

    rows = table.find_all("tr")
    print(f"📊 Trovate {len(rows)} righe nella tabella")

    matches = []
    current_date = None
    skip_date = False
    i = 0

    while i < len(rows):
        row = rows[i]

        # --- Separatore data ---
        date_cell = row.find("td", class_="w1")
        if date_cell:
            date_text = date_cell.get_text(strip=True)
            parsed_date = _parse_date(date_text)
            if parsed_date:
                current_date = parsed_date
                # Se target_date specificata, filtra
                if target_date:
                    skip_date = (current_date != target_date)
                    if not skip_date:
                        print(f"   📅 Data trovata: {current_date}")
                else:
                    print(f"   📅 Data: {current_date}")
            i += 1
            continue

        # Salta se data non corrispondente
        if skip_date:
            i += 1
            continue

        # --- Intestazione (lot1) → salta ---
        if row.get("class") and "lot1" in row.get("class", []):
            i += 1
            continue

        # --- Riga partita (dtd1 o dtd2) ---
        row_classes = row.get("class", [])
        if not row_classes or not any(c in row_classes for c in ["dtd1", "dtd2"]):
            i += 1
            continue

        cells = row.find_all("td")

        # La riga 1 di una partita ha rowspan=2 su campionato, orario, squadre
        # Controlliamo se è la riga con il campionato (ha almeno 7-8 celle)
        has_rowspan = any(c.get("rowspan") for c in cells)

        if not has_rowspan:
            # Questa è una riga live orfana (senza riga apertura sopra) → salta
            i += 1
            continue

        # Riga 1: apertura
        try:
            # Estrai dati dalla riga con rowspan
            league_cell = row.find("td", class_="ss1")
            league_raw = league_cell.get_text(strip=True) if league_cell else "Unknown"

            # Filtra: solo campionati mappati
            if league_raw not in LEAGUE_MAP:
                i += 1
                continue

            league = LEAGUE_MAP[league_raw]

            # Le celle senza class speciale e con rowspan sono orario e squadre
            rowspan_cells = [c for c in cells if c.get("rowspan")]

            # Orario: seconda cella con rowspan (la prima è il campionato)
            match_time = ""
            home = ""
            away = ""

            # Cerchiamo nell'ordine: campionato(ss1), orario, home, quote(sw1)x3, away, compare
            # L'orario è la seconda cella con rowspan
            time_found = False
            for c in rowspan_cells:
                if c == league_cell:
                    continue
                text = c.get_text(strip=True)
                if re.match(r'^\d{1,2}:\d{2}$', text) and not time_found:
                    match_time = text
                    time_found = True
                elif time_found and not home:
                    home = text
                elif home and not away:
                    # Potrebbe essere il link compare
                    if text.lower() != 'compare':
                        away = text

            # Quote apertura (classe sw1)
            odds_cells = row.find_all("td", class_="sw1")
            if len(odds_cells) < 3:
                i += 1
                continue

            q1_ap = _parse_float(odds_cells[0].get_text(strip=True))
            qx_ap = _parse_float(odds_cells[1].get_text(strip=True))
            q2_ap = _parse_float(odds_cells[2].get_text(strip=True))

            if not all([q1_ap, qx_ap, q2_ap]):
                i += 1
                continue

            # Riga 2: live (riga successiva)
            q1_live = None
            qx_live = None
            q2_live = None

            if i + 1 < len(rows):
                next_row = rows[i + 1]
                next_classes = next_row.get("class", [])

                if any(c in next_classes for c in ["dtd1", "dtd2"]):
                    live_cells = next_row.find_all("td")
                    # La riga live ha solo 3 celle (odds1/odds2)
                    odds_live = [c for c in live_cells
                                 if any(cl in (c.get("class") or []) for cl in ["odds1", "odds2"])]

                    if len(odds_live) >= 3:
                        q1_live = _parse_float(odds_live[0].get_text(strip=True))
                        qx_live = _parse_float(odds_live[1].get_text(strip=True))
                        q2_live = _parse_float(odds_live[2].get_text(strip=True))

                    i += 1  # Salta la riga live

            # Salva match
            if current_date and home and away:
                match_data = {
                    "date": current_date,
                    "league": league,
                    "league_raw": league_raw,
                    "match_time": match_time,
                    "home_raw": home,
                    "away_raw": away,
                    "match_key": _normalize_match_key(home, away),
                    "quote_apertura": {"1": q1_ap, "X": qx_ap, "2": q2_ap},
                }

                # Aggiungi live solo se disponibili
                if all([q1_live, qx_live, q2_live]):
                    match_data["quote_chiusura"] = {"1": q1_live, "X": qx_live, "2": q2_live}

                matches.append(match_data)

        except Exception as e:
            print(f"   ⚠️ Errore parsing riga {i}: {e}")

        i += 1

    return matches


def salva_in_mongodb(matches, mode="apertura"):
    """
    Salva le partite in MongoDB.

    mode="apertura": $setOnInsert per quote_apertura + primo snapshot storico
    mode="live": $set quote_chiusura + $push snapshot su storico
    """
    collection = db[COLLECTION]

    inseriti = 0
    aggiornati = 0
    errori = 0
    now = datetime.now(timezone.utc)

    for m in matches:
        try:
            match_key = m["match_key"]
            date = m["date"]

            if mode == "apertura":
                # Primo snapshot: quote apertura
                snapshot_apertura = {
                    "ts": now,
                    "label": "apertura",
                    "quote": m["quote_apertura"],
                }

                result = collection.update_one(
                    {"date": date, "match_key": match_key},
                    {
                        "$setOnInsert": {
                            "home_raw": m["home_raw"],
                            "away_raw": m["away_raw"],
                            "league": m["league"],
                            "league_raw": m["league_raw"],
                            "match_time": m["match_time"],
                            "quote_apertura": m["quote_apertura"],
                            "ts_apertura": now,
                            "n_aggiornamenti": 0,
                            "storico": [snapshot_apertura],
                        }
                    },
                    upsert=True
                )
                if result.upserted_id:
                    inseriti += 1

            elif mode == "live":
                # Quote live da salvare
                quote_live = m.get("quote_chiusura")
                if not quote_live:
                    continue

                # Snapshot con quote live (indicatori aggiunti dopo dal calcolatore)
                snapshot = {
                    "ts": now,
                    "label": "live",
                    "quote": quote_live,
                }

                result = collection.update_one(
                    {"date": date, "match_key": match_key},
                    {
                        "$set": {
                            "quote_chiusura": quote_live,
                            "ts_chiusura": now,
                        },
                        "$inc": {"n_aggiornamenti": 1},
                        "$push": {"storico": snapshot},
                        # Se non esiste ancora, crea con apertura
                        "$setOnInsert": {
                            "home_raw": m["home_raw"],
                            "away_raw": m["away_raw"],
                            "league": m["league"],
                            "league_raw": m["league_raw"],
                            "match_time": m["match_time"],
                            "quote_apertura": m["quote_apertura"],
                            "ts_apertura": now,
                        }
                    },
                    upsert=True
                )
                if result.modified_count > 0:
                    aggiornati += 1
                elif result.upserted_id:
                    inseriti += 1

        except Exception as e:
            print(f"   ❌ Errore MongoDB per {m.get('home_raw', '?')} vs {m.get('away_raw', '?')}: {e}")
            errori += 1

    return inseriti, aggiornati, errori


def run_scraper(target_date=None, mode=None, headless=True):
    """
    Entry point principale.

    Args:
        target_date: 'YYYY-MM-DD' o None per tutte le date
        mode: 'apertura' o 'live' (override env QA_MODE)
        headless: True per Chrome senza finestra
    """
    if mode is None:
        mode = MODE

    print(f"\n{'='*60}")
    print(f"📊 SCRAPER QUOTE ANOMALE — LuckSport")
    print(f"   Modalità: {mode}")
    print(f"   Data target: {target_date or 'tutte'}")
    print(f"   Orario: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")

    start_time = time.time()

    # Crea browser
    driver = _crea_driver(headless=headless)

    try:
        # Scrapa
        matches = scrape_lucksport(driver, target_date=target_date)
        print(f"\n📈 Partite scrapeate: {len(matches)}")

        if not matches:
            print("⚠️ Nessuna partita trovata!")
            return {"scraped": 0, "inserted": 0, "updated": 0, "errors": 0}

        # Log campionati trovati
        leagues = set(m["league_raw"] for m in matches)
        print(f"   Campionati: {len(leagues)}")
        for lg in sorted(leagues):
            count = sum(1 for m in matches if m["league_raw"] == lg)
            print(f"      {lg}: {count} partite")

        # Conta partite con quote live
        with_live = sum(1 for m in matches if "quote_chiusura" in m)
        print(f"   Con quote live: {with_live}/{len(matches)}")

        # Salva in MongoDB
        print(f"\n💾 Salvataggio in MongoDB (mode={mode})...")
        inseriti, aggiornati, errori = salva_in_mongodb(matches, mode=mode)

        elapsed = time.time() - start_time
        print(f"\n{'='*60}")
        print(f"✅ COMPLETATO in {elapsed:.1f}s")
        print(f"   Inseriti: {inseriti}")
        print(f"   Aggiornati: {aggiornati}")
        print(f"   Errori: {errori}")
        print(f"{'='*60}\n")

        return {
            "scraped": len(matches),
            "inserted": inseriti,
            "updated": aggiornati,
            "errors": errori,
        }

    finally:
        driver.quit()
        global _active_driver
        _active_driver = None


# --- Crea indici MongoDB (eseguito una volta) ---
def _ensure_indexes():
    """Crea gli indici necessari se non esistono."""
    collection = db[COLLECTION]
    try:
        collection.create_index([("date", 1), ("match_key", 1)], unique=True)
        collection.create_index([("date", 1), ("league", 1)])
        collection.create_index([("date", 1), ("league_raw", 1)])
        collection.create_index("date")
        print("✅ Indici MongoDB verificati/creati.")
    except Exception as e:
        print(f"⚠️ Errore creazione indici: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scraper Quote Anomale - LuckSport")
    parser.add_argument("--date", type=str, default=None,
                        help="Data target YYYY-MM-DD (default: tutte)")
    parser.add_argument("--mode", type=str, choices=["apertura", "live"], default=None,
                        help="Modalità: apertura o live (default: env QA_MODE o apertura)")
    parser.add_argument("--no-headless", action="store_true",
                        help="Mostra il browser (per debug)")
    parser.add_argument("--create-indexes", action="store_true",
                        help="Crea indici MongoDB ed esci")

    args = parser.parse_args()

    if args.create_indexes:
        _ensure_indexes()
        sys.exit(0)

    # Se non specificata data: scrapa TUTTE le date visibili su LuckSport
    # (apertura cattura anche le partite future: domani, dopodomani, ecc.)
    target_date = args.date

    run_scraper(
        target_date=target_date,
        mode=args.mode,
        headless=not args.no_headless
    )
