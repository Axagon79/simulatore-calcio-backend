"""
scrape_snai_odds.py — Scraper quote Over/Under e Goal/NoGoal da SNAI.it

Aggiunge a h2h_by_round.matches[].odds:
  - over_15, under_15, over_25, under_25, over_35, under_35
  - gg, ng
  - src_ou_gg: 'SNAI', ts_ou_gg: datetime

NON tocca le quote 1X2 (restano da NowGoal).

NOTA: SNAI usa virtual scrolling — solo ~13 righe alla volta nel DOM.
Lo scraper scrolla incrementalmente e accumula dati per (home, away).
"""
import os
import sys
import time
from datetime import datetime, timedelta

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
#  CONFIGURAZIONE LEGHE — 24 campionati (URL verificati SNAI)
# ============================================================
LEAGUES_CONFIG = [
    # ITALIA (3)
    {"name": "Serie A", "url": "https://www.snai.it/sport/CALCIO/SERIE%20A", "sidebar": "ITALIA"},
    {"name": "Serie B", "url": "https://www.snai.it/sport/CALCIO/SERIE%20B", "sidebar": "ITALIA"},
    {"name": "Serie C", "url": "https://www.snai.it/sport/CALCIO/SERIE%20C", "sidebar": "ITALIA"},

    # EUROPA TOP (6)
    {"name": "Premier League", "url": "https://www.snai.it/sport/CALCIO/PREMIER%20LEAGUE", "sidebar": "INGHILTERRA"},
    {"name": "La Liga", "url": "https://www.snai.it/sport/CALCIO/LIGA", "sidebar": "SPAGNA"},
    {"name": "Bundesliga", "url": "https://www.snai.it/sport/CALCIO/BUNDESLIGA", "sidebar": "GERMANIA"},
    {"name": "Ligue 1", "url": "https://www.snai.it/sport/CALCIO/LIGUE%201", "sidebar": "FRANCIA"},
    {"name": "Eredivisie", "url": "https://www.snai.it/sport/CALCIO/OLANDA%201", "sidebar": "OLANDA"},
    {"name": "Liga Portugal", "url": "https://www.snai.it/sport/CALCIO/PORTOGALLO%201", "sidebar": "PORTOGALLO"},

    # EUROPA SERIE B (4)
    {"name": "Championship", "url": "https://www.snai.it/sport/CALCIO/CHAMPIONSHIP", "sidebar": "INGHILTERRA"},
    {"name": "LaLiga 2", "url": "https://www.snai.it/sport/CALCIO/SPAGNA%202", "sidebar": "SPAGNA"},
    {"name": "2. Bundesliga", "url": "https://www.snai.it/sport/CALCIO/GERMANIA%202", "sidebar": "GERMANIA"},
    {"name": "Ligue 2", "url": "https://www.snai.it/sport/CALCIO/FRANCIA%202", "sidebar": "FRANCIA"},

    # EUROPA NORDICI + EXTRA (7)
    {"name": "Scottish Premiership", "url": "https://www.snai.it/sport/CALCIO/SCOZIA%201", "sidebar": "SCOZIA"},
    {"name": "Allsvenskan", "url": "https://www.snai.it/sport/CALCIO/SVEZIA%201", "sidebar": "SVEZIA"},
    {"name": "Eliteserien", "url": "https://www.snai.it/sport/CALCIO/NORVEGIA%201", "sidebar": "NORVEGIA"},
    {"name": "Superligaen", "url": "https://www.snai.it/sport/CALCIO/DANIMARCA%201", "sidebar": "DANIMARCA"},
    {"name": "Jupiler Pro League", "url": "https://www.snai.it/sport/CALCIO/BELGIO%201", "sidebar": "BELGIO"},
    {"name": "Süper Lig", "url": "https://www.snai.it/sport/CALCIO/TURCHIA%201", "sidebar": "TURCHIA"},
    {"name": "League of Ireland Premier Division", "url": "https://www.snai.it/sport/CALCIO/IRLANDA%201", "sidebar": "IRLANDA"},

    # AMERICHE (3)
    {"name": "Brasileirão Serie A", "url": "https://www.snai.it/sport/CALCIO/BRASILE%201", "sidebar": "BRASILE"},
    {"name": "Primera División", "url": "https://www.snai.it/sport/CALCIO/ARGENTINA%201", "sidebar": "ARGENTINA"},
    {"name": "Major League Soccer", "url": "https://www.snai.it/sport/CALCIO/USA%20MLS", "sidebar": "USA"},

    # ASIA (1)
    {"name": "J1 League", "url": "https://www.snai.it/sport/CALCIO/GIAPPONE%201", "sidebar": "GIAPPONE"},

    # COPPE EUROPEE (2) — scrivono in matches_champions_league / matches_europa_league
    # sidebar "EUROPA" = la categoria sotto cui SNAI raggruppa le coppe
    {"name": "Champions League", "url": "https://www.snai.it/sport/CALCIO/CHAMPIONS%20LEAGUE", "sidebar": "EUROPA",
     "is_cup": True, "cup_collection": "matches_champions_league", "cup_teams": "teams_champions_league"},
    {"name": "Europa League", "url": "https://www.snai.it/sport/CALCIO/EUROPA%20LEAGUE", "sidebar": "EUROPA",
     "is_cup": True, "cup_collection": "matches_europa_league", "cup_teams": "teams_europa_league"},
]

