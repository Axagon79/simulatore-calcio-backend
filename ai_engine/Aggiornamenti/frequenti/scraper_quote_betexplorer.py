"""
Scraper Quote 1X2 da BetExplorer — Sostituto di nowgoal_scraper.py + nowgoal_scraper_single.py
Usa requests + BeautifulSoup (NO Selenium). Scrive in h2h_by_round.matches[].odds
"""

import os
import sys
import re
import time
import argparse
from datetime import datetime, timezone

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("No config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

import requests
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURAZIONE CAMPIONATI (36 campionati, 72 URL)
# ============================================================
LEAGUES_CONFIG = [
    # ITALIA
    {"name": "Serie A", "base": "https://www.betexplorer.com/it/football/italy/serie-a"},
    {"name": "Serie B", "base": "https://www.betexplorer.com/it/football/italy/serie-b"},
    {"name": "Serie C - Girone A", "base": "https://www.betexplorer.com/it/football/italy/serie-c-group-a"},
    {"name": "Serie C - Girone B", "base": "https://www.betexplorer.com/it/football/italy/serie-c-group-b"},
    {"name": "Serie C - Girone C", "base": "https://www.betexplorer.com/it/football/italy/serie-c-group-c"},
    # EUROPA TOP
    {"name": "Premier League", "base": "https://www.betexplorer.com/it/football/england/premier-league"},
    {"name": "La Liga", "base": "https://www.betexplorer.com/it/football/spain/laliga"},
    {"name": "Bundesliga", "base": "https://www.betexplorer.com/it/football/germany/bundesliga"},
    {"name": "Ligue 1", "base": "https://www.betexplorer.com/it/football/france/ligue-1"},
    {"name": "Eredivisie", "base": "https://www.betexplorer.com/it/football/netherlands/eredivisie"},
    {"name": "Liga Portugal", "base": "https://www.betexplorer.com/it/football/portugal/liga-portugal"},
    # EUROPA SERIE B
    {"name": "Championship", "base": "https://www.betexplorer.com/it/football/england/championship"},
    {"name": "League One", "base": "https://www.betexplorer.com/it/football/england/league-one"},
    {"name": "LaLiga 2", "base": "https://www.betexplorer.com/it/football/spain/laliga2"},
    {"name": "2. Bundesliga", "base": "https://www.betexplorer.com/it/football/germany/2-bundesliga"},
    {"name": "Ligue 2", "base": "https://www.betexplorer.com/it/football/france/ligue-2"},
    # EUROPA NORDICI + EXTRA
    {"name": "Scottish Premiership", "base": "https://www.betexplorer.com/it/football/scotland/premiership"},
    {"name": "Allsvenskan", "base": "https://www.betexplorer.com/it/football/sweden/allsvenskan"},
    {"name": "Eliteserien", "base": "https://www.betexplorer.com/it/football/norway/eliteserien"},
    {"name": "Superligaen", "base": "https://www.betexplorer.com/it/football/denmark/superliga"},
    {"name": "Jupiler Pro League", "base": "https://www.betexplorer.com/it/football/belgium/jupiler-pro-league"},
    {"name": "Süper Lig", "base": "https://www.betexplorer.com/it/football/turkey/super-lig"},
    {"name": "League of Ireland Premier Division", "base": "https://www.betexplorer.com/it/football/ireland/premier-division"},
    # AMERICHE
    {"name": "Brasileirão Serie A", "base": "https://www.betexplorer.com/it/football/brazil/serie-a-betano"},
    {"name": "Primera División", "base": "https://www.betexplorer.com/it/football/argentina/liga-profesional"},
    {"name": "Major League Soccer", "base": "https://www.betexplorer.com/it/football/usa/mls"},
    # ASIA
    {"name": "J1 League", "base": "https://www.betexplorer.com/it/football/japan/j1-league"},
    # NUOVI CAMPIONATI
    {"name": "League Two", "base": "https://www.betexplorer.com/it/football/england/league-two"},
    {"name": "Veikkausliiga", "base": "https://www.betexplorer.com/it/football/finland/veikkausliiga"},
    {"name": "3. Liga", "base": "https://www.betexplorer.com/it/football/germany/3-liga"},
    {"name": "Liga MX", "base": "https://www.betexplorer.com/it/football/mexico/liga-mx"},
    {"name": "Eerste Divisie", "base": "https://www.betexplorer.com/it/football/netherlands/eerste-divisie"},
    {"name": "Liga Portugal 2", "base": "https://www.betexplorer.com/it/football/portugal/liga-portugal-2"},
    {"name": "1. Lig", "base": "https://www.betexplorer.com/it/football/turkey/1-lig"},
    {"name": "Saudi Pro League", "base": "https://www.betexplorer.com/it/football/saudi-arabia/saudi-professional-league"},
    {"name": "Scottish Championship", "base": "https://www.betexplorer.com/it/football/scotland/championship"},
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
}


# ============================================================
# UTILITY
# ============================================================

def get_round_number_from_text(text):
    """Estrae il numero della giornata da un testo tipo '32.Giornata' o '32. Turno'."""
    match = re.search(r'(\d+)', str(text))
    return int(match.group(1)) if match else 0


def strip_accents(text):
    for k, v in {'á':'a','à':'a','ã':'a','â':'a','é':'e','è':'e','ê':'e',
                  'í':'i','ì':'i','ó':'o','ò':'o','ô':'o','õ':'o',
                  'ú':'u','ù':'u','ü':'u','ñ':'n','ç':'c','ø':'o','å':'a','ä':'a'}.items():
        text = text.replace(k, v)
    return text


def normalize_for_match(name):
    """Normalizza un nome squadra per il confronto."""
    if not name:
        return ""
    name = name.lower().strip()
    name = strip_accents(name)
    # Rimuovi prefissi/suffissi comuni
    for prefix in ['fc ', 'cf ', 'ac ', 'as ', 'sc ', 'us ', 'ss ', 'asd ', 'ssd ']:
        if name.startswith(prefix):
            name = name[len(prefix):]
    for suffix in [' fc', ' cf', ' ac']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


def clean_float(txt):
    try:
        if not txt or txt == '-':
            return None
        return float(txt.strip())
    except:
        return None


def get_odd_from_cell(cell):
    """Estrae la quota da una cella BetExplorer. Cerca in data-odd (td, span, button)."""
    # 1. data-odd direttamente sul td
    odd = cell.get('data-odd')
    if odd:
        val = clean_float(odd)
        if val and 1.01 <= val <= 50.0:
            return val
    # 2. data-odd su un elemento figlio (span o button)
    for tag in cell.find_all(['span', 'button'], attrs={'data-odd': True}):
        val = clean_float(tag['data-odd'])
        if val and 1.01 <= val <= 50.0:
            return val
    # 3. Fallback: testo della cella
    text = cell.get_text(strip=True)
    val = clean_float(text)
    if val and 1.01 <= val <= 50.0:
        return val
    return None


# ============================================================
# PARSING PAGINA BETEXPLORER
# ============================================================

def parse_betexplorer_page(url):
    """
    Scarica una pagina BetExplorer (results o fixtures) e restituisce un dict:
    { round_number: [ {home, away, odds_1, odds_x, odds_2}, ... ], ... }
    """
    rounds_data = {}

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"      ❌ HTTP {r.status_code} per {url}")
            return rounds_data
    except Exception as e:
        print(f"      ❌ Errore richiesta {url}: {e}")
        return rounds_data

    soup = BeautifulSoup(r.text, 'html.parser')
    rows = soup.select('.table-main tr')

    current_round_num = None

    for row in rows:
        # Header di turno: <th> con testo tipo "35. Turno"
        th = row.find('th')
        if th:
            th_text = th.get_text(strip=True)
            round_num = get_round_number_from_text(th_text)
            if round_num > 0:
                current_round_num = round_num
                if current_round_num not in rounds_data:
                    rounds_data[current_round_num] = []
            continue

        if current_round_num is None:
            continue

        cells = row.find_all('td')

        if len(cells) < 5:
            continue

        try:
            # Squadre: cerchiamo la cella con classe h-text-left che contiene il link
            teams_cell = row.find('td', class_='h-text-left')
            if not teams_cell:
                continue
            match_link = teams_cell.find('a')
            if not match_link:
                continue
            spans = match_link.find_all('span')
            if len(spans) < 2:
                continue
            home = spans[0].get_text(strip=True)
            away = spans[1].get_text(strip=True)
            if not home or not away:
                continue

            # Controlla se posticipata (colonna risultato con "POSTP." o simile)
            result_cell = row.find('td', class_='h-text-center')
            result_text = result_cell.get_text(strip=True).upper() if result_cell else ""
            is_postponed = "POSTP" in result_text or "ABN" in result_text or "CANC" in result_text

            # Quote 1X2 (celle con classe table-main__odds)
            odds_cells = row.find_all('td', class_='table-main__odds')
            if len(odds_cells) < 3:
                if is_postponed:
                    rounds_data[current_round_num].append({
                        'home': home,
                        'away': away,
                        'odds_1': None,
                        'odds_x': None,
                        'odds_2': None,
                        'postponed': True,
                    })
                continue

            odds_1 = get_odd_from_cell(odds_cells[0])
            odds_x = get_odd_from_cell(odds_cells[1])
            odds_2 = get_odd_from_cell(odds_cells[2])

            if is_postponed or not (odds_1 and odds_x and odds_2):
                rounds_data[current_round_num].append({
                    'home': home,
                    'away': away,
                    'odds_1': odds_1,
                    'odds_x': odds_x,
                    'odds_2': odds_2,
                    'postponed': is_postponed,
                })
            else:
                rounds_data[current_round_num].append({
                    'home': home,
                    'away': away,
                    'odds_1': odds_1,
                    'odds_x': odds_x,
                    'odds_2': odds_2,
                })
        except:
            continue

    return rounds_data


