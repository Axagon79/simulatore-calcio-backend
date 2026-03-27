"""
scraper_sofascore_post_match.py
Raccoglie statistiche post-partita da SofaScore per le partite concluse.
Usa Selenium + BeautifulSoup per estrarre xG, tiri, possesso, duelli, ecc.

Flusso:
1. Per ogni lega, apre la pagina torneo SofaScore
2. Seleziona il round giusto tramite dropdown
3. Raccoglie i link delle partite finite
4. Apre ogni partita → clicca tab Statistics → estrae stats
5. Salva in collection 'post_match_stats'

Uso:
    python scraper_sofascore_post_match.py                  # oggi (round corrente per ogni lega)
    python scraper_sofascore_post_match.py 2026-03-27       # data specifica
    python scraper_sofascore_post_match.py --backfill 2026-03-20 2026-03-27
"""

import os, sys, time, re, random, json
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# --- Path setup ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db
import undetected_chromedriver as uc

# ═══════════════════════════════════════════════════════════
# CONFIGURAZIONE
# ═══════════════════════════════════════════════════════════
SOFASCORE_BASE = "https://www.sofascore.com"
COLLECTION_NAME = "post_match_stats"
PAGE_LOAD_WAIT = 6        # secondi per caricare pagina torneo (fallback)
STATS_LOAD_WAIT = 5       # secondi per caricare stats partita
BETWEEN_MATCHES_WAIT = 2  # secondi tra una partita e l'altra
MAX_RETRIES = 2

# Mappa leghe: nome nel nostro DB → URL SofaScore
# Pattern: /football/tournament/{country}/{slug}/{league_id}#id:{season_id}
# league_id è fisso per ogni lega, season_id cambia per stagione
SOFASCORE_LEAGUES = {
    # ITALIA
    "Serie A":       {"country": "italy", "slug": "serie-a", "league_id": 23, "season_id": 76457},
    "Serie B":       {"country": "italy", "slug": "serie-b", "league_id": 53, "season_id": 79502},
    "Serie C - Girone A": {"country": "italy", "slug": "serie-c-girone-a", "league_id": 11445, "season_id": 79377},
    "Serie C - Girone B": {"country": "italy", "slug": "serie-c-girone-b", "league_id": 11447, "season_id": 79378},
    "Serie C - Girone C": {"country": "italy", "slug": "serie-c-girone-c", "league_id": 11446, "season_id": 79379},
    # INGHILTERRA
    "Premier League": {"country": "england", "slug": "premier-league", "league_id": 17, "season_id": 76986},
    "Championship":   {"country": "england", "slug": "championship", "league_id": 18, "season_id": 77347},
    "League One":     {"country": "england", "slug": "league-one", "league_id": 24, "season_id": 77352},
    "League Two":     {"country": "england", "slug": "league-two", "league_id": 25, "season_id": 77351},
    # SPAGNA
    "La Liga":        {"country": "spain", "slug": "laliga", "league_id": 8, "season_id": 77559},
    "LaLiga 2":       {"country": "spain", "slug": "laliga-2", "league_id": 54, "season_id": 77558},
    # GERMANIA
    "Bundesliga":     {"country": "germany", "slug": "bundesliga", "league_id": 35, "season_id": 77333},
    "2. Bundesliga":  {"country": "germany", "slug": "2-bundesliga", "league_id": 44, "season_id": 77354},
    "3. Liga":        {"country": "germany", "slug": "3-liga", "league_id": 491, "season_id": 77744},
    # FRANCIA
    "Ligue 1":        {"country": "france", "slug": "ligue-1", "league_id": 34, "season_id": 77356},
    "Ligue 2":        {"country": "france", "slug": "ligue-2", "league_id": 182, "season_id": 77357},
    # OLANDA
    "Eredivisie":     {"country": "netherlands", "slug": "eredivisie", "league_id": 37, "season_id": 77012},
    "Eerste Divisie":  {"country": "netherlands", "slug": "eerste-divisie", "league_id": 131, "season_id": 77156},
    # PORTOGALLO
    "Liga Portugal":  {"country": "portugal", "slug": "liga-portugal", "league_id": 238, "season_id": 77806},
    "Liga Portugal 2": {"country": "portugal", "slug": "liga-portugal-2", "league_id": 239, "season_id": 77801},
    # SCOZIA
    "Scottish Premiership": {"country": "scotland", "slug": "premiership", "league_id": 36, "season_id": 77128},
    "Scottish Championship": {"country": "scotland", "slug": "championship", "league_id": 206, "season_id": 77037},
    # NORDICI
    "Allsvenskan":    {"country": "sweden", "slug": "allsvenskan", "league_id": 40, "season_id": 87925},
    "Eliteserien":    {"country": "norway", "slug": "eliteserien", "league_id": 20, "season_id": 87809},
    "Superligaen":    {"country": "denmark", "slug": "superliga", "league_id": 39, "season_id": 76491},
    "Veikkausliiga":  {"country": "finland", "slug": "veikkausliiga", "league_id": 41, "season_id": 87930},
    # BELGIO / IRLANDA / TURCHIA
    "Jupiler Pro League": {"country": "belgium", "slug": "jupiler-pro-league", "league_id": 38, "season_id": 77040},
    "League of Ireland Premier Division": {"country": "ireland", "slug": "premier-division", "league_id": 192, "season_id": 87682},
    "Süper Lig":      {"country": "turkey", "slug": "super-lig", "league_id": 52, "season_id": 77805},
    "1. Lig":         {"country": "turkey", "slug": "1-lig", "league_id": 98, "season_id": 77977},
    # AMERICHE
    "Brasileirão Serie A": {"country": "brazil", "slug": "brasileirao-serie-a", "league_id": 325, "season_id": 87678},
    "Primera División":    {"country": "argentina", "slug": "liga-profesional", "league_id": 155, "season_id": 87913},
    "Major League Soccer": {"country": "usa", "slug": "mls", "league_id": 242, "season_id": 86668},
    "Liga MX":        {"country": "mexico", "slug": "liga-mx-clausura", "league_id": 11620, "season_id": 87699,
                       "alt": {"slug": "liga-mx-apertura", "league_id": 11621, "season_id": 76500}},
    # ASIA
    "J1 League":      {"country": "japan", "slug": "j1-league", "league_id": 196, "season_id": 87931},
    "Saudi Pro League": {"country": "saudi-arabia", "slug": "saudi-pro-league", "league_id": 955, "season_id": 80443},
}
# NOTA: season_id verificati il 27/03/2026. Vanno aggiornati a inizio nuova stagione.
# Per aggiornare: aprire la lega su sofascore.com e copiare l'ID dall'URL (#id:XXXXX).


