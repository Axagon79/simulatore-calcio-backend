import os
import sys
import time
import random
import re
from datetime import datetime
from bs4 import BeautifulSoup
import requests

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

COLLECTION_NAME = "h2h_by_round"


# ⚠️ IMPOSTAZIONE DI SICUREZZA ⚠️
# True = SOLO SIMULAZIONE (Stampa a video TUTTI I DATI, NON scrive nel DB)
# False = SCRITTURA REALE (Modifica il DB)
DRY_RUN = False 

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

LEAGUES_TM = [
    # ITALIA
    {"name": "Serie A", "url": f"https://www.transfermarkt.it/serie-a/gesamtspielplan/wettbewerb/IT1"},
    {"name": "Serie B", "url": f"https://www.transfermarkt.it/serie-b/gesamtspielplan/wettbewerb/IT2"},
    {"name": "Serie C - Girone A", "url": f"https://www.transfermarkt.it/serie-c-girone-a/gesamtspielplan/wettbewerb/IT3A"},
    {"name": "Serie C - Girone B", "url": f"https://www.transfermarkt.it/serie-c-girone-b/gesamtspielplan/wettbewerb/IT3B"},
    {"name": "Serie C - Girone C", "url": f"https://www.transfermarkt.it/serie-c-girone-c/gesamtspielplan/wettbewerb/IT3C"},
    
    # EUROPA TOP
    {"name": "Premier League", "url": f"https://www.transfermarkt.it/premier-league/gesamtspielplan/wettbewerb/GB1"},
    {"name": "La Liga", "url": f"https://www.transfermarkt.it/laliga/gesamtspielplan/wettbewerb/ES1"},
    {"name": "Bundesliga", "url": f"https://www.transfermarkt.it/bundesliga/gesamtspielplan/wettbewerb/L1"},
    {"name": "Ligue 1", "url": f"https://www.transfermarkt.it/ligue-1/gesamtspielplan/wettbewerb/FR1"},
    {"name": "Eredivisie", "url": f"https://www.transfermarkt.it/eredivisie/gesamtspielplan/wettbewerb/NL1"},
    {"name": "Liga Portugal", "url": f"https://www.transfermarkt.it/liga-nos/gesamtspielplan/wettbewerb/PO1"},
    
    # 🆕 EUROPA SERIE B
    {"name": "Championship", "url": f"https://www.transfermarkt.it/championship/gesamtspielplan/wettbewerb/GB2"},
    {"name": "LaLiga 2", "url": f"https://www.transfermarkt.it/laliga2/gesamtspielplan/wettbewerb/ES2"},
    {"name": "2. Bundesliga", "url": f"https://www.transfermarkt.it/2-bundesliga/gesamtspielplan/wettbewerb/L2"},
    {"name": "Ligue 2", "url": f"https://www.transfermarkt.it/ligue-2/gesamtspielplan/wettbewerb/FR2"},
    
    # 🆕 EUROPA NORDICI + EXTRA
    {"name": "Scottish Premiership", "url": f"https://www.transfermarkt.it/premiership/gesamtspielplan/wettbewerb/SC1"},
    {"name": "Allsvenskan", "url": f"https://www.transfermarkt.it/allsvenskan/gesamtspielplan/wettbewerb/SE1"},
    {"name": "Eliteserien", "url": f"https://www.transfermarkt.it/eliteserien/gesamtspielplan/wettbewerb/NO1"},
    {"name": "Superligaen", "url": f"https://www.transfermarkt.it/superligaen/gesamtspielplan/wettbewerb/DK1"},
    {"name": "Jupiler Pro League", "url": f"https://www.transfermarkt.it/jupiler-pro-league/gesamtspielplan/wettbewerb/BE1"},
    {"name": "Süper Lig", "url": f"https://www.transfermarkt.it/super-lig/gesamtspielplan/wettbewerb/TR1"},
    {"name": "League of Ireland Premier Division", "url": f"https://www.transfermarkt.it/league-of-ireland-premier-division/gesamtspielplan/wettbewerb/IR1"},
    
    # 🆕 AMERICHE
    {"name": "Brasileirão Serie A", "url": f"https://www.transfermarkt.it/campeonato-brasileiro-serie-a/gesamtspielplan/wettbewerb/BRA1"},
    {"name": "Primera División", "url": f"https://www.transfermarkt.it/torneo-inicial/gesamtspielplan/wettbewerb/ARG1"},
    {"name": "Major League Soccer", "url": f"https://www.transfermarkt.it/major-league-soccer/gesamtspielplan/wettbewerb/MLS1"},
    
    # 🆕 ASIA
    {"name": "J1 League", "url": f"https://www.transfermarkt.it/j1-100-year-vision-league/gesamtspielplan/pokalwettbewerb/J1YV"},
]

