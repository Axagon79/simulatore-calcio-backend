"""
sofascore_discover_leagues.py
Scopre gli ID SofaScore per tutte le nostre leghe.

Approccio: prova URL diretti per ogni lega, verificando il titolo della pagina.
Per le leghe con ID noto (da URL confermati), verifica e raccoglie il season_id.
Per le altre, prova ID comuni.

Uso:
    python sofascore_discover_leagues.py
"""

import os, sys, time, re, json
from bs4 import BeautifulSoup

# --- Path setup ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

import undetected_chromedriver as uc

# Le nostre leghe con slug SofaScore e possibili league_id da provare
# Format: (nome_nostro, country, slug_sofascore, [possibili_id])
LEAGUES_TO_DISCOVER = [
    # ITALIA
    ("Serie A", "italy", "serie-a", [23]),
    ("Serie B", "italy", "serie-b", [53]),
    ("Serie C - Girone A", "italy", "serie-c-group-a", [421, 422, 423, 424, 425]),
    ("Serie C - Girone B", "italy", "serie-c-group-b", [421, 422, 423, 424, 425]),
    ("Serie C - Girone C", "italy", "serie-c-group-c", [421, 422, 423, 424, 425]),
    # INGHILTERRA (confermati)
    ("Premier League", "england", "premier-league", [17]),
    ("Championship", "england", "championship", [18]),
    ("League One", "england", "league-one", [24]),
    ("League Two", "england", "league-two", [25]),
    # SPAGNA
    ("La Liga", "spain", "laliga", [8]),
    ("LaLiga 2", "spain", "laliga-2", [54, 55]),
    # GERMANIA
    ("Bundesliga", "germany", "bundesliga", [35]),
    ("2. Bundesliga", "germany", "2-bundesliga", [44, 45, 46]),
    ("3. Liga", "germany", "3-liga", [491, 492, 493, 58, 59, 60]),
    # FRANCIA
    ("Ligue 1", "france", "ligue-1", [34]),
    ("Ligue 2", "france", "ligue-2", [182, 183, 42, 43]),
    # OLANDA
    ("Eredivisie", "netherlands", "eredivisie", [37]),
    ("Eerste Divisie", "netherlands", "eerste-divisie", [131, 132, 133, 38, 39]),
    # PORTOGALLO
    ("Liga Portugal", "portugal", "liga-portugal", [238, 239, 240, 52, 53]),
    ("Liga Portugal 2", "portugal", "liga-portugal-2", [239, 240, 241, 242]),
    # SCOZIA
    ("Scottish Premiership", "scotland", "premiership", [36]),
    ("Scottish Championship", "scotland", "championship", [274, 275, 276]),
    # NORDICI
    ("Allsvenskan", "sweden", "allsvenskan", [40]),
    ("Eliteserien", "norway", "eliteserien", [29]),
    ("Superligaen", "denmark", "superliga", [30, 31]),
    ("Veikkausliiga", "finland", "veikkausliiga", [43, 44]),
    # BELGIO / IRLANDA / TURCHIA
    ("Jupiler Pro League", "belgium", "jupiler-pro-league", [38, 39, 40]),
    ("League of Ireland Premier Division", "republic-of-ireland", "premier-division", [196, 197, 198]),
    ("Süper Lig", "turkey", "super-lig", [52, 53]),
    ("1. Lig", "turkey", "1-lig", [98, 99, 100]),
    # AMERICHE
    ("Brasileirão Serie A", "brazil", "brasileirao-serie-a", [325, 326, 327]),
    ("Primera División", "argentina", "liga-profesional", [155, 156, 11475, 13475]),
    ("Major League Soccer", "usa", "mls", [242, 243, 244]),
    ("Liga MX", "mexico", "liga-mx", [11620, 11621, 352, 353]),
    # ASIA
    ("J1 League", "japan", "j1-league", [196, 197, 198, 34, 284]),
    ("Saudi Pro League", "saudi-arabia", "saudi-pro-league", [955, 956, 957]),
]

OUTPUT_FILE = os.path.join(current_path, "log", "sofascore_leagues_map.json")


def create_browser():
    """Crea browser Chrome headless."""
    print("🌐 Avvio browser Chrome...")
    options = uc.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    try:
        driver = uc.Chrome(options=options, headless=True)
    except Exception:
        try:
            import winreg
            key_path = r"Software\Google\Chrome\BLBeacon"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                ver, _ = winreg.QueryValueEx(key, "version")
                version_main = int(ver.split('.')[0])
            new_options = uc.ChromeOptions()
            new_options.add_argument("--headless")
            new_options.add_argument("--no-sandbox")
            new_options.add_argument("--disable-dev-shm-usage")
            new_options.add_argument("--window-size=1920,1080")
            driver = uc.Chrome(options=new_options, headless=True, version_main=version_main)
        except Exception as e2:
            print(f"❌ Impossibile avviare Chrome: {e2}")
            sys.exit(1)

    print("✅ Browser avviato\n")
    return driver