# ═══════════════════════════════════════════════════════════
# BROWSER SETUP
# ═══════════════════════════════════════════════════════════
def create_browser():
    """Crea browser Chrome con undetected_chromedriver."""
    print("🌐 Avvio browser Chrome...")

    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")

    try:
        driver = uc.Chrome(options=options, headless=True)
    except Exception as e:
        error_msg = str(e).lower()
        if "version" in error_msg or "session" in error_msg:
            print("⚠️ Conflitto versioni Chrome, provo con rilevamento automatico...")
            try:
                import winreg
                key_path = r"Software\Google\Chrome\BLBeacon"
                with winreg.OpenKey(__import__('winreg').HKEY_CURRENT_USER, key_path) as key:
                    ver, _ = winreg.QueryValueEx(key, "version")
                    version_main = int(ver.split('.')[0])
                new_options = uc.ChromeOptions()
                new_options.add_argument("--headless")
                new_options.add_argument("--no-sandbox")
                new_options.add_argument("--disable-dev-shm-usage")
                new_options.add_argument("--disable-blink-features=AutomationControlled")
                new_options.add_argument("--window-size=1920,1080")
                driver = uc.Chrome(options=new_options, headless=True, version_main=version_main)
            except Exception as e2:
                print(f"❌ Impossibile avviare Chrome: {e2}")
                sys.exit(1)
        else:
            print(f"❌ Errore avvio Chrome: {e}")
            sys.exit(1)

    print("✅ Browser avviato")
    return driver


# ═══════════════════════════════════════════════════════════
# STEP 1: NAVIGAZIONE TORNEO + RACCOLTA LINK PER ROUND
# ═══════════════════════════════════════════════════════════
def normalize_name(name):
    """Normalizza nome squadra per matching."""
    import unicodedata
    name = unicodedata.normalize('NFD', name)
    name = ''.join(c for c in name if unicodedata.category(c) != 'Mn')
    name = name.lower().strip()
    # Rimuovi suffissi SOLO a fine stringa (non nel mezzo)
    for suffix in [' fc', ' sc', ' ac', ' ss', ' cf', ' fk', ' sk', ' if', ' bk',
                   ' acc', ' srl', ' spa', ' lp', ' jrs', ' jrs.']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    # Rimuovi punti
    name = name.replace('.', '').strip()
    return name


