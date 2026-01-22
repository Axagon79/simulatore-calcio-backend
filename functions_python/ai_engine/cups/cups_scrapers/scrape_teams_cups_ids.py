"""
SCRAPER ID TRANSFERMARKT - COPPE EUROPEE
Scarica nome + transfermarkt_id + paese per Champions ed Europa League

Output: Salva direttamente in MongoDB
- teams_champions_league
- teams_europa_league
"""

import requests
from bs4 import BeautifulSoup
import sys
import os
import time
import random
from fake_useragent import UserAgent

# Importa configurazione DB
# Cerca config.py nella root del progetto
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# ==================== CONFIGURAZIONE ====================

CUPS_CONFIG = {
    "UCL": {
        "name": "UEFA Champions League",
        "url": "https://www.transfermarkt.it/uefa-champions-league/teilnehmer/pokalwettbewerb/CL/saison_id/2025",
        "season": "2025-2026",
        "collection": "teams_champions_league"
    },
    "UEL": {
        "name": "UEFA Europa League",
        "url": "https://www.transfermarkt.it/uefa-europa-league/teilnehmer/pokalwettbewerb/EL/saison_id/2025",
        "season": "2025-2026",
        "collection": "teams_europa_league"
    }
}

# ==================== FUNZIONI ====================

def scrape_and_save_cup_teams(competition_code, config):
    """
    Scarica lista squadre + ID da Transfermarkt e salva in MongoDB
    
    Args:
        competition_code: "UCL" o "UEL"
        config: dizionario con url, collection e info competizione
    """
    print(f"\n🏆 {config['name']}...")
    
    # Ottieni collection MongoDB
    collection = db[config['collection']]
    
    print(f"   📝 Aggiornamento collection {config['collection']}...")
    
    ua = UserAgent()
    headers = {"User-Agent": ua.random}
    
    teams_count = 0
    
    try:
        print(f"   📡 Connessione a Transfermarkt...")
        response = requests.get(config['url'], headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"   ❌ HTTP {response.status_code}")
            return 0
        
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Trova la tabella con le squadre
        table = soup.find("table", class_="items")
        
        if not table:
            print(f"   ❌ Tabella squadre non trovata")
            return 0
        
        # Trova tutte le righe
        rows = table.find("tbody").find_all("tr")
        
        print(f"   📊 Trovate {len(rows)} righe nella tabella")
        
        for row in rows:
            # Salta righe vuote o di intestazione
            if not row.find("td"):
                continue
            
            # Trova la cella con il nome della squadra
            name_cell = row.find("td", class_="hauptlink")
            
            if not name_cell:
                continue
            
            # Estrai il link
            link = name_cell.find("a")
            
            if not link:
                continue
            
            # Nome squadra
            team_name = link.get("title", "").strip()
            if not team_name:
                team_name = link.text.strip()
            
            # Estrai transfermarkt_id dal link
            href = link.get("href", "")
            
            tm_id = None
            if "verein" in href:
                parts = href.split("/")
                try:
                    verein_index = parts.index("verein")
                    if verein_index + 1 < len(parts):
                        tm_id = int(parts[verein_index + 1])
                except (ValueError, IndexError):
                    pass
            
            if not tm_id:
                print(f"   ⚠️  {team_name}: ID non trovato")
                continue
            
            # Estrai paese dalla bandierina
            country_img = row.find("img", class_="flaggenrahmen")
            country = "???"
            
            if country_img:
                country = country_img.get("title", country_img.get("alt", "???"))
            
            # Documento da inserire/aggiornare in MongoDB
            team_doc = {
                "name": team_name,
                "transfermarkt_id": tm_id,
                "country": country,
                "season": config['season'],
                "status": "active",  # Squadra attiva nella competizione
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Upsert in MongoDB (aggiorna se esiste, inserisce se non esiste)
            result = collection.update_one(
                {
                    "transfermarkt_id": tm_id,
                    "season": config['season']
                },
                {
                    "$set": team_doc,
                    "$setOnInsert": {
                        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                },
                upsert=True
            )
            
            if result.upserted_id:
                teams_count += 1
                status_icon = "➕"
            elif result.modified_count > 0:
                teams_count += 1
                status_icon = "🔄"
            else:
                status_icon = "="
            
            print(f"   {status_icon} {team_name:<30} | ID: {tm_id:<6} | {country}")
        
        print(f"\n   📈 Totale squadre salvate: {teams_count}")
        
    except Exception as e:
        print(f"   ❌ Errore: {e}")
    
    return teams_count


# ==================== MAIN ====================

if __name__ == "__main__":
    print("=" * 70)
    print("🚀 SCRAPER ID TRANSFERMARKT - COPPE EUROPEE")
    print("=" * 70)
    
    total_ucl = 0
    total_uel = 0
    
    # Scrape Champions League
    total_ucl = scrape_and_save_cup_teams("UCL", CUPS_CONFIG["UCL"])
    
    # Pausa tra le richieste
    print("\n⏳ Pausa 5 secondi...")
    time.sleep(random.uniform(5, 7))
    
    # Scrape Europa League
    total_uel = scrape_and_save_cup_teams("UEL", CUPS_CONFIG["UEL"])
    
    print("\n" + "=" * 70)
    print("✅ COMPLETATO!")
    print(f"   Champions League: {total_ucl} squadre salvate")
    print(f"   Europa League: {total_uel} squadre salvate")
    print(f"   Totale: {total_ucl + total_uel} squadre")
    print("=" * 70)