def try_league_url(driver, country, slug, league_id):
    """
    Prova un URL di lega SofaScore e verifica se è valida.
    Ritorna dict con info se trovata, None altrimenti.
    """
    url = f"https://www.sofascore.com/football/tournament/{country}/{slug}/{league_id}"
    driver.get(url)
    time.sleep(4)

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    title = soup.find('title')
    title_text = title.get_text() if title else ''

    # Se la pagina è valida, il titolo contiene il nome della lega
    # Se non valida, redirect o pagina 404
    if 'not found' in title_text.lower() or '404' in title_text:
        return None

    # Cerca il season_id nell'URL corrente o nei link
    current_url = driver.current_url
    season_match = re.search(r'#id:(\d+)', current_url)
    season_id = int(season_match.group(1)) if season_match else None

    # Se non c'è nel URL, cerca nei link della pagina
    if not season_id:
        links = soup.find_all('a', href=True)
        for a in links:
            href = a.get('href', '')
            sm = re.search(rf'/tournament/{country}/{slug}/{league_id}#id:(\d+)', href)
            if sm:
                season_id = int(sm.group(1))
                break

    # Se ancora non trovato, cerca nel testo/attributi della pagina
    if not season_id:
        page_text = driver.page_source
        season_matches = re.findall(r'"seasonId"\s*:\s*(\d+)', page_text)
        if season_matches:
            season_id = int(season_matches[0])

    # Verifica che il titolo abbia senso (non sia una pagina generica)
    if title_text and 'Sofascore' in title_text:
        league_name_from_title = title_text.split(' table')[0].split(' |')[0].strip()
        return {
            'title': league_name_from_title,
            'league_id': league_id,
            'season_id': season_id,
            'url': url + (f'#id:{season_id}' if season_id else ''),
        }

    return None


def discover_all():
    """Scopre tutte le leghe."""
    driver = create_browser()
    results = {}
    not_found = []

    try:
        # Chiudi cookie una volta
        driver.get("https://www.sofascore.com")
        time.sleep(5)
        driver.execute_script('''
            document.querySelectorAll('.fc-dialog-overlay, .fc-consent-root').forEach(e => e.remove());
            document.querySelectorAll('button').forEach(b => {
                if(b.textContent.match(/accept|accett|agree|OK/i)) b.click();
            });
        ''')
        time.sleep(1)

        for our_name, country, slug, possible_ids in LEAGUES_TO_DISCOVER:
            print(f"🔍 {our_name} ({country}/{slug})...")
            found = False

            for lid in possible_ids:
                result = try_league_url(driver, country, slug, lid)
                if result:
                    results[our_name] = {
                        'country': country,
                        'slug': slug,
                        'league_id': result['league_id'],
                        'season_id': result['season_id'],
                        'sofascore_name': result['title'],
                        'url': result['url'],
                    }
                    print(f"   ✅ ID={result['league_id']} | season={result['season_id']} | {result['title']}")
                    found = True
                    break
                else:
                    print(f"   ❌ ID={lid} non valido")

            if not found:
                # Ultimo tentativo: prova slug diversi
                alt_slugs = []
                if 'serie-c' in slug:
                    alt_slugs = [slug.replace('group', 'girone'), slug.replace('-', '')]
                if alt_slugs:
                    for alt_slug in alt_slugs:
                        for lid in possible_ids:
                            result = try_league_url(driver, country, alt_slug, lid)
                            if result:
                                results[our_name] = {
                                    'country': country,
                                    'slug': alt_slug,
                                    'league_id': result['league_id'],
                                    'season_id': result['season_id'],
                                    'sofascore_name': result['title'],
                                    'url': result['url'],
                                }
                                print(f"   ✅ (alt slug) ID={result['league_id']} | season={result['season_id']} | {result['title']}")
                                found = True
                                break
                        if found:
                            break

            if not found:
                not_found.append((our_name, country, slug))
                print(f"   ⚠️ NON TROVATA — serve verifica manuale")

            time.sleep(1)  # Pausa tra richieste

    finally:
        driver.quit()
        print("\n🌐 Browser chiuso")

    return results, not_found


def save_results(leagues_map):
    """Salva la mappa in JSON."""
    log_dir = os.path.dirname(OUTPUT_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(leagues_map, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Mappa salvata in: {OUTPUT_FILE}")


def main():
    print("=" * 60)
    print("🔍 SOFASCORE LEAGUE DISCOVERY")
    print(f"   {len(LEAGUES_TO_DISCOVER)} leghe da scoprire")
    print("=" * 60)

    leagues_map, not_found = discover_all()

    if leagues_map:
        save_results(leagues_map)

        print(f"\n{'='*60}")
        print(f"📊 RISULTATO: {len(leagues_map)}/{len(LEAGUES_TO_DISCOVER)} leghe trovate")
        print(f"{'='*60}")

        # Stampa dizionario Python
        print("\nSOFASCORE_LEAGUES = {")
        for name, info in sorted(leagues_map.items()):
            sid = info['season_id'] if info['season_id'] else 'None  # DA VERIFICARE'
            print(f'    "{name}": {{"country": "{info["country"]}", "slug": "{info["slug"]}", "league_id": {info["league_id"]}, "season_id": {sid}}},')
        print("}")

    if not_found:
        print(f"\n⚠️ {len(not_found)} leghe non trovate:")
        for name, country, slug in not_found:
            print(f"   ❌ {name} — prova su sofascore.com/football/tournament/{country}/...")


if __name__ == '__main__':
    main()