def _get_matches_via_api(driver, league_id, season_id, round_num):
    """
    Metodo VELOCE: usa l'API SofaScore via JavaScript dal browser.
    Ritorna lista di match dict oppure None se fallisce.
    """
    try:
        api_url = f"https://api.sofascore.com/api/v1/unique-tournament/{league_id}/season/{season_id}/events/round/{round_num}"
        result = driver.execute_async_script(f'''
            var callback = arguments[arguments.length - 1];
            fetch("{api_url}")
                .then(r => r.json())
                .then(data => callback(JSON.stringify(data)))
                .catch(e => callback("ERROR: " + e.message));
        ''')

        if not result or result.startswith('ERROR'):
            return None

        data = json.loads(result)
        events = data.get('events', [])
        if not events:
            return None

        matches = []
        for e in events:
            home_name = e.get('homeTeam', {}).get('name', '')
            away_name = e.get('awayTeam', {}).get('name', '')
            match_id = str(e.get('id', ''))
            slug = e.get('slug', '')
            custom_id = e.get('customId', '')

            matches.append({
                'url': f"{SOFASCORE_BASE}/football/match/{slug}/{custom_id}#id:{match_id}",
                'teams_slug': slug,
                'slug': custom_id,
                'match_id': match_id,
                'link_text': f"{home_name} vs {away_name}",
            })

        return matches
    except Exception:
        return None


def _get_matches_via_browser(driver, league_info, round_num):
    """
    Metodo FALLBACK: naviga la pagina torneo + dropdown round.
    Più lento ma funziona sempre.
    """
    country = league_info['country']
    slug = league_info['slug']
    league_id = league_info['league_id']
    season_id = league_info['season_id']

    url = f"{SOFASCORE_BASE}/football/tournament/{country}/{slug}/{league_id}#id:{season_id}"
    print(f"   🌐 [FALLBACK] Apertura pagina torneo: {url}")
    driver.get(url)
    time.sleep(PAGE_LOAD_WAIT)

    # Chiudi overlay/cookie
    driver.execute_script('''
        document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root').forEach(e => e.remove());
        document.querySelectorAll('button').forEach(b => {
            if(b.textContent.match(/accept|accett|agree|OK/i)) b.click();
            if(b.getAttribute('aria-label') === 'Close slide-in banner') b.click();
        });
    ''')
    time.sleep(1)

    # Seleziona il round tramite dropdown combobox
    print(f"   🔄 [FALLBACK] Selezione Round {round_num}...")
    try:
        driver.execute_script(f'''
            var buttons = document.querySelectorAll('button[role="combobox"]');
            for (var b of buttons) {{
                if (b.textContent.match(/round|giornata|matchday|jornada|spieltag|journée/i)) {{
                    b.click();
                    break;
                }}
            }}
        ''')
        time.sleep(2)

        driver.execute_script(f'''
            var options = document.querySelectorAll('li[role="option"], div[role="option"], [role="listbox"] li');
            for (var opt of options) {{
                var text = opt.textContent.trim();
                if (text.match(/^(Round|Giornata|Matchday|Jornada|Spieltag|Journée)\\s*{round_num}$/i) ||
                    text === '{round_num}' ||
                    text === 'Round {round_num}') {{
                    opt.click();
                    break;
                }}
            }}
        ''')
        time.sleep(PAGE_LOAD_WAIT)
    except Exception as e:
        print(f"      ⚠️ Errore selezione round: {e}")
        return []

    # Raccogli link partite dalla pagina
    soup = BeautifulSoup(driver.page_source, 'html.parser')
    links = soup.find_all('a', href=True)

    matches = []
    seen_ids = set()

    for a in links:
        href = a.get('href', '')
        if '/football/match/' not in href:
            continue

        match = re.search(r'/football/match/([^/]+)/([^#]+)#id:(\d+)', href)
        if not match:
            match = re.search(r'/football/match/([^/]+)/([^#\?]+)', href)
            if not match:
                continue

        teams_slug = match.group(1)
        slug_match = match.group(2)
        match_id = match.group(3) if match.lastindex >= 3 else None

        if match_id and match_id in seen_ids:
            continue
        if match_id:
            seen_ids.add(match_id)

        link_text = a.get_text(strip=True)

        matches.append({
            'url': SOFASCORE_BASE + href if not href.startswith('http') else href,
            'teams_slug': teams_slug,
            'slug': slug_match,
            'match_id': match_id,
            'link_text': link_text,
        })

    return matches


def _try_get_matches(driver, league_info, round_num):
    """Prova API poi browser per una specifica configurazione lega."""
    league_id = league_info['league_id']
    season_id = league_info['season_id']

    if season_id:
        matches = _get_matches_via_api(driver, league_id, season_id, round_num)
        if matches:
            print(f"   ⚡ {len(matches)} partite trovate via API (Round {round_num})")
            return matches

    # Fallback browser
    print(f"   ⚠️ API non disponibile, uso navigazione browser...")
    matches = _get_matches_via_browser(driver, league_info, round_num)
    if matches:
        print(f"   🔗 {len(matches)} partite trovate via browser (Round {round_num})")
    return matches