MAX_RETRIES_EMPTY = 3  # Tentativi di reload se 0 partite trovate


# ============================================================
#  NORMALIZZAZIONE NOMI (stessa logica NowGoal)
# ============================================================
def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    replacements = {
        "ü": "u", "ö": "o", "é": "e", "è": "e", "à": "a", "ì": "i",
        "ñ": "n", "ã": "a", "ç": "c", "á": "a", "í": "i",
        "ó": "o", "ú": "u", "ê": "e", "ô": "o", "â": "a",
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
    """Genera lista di alias per una squadra."""
    aliases = {team_name.lower(), normalize_name(team_name)}
    if team_doc and 'aliases' in team_doc:
        for a in team_doc['aliases']:
            aliases.add(a.lower())
            aliases.add(normalize_name(a))
    # Parti del nome (es. "Estoril Praia" → "estoril")
    # Min 5 chars per evitare alias ambigui ("city", "real", "club", ecc.)
    parts = team_name.lower().split()
    if len(parts) > 1:
        for p in parts:
            if len(p) >= 5:
                aliases.add(p)
    return aliases


# ============================================================
#  SELENIUM HELPERS
# ============================================================
def init_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    return webdriver.Chrome(options=options)


def get_available_countries(driver):
    """
    Legge dalla sidebar di SNAI Calcio i nomi delle nazioni disponibili.
    Scrolla il contenitore sidebar per caricare tutte le nazioni.
    Ritorna un set di stringhe UPPERCASE (es. {"ITALIA", "INGHILTERRA", ...}).
    """
    driver.get("https://www.snai.it/sport/CALCIO")
    time.sleep(5)
    close_cookie_banner(driver)

    countries = set()

    # Finestra altissima → tutto il DOM della sidebar è visibile senza virtual scrolling
    driver.set_window_size(1920, 10000)
    time.sleep(2)

    triggers = driver.find_elements(By.CSS_SELECTOR, '[class*="SportNavAccordionTrigger_text"]')
    for t in triggers:
        text = t.text.strip().upper()
        if text:
            countries.add(text)

    # Ripristina dimensione normale per lo scraping delle quote
    driver.set_window_size(1920, 1080)

    # Fallback: se la sidebar non carica, non bloccare lo scraper
    if not countries:
        print("  ⚠️  Sidebar SNAI vuota — scraper procederà con tutte le leghe")
    else:
        print(f"  Nazioni sidebar: {', '.join(sorted(countries))}", flush=True)

    return countries


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


def disable_estesa(driver):
    try:
        cb = driver.find_element(By.ID, "Estesa")
        if cb.is_selected():
            driver.execute_script("arguments[0].click();", cb)
            time.sleep(1)
    except Exception:
        pass


def click_tab(driver, tab_name):
    """Clicca un tab (UNDER/OVER, GOAL/NOGOAL, ecc.). Cerca in vari selettori."""
    aliases = {
        "UNDER/OVER": ["UNDER/OVER", "U/O", "UNDER OVER"],
        "GOAL/NOGOAL": ["GOAL/NOGOAL", "GG/NG", "GOAL NOGOAL", "GOAL/NO GOAL"],
    }
    targets = aliases.get(tab_name.upper(), [tab_name.upper()])

    selectors = [
        '[class*="TableTabs_button"]',
        '[class*="FiltersListScrollable_button"]',
        'button[class*="Tab"]',
    ]
    for sel in selectors:
        tabs = driver.find_elements(By.CSS_SELECTOR, sel)
        for tab in tabs:
            text = tab.text.strip().upper()
            if text and any(t in text or text in t for t in targets):
                driver.execute_script("arguments[0].click();", tab)
                time.sleep(2)
                return True
            try:
                inner = driver.execute_script("return arguments[0].innerHTML", tab).upper()
                if any(t in inner for t in targets):
                    driver.execute_script("arguments[0].click();", tab)
                    time.sleep(2)
                    return True
            except Exception:
                continue
    return False


def safe_float(text):
    """Converte testo in float, ritorna None se non valido."""
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return None


# ============================================================
#  SCROLL-AND-COLLECT (per virtual scrolling SNAI)
#
#  SNAI renderizza solo ~13 righe alla volta nel DOM.
#  Scrolliamo di 400px e accumualiamo dati per (home, away).
# ============================================================
def _scroll_and_collect(driver, reader_fn, scroll_step=400, max_scrolls=30):
    """
    Scroll incrementale per liste virtualizzate.
    reader_fn(driver) -> list of ((home, away), data)
    Accumula risultati deduplicando per (home, away).
    """
    collected = {}
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)

    for _ in range(max_scrolls):
        for key, data in reader_fn(driver):
            if key not in collected:
                collected[key] = data

        at_bottom = driver.execute_script(
            "return Math.ceil(window.scrollY + window.innerHeight) >= document.body.scrollHeight - 5"
        )
        if at_bottom:
            break

        driver.execute_script(f"window.scrollBy(0, {scroll_step});")
        time.sleep(1)

    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)
    return collected