def parse_tm_date(date_str):
    if not date_str: return None
    clean_str = re.sub(r'[a-zA-Z]{3}\s+', '', date_str).strip()
    match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{2,4})', clean_str)
    if match:
        d, m, y = match.groups()
        if len(y) == 2: y = "20" + y 
        return f"{y}-{m}-{d}"
    return None

def scrape_tm_calendar_v8():
    
    print(f"🛠️  MODALITÀ DRY_RUN: {'ATTIVA (Nessuna scrittura)' if DRY_RUN else 'DISATTIVA (Scrittura su DB)'}")
    
    col = db[COLLECTION_NAME]
    
    for league in LEAGUES_TM:
        print(f"\n🌍 Lega: {league['name']}")
        try:
            time.sleep(random.uniform(3, 5))
            resp = requests.get(league['url'], headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.content, "html.parser")
            
            headers = soup.find_all("div", class_="content-box-headline")
            print(f"   Giornate trovate: {len(headers)}")
            
            saved_count = 0
            
            for header in headers:
                round_name = header.get_text(strip=True)
                if "Giornata" not in round_name and "Turno" not in round_name: continue
                
                table = header.find_next("table")
                if not table: continue
                
                matches = []
                rows = table.find_all("tr")
                
                # --- DOPPIA MEMORIA ---
                last_seen_date_str = None
                last_seen_time_str = "00:00" # Default iniziale
                
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) < 5: continue 
                    
                    # 1. DATA (con memoria)
                    raw_date = cells[0].get_text(strip=True)
                    if raw_date:
                        parsed_date = parse_tm_date(raw_date)
                        if parsed_date: last_seen_date_str = parsed_date

                    # 2. ORARIO (con memoria)
                    raw_time = cells[1].get_text(strip=True)
                    time_found = re.search(r'(\d{1,2}:\d{2})', raw_time)
                    
                    match_time = "00:00"
                    if time_found:
                        match_time = time_found.group(1)
                        last_seen_time_str = match_time
                    else:
                        if last_seen_date_str:
                            match_time = last_seen_time_str

                    # 3. OGGETTO COMPLETO
                    date_obj = None
                    if last_seen_date_str:
                        full_dt_str = f"{last_seen_date_str} {match_time}"
                        try:
                            date_obj = datetime.strptime(full_dt_str, "%Y-%m-%d %H:%M")
                        except: pass

                    # Squadre
                    team_links = []
                    for td in cells:
                        a_tag = td.find("a")
                        if a_tag and a_tag.get("title"): 
                            if "spielbericht" in a_tag.get("href", ""): continue 
                            if "datum" in a_tag.get("href", ""): continue
                            team_links.append(a_tag.get_text(strip=True))
                    
                    if len(team_links) < 2: continue
                    
                    home = None
                    away = None
                    home_td = row.find("td", class_="text-right")
                    if home_td: home = home_td.get_text(strip=True)
                    no_border_tds = row.find_all("td", class_="no-border-links")
                    if no_border_tds: away = no_border_tds[-1].get_text(strip=True)
                    if not home or not away:
                        home = team_links[0]
                        away = team_links[-1]
                    home = re.sub(r'\(\d+\.\)', '', home).strip()
                    away = re.sub(r'\(\d+\.\)', '', away).strip()
                    
                    # Risultato
                    score = None
                    status = "Scheduled"
                    res_link = row.find("a", class_="ergebnis-link")
                    if res_link:
                        txt = res_link.get_text(strip=True)
                        if ":" in txt:
                            score = txt
                            status = "Finished"
                    
                    if score:
                        if "annull" in score.lower() or "post" in score.lower():
                            status = "Postponed"
                            score = None
                    
                    matches.append({
                        "home": home, 
                        "away": away, 
                        "status": status, 
                        "real_score": score,
                        "date_obj": date_obj,     
                        "match_time": match_time, 
                        "h2h_data": None
                    })

                if matches:
                    save_round(col, league['name'], round_name, matches)
                    saved_count += 1
            
            print(f"   ✅ Processate {saved_count} giornate.")

        except Exception as e:
            print(f"   ❌ Errore: {e}")