def get_match_links_by_round(driver, league_name, round_num):
    """
    Raccoglie i link delle partite per una lega/round.
    Per leghe con 'alt' (es. Liga MX Apertura/Clausura), prova entrambe.
    """
    league_info = SOFASCORE_LEAGUES.get(league_name)
    if not league_info:
        print(f"      ⚠️ Lega '{league_name}' non presente in SOFASCORE_LEAGUES")
        return []

    # Prova configurazione principale
    matches = _try_get_matches(driver, league_info, round_num)
    if matches:
        return matches

    # Se ha alternativa (es. Liga MX: Clausura → Apertura), prova quella
    alt = league_info.get('alt')
    if alt:
        alt_info = {**league_info, **alt}
        del alt_info['alt']
        print(f"   🔄 Provo configurazione alternativa ({alt.get('slug', '')})...")
        matches = _try_get_matches(driver, alt_info, round_num)
        if matches:
            return matches

    return []


# ═══════════════════════════════════════════════════════════
# STEP 2: MATCHING CON I NOSTRI PRONOSTICI
# ═══════════════════════════════════════════════════════════
def match_team_name(our_name, sofascore_slug):
    """Verifica se il nome squadra corrisponde allo slug SofaScore."""
    our_norm = normalize_name(our_name)
    slug_clean = sofascore_slug.replace('-', ' ').lower()

    # Match diretto
    if our_norm in slug_clean or slug_clean in our_norm:
        return True

    # Match per token (>2 char per catturare abbreviazioni come "ACC", "LP")
    our_tokens = [t for t in our_norm.split() if len(t) > 2]
    slug_tokens = slug_clean.split()

    # Se il primo token del nostro nome (quello principale) è nello slug → match
    if our_tokens and our_tokens[0] in slug_clean:
        return True

    # Se il primo token dello slug è nel nostro nome → match
    if slug_tokens and slug_tokens[0] in our_norm:
        return True

    # Match per qualsiasi token >3 char
    for token in our_tokens:
        if len(token) > 3 and token in slug_clean:
            return True

    return False


def get_predictions_for_date(date_str):
    """Recupera i pronostici per una data dal DB."""
    predictions = list(db['daily_predictions_unified'].find({'date': date_str}))

    if not predictions:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        start = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, 0)
        end = start + timedelta(days=1)
        predictions = list(db['daily_predictions_unified'].find({
            'data_evento': {'$gte': start.strftime("%Y-%m-%d"), '$lt': end.strftime("%Y-%m-%d")}
        }))

    print(f"   📊 {len(predictions)} pronostici trovati per {date_str}")
    return predictions


def find_matching_sofascore_link(prediction, sofascore_matches):
    """Trova il link SofaScore corrispondente a un pronostico."""
    home = prediction.get('home', prediction.get('home_team', ''))
    away = prediction.get('away', prediction.get('away_team', ''))

    if not home or not away:
        return None

    for sm in sofascore_matches:
        slug = sm['teams_slug']
        if match_team_name(home, slug) and match_team_name(away, slug):
            return sm

    return None


# ═══════════════════════════════════════════════════════════
# STEP 3: ESTRAZIONE STATISTICHE
# ═══════════════════════════════════════════════════════════

