"""
Script per aggiungere nuove squadre ai campionati
SENZA toccare le squadre già esistenti
Usa transfermarkt_id come chiave univoca
"""
import time
from fake_useragent import UserAgent
import requests
import os
import sys
from bs4 import BeautifulSoup
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db
from datetime import datetime


def create_team_template(name, country, league, transfermarkt_id, transfermarkt_slug):
    """Crea la struttura completa per una nuova squadra"""
    return {
        # DATI CERTI (da Transfermarkt)
        "name": name,
        "country": country,
        "league": league,
        "transfermarkt_id": transfermarkt_id,
        "transfermarkt_slug": transfermarkt_slug,
        "aliases_transfermarkt": name,
        "aliases": [],
        
        # FORMAZIONE (vuota - verrà popolata)
        "formation": "",
        
        # STATS (vuoto - verrà popolato dagli scraper)
        "stats": {
            "marketValue": None,
            "lastUpdated": None,
            "avgAge": None,
            "ageMalus": None,
            "strengthScore09": None,
            "valueScore09": None,
            "ageMultiplier": None,
            "rawStrength": None,
            "ranking_c": {},
            "motivation": None,
            "motivation_pressure_euro": None,
            "motivation_pressure_releg": None,
            "motivation_progress": None,
            "motivation_pressure_title": None
        },
        
        # SCORES (vuoto - verrà popolato da calculate_attacco_difesa)
        "scores": {
            "attack_home": None,
            "defense_home": None,
            "attack_away": None,
            "defense_away": None,
            "home_power": None,
            "away_power": None
        },
        
        # RANKING (vuoto - verrà popolato dagli scraper)
        "ranking": {
            "league": league,
            "homeStats": {
                "played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "goalsFor": 0,
                "goalsAgainst": 0
            },
            "awayStats": {
                "played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "goalsFor": 0,
                "goalsAgainst": 0
            },
            "awayPoints": 0,
            "homePoints": 0
        },
        
        # TIMESTAMP
        "lastUpdateTransfermarkt": time.time(),
        "last_updated": time.time()
    }
# ═══════════════════════════════════════════════════════════
# CONFIGURAZIONE NUOVI CAMPIONATI
# ═══════════════════════════════════════════════════════════

NEW_LEAGUES = {
    # EUROPA SERIE B
    "Championship": {
        "country": "England",
        "url_value": "https://www.transfermarkt.it/championship/startseite/wettbewerb/GB2"
    },
    "LaLiga 2": {
        "country": "Spain",
        "url_value": "https://www.transfermarkt.it/laliga2/startseite/wettbewerb/ES2"
    },
    "2. Bundesliga": {
        "country": "Germany",
        "url_value": "https://www.transfermarkt.it/2-bundesliga/startseite/wettbewerb/L2"
    },
    "Ligue 2": {
        "country": "France",
        "url_value": "https://www.transfermarkt.it/ligue-2/startseite/wettbewerb/FR2"
    },
    
    # EUROPA NORDICI + EXTRA
    "Scottish Premiership": {
        "country": "Scotland",
        "url_value": "https://www.transfermarkt.it/premiership/startseite/wettbewerb/SC1"
    },
    "Allsvenskan": {
        "country": "Sweden",
        "url_value": "https://www.transfermarkt.it/allsvenskan/startseite/wettbewerb/SE1"
    },
    "Eliteserien": {
        "country": "Norway",
        "url_value": "https://www.transfermarkt.it/eliteserien/startseite/wettbewerb/NO1"
    },
    "Superligaen": {
        "country": "Denmark",
        "url_value": "https://www.transfermarkt.it/superligaen/startseite/wettbewerb/DK1"
    },
    "Jupiler Pro League": {
        "country": "Belgium",
        "url_value": "https://www.transfermarkt.it/jupiler-pro-league/startseite/wettbewerb/BE1"
    },
    "Süper Lig": {
        "country": "Turkey",
        "url_value": "https://www.transfermarkt.it/super-lig/startseite/wettbewerb/TR1"
    },
    "League of Ireland Premier Division": {
        "country": "Ireland",
        "url_value": "https://www.transfermarkt.it/premier-league/startseite/wettbewerb/IR1"
    },
    
    # AMERICHE
    "Brasileirão Serie A": {
        "country": "Brazil",
        "url_value": "https://www.transfermarkt.it/campeonato-brasileiro-serie-a/startseite/wettbewerb/BRA1"
    },
    "Primera División": {
        "country": "Argentina",
        "url_value": "https://www.transfermarkt.it/primera-division/startseite/wettbewerb/AR1N"
    },
    "Major League Soccer": {
        "country": "USA",
        "url_value": "https://www.transfermarkt.it/major-league-soccer/startseite/wettbewerb/MLS1"
    },
    
    # ASIA
    "J1 League": {
        "country": "Japan",
        "url_value": "https://www.transfermarkt.it/j1-100-year-vision-league/teilnehmer/pokalwettbewerb/J1YV"
    }
}

