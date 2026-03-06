"""
scrape_snai_exact_score.py — Mini-scraper quote Risultato Esatto da SNAI.it

Legge dalla collection `re_quota_requests` le richieste pendenti generate da
orchestrate_experts.py, naviga su SNAI per la lega corretta, trova la partita,
apre il dropdown "RISULTATI" e legge la quota del risultato esatto richiesto.

Aggiorna:
  - re_quota_requests.status → 'done' / 'not_found'
  - daily_predictions_unified.pronostici[tipo=RISULTATO_ESATTO].quota
"""
import os
import sys
import time
from datetime import datetime

# Fix percorsi
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config import db
    print(f"DB Connesso: {db.name}")
except ImportError:
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend\ai_engine")
    from config import db

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ============================================================
#  MAPPING LEGA → URL SNAI (copiato da scrape_snai_odds.py)
# ============================================================
LEAGUE_TO_SNAI_URL = {
    # ITALIA
    "Serie A": "https://www.snai.it/sport/CALCIO/SERIE%20A",
    "Serie B": "https://www.snai.it/sport/CALCIO/SERIE%20B",
    "Serie C": "https://www.snai.it/sport/CALCIO/SERIE%20C",
    "Serie C - Girone A": "https://www.snai.it/sport/CALCIO/SERIE%20C",
    "Serie C - Girone B": "https://www.snai.it/sport/CALCIO/SERIE%20C",
    "Serie C - Girone C": "https://www.snai.it/sport/CALCIO/SERIE%20C",
    # EUROPA TOP
    "Premier League": "https://www.snai.it/sport/CALCIO/PREMIER%20LEAGUE",
    "La Liga": "https://www.snai.it/sport/CALCIO/LIGA",
    "Bundesliga": "https://www.snai.it/sport/CALCIO/BUNDESLIGA",
    "Ligue 1": "https://www.snai.it/sport/CALCIO/LIGUE%201",
    "Eredivisie": "https://www.snai.it/sport/CALCIO/OLANDA%201",
    "Liga Portugal": "https://www.snai.it/sport/CALCIO/PORTOGALLO%201",
    # EUROPA SERIE B
    "Championship": "https://www.snai.it/sport/CALCIO/CHAMPIONSHIP",
    "LaLiga 2": "https://www.snai.it/sport/CALCIO/SPAGNA%202",
    "2. Bundesliga": "https://www.snai.it/sport/CALCIO/GERMANIA%202",
    "Ligue 2": "https://www.snai.it/sport/CALCIO/FRANCIA%202",
    # EUROPA NORDICI + EXTRA
    "Scottish Premiership": "https://www.snai.it/sport/CALCIO/SCOZIA%201",
    "Allsvenskan": "https://www.snai.it/sport/CALCIO/SVEZIA%201",
    "Eliteserien": "https://www.snai.it/sport/CALCIO/NORVEGIA%201",
    "Superligaen": "https://www.snai.it/sport/CALCIO/DANIMARCA%201",
    "Jupiler Pro League": "https://www.snai.it/sport/CALCIO/BELGIO%201",
    "Super Lig": "https://www.snai.it/sport/CALCIO/TURCHIA%201",
    "League of Ireland Premier Division": "https://www.snai.it/sport/CALCIO/IRLANDA%201",
    # AMERICHE
    "Brasileirao Serie A": "https://www.snai.it/sport/CALCIO/BRASILE%201",
    "Primera Division": "https://www.snai.it/sport/CALCIO/ARGENTINA%201",
    "Major League Soccer": "https://www.snai.it/sport/CALCIO/USA%20MLS",
    # ASIA
    "J1 League": "https://www.snai.it/sport/CALCIO/GIAPPONE%201",
    # COPPE
    "Champions League": "https://www.snai.it/sport/CALCIO/CHAMPIONS%20LEAGUE",
    "Europa League": "https://www.snai.it/sport/CALCIO/EUROPA%20LEAGUE",
}