# Mappa stat name → chiave standardizzata
STAT_MAP = {
    # ── Match overview ──
    'ball possession': 'possession',
    'expected goals (xg)': 'xg',
    'big chances': 'big_chances',
    'total shots': 'total_shots',
    'goalkeeper saves': 'saves',
    'corner kicks': 'corners',
    'fouls': 'fouls',
    'passes': 'passes',
    'tackles': 'tackles',
    'free kicks': 'free_kicks',
    'yellow cards': 'yellow_cards',
    'red cards': 'red_cards',
    # ── Shots ──
    'shots on target': 'shots_on_target',
    'shots off target': 'shots_off_target',
    'blocked shots': 'blocked_shots',
    'shots inside box': 'shots_inside_box',
    'shots outside box': 'shots_outside_box',
    'hit woodwork': 'hit_woodwork',
    # ── Attack ──
    'big chances scored': 'big_chances_scored',
    'big chances missed': 'big_chances_missed',
    'touches in opposition box': 'touches_in_opp_box',
    'touches in penalty area': 'touches_in_opp_box',  # alias
    'fouls in final third': 'fouls_in_final_third',
    'fouled in final third': 'fouls_in_final_third',
    'offsides': 'offsides',
    # ── Duels ──
    'duels': 'duels_total',
    'dispossessed': 'dispossessed',
    'ground duels': 'ground_duels',
    'aerial duels': 'aerial_duels',
    'dribbles': 'dribbles',
    # ── Passes ──
    'accurate passes': 'accurate_passes',
    'throw-ins': 'throw_ins',
    'final third entries': 'final_third_entries',
    'passes in final third': 'passes_in_final_third',
    'long balls': 'long_balls',
    'crosses': 'crosses',
    'through balls': 'through_balls',
    # ── Defending ──
    'tackles won': 'tackles_won',
    'total tackles': 'total_tackles',
    'interceptions': 'interceptions',
    'recoveries': 'recoveries',
    'clearances': 'clearances',
    'errors leading to shot': 'errors_leading_to_shot',
    'errors leading to goal': 'errors_leading_to_goal',
    # ── Goalkeeping ──
    'goal kicks': 'goal_kicks',
    'big saves': 'big_saves',
    'high claims': 'high_claims',
    'punches': 'punches',
    # ── Italiano (SofaScore può mostrare in italiano) ──
    'possesso palla': 'possession',
    'expected goals': 'xg',
    'tiri totali': 'total_shots',
    'tiri in porta': 'shots_on_target',
    'tiri fuori': 'shots_off_target',
    'tiri bloccati': 'blocked_shots',
    'parate': 'saves',
    'parate del portiere': 'saves',
    'calci d\'angolo': 'corners',
    'falli': 'fouls',
    'passaggi': 'passes',
    'passaggi precisi': 'accurate_passes',
    'contrasti': 'tackles',
    'contrasti vinti': 'tackles_won',
    'intercetti': 'interceptions',
    'respinte': 'clearances',
    'recuperi': 'recoveries',
    'fuorigioco': 'offsides',
    'cartellini gialli': 'yellow_cards',
    'cartellini rossi': 'red_cards',
    'palo': 'hit_woodwork',
    'grandi occasioni': 'big_chances',
    'grandi occasioni mancate': 'big_chances_missed',
    'grandi occasioni segnate': 'big_chances_scored',
    'tocchi in area avversaria': 'touches_in_opp_box',
    'dribbling': 'dribbles',
    'duelli': 'duels_total',
    'duelli a terra': 'ground_duels',
    'duelli aerei': 'aerial_duels',
    'lanci lunghi': 'long_balls',
    'cross': 'crosses',
    'rimesse laterali': 'throw_ins',
    'rinvii dal fondo': 'goal_kicks',
    'uscite alte': 'high_claims',
    'pugni': 'punches',
    'grandi parate': 'big_saves',
    'falli subiti nel terzo finale': 'fouls_in_final_third',
    'errori che portano al tiro': 'errors_leading_to_shot',
    'errori che portano al gol': 'errors_leading_to_goal',
    'entrate nel terzo finale': 'final_third_entries',
}


def parse_stat_value(raw):
    """Parsa un valore statistico (numero, percentuale, o frazionario)."""
    raw = raw.strip().replace(',', '')

    # Percentuale: "60%"
    pct_match = re.match(r'(\d+(?:\.\d+)?)%', raw)
    if pct_match:
        return float(pct_match.group(1))

    # Frazionario: "27/50" → ritorna come stringa
    frac_match = re.match(r'(\d+)/(\d+)', raw)
    if frac_match:
        return raw  # mantieni come "27/50"

    # Numero semplice
    try:
        if '.' in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _extract_stats_via_api(driver, match_id):
    """
    Metodo VELOCE: scarica statistiche via API SofaScore.
    Ritorna (home_stats, away_stats) oppure None se fallisce.
    """
    try:
        api_url = f"https://api.sofascore.com/api/v1/event/{match_id}/statistics"
        result = driver.execute_async_script(f'''
            var callback = arguments[arguments.length - 1];
            fetch("{api_url}")
                .then(r => r.json())
                .then(data => callback(JSON.stringify(data)))
                .catch(e => callback("ERROR: " + e.message));
        ''')

        if not result or result.startswith('ERROR'):
            return None

        data = json.loads(result)
        sections = data.get('statistics', [])
        if not sections:
            return None

        home_stats = {}
        away_stats = {}

        # Cerca il periodo "ALL" (statistiche complete)
        for section in sections:
            if section.get('period') != 'ALL':
                continue
            for group in section.get('groups', []):
                for item in group.get('statisticsItems', []):
                    stat_name = item.get('name', '').lower()
                    stat_key = STAT_MAP.get(stat_name)
                    if not stat_key:
                        continue

                    home_val = item.get('home', '')
                    away_val = item.get('away', '')

                    home_stats[stat_key] = parse_stat_value(str(home_val))
                    away_stats[stat_key] = parse_stat_value(str(away_val))

        if not home_stats:
            return None

        return home_stats, away_stats

    except Exception:
        return None


