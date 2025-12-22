import os
import sys
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from config import db
    print(f"✅ DB Connesso: {db.name}")
except ImportError:
    print("❌ Errore Import Config")
    sys.exit(1)

# --- CONFIGURAZIONE ---
COLLECTION_NAME = "h2h_by_round"
TARGET_SEASON = "2025"
REPORT_FILE = "report_verifica_id.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0.0.0 Safari/537.36"
    )
}

LEAGUES_TM = [
    {"name": "Serie A", "url": f"https://www.transfermarkt.it/serie-a/gesamtspielplan/wettbewerb/IT1/saison_id/{TARGET_SEASON}"},
    {"name": "Serie B", "url": f"https://www.transfermarkt.it/serie-b/gesamtspielplan/wettbewerb/IT2/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone A", "url": f"https://www.transfermarkt.it/serie-c-girone-a/gesamtspielplan/wettbewerb/IT3A/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone B", "url": f"https://www.transfermarkt.it/serie-c-girone-b/gesamtspielplan/wettbewerb/IT3B/saison_id/{TARGET_SEASON}"},
    {"name": "Serie C - Girone C", "url": f"https://www.transfermarkt.it/serie-c-girone-c/gesamtspielplan/wettbewerb/IT3C/saison_id/{TARGET_SEASON}"},
    {"name": "Premier League", "url": f"https://www.transfermarkt.it/premier-league/gesamtspielplan/wettbewerb/GB1/saison_id/{TARGET_SEASON}"},
    {"name": "La Liga", "url": f"https://www.transfermarkt.it/laliga/gesamtspielplan/wettbewerb/ES1/saison_id/{TARGET_SEASON}"},
    {"name": "Bundesliga", "url": f"https://www.transfermarkt.it/bundesliga/gesamtspielplan/wettbewerb/L1/saison_id/{TARGET_SEASON}"},
    {"name": "Ligue 1", "url": f"https://www.transfermarkt.it/ligue-1/gesamtspielplan/wettbewerb/FR1/saison_id/{TARGET_SEASON}"},
    {"name": "Eredivisie", "url": f"https://www.transfermarkt.it/eredivisie/gesamtspielplan/wettbewerb/NL1/saison_id/{TARGET_SEASON}"},
    {"name": "Liga Portugal", "url": f"https://www.transfermarkt.it/liga-nos/gesamtspielplan/wettbewerb/PO1/saison_id/{TARGET_SEASON}"}
]

# --- UTILS ---
def extract_tm_id(url):
    """Estrae l'ID numerico dal link."""
    if not url: return None
    match = re.search(r'/verein/(\d+)', url)
    return match.group(1) if match else None

def extract_round_number(text):
    """Estrae il numero della giornata."""
    if not text: return None
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None

def normalize_key(name):
    """Normalizzazione base per il confronto visivo."""
    if not name: return ""
    return name.lower().strip().replace(" ", "").replace("-", "")

def log_msg(msg, report_list):
    """Stampa a video e aggiunge alla lista per il file."""
    print(msg)
    report_list.append(msg)