# ============================================================
#  NORMALIZZAZIONE NOMI (stessa logica dello scraper principale)
# ============================================================
def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    replacements = {
        "\u00fc": "u", "\u00f6": "o", "\u00e9": "e", "\u00e8": "e", "\u00e0": "a", "\u00ec": "i",
        "\u00f1": "n", "\u00e3": "a", "\u00e7": "c", "\u00e1": "a", "\u00ed": "i",
        "\u00f3": "o", "\u00fa": "u", "\u00ea": "e", "\u00f4": "o", "\u00e2": "a",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    prefixes = ["fc ", "cf ", "ac ", "as ", "sc ", "us ", "ss ", "asd ", "asc "]
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
    suffixes = [" fc", " cf", " ac", " calcio", " 1913", " 1928", " 1918"]
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


def get_team_aliases(team_name, team_doc=None):
    """Genera lista di alias per una squadra (copiato da scrape_snai_odds.py)."""
    aliases = {team_name.lower(), normalize_name(team_name)}
    if team_doc and 'aliases' in team_doc:
        for a in team_doc['aliases']:
            aliases.add(a.lower())
            aliases.add(normalize_name(a))
    # Parti del nome (es. "Estoril Praia" -> "estoril")
    # Min 5 chars per evitare alias ambigui ("city", "real", "club", ecc.)
    parts = team_name.lower().split()
    if len(parts) > 1:
        for p in parts:
            if len(p) >= 5:
                aliases.add(p)
    return aliases


def names_match_aliases(aliases, snai_name):
    """Verifica se il nome SNAI corrisponde a uno degli alias."""
    snai_norm = normalize_name(snai_name)
    snai_low = snai_name.lower().strip()
    return any(
        a in snai_norm or a in snai_low or snai_norm in a or snai_low in a
        for a in aliases
    )


# ============================================================
#  SELENIUM
# ============================================================
def init_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    return webdriver.Chrome(options=options)


def close_cookie_banner(driver):
    try:
        for btn in driver.find_elements(By.CSS_SELECTOR, '[class*="cookiebanner"] button'):
            if 'accett' in btn.text.lower():
                btn.click()
                time.sleep(1)
                return True
    except Exception:
        pass
    try:
        driver.execute_script("document.querySelector('[class*=\"cookiebanner\"]')?.remove()")
    except Exception:
        pass
    return False


def click_mostra_di_piu(driver):
    """Clicca il bottone 'Mostra di piu' per espandere i mercati."""
    try:
        buttons = driver.find_elements(
            By.CSS_SELECTOR, '[class*="ScommesseAccordionFilterPrimary_button"]'
        )
        for btn in buttons:
            if 'MOSTRA' in btn.text.strip().upper():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(3)
                return True
    except Exception as e:
        print(f"    Errore click 'Mostra di piu': {e}")
    return False


def click_risultati_tab(driver):
    """Clicca il bottone 'RISULTATI' nella griglia filtri ScommesseFiltersList.
    NOTA: i bottoni sono duplicati (mobile/desktop). Serve l'ULTIMO match."""
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            risultati_btn = None
            buttons = driver.find_elements(
                By.CSS_SELECTOR, '[class*="ScommesseFiltersList_button"]'
            )
            for btn in buttons:
                if btn.text.strip().upper() == 'RISULTATI':
                    risultati_btn = btn  # prendi l'ultimo (desktop)
            if risultati_btn:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", risultati_btn)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", risultati_btn)
                # Attendi che il dropdown RE appaia (polling fino a 10s)
                for _ in range(10):
                    time.sleep(1)
                    dropdowns = driver.find_elements(By.CSS_SELECTOR, '[class*="ScommesseTableQuotaSelectContainer_button"]')
                    if dropdowns:
                        return True
                # Dropdown non apparso — retry con scroll top + Mostra di piu
                if attempt < max_attempts - 1:
                    print(f"    Dropdown RE non apparso, retry ({attempt+1}/{max_attempts})...")
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    click_mostra_di_piu(driver)
                    time.sleep(1)
                    continue
                # Ultimo tentativo fallito, procedi comunque
                return True
        except Exception as e:
            print(f"    Errore click 'RISULTATI': {e}")
    return False


