"""
scrape_sportradar_h2h.py — Scraper H2H Sportradar per partite coppa UCL/UEL.

Estrae dati H2H da Sportradar per le partite di coppa del giorno:
  - Forma (lettere V/P/S + percentuale)
  - Classifica Champions/Europa League
  - Over/Under %, media gol, clean sheet %, score %
  - Gol totali e media nei precedenti H2H
  - Commenti generati da Sportradar
  - Standing dettagliato (V/P/S/GF/GS/Diff)

Salva i dati nel campo `sportradar_h2h` del documento partita.

Uso nella pipeline: se non ci sono partite coppa oggi, esce subito (0 Chrome).
"""
import os
import sys
import re
import time
from datetime import datetime

# Fix percorsi (stesso pattern degli altri script in frequenti/)
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config import db
except ImportError:
    sys.path.append(r"C:\Progetti\simulatore-calcio-backend")
    from config import db

# ============================================================
# CONFIGURAZIONE
# ============================================================

SEASONS = {
    'Champions League': {
        'season_id': 131129,
        'matches': db['matches_champions_league'],
        'teams': db['teams_champions_league'],
    },
    'Europa League': {
        'season_id': 131635,
        'matches': db['matches_europa_league'],
        'teams': db['teams_europa_league'],
    },
}

BASE_URL = "https://s5.sir.sportradar.com/snai/it/1/season"


# ============================================================
# LOOKUP: nome squadra → sportradar_id
# ============================================================

def build_team_lookup():
    """Costruisce lookup nome/alias → {sportradar_id, name} per tutte le squadre coppe."""
    lookup = {}
    for comp, cfg in SEASONS.items():
        for doc in cfg['teams'].find({'sportradar_id': {'$exists': True}}, {'name': 1, 'aliases': 1, 'sportradar_id': 1}):
            sr_id = doc['sportradar_id']
            name = doc['name']
            lookup[name.lower()] = {'sportradar_id': sr_id, 'name': name, 'comp': comp}
            for alias in doc.get('aliases', []):
                if isinstance(alias, str):
                    lookup[alias.lower()] = {'sportradar_id': sr_id, 'name': name, 'comp': comp}
    return lookup


def get_sportradar_id(team_name, lookup):
    """Cerca sportradar_id per nome squadra (esatto, case-insensitive, parziale)."""
    entry = lookup.get(team_name.lower())
    if entry:
        return entry['sportradar_id']
    for key, entry in lookup.items():
        if team_name.lower() in key or key in team_name.lower():
            return entry['sportradar_id']
    return None


# ============================================================
# SCRAPING H2H
# ============================================================

def _name_matches(sr_name, db_name):
    """Verifica se il nome Sportradar corrisponde al nome DB (case-insensitive, parziale)."""
    sr = sr_name.strip().lower()
    db_n = db_name.strip().lower()
    return sr in db_n or db_n in sr or sr == db_n


