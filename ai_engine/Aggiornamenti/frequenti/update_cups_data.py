"""
UPDATE CUPS DATA - Script Completo Aggiornamento Coppe Europee

Scarica e aggiorna:
1. Valore Rosa (Transfermarkt) - statico
2. ELO Rating (ClubElo API) - dinamico
3. Partite e Quote (Nowgoal) - dinamico

Usage:
    python update_cups_data.py              # Aggiorna tutto (default)
    python update_cups_data.py --competition UCL   # Solo Champions League
    python update_cups_data.py --competition UEL   # Solo Europa League
"""

import requests
from bs4 import BeautifulSoup
import sys
import os
import time
import random
import argparse
import re
from io import StringIO
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
from fake_useragent import UserAgent

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    print("⚠️  Selenium non installato. Funzionalità partite/quote non disponibile.")
    SELENIUM_AVAILABLE = False

# Importa configurazione DB
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)


from config import db

# ==================== CONFIGURAZIONE ====================

COMPETITIONS = {
    "UCL": {
        "name": "Champions League",
        "teams_collection": "teams_champions_league",
        "matches_collection": "matches_champions_league",
        "nowgoal_url": "https://football.nowgoal26.com/cupmatch/103",
        "season": "2025-2026"
    },
    "UEL": {
        "name": "Europa League",
        "teams_collection": "teams_europa_league",
        "matches_collection": "matches_europa_league",
        "nowgoal_url": "https://football.nowgoal26.com/cupmatch/113",
        "season": "2025-2026"
    }
}

# Range per normalizzazione (da aggiornare con dati reali)
ELO_MIN = 1300  # Da ClubElo Champions
ELO_MAX = 2047  # Da ClubElo Champions
BUFFER = 0.2    # 20% buffer per normalizzazione

# ==================== FUNZIONI NORMALIZZAZIONE ====================

def normalize_with_buffer(value, min_val, max_val, buffer=0.2):
    """
    Normalizza valore con buffer su scala 5-25
    
    Args:
        value: valore da normalizzare
        min_val: valore minimo del range
        max_val: valore massimo del range
        buffer: percentuale di buffer (default 20%)
    
    Returns:
        valore normalizzato tra 5 e 25
    """
    buffer_low = min_val * (1 - buffer)
    buffer_high = max_val * (1 + buffer)
    
    normalized = 5 + ((value - buffer_low) / (buffer_high - buffer_low)) * 20
    
    # Clamp tra 5 e 25
    return max(5, min(25, normalized))


def clean_money_value(raw_text):
    """
    Converte stringa Transfermarkt in valore numerico
    Esempi: "€50.00m" -> 50000000, "€1.20bn" -> 1200000000
    """
    raw_text = raw_text.replace("€", "").strip().lower()
    
    multiplier = 1
    if "bn" in raw_text or "mld" in raw_text or "bld" in raw_text:
        multiplier = 1_000_000_000
        raw_text = raw_text.replace("bn", "").replace("mld", "").replace("bld", "").strip()
    elif "mln" in raw_text:  # PRIMA mln (specifico)
        multiplier = 1_000_000
        raw_text = raw_text.replace("mln", "").strip()
    elif "m" in raw_text:  # POI m (generico)
        multiplier = 1_000_000
        raw_text = raw_text.replace("m", "").strip()
    elif "k" in raw_text:
        multiplier = 1_000
        raw_text = raw_text.replace("k", "").strip()
    
    try:
        value = float(raw_text.replace(",", "."))
        return int(value * multiplier)
    except:
        return 0


# ==================== 1. VALORE ROSA TRANSFERMARKT ====================