def _read_visible_matches(driver):
    """Legge (home, away) dalle righe visibili."""
    containers = driver.find_elements(By.CSS_SELECTOR, '[class*="ScommesseTableRow_container"]')
    results = []
    for c in containers:
        try:
            names = c.find_elements(By.CSS_SELECTOR, '[class*="Competitors_name"]')
            if len(names) >= 2:
                h, a = names[0].text.strip(), names[1].text.strip()
                if h and a:
                    results.append(((h, a), True))
        except Exception:
            continue
    return results


def scroll_and_collect_matches(driver):
    """Raccoglie TUTTI i nomi partite scrollando la pagina."""
    return _scroll_and_collect(driver, _read_visible_matches)


def _read_visible_ou(driver):
    """Legge quote O/U dalle righe visibili, paired con nomi squadre."""
    containers = driver.find_elements(By.CSS_SELECTOR, '[class*="ScommesseTableRow_container"]')
    results = []
    for c in containers:
        try:
            names = c.find_elements(By.CSS_SELECTOR, '[class*="Competitors_name"]')
            if len(names) < 2:
                continue
            h, a = names[0].text.strip(), names[1].text.strip()
            if not h or not a:
                continue

            ou_group = c.find_element(By.CSS_SELECTOR, '[data-idx="1"]')
            quotas = ou_group.find_elements(By.CSS_SELECTOR, '[class*="quotaWrapper"]')
            vals = [q.text.strip() for q in quotas if q.text.strip()]
            if len(vals) >= 2:
                results.append(((h, a), (safe_float(vals[0]), safe_float(vals[1]))))
        except Exception:
            continue
    return results


def select_global_ou_level(driver, level):
    """Seleziona il livello O/U globale (es. '1.5', '2.5', '3.5')."""
    try:
        selector_btn = driver.find_element(
            By.CSS_SELECTOR, '[class*="InfoAggSelector_button"]'
        )
    except Exception:
        return False

    current = selector_btn.text.strip()
    if current == level:
        return True

    driver.execute_script("arguments[0].click();", selector_btn)
    time.sleep(0.8)

    options = driver.find_elements(By.CSS_SELECTOR, '[class*="InfoAggSelector"] li, [class*="InfoAggSelector"] button')
    for opt in options:
        if opt.text.strip() == level:
            driver.execute_script("arguments[0].click();", opt)
            time.sleep(1.5)
            return True

    elems = driver.find_elements(By.XPATH, f"//*[text()='{level}']")
    for e in elems:
        if e.is_displayed():
            driver.execute_script("arguments[0].click();", e)
            time.sleep(1.5)
            return True

    return False


def scroll_and_collect_ou(driver):
    """
    Estrae O/U 1.5, 2.5, 3.5 scrollando per ogni livello.
    Ritorna dict: {(home, away): {under_15, over_15, under_25, ...}}
    """
    results = {}

    for level, u_key, o_key in [
        ("1.5", "under_15", "over_15"),
        ("2.5", "under_25", "over_25"),
        ("3.5", "under_35", "over_35"),
    ]:
        if select_global_ou_level(driver, level):
            level_data = _scroll_and_collect(driver, _read_visible_ou)
            for key, (under, over) in level_data.items():
                if key not in results:
                    results[key] = {}
                results[key][u_key] = under
                results[key][o_key] = over

    return results


def _read_visible_gg_ng(driver):
    """Legge quote GG/NG dalle righe visibili, paired con nomi squadre."""
    containers = driver.find_elements(By.CSS_SELECTOR, '[class*="ScommesseTableRow_container"]')
    results = []
    for c in containers:
        try:
            names = c.find_elements(By.CSS_SELECTOR, '[class*="Competitors_name"]')
            if len(names) < 2:
                continue
            h, a = names[0].text.strip(), names[1].text.strip()
            if not h or not a:
                continue

            gg_group = c.find_element(By.CSS_SELECTOR, '[data-idx="2"]')
            quotas = gg_group.find_elements(By.CSS_SELECTOR, '[class*="quotaWrapper"]')
            vals = [q.text.strip() for q in quotas if q.text.strip()]
            if len(vals) >= 2:
                results.append(((h, a), {
                    'gg': safe_float(vals[0]),
                    'ng': safe_float(vals[1]),
                }))
        except Exception:
            continue
    return results


def scroll_and_collect_gg_ng(driver):
    """Estrae GG/NG scrollando la pagina."""
    return _scroll_and_collect(driver, _read_visible_gg_ng)