def _extract_stats_via_browser(driver, match_url):
    """
    Metodo FALLBACK: apre la pagina partita e parsa con BeautifulSoup.
    """
    driver.get(match_url)
    time.sleep(STATS_LOAD_WAIT)

    # Chiudi eventuali overlay
    driver.execute_script('''
        document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root').forEach(e => e.remove());
        document.querySelectorAll('button').forEach(b => {
            if(b.textContent.match(/accept|accett|agree|OK/i)) b.click();
            if(b.getAttribute('aria-label') === 'Close slide-in banner') b.click();
        });
    ''')
    time.sleep(0.5)

    # Clicca sul tab "Statistics"
    driver.execute_script('''
        var tab = document.querySelector('[data-testid="tab-statistics"]');
        if(tab) tab.click();
    ''')
    time.sleep(STATS_LOAD_WAIT)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    all_text = soup.get_text(separator='|', strip=True)

    home_stats = {}
    away_stats = {}
    tokens = all_text.split('|')

    for stat_label, stat_key in STAT_MAP.items():
        for i, token in enumerate(tokens):
            if token.lower().strip() == stat_label:
                if i > 0 and i < len(tokens) - 1:
                    home_raw = tokens[i - 1].strip()
                    away_raw = tokens[i + 1].strip()
                    if re.match(r'[\d./%]+', home_raw) and re.match(r'[\d./%]+', away_raw):
                        home_stats[stat_key] = parse_stat_value(home_raw)
                        away_stats[stat_key] = parse_stat_value(away_raw)
                        break

                if i < len(tokens) - 2:
                    val1 = tokens[i + 1].strip()
                    val2 = tokens[i + 2].strip()
                    if re.match(r'[\d./%]+', val1) and re.match(r'[\d./%]+', val2):
                        home_stats[stat_key] = parse_stat_value(val1)
                        away_stats[stat_key] = parse_stat_value(val2)
                        break

    if not home_stats:
        return None

    return home_stats, away_stats


def extract_match_stats(driver, match_url, match_id=None):
    """
    Estrae statistiche post-partita. Prova API (veloce), poi fallback browser.
    Ritorna dict con home_stats, away_stats, home_score, away_score.
    """
    home_stats = None
    away_stats = None

    # Metodo 1: API veloce (se abbiamo il match_id)
    if match_id:
        api_result = _extract_stats_via_api(driver, match_id)
        if api_result:
            home_stats, away_stats = api_result
            print(f"         ⚡ {len(home_stats)} statistiche estratte via API")

    # Metodo 2: Fallback browser
    if not home_stats:
        if match_id:
            print(f"         ⚠️ API stats non disponibile, uso browser...")
        browser_result = _extract_stats_via_browser(driver, match_url)
        if browser_result:
            home_stats, away_stats = browser_result
            print(f"         📊 {len(home_stats)} statistiche estratte via browser")

    if not home_stats:
        print(f"         ⚠️ Nessuna statistica trovata!")
        return None

    # Risultato (score viene dal match event API o dal prediction)
    return {
        'home_team': None,
        'away_team': None,
        'home_score': None,
        'away_score': None,
        'home_stats': home_stats,
        'away_stats': away_stats,
    }