def update_transfermarkt_values(competition_code):
    """
    Aggiorna valore rosa per tutte le squadre di una competizione
    Scarica dalla pagina partecipanti (1 sola richiesta invece di 36!)
    """
    config = COMPETITIONS[competition_code]
    collection = db[config['teams_collection']]
    
    print(f"\n💰 VALORE ROSA - {config['name']}")
    print("=" * 70)
    
    # URL pagina partecipanti Transfermarkt
    if competition_code == "UCL":
        url = "https://www.transfermarkt.it/uefa-champions-league/teilnehmer/pokalwettbewerb/CL/saison_id/2025"
    elif competition_code == "UEL":
        url = "https://www.transfermarkt.it/uefa-europa-league/teilnehmer/pokalwettbewerb/EL/saison_id/2025"
    else:
        print("   ❌ Competizione non supportata")
        return
    
    print(f"   📡 Scaricamento da: {url}\n")
    
    ua = UserAgent()
    headers = {"User-Agent": ua.random}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"   ❌ HTTP {response.status_code}")
            return
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Trova la tabella
        table = soup.find("table", class_="items")
        
        if not table:
            print("   ❌ Tabella non trovata")
            return
        
        rows = table.find("tbody").find_all("tr")
        
        print(f"   📊 Trovate {len(rows)} squadre\n")
        
        values_list = []
        updated = 0
        
        for i, row in enumerate(rows, 1):
            try:
                # Nome squadra (dalla cella con class="hauptlink")
                name_cell = row.find("td", class_="hauptlink")
                if not name_cell:
                    continue
                
                team_name = name_cell.find("a").get("title", "").strip()
                
                # Valore di mercato totale (penultima colonna - class="rechts")
                value_cells = row.find_all("td", class_="rechts")
                
                if len(value_cells) < 2:
                    continue
                
                # Il valore totale è la penultima cella
                raw_value = value_cells[-2].get_text(strip=True)
                
                if "€" not in raw_value:
                    continue
                
                # Converti valore
                value = clean_money_value(raw_value)
                
                if value == 0:
                    print(f"   {i:2}. ⚠️  {team_name:<30} | Valore non valido: {raw_value}")
                    continue
                
                values_list.append(value)
                
                # Aggiorna DB (cerca per nome)
                result = collection.update_one(
                    {"name": team_name, "status": "active"},
                    {
                        "$set": {
                            "valore_rosa_transfermarkt": value,
                            "valore_rosa_updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                    }
                )
                
                if result.matched_count > 0:
                    updated += 1
                    print(f"   {i:2}. ✅ {team_name:<30} | €{value:,}")
                else:
                    # Prova a cercare negli alias o case-insensitive
                    team_doc = collection.find_one({
                        "$or": [
                            {"aliases": team_name},
                            {"name": {"$regex": f"^{re.escape(team_name)}$", "$options": "i"}}
                        ],
                        "status": "active"
                    })
                    
                    if team_doc:
                        collection.update_one(
                            {"_id": team_doc["_id"]},
                            {
                                "$set": {
                                    "valore_rosa_transfermarkt": value,
                                    "valore_rosa_updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                                }
                            }
                        )
                        updated += 1
                        print(f"   {i:2}. ✅ {team_name:<30} | €{value:,} (alias match)")
                    else:
                        print(f"   {i:2}. ⚠️  {team_name:<30} | €{value:,} (non trovata in DB)")
                
            except Exception as e:
                print(f"   {i:2}. ❌ Errore riga: {e}")
                continue
        
        # Calcola min-max per normalizzazione
        if values_list:
            min_value = min(values_list)
            max_value = max(values_list)
            
            print(f"\n   📈 Range Valori Rosa:")
            print(f"      MIN: €{min_value:,}")
            print(f"      MAX: €{max_value:,}")
            print(f"   ✅ Aggiornate: {updated}/{len(values_list)}")
        
    except Exception as e:
        print(f"   ❌ Errore: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n   ✅ Completato {config['name']}")


def scrape_transfermarkt_value(transfermarkt_id):
    """
    DEPRECATA - Non più usata, tenuta solo per riferimento
    """
    pass


# ==================== 2. ELO RATING (ClubElo API) ====================

def get_elo_ratings_today():
    """
    Scarica rating ELO di tutte le squadre da ClubElo API
    
    Returns:
        DataFrame con colonne: Club, Elo, Country, Level
    """
    today = time.strftime("%Y-%m-%d")
    url = f"http://api.clubelo.com/{today}"
    
    print(f"\n⚡ ELO RATING - ClubElo API")
    print("=" * 70)
    print(f"   📡 Scaricando dati da: {url}\n")
    
    try:
        response = requests.get(url, timeout=30)
        
        if response.status_code != 200:
            print(f"   ❌ HTTP {response.status_code}")
            return None
        
        # Converti CSV in DataFrame
        df = pd.read_csv(StringIO(response.text))
        
        print(f"   ✅ Scaricate {len(df)} squadre con ELO")
        
        return df
        
    except Exception as e:
        print(f"   ❌ Errore: {e}")
        return None


def match_team_to_elo(team_name, elo_df, team_aliases=None):
    """
    Trova il rating ELO di una squadra nel DataFrame ClubElo
    
    Prova diversi match:
    0. Alias dal database (se forniti)
    1. Nome esatto
    2. Nome case-insensitive
    3. Contiene nome
    4. Nome contiene Club
    
    Args:
        team_name: nome squadra da cercare
        elo_df: DataFrame con dati ClubElo
        team_aliases: lista di alias dalla collezione MongoDB (opzionale)
        
    Returns:
        elo_rating (int) o None
    """
    if elo_df is None or elo_df.empty:
        return None
    
    # 0. Prova con gli alias dal database
    if team_aliases:
        for alias in team_aliases:
            # Match esatto con alias
            match = elo_df[elo_df['Club'] == alias]
            if not match.empty:
                return int(match.iloc[0]['Elo'])
            # Match case-insensitive con alias
            match = elo_df[elo_df['Club'].str.lower() == alias.lower()]
            if not match.empty:
                return int(match.iloc[0]['Elo'])
    
    # 1. Match esatto con nome principale
    match = elo_df[elo_df['Club'] == team_name]
    if not match.empty:
        return int(match.iloc[0]['Elo'])
    
    # 2. Match case-insensitive con nome principale
    match = elo_df[elo_df['Club'].str.lower() == team_name.lower()]
    if not match.empty:
        return int(match.iloc[0]['Elo'])
    
    # 3. Contiene (partial match)
    match = elo_df[elo_df['Club'].str.contains(team_name, case=False, na=False, regex=False)]
    if not match.empty:
        return int(match.iloc[0]['Elo'])
    
    # 4. Team name contiene Club name
    for _, row in elo_df.iterrows():
        if row['Club'].lower() in team_name.lower():
            return int(row['Elo'])
    
    return None


def update_elo_ratings(competition_code, elo_df):
    """
    Aggiorna ELO rating per tutte le squadre di una competizione
    Usa gli alias dal database per migliorare il matching
    """
    config = COMPETITIONS[competition_code]
    collection = db[config['teams_collection']]
    
    print(f"\n⚡ ELO UPDATE - {config['name']}")
    print("=" * 70)
    
    teams = list(collection.find({"status": "active", "season": config['season']}))
    
    print(f"   📊 Aggiornamento {len(teams)} squadre\n")
    
    updated = 0
    not_found = 0
    
    for i, team in enumerate(teams, 1):
        team_name = team['name']
        team_aliases = team.get('aliases', [])  # Legge gli alias dal DB
        
        print(f"   {i:2}. {team_name:<30} | ", end="", flush=True)
        
        # Cerca ELO (passando gli alias)
        elo = match_team_to_elo(team_name, elo_df, team_aliases)
        
        if elo:
            # Aggiorna DB
            collection.update_one(
                {"_id": team['_id']},
                {
                    "$set": {
                        "elo_rating": elo,
                        "elo_source": "clubelo.com",
                        "elo_updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                }
            )
            
            print(f"ELO: {elo}")
            updated += 1
        else:
            print(f"⚠️  ELO non trovato")
            not_found += 1
    
    print(f"\n   ✅ Aggiornate: {updated}")
    print(f"   ⚠️  Non trovate: {not_found}")


# ==================== 3. CALCOLO RATING BASE ====================

def calculate_rating_base(competition_code, rosa_min, rosa_max):
    """
    Calcola rating base (20% Rosa + 80% ELO) per tutte le squadre
    """
    config = COMPETITIONS[competition_code]
    collection = db[config['teams_collection']]
    
    print(f"\n🎯 RATING BASE - {config['name']}")
    print("=" * 70)
    
    teams = list(collection.find({"status": "active", "season": config['season']}))
    
    print(f"   📊 Calcolo rating per {len(teams)} squadre\n")
    
    for i, team in enumerate(teams, 1):
        team_name = team['name']
        valore_rosa = team.get('valore_rosa_transfermarkt', 0)
        elo = team.get('elo_rating', 0)
        
        if valore_rosa == 0 or elo == 0:
            print(f"   {i:2}. ⚠️  {team_name:<30} | Dati mancanti")
            continue
        
        # Normalizza
        rosa_norm = normalize_with_buffer(valore_rosa, rosa_min, rosa_max, BUFFER)
        elo_norm = normalize_with_buffer(elo, ELO_MIN, ELO_MAX, BUFFER)
        
        # Calcola componenti
        componente_rosa = rosa_norm * 0.2
        componente_elo = elo_norm * 0.8
        total_base = componente_rosa + componente_elo
        
        # Aggiorna DB
        collection.update_one(
            {"_id": team['_id']},
            {
                "$set": {
                    "rating_base": {
                        "componente_rosa": round(componente_rosa, 2),
                        "componente_elo": round(componente_elo, 2),
                        "total_base": round(total_base, 2)
                    },
                    "rating_updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            }
        )
        
        print(f"   {i:2}. ✅ {team_name:<30} | Rating: {total_base:.2f}")
    
    print(f"\n   ✅ Completato {config['name']}")


# ==================== 4. PARTITE E QUOTE (NOWGOAL) ====================

# ==================== 4. PARTITE E QUOTE (NOWGOAL) ====================

def normalize_team_name(name: str) -> str:
    """Normalizza nome squadra per matching"""
    if not name:
        return ""
    
    name = name.lower().strip()
    
    # Rimuovi caratteri speciali
    replacements = {
        "ü": "u", "ö": "o", "é": "e", "è": "e", "à": "a",
        "ñ": "n", "ã": "a", "ç": "c", "á": "a", "í": "i",
        "ó": "o", "ú": "u", "ê": "e", "ô": "o", "â": "a",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    
    # Rimuovi prefissi/suffissi comuni
    prefixes = ["fc ", "cf ", "ac ", "as ", "sc ", "us "]
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
    return name.strip()


def extract_odds_from_row(row_text: str) -> Optional[Dict]:
    """
    Estrae quote (home, draw, away) da una riga HTML di Nowgoal
    
    Formato tipico: "... 1.80 3.50 4.20 ..."
    """
    # Pattern per trovare 3 numeri decimali consecutivi (quote)
    # Cerca pattern tipo: 1.50 3.20 5.00
    pattern = r'(\d+\.\d{2})\s+(\d+\.\d{2})\s+(\d+\.\d{2})'
    
    matches = re.findall(pattern, row_text)
    
    if matches:
        # Prendi il primo match (di solito le quote principali)
        home, draw, away = matches[0]
        
        return {
            "home": float(home),
            "draw": float(draw),
            "away": float(away)
        }
    
    return None


def parse_match_result(row, row_text: str) -> Optional[Dict]:
    """
    Estrae il risultato di una partita se già giocata
    Cerca nella cella con class="point"
    """
    # Se row è una stringa, non possiamo fare il parsing HTML
    if isinstance(row, str):
        return None
    
    # Cerca la cella del risultato (ha class="point")
    score_cell = row.find("div", class_="point")
    
    if not score_cell:
        return None
    
    # Estrai i numeri dai tag <font>
    fonts = score_cell.find_all("font")
    
    if len(fonts) >= 2:
        try:
            # Primo <font> = gol casa (es: "0-")
            home_text = fonts[0].get_text(strip=True).replace("-", "")
            # Secondo <font> = gol trasferta (es: "2")
            away_text = fonts[1].get_text(strip=True).replace("-", "")
            
            home_score = int(home_text)
            away_score = int(away_text)
            
            return {
                "home_score": home_score,
                "away_score": away_score
            }
        except (ValueError, IndexError):
            return None
    
    return None


def scrape_nowgoal_matches(competition_code):
    """
    Scarica partite e quote da Nowgoal usando Selenium
    """
    if not SELENIUM_AVAILABLE:
        print("\n   ❌ Selenium non disponibile. Installa con: pip install selenium webdriver-manager")
        return
    
    config = COMPETITIONS[competition_code]
    
    print(f"\n⚽ PARTITE & QUOTE - {config['name']}")
    print("=" * 70)
    print(f"   📡 URL: {config['nowgoal_url']}\n")
    
    # Setup Chrome headless
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    
    ua = UserAgent()
    chrome_options.add_argument(f"user-agent={ua.random}")
    
    driver = None
    matches_data = []
    
    try:
        print("   🌐 Avvio Chrome...")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        
        print("   📥 Caricamento pagina...")
        driver.get(config['nowgoal_url'])
        
        # Aspetta che la tabella si carichi
        wait = WebDriverWait(driver, 20)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        
        time.sleep(3)  # Tempo extra per JavaScript
        
        print("   🔍 Parsing HTML...\n")
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Trova la tabella principale con le partite
        # Nowgoal usa <table class="items">
        table = soup.find("table", id="Table3")
        
        if not table:
            print("   ❌ Tabella partite non trovata")
            return
        
        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
        
        print(f"   📊 Trovate {len(rows)} righe\n")
        
        for i, row in enumerate(rows, 1):
            try:
                # Estrai testo completo della riga
                row_text = row.get_text(" ", strip=True)
                
                # Cerca celle con nomi squadre
                cells = row.find_all("td")
                
                if len(cells) < 3:
                    continue
                
                # Cerca data/ora (di solito prima colonna)
                # Cerca la cella con name="timeData"
                time_cell = row.find("td", attrs={"name": "timeData"})
                if time_cell:
                    # Prende il testo visibile e sostituisce <br> con spazio
                    date_text = time_cell.get_text(separator=" ", strip=True)
                    date_cell = date_text  # Es: "16-09-2025 17:45"
                else:
                    date_cell = None
                
                # Cerca nome squadre (di solito hanno class="team" o link)
                team_links = row.find_all("a", href=re.compile(r"/team/"))
                
                if len(team_links) < 2:
                    continue
                
                home_team = team_links[0].get_text(strip=True)
                away_team = team_links[1].get_text(strip=True)
                
                if not home_team or not away_team:
                    continue
                
                # Estrai quote
                odds = extract_odds_from_row(row_text)
                
                # Estrai risultato se presente
                result = parse_match_result(row, row_text)
                
                # Determina status
                if result:
                    status = "finished"
                elif odds:
                    status = "scheduled"
                else:
                    status = "scheduled"  # Senza quote ma futura
                
                match_data = {
                    "home_team": home_team,
                    "away_team": away_team,
                    "competition": competition_code,
                    "season": config['season'],
                    "status": status,
                    "match_date": date_cell,
                    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                
                if odds:
                    match_data["odds"] = {
                        **odds,
                        "source": "nowgoal",
                        "odds_date": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                
                if result:
                    match_data["result"] = result
                
                matches_data.append(match_data)
                
                status_icon = "✅" if odds else ("🏁" if result else "⏳")
                odds_str = f"[{odds['home']:.2f}|{odds['draw']:.2f}|{odds['away']:.2f}]" if odds else "[no odds]"
                result_str = f" {result['home_score']}-{result['away_score']}" if result else ""
                
                print(f"   {i:3}. {status_icon} {home_team:<25} vs {away_team:<25} {odds_str}{result_str} [{date_cell}]")
                
            except Exception as e:
                print(f"   ⚠️  Riga {i}: Errore parsing - {e}")
                continue
        
        print(f"\n   📈 Totale partite trovate: {len(matches_data)}")
        
        # Salva nel DB
        if matches_data:
            collection = db[config['matches_collection']]
            
            print(f"   💾 Salvataggio in {config['matches_collection']}...")
            
            inserted = 0
            updated = 0
            
            for match in matches_data:
                # Upsert: aggiorna se esiste (stesso home/away/season), inserisci se non esiste
                result = collection.update_one(
                    {
                        "home_team": match['home_team'],
                        "away_team": match['away_team'],
                        "season": match['season']
                    },
                    {
                        "$set": match,
                        "$setOnInsert": {
                            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                    },
                    upsert=True
                )
                
                if result.upserted_id:
                    inserted += 1
                elif result.modified_count > 0:
                    updated += 1
            
            print(f"   ➕ Inserite: {inserted}")
            print(f"   🔄 Aggiornate: {updated}")
        
    except Exception as e:
        print(f"\n   ❌ Errore: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if driver:
            driver.quit()
    
    print(f"\n   ✅ Completato {config['name']}")


# ==================== MAIN ====================

def main():
    parser = argparse.ArgumentParser(description='Aggiorna dati coppe europee')
    parser.add_argument('--competition', choices=['UCL', 'UEL', 'ALL'], default='ALL',
                       help='Competizione da aggiornare (default: ALL)')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🚀 UPDATE CUPS DATA - Aggiornamento Coppe Europee")
    print("=" * 70)
    print(f"   Competizioni: {args.competition}")
    print("=" * 70)
    
    # Determina quali competizioni aggiornare
    competitions = ['UCL', 'UEL'] if args.competition == 'ALL' else [args.competition]
    
    # 1. VALORE ROSA (sempre)
    for comp in competitions:
        update_transfermarkt_values(comp)
        time.sleep(random.uniform(5, 8))
    
    # 2. ELO RATING (sempre)
    elo_df = get_elo_ratings_today()
    if elo_df is not None:
        for comp in competitions:
            update_elo_ratings(comp, elo_df)
    
    # 3. RATING BASE (sempre)
    for comp in competitions:
        collection = db[COMPETITIONS[comp]['teams_collection']]
        teams = list(collection.find({
            "status": "active",
            "valore_rosa_transfermarkt": {"$exists": True, "$gt": 0}
        }))
        
        if teams:
            values = [t['valore_rosa_transfermarkt'] for t in teams]
            rosa_min = min(values)
            rosa_max = max(values)
            
            calculate_rating_base(comp, rosa_min, rosa_max)
    
    # 4. PARTITE E QUOTE (sempre)
    for comp in competitions:
        scrape_nowgoal_matches(comp)
        time.sleep(random.uniform(3, 5))
    
    print("\n" + "=" * 70)
    print("✅ AGGIORNAMENTO COMPLETATO!")
    print("=" * 70)


if __name__ == "__main__":
    main()