# ============================================================
#  MATCHING E UPDATE DB
# ============================================================
def find_and_update_odds(league_name, ou_data, gg_data, teams_by_tm_id=None, teams_by_name=None):
    """
    Trova le partite nel DB e aggiorna le odds con O/U e GG/NG.
    ou_data e gg_data sono dict con chiavi (scraped_home, scraped_away).
    Non sovrascrive 1/X/2 (NowGoal).
    teams_by_tm_id/teams_by_name: cache pre-caricata (evita ~21.888 query singole).
    """
    league_patterns = [league_name]
    if league_name == "Serie C":
        league_patterns = ["Serie C - Girone A", "Serie C - Girone B", "Serie C - Girone C"]

    updated = 0
    matched_snai_pairs = set()

    # Tutti i nomi SNAI scrappati (per calcolo unmatched)
    all_snai_pairs = set()
    for (sh, sa) in ou_data.keys():
        all_snai_pairs.add((sh, sa))
    for (sh, sa) in gg_data.keys():
        all_snai_pairs.add((sh, sa))

    # Pre-compute chiavi normalizzate per matching veloce
    ou_keys_norm = []
    for (sh, sa), data in ou_data.items():
        ou_keys_norm.append((normalize_name(sh), normalize_name(sa), sh.lower(), sa.lower(), sh, sa, data))

    gg_keys_norm = []
    for (sh, sa), data in gg_data.items():
        gg_keys_norm.append((normalize_name(sh), normalize_name(sa), sh.lower(), sa.lower(), sh, sa, data))

    for league_pat in league_patterns:
        rounds = list(db.h2h_by_round.find({"league": league_pat}))

        for round_doc in rounds:
            modified = False

            for m in round_doc.get('matches', []):
                home_db = m.get('home', '')
                away_db = m.get('away', '')

                if not home_db or not away_db:
                    continue

                # Filtro data: aggiorna solo partite tra -2 e +30 giorni da oggi
                date_obj = m.get('date_obj')
                if date_obj:
                    diff_days = (date_obj.replace(tzinfo=None) - datetime.now()).days
                    if diff_days < -2 or diff_days > 30:
                        continue

                # Freshness check: salta se quote O/U+GG aggiornate meno di 1 ora fa
                existing_ts = m.get('odds', {}).get('ts_ou_gg')
                if existing_ts:
                    age_hours = (datetime.now() - existing_ts.replace(tzinfo=None)).total_seconds() / 3600
                    if age_hours < 1:
                        continue

                # Lookup da cache in memoria (se disponibile) invece di query DB
                if teams_by_tm_id is not None:
                    home_doc = teams_by_tm_id.get(m.get('home_tm_id')) or (teams_by_name or {}).get(home_db)
                    away_doc = teams_by_tm_id.get(m.get('away_tm_id')) or (teams_by_name or {}).get(away_db)
                else:
                    home_doc = db.teams.find_one({"transfermarkt_id": m.get('home_tm_id')}) if m.get('home_tm_id') else db.teams.find_one({"name": home_db})
                    away_doc = db.teams.find_one({"transfermarkt_id": m.get('away_tm_id')}) if m.get('away_tm_id') else db.teams.find_one({"name": away_db})
                home_aliases = get_team_aliases(home_db, home_doc)
                away_aliases = get_team_aliases(away_db, away_doc)

                new_fields = {}
                now = datetime.now()

                # Cerca match O/U
                for sh_norm, sa_norm, sh_low, sa_low, sh_orig, sa_orig, ou in ou_keys_norm:
                    home_found = any(
                        a in sh_norm or a in sh_low or sh_norm in a or sh_low in a
                        for a in home_aliases
                    )
                    away_found = any(
                        a in sa_norm or a in sa_low or sa_norm in a or sa_low in a
                        for a in away_aliases
                    )
                    if home_found and away_found:
                        matched_snai_pairs.add((sh_orig, sa_orig))
                        for key in ['under_15', 'over_15', 'under_25', 'over_25', 'under_35', 'over_35']:
                            if ou.get(key) is not None:
                                new_fields[key] = ou[key]
                        break

                # Cerca match GG/NG
                for sh_norm, sa_norm, sh_low, sa_low, sh_orig, sa_orig, gg in gg_keys_norm:
                    home_found = any(
                        a in sh_norm or a in sh_low or sh_norm in a or sh_low in a
                        for a in home_aliases
                    )
                    away_found = any(
                        a in sa_norm or a in sa_low or sa_norm in a or sa_low in a
                        for a in away_aliases
                    )
                    if home_found and away_found:
                        matched_snai_pairs.add((sh_orig, sa_orig))
                        if gg.get('gg') is not None:
                            new_fields['gg'] = gg['gg']
                        if gg.get('ng') is not None:
                            new_fields['ng'] = gg['ng']
                        break

                if new_fields:
                    if 'odds' not in m:
                        m['odds'] = {}
                    m['odds'].update(new_fields)
                    m['odds']['src_ou_gg'] = 'SNAI'
                    m['odds']['ts_ou_gg'] = now
                    modified = True
                    updated += 1

                    # Aggiorna anche daily_predictions (quote visibili subito nel frontend)
                    if m.get('home_mongo_id') and m.get('away_mongo_id'):
                        dp_update = {f"odds.{k}": v for k, v in new_fields.items()}
                        dp_update["odds.src_ou_gg"] = "SNAI"
                        dp_update["odds.ts_ou_gg"] = now
                        db.daily_predictions.update_many(
                            {"home_mongo_id": m['home_mongo_id'], "away_mongo_id": m['away_mongo_id']},
                            {"$set": dp_update}
                        )
                        db.daily_predictions_sandbox.update_many(
                            {"home_mongo_id": m['home_mongo_id'], "away_mongo_id": m['away_mongo_id']},
                            {"$set": dp_update}
                        )

            if modified:
                db.h2h_by_round.update_one(
                    {"_id": round_doc["_id"]},
                    {"$set": {"matches": round_doc["matches"]}}
                )

    unmatched = all_snai_pairs - matched_snai_pairs
    return updated, unmatched