def find_match_row(driver, home_aliases, away_aliases):
    """Trova la riga della partita nella pagina SNAI. Ritorna l'elemento container o None."""
    containers = driver.find_elements(By.CSS_SELECTOR, '[class*="ScommesseTableRow_container"]')
    for c in containers:
        try:
            names = c.find_elements(By.CSS_SELECTOR, '[class*="Competitors_name"]')
            if len(names) >= 2:
                snai_home = names[0].text.strip()
                snai_away = names[1].text.strip()
                if names_match_aliases(home_aliases, snai_home) and names_match_aliases(away_aliases, snai_away):
                    return c
        except Exception:
            continue

    # Scroll per trovare partite non visibili (virtual scrolling)
    for _ in range(20):
        driver.execute_script("window.scrollBy(0, 400);")
        time.sleep(0.8)
        containers = driver.find_elements(By.CSS_SELECTOR, '[class*="ScommesseTableRow_container"]')
        for c in containers:
            try:
                names = c.find_elements(By.CSS_SELECTOR, '[class*="Competitors_name"]')
                if len(names) >= 2:
                    snai_home = names[0].text.strip()
                    snai_away = names[1].text.strip()
                    if names_match_aliases(home_aliases, snai_home) and names_match_aliases(away_aliases, snai_away):
                        return c
            except Exception:
                continue
        # Check se siamo in fondo
        at_bottom = driver.execute_script(
            "return Math.ceil(window.scrollY + window.innerHeight) >= document.body.scrollHeight - 5"
        )
        if at_bottom:
            break

    return None


def get_exact_score_quota(driver, match_row, target_score):
    """
    Apre il dropdown risultati esatti di una partita e legge la quota
    per il risultato richiesto. target_score formato "H:A" o "H-A".
    Ritorna la quota (float) o None.
    """
    # Normalizza il formato score: "2:1" → "2-1" (SNAI usa il trattino)
    target = target_score.replace(':', '-')

    try:
        # Trova il dropdown button nella riga
        dropdown_btn = match_row.find_element(
            By.CSS_SELECTOR, '[class*="ScommesseTableQuotaSelectContainer_button"]'
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown_btn)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", dropdown_btn)
        time.sleep(1.5)

        # Leggi tutte le opzioni dal menu aperto
        menu_buttons = driver.find_elements(By.CSS_SELECTOR, '[class*="ScommesseQuoteList_btn"]')
        for btn in menu_buttons:
            try:
                score_el = btn.find_element(By.CSS_SELECTOR, '[class*="ScommesseQuoteList_left"]')
                score_text = score_el.text.strip()
                if score_text == target:
                    quota_el = btn.find_element(By.CSS_SELECTOR, '[class*="ScommesseQuoteList_singleItem"]')
                    quota_text = quota_el.text.strip()
                    # Chiudi il dropdown cliccando altrove
                    driver.execute_script("arguments[0].click();", dropdown_btn)
                    time.sleep(0.5)
                    try:
                        return float(quota_text)
                    except ValueError:
                        return None
            except Exception:
                continue

        # Score non trovato, chiudi dropdown
        driver.execute_script("arguments[0].click();", dropdown_btn)
        time.sleep(0.5)
        return None

    except Exception as e:
        print(f"    Errore lettura dropdown RE: {e}")
        return None