# ═══════════════════════════════════════════════════════════
# FUNZIONI DI CONTROLLO E INSERIMENTO
# ═══════════════════════════════════════════════════════════

def team_exists_by_id(transfermarkt_id):
    """Verifica se una squadra esiste già usando l'ID univoco Transfermarkt"""
    if not transfermarkt_id:
        return False
    
    existing = db.teams.find_one({"transfermarkt_id": transfermarkt_id})
    return existing is not None

def add_team_to_db(team_data):
    """Aggiunge una squadra al DB solo se non esiste (controlla per ID)"""
    team_name = team_data["name"]
    league_name = team_data["league"]
    tm_id = team_data.get("transfermarkt_id")
    
    # ✅ CONTROLLO PRIMARIO: ID Transfermarkt (univoco al 100%)
    if tm_id and team_exists_by_id(tm_id):
        print(f"⏭️  SKIP (ID exists): {team_name} (TM_ID: {tm_id})")
        return False
    
    # ✅ CONTROLLO SECONDARIO: Nome + Lega (sicurezza extra)
    existing_by_name = db.teams.find_one({
        "name": team_name,
        "league": league_name
    })
    
    if existing_by_name:
        print(f"⚠️  SKIP (Name exists): {team_name} ({league_name})")
        print(f"   DB ha: {existing_by_name.get('name')} (ID: {existing_by_name.get('transfermarkt_id')})")
        print(f"   Nuovo: {team_name} (ID: {tm_id})")
        return False
    
    # ✅ Inserisci nuova squadra
    db.teams.insert_one(team_data)
    print(f"✅ ADDED: {team_name} ({league_name}) [ID: {tm_id}]")
    return True

def scrape_and_add_league(league_name, league_config):
    """Scrapa una lega da Transfermarkt e aggiunge le squadre"""
    import requests
    from bs4 import BeautifulSoup
    import random
    from fake_useragent import UserAgent
    
    print(f"\n🔍 Scraping {league_name}...")
    
    ua = UserAgent()
    headers = {"User-Agent": ua.random}
    
    url = league_config["url_value"]
    country = league_config["country"]
    
    added_count = 0
    
    try:
        print(f"   📡 Connessione a Transfermarkt...")
        r = requests.get(url, headers=headers, timeout=20)
        
        if r.status_code != 200:
            print(f"   ❌ HTTP {r.status_code}")
            return 0
        
        soup = BeautifulSoup(r.content, "html.parser")
        rows = soup.select("table.items tbody tr")
        
        print(f"   ✅ Trovate {len(rows)} squadre")
        
        for row in rows:
            try:
                # Estrai nome squadra
                name_tag = row.find("td", class_="hauptlink")
                if not name_tag:
                    continue
                
                team_name = name_tag.text.strip().replace("\n", "")
                
                # Estrai link (contiene ID e slug)
                link_tag = name_tag.find("a")
                if not link_tag or not link_tag.get("href"):
                    continue
                
                href = link_tag["href"]
                # Esempio: /inter-mailand/startseite/verein/46
                parts = href.split("/")

                if len(parts) < 5:
                    continue

                # ✅ FILTRA SOLO SQUADRE (deve contenere "verein")
                if "verein" not in href:
                    continue

                transfermarkt_slug = parts[1]  # "inter-mailand"
                transfermarkt_id = int(parts[4])  # 46
                
                # Crea template
                team_data = create_team_template(
                    name=team_name,
                    country=country,
                    league=league_name,
                    transfermarkt_id=transfermarkt_id,
                    transfermarkt_slug=transfermarkt_slug
                )
                
                # Inserisci nel DB
                if add_team_to_db(team_data):
                    added_count += 1
                    
            except Exception as e:
                print(f"   ⚠️ Errore parsing squadra: {e}")
                continue
        
        print(f"   📊 {added_count} nuove squadre aggiunte")
        
    except Exception as e:
        print(f"   ❌ Errore scraping: {e}")
    
    return added_count

# ═══════════════════════════════════════════════════════════
# ESECUZIONE
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🚀 INIZIO POPOLAZIONE NUOVI CAMPIONATI\n")
    print("⚠️  Questo script NON modificherà le squadre esistenti\n")
    
    total_added = 0
    
    for league_name, league_config in NEW_LEAGUES.items():
        added = scrape_and_add_league(league_name, league_config)
        total_added += added
        time.sleep(2)  # Pausa tra una lega e l'altra
    
    print(f"\n✅ COMPLETATO! {total_added} squadre totali aggiunte")