# ============================================================
#  COPPE — MATCHING E UPDATE DB
# ============================================================
def find_and_update_odds_cups(cup_collection, cup_teams_collection, ou_data, gg_data):
    """
    Trova le partite di coppa nel DB e aggiorna odds con O/U e GG/NG.
    Scrive in matches_champions_league / matches_europa_league.
    Propaga anche a daily_predictions, daily_predictions_sandbox, daily_predictions_unified.
    """
    coll = db[cup_collection]
    teams_coll = db[cup_teams_collection]

    # Carica teams coppe: by tm_id (primario), by name, by alias (fallback)
    cup_teams = {}
    cup_teams_by_tm_id = {}
    cup_teams_by_alias = {}
    for t in teams_coll.find({}, {"name": 1, "aliases": 1, "transfermarkt_id": 1}):
        cup_teams[t['name']] = t
        if t.get('transfermarkt_id'):
            cup_teams_by_tm_id[t['transfermarkt_id']] = t
        # Indice aggiuntivo: ogni alias (normalizzato) → team doc
        for a in t.get('aliases', []):
            cup_teams_by_alias[normalize_name(a)] = t
        cup_teams_by_alias[normalize_name(t['name'])] = t

    updated = 0
    matched_snai_pairs = set()
    all_snai_pairs = set()
    for (sh, sa) in ou_data.keys():
        all_snai_pairs.add((sh, sa))
    for (sh, sa) in gg_data.keys():
        all_snai_pairs.add((sh, sa))

    # Pre-compute chiavi normalizzate
    ou_keys_norm = []
    for (sh, sa), data in ou_data.items():
        ou_keys_norm.append((normalize_name(sh), normalize_name(sa), sh.lower(), sa.lower(), sh, sa, data))
    gg_keys_norm = []
    for (sh, sa), data in gg_data.items():
        gg_keys_norm.append((normalize_name(sh), normalize_name(sa), sh.lower(), sa.lower(), sh, sa, data))

    # Partite di coppa scheduled o recenti
    matches = list(coll.find({"status": {"$in": ["scheduled", "Scheduled", "not_started"]}}))
    print(f"    Partite coppa in DB: {len(matches)}")

    for m in matches:
        home_db = m.get('home_team', '')
        away_db = m.get('away_team', '')
        if not home_db or not away_db:
            continue

        # Freshness: salta se aggiornate meno di 1 ora fa
        existing_ts = m.get('odds', {}).get('ts_ou_gg')
        if existing_ts:
            ts = existing_ts if isinstance(existing_ts, datetime) else datetime.strptime(str(existing_ts)[:19], "%Y-%m-%d %H:%M:%S")
            age_hours = (datetime.now() - ts).total_seconds() / 3600
            if age_hours < 1:
                continue

        # Genera alias per matching (tm_id → nome esatto → alias normalizzato)
        home_doc = cup_teams_by_tm_id.get(m.get('home_tm_id')) or cup_teams.get(home_db) or cup_teams_by_alias.get(normalize_name(home_db))
        away_doc = cup_teams_by_tm_id.get(m.get('away_tm_id')) or cup_teams.get(away_db) or cup_teams_by_alias.get(normalize_name(away_db))
        home_aliases = get_team_aliases(home_db, home_doc)
        away_aliases = get_team_aliases(away_db, away_doc)

        new_fields = {}
        now = datetime.now()

        # Cerca match O/U
        for sh_norm, sa_norm, sh_low, sa_low, sh_orig, sa_orig, ou in ou_keys_norm:
            home_found = any(
                a in sh_norm or a in sh_low or sh_norm in a or sh_low in a
                for a in home_aliases
            )
            away_found = any(
                a in sa_norm or a in sa_low or sa_norm in a or sa_low in a
                for a in away_aliases
            )
            if home_found and away_found:
                matched_snai_pairs.add((sh_orig, sa_orig))
                for key in ['under_15', 'over_15', 'under_25', 'over_25', 'under_35', 'over_35']:
                    if ou.get(key) is not None:
                        new_fields[key] = ou[key]
                break

        # Cerca match GG/NG
        for sh_norm, sa_norm, sh_low, sa_low, sh_orig, sa_orig, gg in gg_keys_norm:
            home_found = any(
                a in sh_norm or a in sh_low or sh_norm in a or sh_low in a
                for a in home_aliases
            )
            away_found = any(
                a in sa_norm or a in sa_low or sa_norm in a or sa_low in a
                for a in away_aliases
            )
            if home_found and away_found:
                matched_snai_pairs.add((sh_orig, sa_orig))
                if gg.get('gg') is not None:
                    new_fields['gg'] = gg['gg']
                if gg.get('ng') is not None:
                    new_fields['ng'] = gg['ng']
                break

        if new_fields:
            # Aggiorna documento coppa
            odds_update = {f"odds.{k}": v for k, v in new_fields.items()}
            odds_update["odds.src_ou_gg"] = "SNAI"
            odds_update["odds.ts_ou_gg"] = now
            coll.update_one({"_id": m["_id"]}, {"$set": odds_update})
            updated += 1

            # Propaga a daily_predictions, daily_predictions_sandbox, daily_predictions_unified
            # Le coppe matchano per home_team/away_team → nel DB pronostici usano home/away
            dp_update = {f"odds.{k}": v for k, v in new_fields.items()}
            dp_update["odds.src_ou_gg"] = "SNAI"
            dp_update["odds.ts_ou_gg"] = now
            home_norm = normalize_name(home_db)
            away_norm = normalize_name(away_db)
            # Cerca per nome normalizzato nelle predictions (i nomi potrebbero differire leggermente)
            for dp_coll_name in ['daily_predictions', 'daily_predictions_sandbox', 'daily_predictions_unified']:
                dp_coll = db[dp_coll_name]
                # Prova match diretto
                result = dp_coll.update_many(
                    {"home": home_db, "away": away_db, "is_cup": True},
                    {"$set": dp_update}
                )
                if result.modified_count == 0:
                    # Fallback: cerca con regex case-insensitive
                    dp_coll.update_many(
                        {"home": {"$regex": f"^{home_norm}$", "$options": "i"}, "away": {"$regex": f"^{away_norm}$", "$options": "i"}, "is_cup": True},
                        {"$set": dp_update}
                    )

    unmatched = all_snai_pairs - matched_snai_pairs
    return updated, unmatched