def extract_h2h_data(driver, season_id, home_id, away_id, home_name, away_name):
    """Naviga alla pagina H2H e estrae i dati chiave."""
    from selenium.webdriver.common.by import By

    url = f"{BASE_URL}/{season_id}/h2h/{home_id}/{away_id}"
    print(f"  URL: {url}")

    try:
        driver.get(url)
        time.sleep(5)
    except Exception as e:
        print(f"  Errore caricamento: {e}")
        return None

    body_text = driver.find_element(By.TAG_NAME, 'body').text

    result = {
        'home_name': home_name,
        'away_name': away_name,
        'home_sportradar_id': home_id,
        'away_sportradar_id': away_id,
        'scraped_at': datetime.now().isoformat(),
    }

    # --- PERFORMANCE (forma lettere + %) ---
    forma_pct = re.findall(r'PUNTI\n(\d+)%\n\d+%\nFORMA', body_text)
    if len(forma_pct) >= 2:
        result['home_form_pct'] = int(forma_pct[0])
        result['away_form_pct'] = int(forma_pct[1])
        print(f"  Forma %: {home_name} {forma_pct[0]}% | {away_name} {forma_pct[1]}%")
    else:
        result['home_form_pct'] = None
        result['away_form_pct'] = None

    perf_blocks = re.findall(r'PERFORMANCE\n((?:[VPS]\n?)+)', body_text)
    if len(perf_blocks) >= 2:
        home_form = [c for c in perf_blocks[0].strip().split('\n') if c in ('V', 'P', 'S')]
        away_form = [c for c in perf_blocks[1].strip().split('\n') if c in ('V', 'P', 'S')]
        result['home_form'] = home_form[:6]
        result['away_form'] = away_form[:6]
        print(f"  Forma: {home_name} {''.join(home_form[:6])} | {away_name} {''.join(away_form[:6])}")
    else:
        result['home_form'] = []
        result['away_form'] = []

    # --- CLASSIFICA ---
    classifica = re.findall(r'#(\d+)\n(\d+)\nPUNTI', body_text)
    if len(classifica) >= 2:
        result['home_position'] = int(classifica[0][0])
        result['home_points'] = int(classifica[0][1])
        result['away_position'] = int(classifica[1][0])
        result['away_points'] = int(classifica[1][1])
        print(f"  Classifica: {home_name} #{classifica[0][0]} ({classifica[0][1]}pt) | {away_name} #{classifica[1][0]} ({classifica[1][1]}pt)")
    else:
        result['home_position'] = None
        result['away_position'] = None

    # --- GOL H2H (precedenti) ---
    h2h_goals = re.findall(r'Gol Totali\n(\d+)\nMedia Gol/Partita\n([\d.]+)', body_text)
    if len(h2h_goals) >= 2:
        result['home_h2h_total_goals'] = int(h2h_goals[0][0])
        result['home_h2h_avg_goals'] = float(h2h_goals[0][1])
        result['away_h2h_total_goals'] = int(h2h_goals[1][0])
        result['away_h2h_avg_goals'] = float(h2h_goals[1][1])
        print(f"  Gol H2H: {home_name} {h2h_goals[0][0]}tot ({h2h_goals[0][1]}/p) | {away_name} {h2h_goals[1][0]}tot ({h2h_goals[1][1]}/p)")
    elif len(h2h_goals) == 1:
        result['home_h2h_total_goals'] = int(h2h_goals[0][0])
        result['home_h2h_avg_goals'] = float(h2h_goals[0][1])

    # --- COMMENTI GENERATI ---
    comments = []
    lines = body_text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if (line.startswith('Quando ') or
            re.match(r'^[A-Z][A-Z\s]+ (non perde|ha vinto|ha perso|non ha mai|è imbattut)', line) or
            re.match(r'^[A-Za-z].+ (non perde|ha vinto|ha perso|non ha mai|è imbattut|striscia)', line)):
            comments.append(line)
    result['comments'] = comments
    if comments:
        print(f"  Commenti: {len(comments)}")
        for c in comments:
            print(f"    → {c}")

    # --- H2H PRECEDENTI ---
    h2h_score = re.search(
        r'PUNTEGGIO TOTALE\n(\d+)\s+\([\d.]+%\)\n(\d+)\s+\([\d.]+%\)\n(\d+)\s+\([\d.]+%\)',
        body_text
    )
    if h2h_score:
        result['h2h_home_wins'] = int(h2h_score.group(1))
        result['h2h_draws'] = int(h2h_score.group(2))
        result['h2h_away_wins'] = int(h2h_score.group(3))
        total = result['h2h_home_wins'] + result['h2h_draws'] + result['h2h_away_wins']
        print(f"  H2H: {result['h2h_home_wins']}V-{result['h2h_draws']}P-{result['h2h_away_wins']}S (tot {total})")

    # --- OVER/UNDER STATS ---
    ou_pattern = re.findall(
        r'([A-Z][A-Za-zÀ-ÿ\s\.]+?)\s+(\d+)\n(\d+)\n(\d+(?:\.\d+)?)\n%\n(\d+(?:\.\d+)?)\n%\n(\d+)\n([\d.]+)\s+(\d+)\s+partite,\s+(\d+)%\s+(\d+)\s+partite,\s+(\d+)%',
        body_text
    )
    if len(ou_pattern) >= 2:
        for name, played, _over_n, over_pct, under_pct, _threshold, avg_goals, _cs_n, cs_pct, _goal_n, goal_pct in ou_pattern[:2]:
            name_clean = name.strip()
            if _name_matches(name_clean, home_name):
                prefix = 'home'
            elif _name_matches(name_clean, away_name):
                prefix = 'away'
            else:
                prefix = 'home' if 'home_over_pct' not in result else 'away'

            result[f'{prefix}_played'] = int(played)
            result[f'{prefix}_over_pct'] = float(over_pct)
            result[f'{prefix}_under_pct'] = float(under_pct)
            result[f'{prefix}_avg_goals_cl'] = float(avg_goals)
            result[f'{prefix}_clean_sheet_pct'] = float(cs_pct)
            result[f'{prefix}_score_pct'] = float(goal_pct)
            side = "HOME" if prefix == 'home' else "AWAY"
            print(f"  O/U {name_clean} ({side}): Over {over_pct}% | AvgGol {avg_goals} | CS {cs_pct}% | Score {goal_pct}%")
    elif len(ou_pattern) == 1:
        name, played, _over_n, over_pct, under_pct, _threshold, avg_goals, _cs_n, cs_pct, _goal_n, goal_pct = ou_pattern[0]
        name_clean = name.strip()
        prefix = 'home' if _name_matches(name_clean, home_name) else 'away'
        result[f'{prefix}_played'] = int(played)
        result[f'{prefix}_over_pct'] = float(over_pct)
        result[f'{prefix}_under_pct'] = float(under_pct)
        result[f'{prefix}_avg_goals_cl'] = float(avg_goals)
        result[f'{prefix}_clean_sheet_pct'] = float(cs_pct)
        result[f'{prefix}_score_pct'] = float(goal_pct)

    # --- CLASSIFICA DETTAGLIATA (G V P S GF GS Diff PT) ---
    standing_pattern = re.findall(
        r'(\d+)\n([A-Z][A-Za-zÀ-ÿ\s\.]+)\n(\d+ \d+ \d+ \d+ \d+ \d+ -?\d+ \d+)',
        body_text
    )
    if standing_pattern:
        for pos, name, stats_str in standing_pattern:
            name_clean = name.strip()
            parts = stats_str.split()
            if len(parts) >= 8:
                standing = {
                    'position': int(pos),
                    'played': int(parts[0]),
                    'wins': int(parts[1]),
                    'draws': int(parts[2]),
                    'losses': int(parts[3]),
                    'goals_for': int(parts[4]),
                    'goals_against': int(parts[5]),
                    'goal_diff': int(parts[6]),
                    'points': int(parts[7]),
                }
                if _name_matches(name_clean, home_name):
                    result['home_standing'] = standing
                    print(f"  Standing {name_clean} (HOME): {standing['wins']}V-{standing['draws']}P-{standing['losses']}S GF:{standing['goals_for']} GS:{standing['goals_against']}")
                elif _name_matches(name_clean, away_name):
                    result['away_standing'] = standing
                    print(f"  Standing {name_clean} (AWAY): {standing['wins']}V-{standing['draws']}P-{standing['losses']}S GF:{standing['goals_for']} GS:{standing['goals_against']}")

    return result