def verify_league(col, league, report_list):
    header_msg = f"\n🌍 VERIFICA: {league['name']}..."
    log_msg(header_msg, report_list)
    
    matches_checked = 0
    matches_ok = 0
    matches_error = 0
    
    try:
        resp = requests.get(league['url'], headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.content, "html.parser")
        headers = soup.find_all("div", class_="content-box-headline")

        for header in headers:
            round_name_tm = header.get_text(strip=True)
            round_num = extract_round_number(round_name_tm)
            
            if not round_num: continue

            # Cerchiamo il documento nel DB
            safe_league = league['name'].replace(" ", "")
            doc_id = f"{safe_league}_{round_num}Giornata"
            
            db_doc = col.find_one({"_id": doc_id})
            
            # Se il documento non esiste, lo segnaliamo (potrebbe essere normale per giornate future molto lontane)
            if not db_doc:
                # log_msg(f"   ℹ️ Doc DB mancante: {doc_id}", report_list)
                continue

            db_matches = db_doc.get("matches", [])
            
            table = header.find_next("table")
            if not table: continue
            rows = table.find_all("tr")

            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5: continue

                # Estrarre i link
                team_links = [
                    a for a in row.find_all("a")
                    if a.get("title") and "spielbericht" not in a.get("href", "") and "verein" in a.get("href", "")
                ]
                if len(team_links) < 2: continue

                # Dati da Transfermarkt
                home_name_tm = team_links[0].get_text(strip=True)
                away_name_tm = team_links[-1].get_text(strip=True)
                home_id_tm = extract_tm_id(team_links[0]['href'])
                away_id_tm = extract_tm_id(team_links[-1]['href'])

                if not home_id_tm or not away_id_tm: continue
                
                # Cerca la corrispondenza nel DB (per ID)
                match_found = False
                for m in db_matches:
                    db_h_id = str(m.get('home_tm_id', ''))
                    db_a_id = str(m.get('away_tm_id', ''))
                    
                    # 1. CASO PERFETTO: Gli ID corrispondono
                    if db_h_id == home_id_tm and db_a_id == away_id_tm:
                        match_found = True
                        matches_checked += 1
                        matches_ok += 1
                        # Controllo Extra sui nomi (Sanity Check)
                        # Se i nomi sono molto diversi, lo segnaliamo come Warning
                        h_db_norm = normalize_key(m['home'])
                        h_tm_norm = normalize_key(home_name_tm)
                        if (h_db_norm not in h_tm_norm) and (h_tm_norm not in h_db_norm):
                             log_msg(f"   ⚠️ WARNING NOMI: ID OK ({db_h_id}) ma nomi diversi: DB='{m['home']}' vs TM='{home_name_tm}'", report_list)
                        break
                
                # 2. CASO ERRORE: Non ho trovato l'ID nel DB per questa partita
                if not match_found:
                    # Provo a cercare se esiste la partita nel DB ma con ID sbagliati (tramite Nome)
                    found_by_name = False
                    for m in db_matches:
                        h_db_norm = normalize_key(m['home'])
                        a_db_norm = normalize_key(m['away'])
                        h_tm_norm = normalize_key(home_name_tm)
                        a_tm_norm = normalize_key(away_name_tm)
                        
                        if (h_tm_norm in h_db_norm or h_db_norm in h_tm_norm) and \
                           (a_tm_norm in a_db_norm or a_db_norm in a_tm_norm):
                            
                            found_by_name = True
                            matches_error += 1
                            msg = (f"   ❌ ERRORE ID [{doc_id}]: {m['home']} vs {m['away']}\n"
                                   f"      -> ID DB: {m.get('home_tm_id')} - {m.get('away_tm_id')}\n"
                                   f"      -> ID TM: {home_id_tm} - {away_id_tm} (Corretti)\n"
                                   f"      -> AZIONE: Correggi manualmente gli ID nel DB!")
                            log_msg(msg, report_list)
                            break
                    
                    if not found_by_name:
                         # Caso estremo: La partita c'è su TM ma non esiste proprio nel DB (nemmeno coi nomi)
                         # log_msg(f"   ❓ Partita mancante nel DB: {home_name_tm} vs {away_name_tm}", report_list)
                         pass

    except Exception as e:
        log_msg(f"   ❌ Errore Critico {league['name']}: {e}", report_list)

    summary = f"   🏁 {league['name']}: Controllati {matches_checked} | OK {matches_ok} | ERRORI ID {matches_error}"
    log_msg(summary, report_list)
    log_msg("-" * 50, report_list)

def run_verification():
    report_list = []
    log_msg("\n🕵️  AVVIO VERIFICA INTEGRITÀ ID (READ-ONLY)", report_list)
    log_msg(f"📅 Data: {datetime.now()}", report_list)
    log_msg("=" * 50, report_list)

    col = db[COLLECTION_NAME]
    
    for league in LEAGUES_TM:
        verify_league(col, league, report_list)

    # Scrittura file
    try:
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            for line in report_list:
                f.write(line + "\n")
        print(f"\n✅ Report salvato correttamente in: {REPORT_FILE}")
    except Exception as e:
        print(f"\n❌ Impossibile salvare il file report: {e}")

if __name__ == "__main__":
    run_verification()