def league_is_fresh_cups(cup_collection):
    """Controlla se le quote O/U+GG delle coppe sono aggiornate (<1h)."""
    coll = db[cup_collection]
    soglia = datetime.now() - timedelta(hours=1)

    # Cerca il ts_ou_gg più recente tra le partite scheduled
    result = list(coll.aggregate([
        {"$match": {"status": {"$in": ["scheduled", "Scheduled", "not_started"]}, "odds.ts_ou_gg": {"$exists": True}}},
        {"$group": {"_id": None, "max_ts": {"$max": "$odds.ts_ou_gg"}}}
    ]))

    if not result or not result[0].get('max_ts'):
        print(f"    [freshness] {cup_collection}: nessun ts_ou_gg trovato")
        return False

    max_ts = result[0]['max_ts']
    if isinstance(max_ts, str):
        max_ts = datetime.strptime(max_ts[:19], "%Y-%m-%d %H:%M:%S")
    else:
        max_ts = max_ts.replace(tzinfo=None)

    age_min = int((datetime.now() - max_ts).total_seconds() / 60)
    is_fresh = max_ts > soglia
    print(f"    [freshness] {cup_collection}: ultimo update {age_min} min fa → {'SKIP' if is_fresh else 'SCRAPE'}")
    return is_fresh