# ============================================================
# MATCHING SQUADRE
# ============================================================

def build_teams_cache(league_name):
    """
    Costruisce una cache per il matching SOLO per un campionato specifico.
    normalizzato -> nome usato in h2h_by_round (solo squadre di quel campionato).
    """
    # 1. Raccogli solo i nomi usati in h2h_by_round per questo campionato
    h2h_names = set()
    for doc in db.h2h_by_round.find({"league": league_name}, {"matches.home": 1, "matches.away": 1}):
        for m in doc.get('matches', []):
            h2h_names.add(m.get('home', ''))
            h2h_names.add(m.get('away', ''))
    h2h_names.discard('')

    # 2. Per ogni nome h2h, crea mapping: normalizzato -> nome h2h
    cache = {}
    for name in h2h_names:
        cache[normalize_for_match(name)] = name

    # 3. Aggiungi alias dal DB teams, MA solo se puntano a un nome che esiste in h2h
    #    Cerca corrispondenza sia per name che per qualsiasi alias
    for t in db.teams.find({"league": league_name}, {"name": 1, "aliases": 1}):
        db_name = t['name']
        all_names = [db_name] + [a for a in t.get('aliases', []) if isinstance(a, str) and a.strip()]

        # Trova quale nome h2h corrisponde a questa squadra
        h2h_name = None
        for n in all_names:
            norm_n = normalize_for_match(n)
            if norm_n in cache:
                h2h_name = cache[norm_n]
                break
            if n in h2h_names:
                h2h_name = n
                break

        if h2h_name:
            # Aggiungi tutti gli alias (incluso il name) come puntatori al nome h2h
            for n in all_names:
                norm_n = normalize_for_match(n)
                if norm_n not in cache:
                    cache[norm_n] = h2h_name

    return cache