# ═══════════════════════════════════════════════════════════
# STEP 4: SALVATAGGIO SU DB
# ═══════════════════════════════════════════════════════════
def save_to_db(date_str, prediction, stats_data, sofascore_match):
    """Salva le statistiche post-partita nel DB (un doc per partita)."""
    home = prediction.get('home', '')
    away = prediction.get('away', '')

    doc = {
        'date': date_str,
        'date_obj': datetime.strptime(date_str, "%Y-%m-%d"),
        'league': prediction.get('league', ''),
        'giornata': prediction.get('giornata'),
        'home': home,
        'away': away,
        'risultato': f"{stats_data.get('home_score', '?')}-{stats_data.get('away_score', '?')}",
        'sofascore_match_id': sofascore_match.get('match_id'),
        'sofascore_url': sofascore_match.get('url', ''),
        'home_stats': stats_data['home_stats'],
        'away_stats': stats_data['away_stats'],
        # Campi per analisi AI (popolati dopo da Mistral)
        'ai_analysis': None,
        'updated_at': datetime.now(),
    }

    # Upsert per partita (non per pronostico)
    db[COLLECTION_NAME].update_one(
        {'date': date_str, 'home': home, 'away': away},
        {'$set': doc, '$setOnInsert': {'created_at': datetime.now()}},
        upsert=True
    )


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
def scrape_date(driver, date_str):
    """Processa tutte le partite pronosticate di una data, navigando per lega/round.
    Ritorna dict con statistiche dettagliate per il report finale."""
    report = {
        'date': date_str,
        'total_predictions': 0,
        'already_done': 0,
        'saved': 0,
        'no_giornata': [],       # (home, away, league)
        'no_round_found': [],    # (league, giornata)
        'no_match_found': [],    # (home, away, league, giornata)
        'no_stats': [],          # (home, away, league, giornata, motivo)
        'by_league': {},         # league → {salvate, totali}
    }

    print(f"\n{'='*60}")
    print(f"📅 ELABORAZIONE: {date_str}")
    print(f"{'='*60}")

    # 1. Recupera pronostici per questa data
    predictions = get_predictions_for_date(date_str)
    if not predictions:
        print("   ⚠️ Nessun pronostico per questa data")
        return report

    report['total_predictions'] = len(predictions)

    # 2. Controlla quali non abbiamo già in post_match_stats
    already_done = set()
    existing = db[COLLECTION_NAME].find({'date': date_str}, {'home': 1, 'away': 1})
    for doc in existing:
        already_done.add((doc.get('home', ''), doc.get('away', '')))

    to_process = [p for p in predictions
                  if (p.get('home', ''), p.get('away', '')) not in already_done]

    report['already_done'] = len(already_done)

    if not to_process:
        print(f"   ✅ Tutte le stats già raccolte per {date_str}")
        return report

    print(f"   🆕 {len(to_process)} partite da processare (su {len(predictions)} pronostici)")

    # 3. Raggruppa per (lega, giornata)
    by_league_round = {}
    for pred in to_process:
        league = pred.get('league', '')
        giornata = pred.get('giornata')

        if not giornata:
            # Fallback: cerca giornata in h2h_by_round
            home = pred.get('home', '')
            away = pred.get('away', '')
            r = db['h2h_by_round'].find_one(
                {'league': league, 'matches': {'$elemMatch': {'home': home, 'away': away}}},
                {'round_name': 1}
            )
            if r:
                rnum_match = re.search(r'(\d+)', r.get('round_name', ''))
                giornata = int(rnum_match.group(1)) if rnum_match else None

        if not giornata:
            print(f"   ⚠️ Giornata non trovata per {pred.get('home')} vs {pred.get('away')} ({league})")
            report['no_giornata'].append((pred.get('home', ''), pred.get('away', ''), league))
            continue

        key = (league, giornata)
        if key not in by_league_round:
            by_league_round[key] = []
        by_league_round[key].append(pred)

    print(f"   📋 {len(by_league_round)} gruppi lega/giornata da navigare")

    # 4. Per ogni lega/round, apri SofaScore, raccogli link, matcha e scarica
    saved = 0
    matches_cache = {}  # (home_norm, away_norm) → (stats_data, sofascore_match)

    for (league, giornata), preds in by_league_round.items():
        print(f"\n{'─'*50}")
        print(f"   ⚽ {league} — Giornata {giornata} ({len(preds)} partite)")

        if league not in report['by_league']:
            report['by_league'][league] = {'salvate': 0, 'totali': 0}
        report['by_league'][league]['totali'] += len(preds)

        # Naviga alla pagina torneo + round
        sofascore_matches = get_match_links_by_round(driver, league, giornata)
        if not sofascore_matches:
            print(f"   ❌ Nessuna partita trovata su SofaScore per {league} Round {giornata}")
            report['no_round_found'].append((league, giornata))
            continue

        for pred in preds:
            home = pred.get('home', '')
            away = pred.get('away', '')
            cache_key = (normalize_name(home), normalize_name(away))

            print(f"\n      🔍 {home} vs {away}")

            # Cerca in cache
            cached = matches_cache.get(cache_key)
            if cached:
                stats_data, sofascore_match = cached
                print(f"         📦 Stats da cache")
            else:
                # Trova link SofaScore
                sofascore_match = find_matching_sofascore_link(pred, sofascore_matches)
                if not sofascore_match:
                    print(f"         ⚠️ Partita non trovata su SofaScore")
                    report['no_match_found'].append((home, away, league, giornata))
                    continue

                print(f"         🔗 {sofascore_match['url']}")

                # Scarica stats
                stats_data = None
                for attempt in range(MAX_RETRIES + 1):
                    stats_data = extract_match_stats(driver, sofascore_match['url'], sofascore_match.get('match_id'))
                    if stats_data:
                        matches_cache[cache_key] = (stats_data, sofascore_match)
                        break
                    if attempt < MAX_RETRIES:
                        print(f"         🔄 Tentativo {attempt + 2}...")
                        time.sleep(3)

                if not stats_data:
                    print(f"         ❌ Impossibile estrarre statistiche")
                    report['no_stats'].append((home, away, league, giornata, 'estrazione fallita'))
                    continue

                # Pausa tra partite
                time.sleep(BETWEEN_MATCHES_WAIT + random.uniform(1, 3))

            # Salva (un doc per partita, non per pronostico)
            save_to_db(date_str, pred, stats_data, sofascore_match)
            saved += 1
            report['by_league'][league]['salvate'] += 1
            print(f"         ✅ Salvato")

        # Pausa tra leghe
        time.sleep(2)

    report['saved'] = saved
    return report