# ============================================================
#  MAIN
# ============================================================
def scrape_league(driver, league, teams_by_tm_id, teams_by_name, is_first=False):
    """Scrapa una singola lega. Ritorna (partite_trovate, aggiornate)."""
    name = league['name']
    url = league['url']

    print(f"\n  [{name}] Navigando...", flush=True)
    driver.get(url)
    time.sleep(5)

    if is_first:
        close_cookie_banner(driver)
        time.sleep(1)

    disable_estesa(driver)

    # Raccogli nomi partite (scroll per virtual list) — con retry + reload
    matches = scroll_and_collect_matches(driver)
    if not matches:
        for attempt in range(2, MAX_RETRIES_EMPTY + 1):
            print(f"  [{name}] 0 partite, tentativo {attempt}/{MAX_RETRIES_EMPTY} (reload)...", flush=True)
            driver.get(url)
            time.sleep(5)
            disable_estesa(driver)
            matches = scroll_and_collect_matches(driver)
            if matches:
                break

    if not matches:
        print(f"  [{name}] 0 partite dopo {MAX_RETRIES_EMPTY} tentativi, skip")
        return 0, 0, set()

    print(f"  [{name}] {len(matches)} partite trovate", flush=True)

    # Tab UNDER/OVER → estrai O/U (scroll per ogni livello)
    ou_data = {}
    if click_tab(driver, "UNDER/OVER"):
        ou_data = scroll_and_collect_ou(driver)
        print(f"  [{name}] O/U estratte per {len(ou_data)} partite")
    else:
        print(f"  [{name}] Tab UNDER/OVER non trovato")

    # Tab GOAL/NOGOAL → estrai GG/NG (scroll)
    gg_data = {}
    if click_tab(driver, "GOAL/NOGOAL"):
        gg_data = scroll_and_collect_gg_ng(driver)
        print(f"  [{name}] GG/NG estratte per {len(gg_data)} partite")
    else:
        print(f"  [{name}] Tab GOAL/NOGOAL non trovato")

    if not ou_data and not gg_data:
        print(f"  [{name}] Nessuna quota estratta, skip")
        return len(matches), 0, set()

    # Match con DB e aggiorna — routing diverso per coppe vs campionati
    if league.get('is_cup'):
        updated, unmatched = find_and_update_odds_cups(
            league['cup_collection'], league['cup_teams'], ou_data, gg_data
        )
    else:
        updated, unmatched = find_and_update_odds(name, ou_data, gg_data, teams_by_tm_id, teams_by_name)
    print(f"  [{name}] Aggiornate: {updated}")
    if unmatched:
        print(f"  [{name}] ⚠️  {len(unmatched)} partite SNAI senza match DB")

    return len(matches), updated, unmatched


def _append_unmatched_log(all_unmatched):
    """
    Appende nomi SNAI non matchati al log cumulativo.
    NON sovrascrive: ogni run aggiunge solo le nuove entry.
    Il file accumula dati nel tempo perché ogni run vede solo le partite in programma.
    """
    log_path = os.path.join(project_root, "log", "squadre-non-trovate-snai.txt")

    # Carica entry esistenti per evitare duplicati
    existing = set()
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("="):
                    existing.add(line)

    # Prepara nuove entry
    new_entries = []
    for league, (home, away) in all_unmatched:
        entry = f"[{league}] {home} vs {away}"
        if entry not in existing:
            new_entries.append(entry)

    if not new_entries:
        print(f"\n  Log unmatched: nessuna nuova entry da aggiungere")
        return

    # Append al file
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n# --- Run {datetime.now().strftime('%Y-%m-%d %H:%M')} ---\n")
        for entry in new_entries:
            f.write(entry + "\n")

    print(f"\n  Log unmatched: {len(new_entries)} nuove entry aggiunte → log/squadre-non-trovate-snai.txt")


def propagate_to_sandbox(league_name):
    """Propaga le quote SNAI già presenti in h2h_by_round a daily_predictions_sandbox.
    Usa aggregation server-side per filtrare solo match con quote SNAI."""
    league_patterns = [league_name]
    if league_name == "Serie C":
        league_patterns = ["Serie C - Girone A", "Serie C - Girone B", "Serie C - Girone C"]

    count = 0
    for league_pat in league_patterns:
        for doc in db.h2h_by_round.aggregate([
            {"$match": {"league": league_pat}},
            {"$unwind": "$matches"},
            {"$match": {
                "matches.odds.ts_ou_gg": {"$exists": True},
                "matches.home_mongo_id": {"$exists": True, "$ne": None},
                "matches.away_mongo_id": {"$exists": True, "$ne": None}
            }},
            {"$replaceRoot": {"newRoot": "$matches"}}
        ]):
            odds = doc.get('odds', {})
            snai_fields = {k: v for k, v in odds.items() if k in (
                'over_15', 'under_15', 'over_25', 'under_25', 'over_35', 'under_35', 'gg', 'ng'
            )}
            if not snai_fields:
                continue
            dp_update = {f"odds.{k}": v for k, v in snai_fields.items()}
            dp_update["odds.src_ou_gg"] = "SNAI"
            dp_update["odds.ts_ou_gg"] = odds['ts_ou_gg']
            result = db.daily_predictions_sandbox.update_many(
                {"home_mongo_id": doc['home_mongo_id'], "away_mongo_id": doc['away_mongo_id']},
                {"$set": dp_update}
            )
            count += result.modified_count
    if count:
        print(f"    → Sandbox: {count} pronostici aggiornati con quote esistenti")
    return count