def save_round(col, league, round_name, matches):
    safe_round = round_name.replace(".", "").replace(" ", "")
    safe_league = league.replace(" ", "")
    doc_id = f"{safe_league}_{safe_round}"
    
    # 1. Recupero il documento esistente per fare il MERGE
    existing_doc = col.find_one({"_id": doc_id})
    
    # 2. Logica di Merge Intelligente (per NOME SQUADRE)
    if existing_doc:
        old_matches_map = {
            f"{m['home'].strip()} vs {m['away'].strip()}": m 
            for m in existing_doc.get("matches", [])
        }

        for new_match in matches:
            match_key = f"{new_match['home'].strip()} vs {new_match['away'].strip()}"
            
            if match_key in old_matches_map:
                old_match = old_matches_map[match_key]
                # Copiamo i dati vecchi preziosi nel nuovo oggetto
                for key in old_match:
                    # FIX: h2h_data NON è nella lista nera, quindi viene copiato (preservando Lucifero)
                    if key not in ["home", "away", "status", "real_score", "date_obj", "match_time"]:
                        new_match[key] = old_match[key]

    # 3. BLOCCO DRY RUN (CON VERIFICA COMPLETA DI TUTTI I CAMPI)
    if DRY_RUN:
        print(f"\n   [DRY RUN 🛡️] Documento: {doc_id}")
        print(f"   [DRY RUN 🛡️] Match trovati: {len(matches)}")
        
        # Mostra un match di esempio COMPLETO
        if matches:
            m = matches[0]
            print(f"\n   [DRY RUN] CONTROLLO CAMPI PRIMO MATCH ({m.get('home')} vs {m.get('away')}):")
            
            # Helper per cercare i dati sia alla radice che dentro h2h_data
            h2h_obj = m.get('h2h_data') if isinstance(m.get('h2h_data'), dict) else {}
            
            def check_field(field_name):
                # Cerca prima nella root
                val = m.get(field_name)
                # Se non c'è, cerca dentro h2h_data
                if val is None:
                    val = h2h_obj.get(field_name)
                return f"{val} {'✅' if val is not None else '❌'}"

            # --- CAMPI BASE (Scraper) ---
            print(f"      home: {m.get('home')} ✅")
            print(f"      away: {m.get('away')} ✅")
            print(f"      real_score: {m.get('real_score')} ✅")
            print(f"      h2h_data (Oggetto): {type(m.get('h2h_data'))} {'✅' if m.get('h2h_data') else '❌'}")
            
            # --- CAMPI PRESERVATI (Merge) - LISTA COMPLETA ---
            print(f"\n      --- DATI RECUPERATI (Lucifero, BVS, Classifica) ---")
            print(f"      home_tm_id: {check_field('home_tm_id')}")
            print(f"      away_tm_id: {check_field('away_tm_id')}")
            print(f"      h2h_last_updated: {check_field('h2h_last_updated')}")
            print(f"      lucifero_home: {check_field('lucifero_home')}")
            print(f"      lucifero_away: {check_field('lucifero_away')}")
            print(f"      lucifero_trend_home: {check_field('lucifero_trend_home')}")
            print(f"      lucifero_trend_away: {check_field('lucifero_trend_away')}")
            print(f"      bvs_advice: {check_field('bvs_advice')}")
            print(f"      bvs_index: {check_field('bvs_index')}")
            print(f"      bvs_away: {check_field('bvs_away')}")
            print(f"      bvs_match_index: {check_field('bvs_match_index')}")
            print(f"      classification: {check_field('classification')}")
            print(f"      is_linear: {check_field('is_linear')}")
            print(f"      diff_perc: {check_field('diff_perc')}")
            print(f"      gap_reale: {check_field('gap_reale')}")
            print(f"      tip_sign: {check_field('tip_sign')}")
            print(f"      tip_market: {check_field('tip_market')}")
            print(f"      trust_home_letter: {check_field('trust_home_letter')}")
            print(f"      trust_away_letter: {check_field('trust_away_letter')}")
            print(f"      last_bvs_update: {check_field('last_bvs_update')}")
            print(f"      home_rank: {check_field('home_rank')}")
            print(f"      home_points: {check_field('home_points')}")
            print(f"      away_rank: {check_field('away_rank')}")
            print(f"      away_points: {check_field('away_points')}")
            print(f"      odds: {check_field('odds')}")
        
        # 🛑 STOP! NON PROCEDERE ALLA SCRITTURA 🛑
        return 

    # 4. SALVATAGGIO REALE (Solo se DRY_RUN = False)
    col.update_one({"_id": doc_id}, {
        "$set": {
            "league": league, 
            "round_name": round_name, 
            
            "matches": matches, 
            "last_updated": datetime.now()
        }
    }, upsert=True)

if __name__ == "__main__":
    scrape_tm_calendar_v8()