def print_final_report(all_reports, start_time):
    """Stampa report finale dettagliato."""
    elapsed = time.time() - start_time
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)

    total_predictions = sum(r['total_predictions'] for r in all_reports)
    total_already = sum(r['already_done'] for r in all_reports)
    total_saved = sum(r['saved'] for r in all_reports)
    all_no_giornata = []
    all_no_round = []
    all_no_match = []
    all_no_stats = []
    league_totals = {}

    for r in all_reports:
        all_no_giornata.extend(r['no_giornata'])
        all_no_round.extend(r['no_round_found'])
        all_no_match.extend(r['no_match_found'])
        all_no_stats.extend(r['no_stats'])
        for league, counts in r['by_league'].items():
            if league not in league_totals:
                league_totals[league] = {'salvate': 0, 'totali': 0}
            league_totals[league]['salvate'] += counts['salvate']
            league_totals[league]['totali'] += counts['totali']

    total_errors = len(all_no_giornata) + len(all_no_round) + len(all_no_match) + len(all_no_stats)

    print(f"\n{'='*70}")
    print(f"{'='*70}")
    print(f"  REPORT FINALE — SCRAPER SOFASCORE POST-MATCH")
    print(f"{'='*70}")
    print(f"  Date processate:    {len(all_reports)}")
    print(f"  Pronostici trovati: {total_predictions}")
    print(f"  Gia presenti:       {total_already}")
    print(f"  Salvate ora:        {total_saved}")
    print(f"  Errori totali:      {total_errors}")
    print(f"  Tempo:              {mins}m {secs}s")
    print(f"{'='*70}")

    # Per lega
    if league_totals:
        print(f"\n  PER LEGA:")
        for league in sorted(league_totals.keys()):
            c = league_totals[league]
            pct = f"{c['salvate']*100//c['totali']}%" if c['totali'] > 0 else '-'
            status = "✅" if c['salvate'] == c['totali'] else "⚠️"
            print(f"    {status} {league:35s}  {c['salvate']:3d}/{c['totali']:<3d}  ({pct})")

    # Errori dettagliati
    if all_no_giornata:
        print(f"\n  GIORNATA NON TROVATA ({len(all_no_giornata)}):")
        for home, away, league in all_no_giornata:
            print(f"    - {home} vs {away} ({league})")

    if all_no_round:
        print(f"\n  ROUND NON TROVATO SU SOFASCORE ({len(all_no_round)}):")
        # Raggruppa per lega
        from collections import Counter
        round_counts = Counter(league for league, _ in all_no_round)
        for league, count in round_counts.most_common():
            rounds = [str(g) for l, g in all_no_round if l == league]
            print(f"    - {league}: round {', '.join(rounds)}")

    if all_no_match:
        print(f"\n  PARTITA NON TROVATA SU SOFASCORE ({len(all_no_match)}):")
        for home, away, league, giornata in all_no_match:
            print(f"    - {home} vs {away} ({league}, Round {giornata})")

    if all_no_stats:
        print(f"\n  STATISTICHE NON ESTRATTE ({len(all_no_stats)}):")
        for home, away, league, giornata, motivo in all_no_stats:
            print(f"    - {home} vs {away} ({league}, Round {giornata}) — {motivo}")

    if not total_errors:
        print(f"\n  ✅ Nessun errore!")

    print(f"\n{'='*70}")

    # Salva report su file log
    log_dir = os.path.join(current_path, 'log')
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'sofascore_post_match_report.json')
    report_data = {
        'timestamp': datetime.now().isoformat(),
        'elapsed_seconds': int(elapsed),
        'dates_processed': len(all_reports),
        'total_predictions': total_predictions,
        'already_done': total_already,
        'saved': total_saved,
        'errors': {
            'no_giornata': [{'home': h, 'away': a, 'league': l} for h, a, l in all_no_giornata],
            'no_round_found': [{'league': l, 'round': g} for l, g in all_no_round],
            'no_match_found': [{'home': h, 'away': a, 'league': l, 'round': g} for h, a, l, g in all_no_match],
            'no_stats': [{'home': h, 'away': a, 'league': l, 'round': g, 'reason': m} for h, a, l, g, m in all_no_stats],
        },
        'by_league': league_totals,
    }
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"  Report salvato in: {log_file}")
    print(f"{'='*70}\n")


def main():
    args = sys.argv[1:]

    # Determina date da processare
    if len(args) >= 3 and args[0] == '--backfill':
        start = datetime.strptime(args[1], "%Y-%m-%d")
        end = datetime.strptime(args[2], "%Y-%m-%d")
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        print(f"📅 Backfill: {len(dates)} giorni ({args[1]} → {args[2]})")
    elif len(args) == 1:
        dates = [args[0]]
    else:
        dates = [datetime.now().strftime("%Y-%m-%d")]

    # Avvia browser
    driver = create_browser()
    all_reports = []
    start_time = time.time()

    try:
        # Chiudi cookie una volta
        driver.get(SOFASCORE_BASE)
        time.sleep(5)
        driver.execute_script('''
            document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root').forEach(e => e.remove());
            document.querySelectorAll('button').forEach(b => {
                if(b.textContent.match(/accept|accett|agree|OK/i)) b.click();
            });
        ''')
        time.sleep(1)

        for date_str in dates:
            report = scrape_date(driver, date_str)
            all_reports.append(report)
    finally:
        driver.quit()
        print("\n🌐 Browser chiuso")

    # Report finale
    print_final_report(all_reports, start_time)


if __name__ == '__main__':
    main()