def league_is_fresh(league_name, max_age_hours=1):
    """
    Controlla se la lega è stata aggiornata di recente.
    Usa aggregation MongoDB (server-side) per trovare il MAX ts_ou_gg.
    """
    league_patterns = [league_name]
    if league_name == "Serie C":
        league_patterns = ["Serie C - Girone A", "Serie C - Girone B", "Serie C - Girone C"]

    soglia = datetime.now() - timedelta(hours=max_age_hours)
    latest_ts = None

    for league_pat in league_patterns:
        result = list(db.h2h_by_round.aggregate([
            {"$match": {"league": league_pat}},
            {"$unwind": "$matches"},
            {"$group": {"_id": None, "max_ts": {"$max": "$matches.odds.ts_ou_gg"}}}
        ]))
        if result and result[0].get('max_ts'):
            ts = result[0]['max_ts'].replace(tzinfo=None)
            if latest_ts is None or ts > latest_ts:
                latest_ts = ts

    if latest_ts is None:
        print(f"    [freshness] {league_name}: nessun ts_ou_gg trovato")
        return False

    age_min = int((datetime.now() - latest_ts).total_seconds() / 60)
    is_fresh = latest_ts > soglia
    print(f"    [freshness] {league_name}: ultimo update {age_min} min fa → {'SKIP' if is_fresh else 'SCRAPE'}")
    return is_fresh


def run_scraper():
    # Supporto esecuzione parallela: SNAI_LEAGUE_GROUP=0/1/2 processa solo 1/3 delle leghe
    league_group = os.environ.get("SNAI_LEAGUE_GROUP")
    if league_group is not None:
        group_idx = int(league_group)
        total_leagues = len(LEAGUES_CONFIG)
        chunk_size = (total_leagues + 2) // 3  # arrotonda per eccesso
        start = group_idx * chunk_size
        end = min(start + chunk_size, total_leagues)
        leagues_to_process = LEAGUES_CONFIG[start:end]
        group_label = f" (GRUPPO {group_idx}: {len(leagues_to_process)} leghe, indici {start}-{end-1})"
    else:
        leagues_to_process = LEAGUES_CONFIG
        group_label = ""

    print(f"\n{'='*55}")
    print(f"  SCRAPER SNAI — Quote O/U + GG/NG{group_label}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    # Indici MongoDB (idempotenti — se esistono già, noop)
    db.h2h_by_round.create_index("league")
    db.teams.create_index("transfermarkt_id")
    print("  Indici MongoDB verificati (league, transfermarkt_id)")

    # Batch loading teams — 1 query invece di ~21.888
    all_teams = list(db.teams.find({}, {"name": 1, "transfermarkt_id": 1, "aliases": 1}))
    teams_by_tm_id = {}
    teams_by_name = {}
    for t in all_teams:
        if t.get('transfermarkt_id'):
            teams_by_tm_id[t['transfermarkt_id']] = t
        if t.get('name'):
            teams_by_name[t['name']] = t
    print(f"  Teams caricati in memoria: {len(all_teams)} ({len(teams_by_tm_id)} con tm_id)")

    driver = init_driver()
    total_matches = 0
    total_updated = 0
    total_skipped = 0
    total_sandbox_propagated = 0
    all_unmatched = []

    try:
        # Leggi nazioni disponibili dalla sidebar SNAI
        available = get_available_countries(driver)
        if available:
            print(f"  Sidebar SNAI: {len(available)} nazioni trovate")

        first_league = True
        for league in leagues_to_process:
            sidebar_country = league.get('sidebar', '')

            # Skip se la nazione non è nella sidebar (fuori stagione / non disponibile)
            # Per le coppe: sidebar potrebbe avere "CHAMPIONS LEAGUE" come voce diretta
            if available and sidebar_country and sidebar_country not in available:
                print(f"\n  [{league['name']}] ⏭️  {sidebar_country} non in sidebar, skip")
                total_skipped += 1
                continue

            # Skip se tutte le partite hanno quote aggiornate da meno di 1 ora
            if league.get('is_cup'):
                if league_is_fresh_cups(league['cup_collection']):
                    print(f"\n  [{league['name']}] ⏩ Quote coppa già aggiornate (<1h), skip")
                    total_skipped += 1
                    continue
            else:
                if league_is_fresh(league['name']):
                    print(f"\n  [{league['name']}] ⏩ Quote già aggiornate (<1h), skip")
                    total_sandbox_propagated += propagate_to_sandbox(league['name'])
                    total_skipped += 1
                    continue

            try:
                found, updated, unmatched = scrape_league(driver, league, teams_by_tm_id, teams_by_name, is_first=first_league)
                first_league = False
                total_matches += found
                total_updated += updated
                for pair in unmatched:
                    all_unmatched.append((league['name'], pair))
            except Exception as e:
                print(f"  [{league['name']}] ERRORE: {e}")
                continue
    finally:
        driver.quit()

    # Log cumulativo nomi non matchati
    if all_unmatched:
        _append_unmatched_log(all_unmatched)

    print(f"\n{'='*55}")
    print(f"  COMPLETATO")
    print(f"  Partite trovate: {total_matches}")
    print(f"  Quote aggiornate: {total_updated}")
    if total_sandbox_propagated:
        print(f"  🧪 Sandbox aggiornati (da cache): {total_sandbox_propagated}")
    if total_skipped:
        print(f"  ⏭️  Leghe saltate (non in sidebar): {total_skipped}")
    if all_unmatched:
        print(f"  ⚠️  Partite SNAI senza match: {len(all_unmatched)}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")


if __name__ == "__main__":
    run_scraper()