# ============================================================
#  MAIN
# ============================================================
def process_requests():
    """Processa le richieste pendenti di quote RE da SNAI."""
    requests = list(db['re_quota_requests'].find({'status': 'pending'}))

    if not requests:
        print("  Nessuna richiesta RE pendente")
        return 0

    print(f"  {len(requests)} richieste RE da processare")

    # Raggruppa per lega (1 navigazione per lega)
    by_league = {}
    for req in requests:
        league = req['league']
        if league not in by_league:
            by_league[league] = []
        by_league[league].append(req)

    driver = None
    processed = 0
    first_page = True

    try:
        driver = init_driver()

        for league, reqs in by_league.items():
            url = LEAGUE_TO_SNAI_URL.get(league)
            if not url:
                print(f"  [{league}] URL SNAI non trovato, skip {len(reqs)} richieste")
                for req in reqs:
                    db['re_quota_requests'].update_one(
                        {'_id': req['_id']},
                        {'$set': {'status': 'no_url', 'processed_at': datetime.now()}}
                    )
                continue

            print(f"\n  [{league}] Navigando... ({len(reqs)} richieste)")
            driver.get(url)
            time.sleep(4)
            # Refresh per partire puliti (evita stato residuo dalla lega precedente)
            driver.refresh()
            time.sleep(5)

            if first_page:
                close_cookie_banner(driver)
                time.sleep(1)
                first_page = False

            # Espandi mercati e vai su RISULTATI
            if not click_mostra_di_piu(driver):
                print(f"  [{league}] 'Mostra di piu' non trovato, skip")
                for req in reqs:
                    db['re_quota_requests'].update_one(
                        {'_id': req['_id']},
                        {'$set': {'status': 'nav_error', 'processed_at': datetime.now()}}
                    )
                continue

            if not click_risultati_tab(driver):
                print(f"  [{league}] Tab 'RISULTATI' non trovato, skip")
                for req in reqs:
                    db['re_quota_requests'].update_one(
                        {'_id': req['_id']},
                        {'$set': {'status': 'nav_error', 'processed_at': datetime.now()}}
                    )
                continue

            time.sleep(1)

            # Processa ogni richiesta di questa lega
            for req in reqs:
                home = req['home']
                away = req['away']
                score = req['score']

                print(f"    {home} vs {away} — RE {score}...", end=" ", flush=True)

                # Carica aliases da DB
                home_doc = db.teams.find_one({"name": home}, {"name": 1, "aliases": 1})
                away_doc = db.teams.find_one({"name": away}, {"name": 1, "aliases": 1})
                home_aliases = get_team_aliases(home, home_doc)
                away_aliases = get_team_aliases(away, away_doc)

                # Trova la riga della partita
                match_row = find_match_row(driver, home_aliases, away_aliases)
                if not match_row:
                    print("partita non trovata")
                    db['re_quota_requests'].update_one(
                        {'_id': req['_id']},
                        {'$set': {'status': 'match_not_found', 'processed_at': datetime.now()}}
                    )
                    continue

                # Leggi la quota
                quota = get_exact_score_quota(driver, match_row, score)
                if quota:
                    print(f"quota {quota}")

                    # Aggiorna la request
                    db['re_quota_requests'].update_one(
                        {'_id': req['_id']},
                        {'$set': {'status': 'done', 'quota': quota, 'processed_at': datetime.now()}}
                    )

                    # Aggiorna daily_predictions_unified
                    db['daily_predictions_unified'].update_one(
                        {
                            'home': home,
                            'away': away,
                            'date': req['date'],
                            'pronostici.tipo': 'RISULTATO_ESATTO',
                            'pronostici.pronostico': score,
                        },
                        {'$set': {'pronostici.$.quota': quota}}
                    )
                    processed += 1
                else:
                    print("quota non trovata")
                    db['re_quota_requests'].update_one(
                        {'_id': req['_id']},
                        {'$set': {'status': 'not_found', 'processed_at': datetime.now()}}
                    )

    except Exception as e:
        print(f"\n  Errore scraper RE: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    print(f"\n  RE quote processate: {processed}/{len(requests)}")
    return processed


if __name__ == '__main__':
    print(f"\n{'='*60}")
    print(f"  SCRAPER SNAI — Quote Risultato Esatto")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    process_requests()