def find_best_match(betexplorer_name, teams_cache):
    """Trova il nome h2h_by_round corrispondente a un nome BetExplorer."""
    norm = normalize_for_match(betexplorer_name)

    # Match esatto normalizzato
    if norm in teams_cache:
        return teams_cache[norm]

    # Match parziale: preferiamo alias contenuto in norm (più specifico)
    best = None
    best_len = 0
    for alias_norm, h2h_name in teams_cache.items():
        if len(norm) >= 3 and len(alias_norm) >= 3:
            if alias_norm in norm and len(alias_norm) > best_len:
                best = h2h_name
                best_len = len(alias_norm)
            elif norm in alias_norm and len(norm) > best_len:
                best = h2h_name
                best_len = len(norm)

    return best


def match_teams(be_home, be_away, match_home, match_away, teams_cache, debug=False):
    """
    Verifica se una partita BetExplorer corrisponde a una partita h2h_by_round.
    """
    db_home = find_best_match(be_home, teams_cache)
    db_away = find_best_match(be_away, teams_cache)

    if debug:
        print(f"         MATCH DEBUG: BE '{be_home}' -> DB '{db_home}' (cercato: '{match_home}') | BE '{be_away}' -> DB '{db_away}' (cercato: '{match_away}')")

    if not db_home or not db_away:
        return False

    return db_home == match_home and db_away == match_away