# ============================================================
# MAIN
# ============================================================

def main():
    print(f"{'='*80}")
    print(f"  SCRAPER H2H SPORTRADAR — TUTTE LE PARTITE COPPA SCHEDULED")
    print(f"{'='*80}")

    # Build lookup
    lookup = build_team_lookup()
    print(f"Team lookup: {len(lookup)} entries")

    # Trova TUTTE le partite scheduled (non solo oggi)
    matches_to_scrape = []
    for comp, cfg in SEASONS.items():
        matches = list(cfg['matches'].find({
            'status': {'$in': ['scheduled', 'Scheduled', 'not_started']}
        }))
        print(f"  {comp}: {len(matches)} partite scheduled")
        for m in matches:
            home = m.get('home_team', '')
            away = m.get('away_team', '')
            home_sr = get_sportradar_id(home, lookup)
            away_sr = get_sportradar_id(away, lookup)

            if home_sr and away_sr:
                matches_to_scrape.append({
                    'comp': comp,
                    'season_id': cfg['season_id'],
                    'match_id': m['_id'],
                    'home': home,
                    'away': away,
                    'home_sr': home_sr,
                    'away_sr': away_sr,
                    'coll': cfg['matches'],
                    'match_date': m.get('match_date', ''),
                })
            else:
                missing = []
                if not home_sr: missing.append(f"{home} (home)")
                if not away_sr: missing.append(f"{away} (away)")
                print(f"  SKIP {home} vs {away} [{comp}] — ID mancante: {', '.join(missing)}")

    print(f"\nPartite da scrapare: {len(matches_to_scrape)}")
    if not matches_to_scrape:
        print("Nessuna partita coppa scheduled trovata. Skip.")
        return

    # Avvia Chrome solo se ci sono partite
    import undetected_chromedriver as uc

    print("\nAvvio Chrome...")
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = uc.Chrome(options=options, user_multi_procs=True)
    driver.set_page_load_timeout(30)

    results = []
    errors = []

    try:
        for i, match in enumerate(matches_to_scrape):
            print(f"\n[{i+1}/{len(matches_to_scrape)}] {match['home']} vs {match['away']} [{match['comp']}] ({match.get('match_date', '?')})")

            data = extract_h2h_data(
                driver,
                match['season_id'],
                match['home_sr'],
                match['away_sr'],
                match['home'],
                match['away']
            )

            if data:
                results.append({**data, 'match_id': match['match_id'], 'comp': match['comp']})
                match['coll'].update_one(
                    {'_id': match['match_id']},
                    {'$set': {'sportradar_h2h': data}}
                )
                print(f"  ✅ Salvato in DB!")
            else:
                errors.append(f"{match['home']} vs {match['away']}")

            if i < len(matches_to_scrape) - 1:
                time.sleep(2)

    except Exception as e:
        print(f"\nERRORE FATALE: {e}")
        import traceback
        traceback.print_exc()

    finally:
        driver.quit()
        print("\nBrowser chiuso.")

    # Riepilogo
    print(f"\n{'='*80}")
    print(f"  RIEPILOGO")
    print(f"{'='*80}")
    print(f"  Scrappate: {len(results)}/{len(matches_to_scrape)}")
    if errors:
        print(f"  Errori: {errors}")

    for r in results:
        print(f"\n  {r['home_name']} vs {r['away_name']}:")
        if r.get('home_form'):
            print(f"    Forma: {''.join(r['home_form'])} vs {''.join(r['away_form'])}")
        if r.get('home_position'):
            print(f"    Classifica: #{r['home_position']}({r.get('home_points',0)}pt) vs #{r['away_position']}({r.get('away_points',0)}pt)")
        if r.get('home_over_pct'):
            print(f"    Over: {r['home_over_pct']}% vs {r.get('away_over_pct','?')}%")
            print(f"    Avg gol CL: {r.get('home_avg_goals_cl','?')} vs {r.get('away_avg_goals_cl','?')}")


if __name__ == '__main__':
    main()
