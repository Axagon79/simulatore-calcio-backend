import os
import sys
import time
import importlib.util
import re
import requests
from datetime import datetime
from bs4 import BeautifulSoup

# --- CONFIGURAZIONE PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
# Il file è in: ai_engine/Aggiornamenti/frequenti/script.py
# Dobbiamo salire di 2 livelli per arrivare ad ai_engine
aggiornamenti_dir = os.path.dirname(current_dir)  # Sale a "Aggiornamenti"
ai_engine_dir = os.path.dirname(aggiornamenti_dir)  # Sale ad "ai_engine"
project_root = os.path.dirname(ai_engine_dir)  # Sale a "simulatore-calcio-backend"

# Aggiungiamo ai percorsi di ricerca
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Debug: stampiamo i percorsi per vedere se sono giusti
print(f"📂 ai_engine_dir: {ai_engine_dir}")
print(f"📂 project_root: {project_root}")

# Percorso esplicito desiderato
explicit_config_path = os.path.join(
    "C:\\Progetti\\simulatore-calcio-backend",
    "functions_python",
    "ai_engine",
    "config.py"
)

# Percorso calcolato (fallback originale)
calculated_config_path = os.path.join(project_root, "config.py")

# Scegli quale usare: preferisci il percorso esplicito
config_path = explicit_config_path if os.path.exists(explicit_config_path) else calculated_config_path

print(f"🔎 Trying to load config from: {config_path}")

try:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"config.py non trovato in: {config_path}")

    spec = importlib.util.spec_from_file_location("config", config_path)
    config_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config_module)
    db = config_module.db
    print(f"✅ DB Connesso: {db.name}")
except Exception as e:
    print(f"❌ Errore Import Config: {e}")
    sys.exit(1)


# --- CONFIGURAZIONE ---
COLLECTION_NAME = "h2h_by_round"
TARGET_SEASON = "2025"
DEBUG_MODE = True  # ATTIVA DEBUG PER CAPIRE IL PROBLEMA

# HEADERS AGGIORNATI - Anti-cache aggressivo + browser moderno
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Referer": "https://www.transfermarkt.it/"
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
    """Estrae l'ID numerico dal link (es. /verein/1234)."""
    if not url: return None
    match = re.search(r'/verein/(\d+)', url)
    return match.group(1) if match else None

def extract_round_number(text):
    """Estrae solo il numero dalla giornata (es. '19. Giornata' -> '19')."""
    if not text: return None
    match = re.search(r'(\d+)', text)
    return match.group(1) if match else None