# ============================================================
# LOGICA PRINCIPALE
# ============================================================

def get_target_rounds(league_name):
    """
    Recupera le 3 giornate da processare (precedente, attuale, successiva)
    da league_current_rounds + h2h_by_round. Stessa logica di nowgoal_scraper.py.
    """
    # Giornata corrente dal DB
    current_doc = db.league_current_rounds.find_one({"league": league_name})
    current_round = current_doc['current_round'] if current_doc else None

    # Tutte le giornate del campionato
    rounds_cursor = db.h2h_by_round.find({"league": league_name})
    rounds_list = list(rounds_cursor)
    if not rounds_list:
        return []

    rounds_list.sort(key=lambda x: get_round_number_from_text(x.get('round_name', '0')))

    if current_round is None:
        anchor_index = len(rounds_list) - 1
    else:
        anchor_index = -1
        for i, r in enumerate(rounds_list):
            if get_round_number_from_text(r.get('round_name', '0')) == current_round:
                anchor_index = i
                break
        if anchor_index == -1:
            anchor_index = len(rounds_list) - 1

    indices = [anchor_index, anchor_index - 1, anchor_index + 1]
    return [rounds_list[i] for i in indices if 0 <= i < len(rounds_list)]


def run_scraper(dry_run=False):
    mode = "DRY-RUN (nessuna scrittura DB)" if dry_run else "LIVE"
    print(f"\n🚀 AVVIO SCRAPER QUOTE 1X2 (BetExplorer — NO Selenium) [{mode}]")
    print(f"   📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    scraper_start = time.time()
    total_updated = 0
    total_found = 0
    total_not_matched = 0
    total_no_odds = 0  # Quote non ancora disponibili su BE
    total_auto_alias = []  # Lista alias aggiunti automaticamente
    all_odds_lines = []  # Dettaglio quote per partita (per report file)
    league_stats = []

    total_leagues = len(LEAGUES_CONFIG)
    debug_league = "Serie C - Girone A"  # Log dettagliato solo per questo campionato
    debug_lines = []

    for idx, league in enumerate(LEAGUES_CONFIG, 1):
        lname = league['name']
        base_url = league['base']
        is_debug = (lname == debug_league)
        pct = int(idx / total_leagues * 100)
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"\r   [{bar}] {pct}% ({idx}/{total_leagues}) {lname:<40}", end="", flush=True)
        print()  # newline per i log sotto
        league_start = time.time()
        league_updated = 0
        league_found = 0
        league_not_matched = 0
        league_no_odds = 0
        league_repaired = 0
        league_postponed = 0

        try:
            # 1. Giornate target da DB
            rounds_to_process = get_target_rounds(lname)
            if not rounds_to_process:
                print(f"   ⚠️ {lname}: nessuna giornata trovata in h2h_by_round")
                continue

            # Cache teams solo per questo campionato
            teams_cache = build_teams_cache(lname)
            all_odds_lines.append(f"\n--- {lname} ---")

            target_round_nums = set()
            for rd in rounds_to_process:
                target_round_nums.add(get_round_number_from_text(rd.get('round_name', '0')))

            # 2. Scarica pagine results + fixtures
            url_results = f"{base_url}/results/"
            url_fixtures = f"{base_url}/fixtures/"

            results_data = parse_betexplorer_page(url_results)
            time.sleep(0.3)
            fixtures_data = parse_betexplorer_page(url_fixtures)
            time.sleep(0.3)

            if is_debug:
                debug_lines.append(f"\n{'='*60}")
                debug_lines.append(f"DEBUG {lname}")
                debug_lines.append(f"Giornate target: {sorted(target_round_nums)}")
                debug_lines.append(f"Turni in /results/: {sorted(results_data.keys())}")
                debug_lines.append(f"Turni in /fixtures/: {sorted(fixtures_data.keys())}")

            # Unisci i dati: per ogni turno, combina results e fixtures
            all_rounds_data = {}
            for rnum in target_round_nums:
                matches_from_results = results_data.get(rnum, [])
                matches_from_fixtures = fixtures_data.get(rnum, [])
                all_rounds_data[rnum] = matches_from_results + matches_from_fixtures
                if is_debug:
                    debug_lines.append(f"\n--- Turno {rnum}: {len(matches_from_results)} da results + {len(matches_from_fixtures)} da fixtures ---")
                    for be in all_rounds_data[rnum]:
                        debug_lines.append(f"   BE: {be['home']} vs {be['away']} | {be['odds_1']} {be['odds_x']} {be['odds_2']}")

            # 3. Per ogni giornata target, aggiorna le quote in h2h_by_round
            for round_doc in rounds_to_process:
                round_num = get_round_number_from_text(round_doc.get('round_name', '0'))
                be_matches = all_rounds_data.get(round_num, [])
                matches = round_doc['matches']
                mod = False
                match_count = 0
                round_no_odds = 0
                round_postponed = 0
                round_not_matched = 0
                round_repaired = 0
                round_failed_names = []  # partite non riparabili
                be_used = set()  # indici BE già abbinati

                all_odds_lines.append(f"\n   --- G.{round_num} ---")
                print(f"   🔄 {lname} G.{round_num}...", end="")

                if is_debug:
                    debug_lines.append(f"\n--- MATCHING Turno {round_num} ({len(matches)} partite DB vs {len(be_matches)} partite BE) ---")

                # Prima passata: matching normale
                unmatched_db = []
                for m in matches:
                    found = False
                    for bi, be in enumerate(be_matches):
                        if bi in be_used:
                            continue
                        if match_teams(be['home'], be['away'], m['home'], m['away'], teams_cache, debug=False):
                            be_used.add(bi)

                            # Partita posticipata su BE → niente quote, aggiorna status DB + unified
                            if be.get('postponed'):
                                found = True
                                league_no_odds += 1
                                league_postponed += 1
                                round_postponed += 1
                                if not m.get('match_status_detail') and not dry_run:
                                    db.h2h_by_round.update_one(
                                        {"_id": round_doc["_id"], "matches.home": m['home'], "matches.away": m['away']},
                                        {"$set": {"matches.$.match_status_detail": "Postp."}}
                                    )
                                    db.daily_predictions_unified.update_many(
                                        {"home": m['home'], "away": m['away'], "league": lname},
                                        {"$set": {"match_status_detail": "Postp."}}
                                    )
                                all_odds_lines.append(f"   ⏳ {m['home']} vs {m['away']} — POSTICIPATA")
                                if is_debug:
                                    debug_lines.append(f"   ⏳ {m['home']} vs {m['away']} — POSTICIPATA")
                                break

                            new_odds = {'1': be['odds_1'], 'X': be['odds_x'], '2': be['odds_2']}

                            # Quote incomplete → salta
                            if not new_odds['1'] or not new_odds['X'] or not new_odds['2']:
                                found = True
                                league_no_odds += 1
                                round_no_odds += 1
                                all_odds_lines.append(f"   ⏳ {m['home']} vs {m['away']} — quote incomplete su BE")
                                break

                            should_update = False

                            if 'odds' not in m:
                                should_update = True
                            else:
                                is_fresh = (datetime.now() - m['odds'].get('ts', datetime.min)).total_seconds() < 21600
                                is_different = (
                                    m['odds'].get('1') != new_odds['1'] or
                                    m['odds'].get('X') != new_odds['X'] or
                                    m['odds'].get('2') != new_odds['2']
                                )
                                if not is_fresh or is_different:
                                    should_update = True

                            if should_update:
                                if 'odds' not in m:
                                    m['odds'] = {}
                                m['odds']['1'] = new_odds['1']
                                m['odds']['X'] = new_odds['X']
                                m['odds']['2'] = new_odds['2']
                                m['odds']['src'] = "BetExplorer"
                                m['odds']['ts'] = datetime.now()
                                mod = True
                                match_count += 1

                            found = True
                            league_found += 1
                            all_odds_lines.append(f"   {m['home']:<20} vs {m['away']:<20} | 1: {new_odds['1']:<6} X: {new_odds['X']:<6} 2: {new_odds['2']:<6}")
                            if is_debug:
                                debug_lines.append(f"   ✅ {m['home']} vs {m['away']}  ←  BE: {be['home']} vs {be['away']}")
                            break

                    if not found:
                        if len(be_matches) == 0:
                            league_no_odds += 1
                            round_no_odds += 1
                            if is_debug:
                                debug_lines.append(f"   ⏳ {m['home']} vs {m['away']}  — turno assente su BE")
                        else:
                            unmatched_db.append(m)

                # Seconda passata: auto-repair per i non matchati
                be_remaining = [be for bi, be in enumerate(be_matches) if bi not in be_used]
                for m in unmatched_db:
                    repaired = False
                    norm_db_h = normalize_for_match(m['home'])
                    norm_db_a = normalize_for_match(m['away'])

                    for be in be_remaining:
                        norm_be_h = normalize_for_match(be['home'])
                        norm_be_a = normalize_for_match(be['away'])

                        # Match parziale: uno contenuto nell'altro (entrambe le squadre)
                        home_ok = (norm_db_h in norm_be_h or norm_be_h in norm_db_h) and min(len(norm_db_h), len(norm_be_h)) >= 3
                        away_ok = (norm_db_a in norm_be_a or norm_be_a in norm_db_a) and min(len(norm_db_a), len(norm_be_a)) >= 3

                        if home_ok and away_ok:
                            # Auto-repair: aggiungi alias in db.teams
                            for db_name, be_name in [(m['home'], be['home']), (m['away'], be['away'])]:
                                if normalize_for_match(be_name) not in teams_cache:
                                    if not dry_run:
                                        team_doc = db.teams.find_one({"league": lname, "aliases": db_name})
                                        if not team_doc:
                                            team_doc = db.teams.find_one({"league": lname, "name": db_name})
                                        if team_doc:
                                            existing = team_doc.get('aliases', [])
                                            if be_name not in existing:
                                                db.teams.update_one(
                                                    {"_id": team_doc["_id"]},
                                                    {"$addToSet": {"aliases": be_name}}
                                                )
                                    teams_cache[normalize_for_match(be_name)] = db_name
                                    total_auto_alias.append({"be": be_name, "db": db_name, "league": lname})
                                    if is_debug:
                                        debug_lines.append(f"   🔧 AUTO-ALIAS: '{be_name}' → '{db_name}'")

                            # Aggiorna quote
                            new_odds = {'1': be['odds_1'], 'X': be['odds_x'], '2': be['odds_2']}
                            if 'odds' not in m:
                                m['odds'] = {}
                            m['odds']['1'] = new_odds['1']
                            m['odds']['X'] = new_odds['X']
                            m['odds']['2'] = new_odds['2']
                            m['odds']['src'] = "BetExplorer"
                            m['odds']['ts'] = datetime.now()
                            mod = True
                            match_count += 1
                            league_found += 1
                            league_repaired += 1
                            round_repaired += 1
                            be_remaining.remove(be)

                            all_odds_lines.append(f"   🔧 {m['home']:<20} vs {m['away']:<20} | 1: {new_odds['1']:<6} X: {new_odds['X']:<6} 2: {new_odds['2']:<6} (auto-repair)")
                            if is_debug:
                                debug_lines.append(f"   ✅ {m['home']} vs {m['away']}  ←  BE: {be['home']} vs {be['away']} (auto-repair)")
                            repaired = True
                            break

                    if not repaired:
                        be_names_left = [f"'{b['home']}' vs '{b['away']}'" for b in be_remaining]
                        if len(be_remaining) == 0:
                            league_no_odds += 1
                            round_no_odds += 1
                            all_odds_lines.append(f"   ⏳ {m['home']} vs {m['away']} — assente su BE")
                        else:
                            league_not_matched += 1
                            round_not_matched += 1
                            round_failed_names.append(f"{m['home']} vs {m['away']}")
                            all_odds_lines.append(f"   ❌ {m['home']} vs {m['away']}  |  BE rimaste: {'; '.join(be_names_left)}")
                        if is_debug:
                            debug_lines.append(f"   ❌ {m['home']} vs {m['away']}")

                # Riga riepilogo giornata (stile vecchio scraper)
                parts = []
                if match_count > 0:
                    parts.append(f"✅ {match_count} aggiornate")
                if round_repaired > 0:
                    parts.append(f"🔧 {round_repaired} auto-repair")
                if round_postponed > 0:
                    parts.append(f"⏳ {round_postponed} posticipate")
                if round_no_odds > 0 and len(be_matches) > 0:
                    parts.append(f"⏳ {round_no_odds} senza quote")
                if round_no_odds > 0 and len(be_matches) == 0:
                    parts.append(f"⏳ {round_no_odds} turno assente su BE")
                if round_not_matched > 0:
                    parts.append(f"❌ {round_not_matched} non riparabili")
                if not parts:
                    parts.append("(nessuna variazione)")
                # Alert se BE ha partite ma nessuna matchata (possibile problema URL/matching)
                if len(be_matches) > 0 and league_found == 0 and match_count == 0 and round_no_odds == len(matches):
                    parts.append(f"⚠️ 0 match su {len(be_matches)} BE — verificare matching/URL!")
                print(f" {', '.join(parts)}")
                for fn in round_failed_names:
                    print(f"      ❌ {fn}")

                if mod:
                    if not dry_run:
                        db.h2h_by_round.update_one(
                            {"_id": round_doc["_id"]},
                            {"$set": {"matches": matches}}
                        )
                    league_updated += match_count

            league_elapsed = time.time() - league_start
            total_updated += league_updated
            total_found += league_found
            total_not_matched += league_not_matched
            total_no_odds += league_no_odds

            status = "✅" if league_not_matched == 0 else "⚠️"
            parts = [f"{league_found} trovate", f"{league_updated} aggiornate"]
            if league_repaired > 0:
                parts.append(f"🔧 {league_repaired} auto-repair")
            if league_postponed > 0:
                parts.append(f"⏳ {league_postponed} posticipate")
            if league_no_odds - league_postponed > 0:
                parts.append(f"⏳ {league_no_odds - league_postponed} senza quote")
            if league_not_matched > 0:
                parts.append(f"❌ {league_not_matched} non riparabili")
            print(f"   {status} {lname}: {', '.join(parts)} ({league_elapsed:.1f}s)")

            league_stats.append({
                "name": lname,
                "updated": league_updated,
                "found": league_found,
                "repaired": league_repaired,
                "postponed": league_postponed,
                "not_matched": league_not_matched,
                "no_odds": league_no_odds,
                "time": league_elapsed
            })

        except Exception as e:
            print(f"   ❌ {lname}: errore — {e}")
            league_stats.append({"name": lname, "updated": 0, "found": 0, "not_matched": 0, "time": 0, "error": str(e)})

    # RIEPILOGO
    total_elapsed = time.time() - scraper_start

    report_lines = []
    report_lines.append(f"{'='*96}")
    report_lines.append(f"📊 RIEPILOGO SCRAPER BETEXPLORER (Quote 1X2) — {'DRY-RUN' if dry_run else 'LIVE'}")
    report_lines.append(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"{'='*96}")
    report_lines.append(f"{'Campionato':<40} | {'Trovate':>8} | {'Aggiorn':>8} | {'No Quote':>8} | {'Match KO':>8} | {'Tempo':>8}")
    report_lines.append(f"{'-'*96}")
    for s in league_stats:
        err = f" ❌ {s['error'][:30]}" if 'error' in s else ""
        report_lines.append(f"{s['name']:<40} | {s['found']:>8} | {s['updated']:>8} | {s.get('no_odds',0):>8} | {s['not_matched']:>8} | {s['time']:>6.1f}s{err}")
    report_lines.append(f"{'-'*96}")
    report_lines.append(f"{'TOTALE':<40} | {total_found:>8} | {total_updated:>8} | {total_no_odds:>8} | {total_not_matched:>8} | {total_elapsed:>6.1f}s")
    report_lines.append(f"{'='*96}")
    report_lines.append(f"⏱️ Tempo totale: {total_elapsed/60:.1f} minuti")
    if total_no_odds > 0:
        report_lines.append(f"ℹ️ {total_no_odds} partite senza quote = turno non ancora pubblicato su BetExplorer (normale)")
    if total_not_matched > 0:
        report_lines.append(f"⚠️ {total_not_matched} MATCH FALLITI = partita presente su BE ma non riconosciuta (DA VERIFICARE)")
    if total_auto_alias:
        report_lines.append(f"\n🔧 ALIAS AGGIUNTI AUTOMATICAMENTE ({len(total_auto_alias)}):")
        for a in total_auto_alias:
            saved = "salvato in DB" if not dry_run else "NON salvato (dry-run)"
            report_lines.append(f"   '{a['be']}' → '{a['db']}'  [{a['league']}]  ({saved})")

    report_text = "\n".join(report_lines)
    print(f"\n{report_text}")

    # Salva report + debug su file
    log_dir = os.path.join(current_path, "log")
    os.makedirs(log_dir, exist_ok=True)
    report_path = os.path.join(log_dir, "betexplorer_quote_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
        if all_odds_lines:
            f.write("\n\n" + "="*80 + "\n")
            f.write("DETTAGLIO QUOTE PER PARTITA\n")
            f.write("="*80 + "\n")
            f.write("\n".join(all_odds_lines))
        if debug_lines:
            f.write("\n\n" + "="*80 + "\n")
            f.write(f"DEBUG DETTAGLIATO — {debug_league}\n")
            f.write("="*80 + "\n")
            f.write("\n".join(debug_lines))
    print(f"\n📄 Report salvato in: {report_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Esegui senza scrivere sul DB')
    args = parser.parse_args()
    run_scraper(dry_run=args.dry_run)