def process_league(col, league):
    print(f"\n🌐 Elaborazione: {league['name']}...")
    updated_count = 0
    
    # STATISTICHE DEBUG
    stats = {
        "headers_found": 0,
        "rounds_processed": 0,
        "db_docs_found": 0,
        "rows_analyzed": 0,
        "scores_extracted": 0,
        "matches_checked": 0,
        "already_updated": 0
    }
    
    # STRATEGIA 1: Creiamo una sessione persistente con cookie
    session = requests.Session()
    session.headers.update(HEADERS)
    
    try:
        # STEP 1: Prima visita alla homepage per ottenere cookie iniziali
        if DEBUG_MODE:
            print(f"   🔄 Inizializzazione sessione...")
        try:
            session.get("https://www.transfermarkt.it/", timeout=10)
            time.sleep(1.5)
        except Exception as e:
            if DEBUG_MODE:
                print(f"   ⚠️ Warning homepage: {e}")
        
        # STEP 2: Richiesta vera con parametri anti-cache nell'URL
        cache_buster = f"?_={int(time.time() * 1000)}"
        final_url = league['url'] + cache_buster
        
        if DEBUG_MODE:
            print(f"   📥 Scaricamento dati...")
        resp = session.get(final_url, timeout=20)
        
        if resp.status_code != 200:
            print(f"   ❌ HTTP {resp.status_code}")
            return updated_count
        
        soup = BeautifulSoup(resp.content, "html.parser")
        headers = soup.find_all("div", class_="content-box-headline")
        
        stats["headers_found"] = len(headers)
        
        if not headers:
            print(f"   ⚠️ Nessuna giornata trovata nel HTML")
            return updated_count
        
        if DEBUG_MODE:
            print(f"   📋 Giornate trovate: {len(headers)}")

        for header in headers:
            round_name_tm = header.get_text(strip=True)
            round_num = extract_round_number(round_name_tm)
            if not round_num: 
                continue
            
            stats["rounds_processed"] += 1

            safe_league = league['name'].replace(" ", "")
            doc_id = f"{safe_league}_{round_num}Giornata"

            db_doc = col.find_one({"_id": doc_id})
            if not db_doc:
                if DEBUG_MODE:
                    print(f"   ⚠️ Doc non trovato in DB: {doc_id}")
                continue
            
            stats["db_docs_found"] += 1

            db_matches = db_doc.get("matches", [])
            modified_doc = False

            table = header.find_next("table")
            if not table: 
                if DEBUG_MODE:
                    print(f"   ⚠️ Tabella non trovata per giornata {round_num}")
                continue
            
            rows = table.find_all("tr")

            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 5: 
                    continue
                
                stats["rows_analyzed"] += 1

                # Estrarre i link per gli ID
                team_links = [
                    a for a in row.find_all("a")
                    if a.get("title") and "spielbericht" not in a.get("href", "") and "verein" in a.get("href", "")
                ]
                if len(team_links) < 2: 
                    continue

                home_id_tm = extract_tm_id(team_links[0]['href'])
                away_id_tm = extract_tm_id(team_links[-1]['href'])
                if not home_id_tm or not away_id_tm: 
                    continue

                # --- LOGICA POSIZIONALE ---
                final_score = None
                full_text = row.get_text(" ", strip=True)
                candidates = re.findall(r'(\d+:\d+)', full_text)
                
                if not candidates:
                    continue
                
                candidate_score = candidates[-1]
                
                if len(candidate_score) <= 4:
                    final_score = candidate_score
                    stats["scores_extracted"] += 1
                else:
                    continue

                # --- AGGIORNAMENTO DB ---
                match_found = False
                for m in db_matches:
                    db_h_id = str(m.get('home_tm_id', ''))
                    db_a_id = str(m.get('away_tm_id', ''))

                    if db_h_id == home_id_tm and db_a_id == away_id_tm:
                        match_found = True
                        stats["matches_checked"] += 1
                        
                        if m.get('real_score') != final_score:
                            m['real_score'] = final_score
                            m['status'] = "Finished"
                            modified_doc = True
                            updated_count += 1
                            print(f"   ✅ {m['home']} - {m['away']} -> {final_score}")
                        else:
                            stats["already_updated"] += 1
                            if DEBUG_MODE:
                                print(f"   ℹ️ {m['home']} - {m['away']} già aggiornato ({final_score})")
                        break
                
                # Se non ha trovato match, logga il problema
                if not match_found:
                    home_name = team_links[0].get('title', 'Unknown')
                    away_name = team_links[-1].get('title', 'Unknown')
                    print(f"   ⚠️ MISMATCH: {home_name} ({home_id_tm}) - {away_name} ({away_id_tm}) = {final_score}")
                    print(f"      → Non trovato in DB. Verifica TM_ID nel database!")

            if modified_doc:
                col.update_one(
                    {"_id": doc_id},
                    {"$set": {"matches": db_matches, "last_updated": datetime.now()}}
                )

    except requests.exceptions.Timeout:
        print(f"   ⏱️ Timeout - il sito è troppo lento")
    except requests.exceptions.ConnectionError:
        print(f"   🔌 Errore connessione")
    except Exception as e:
        print(f"   ❌ Errore: {e}")
        if DEBUG_MODE:
            import traceback
            traceback.print_exc()
    finally:
        session.close()
    
    # STAMPA STATISTICHE
    if DEBUG_MODE:
        print(f"\n   📊 STATISTICHE {league['name']}:")
        print(f"      - Giornate HTML trovate: {stats['headers_found']}")
        print(f"      - Giornate processate: {stats['rounds_processed']}")
        print(f"      - Doc DB trovati: {stats['db_docs_found']}")
        print(f"      - Righe analizzate: {stats['rows_analyzed']}")
        print(f"      - Risultati estratti: {stats['scores_extracted']}")
        print(f"      - Match controllati DB: {stats['matches_checked']}")
        print(f"      - Già aggiornati: {stats['already_updated']}")
        print(f"      - Nuovi aggiornamenti: {updated_count}")

    return updated_count

def run_auto_update():
    print("\n🚀 AGGIORNAMENTO AUTOMATICO (MODALITÀ DEBUG - TUTTE LE LEGHE)")
    print("📌 Strategia: Session + Cache-buster + Diagnostica avanzata\n")
    
    col = db[COLLECTION_NAME]
    
    total = 0
    start_time = time.time()
    
    # TESTA TUTTE LE LEGHE
    for idx, league in enumerate(LEAGUES_TM, 1):
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(LEAGUES_TM)}] {league['name']}")
        print(f"{'='*60}")
        
        league_start = time.time()
        count = process_league(col, league)
        total += count
        elapsed = time.time() - league_start
        
        print(f"\n   ⏱️ Tempo lega: {elapsed:.1f}s | Aggiornamenti: {count}")
        
        # Pausa tra le leghe
        if idx < len(LEAGUES_TM):
            time.sleep(2)
    
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"🏁 FINE. Totale aggiornamenti: {total}")
    print(f"⏱️ Tempo totale: {total_time:.1f}s")
    print(f"{'='*60}")
    
    if total == 0:
        print("\n💡 DIAGNOSI FINALE:")
        print("   ✅ Se tutte le leghe hanno 'Già aggiornati' > 0 → Tutto ok!")
        print("   ⚠️ Se una lega ha 'Risultati estratti' diverso da 'Match controllati'")
        print("      → Problema di matching TM_ID tra sito e DB")
        print("   ❌ Se 'Giornate HTML trovate' = 0 → Problema HTML o cache")

if __name__ == "__main__":
    run_auto_update()