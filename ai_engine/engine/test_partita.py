import sys
import os
from datetime import datetime

# --- SETUP PERCORSI ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
sys.path.append(PROJECT_ROOT)

# --- IMPORT DATABASE ---
try:
    from config import db
except ImportError:
    sys.path.append(os.path.dirname(CURRENT_DIR))
    from config import db

# --- IMPORT MOTORE ---
from engine_core import predict_match
from goals_converter import calculate_goals_from_engine

# --- MAPPA NAZIONI ---
NATION_MAP = {
    "Italia": ["Serie A", "Serie B", "Serie C", "Coppa Italia"],
    "Inghilterra": ["Premier League", "Championship", "FA Cup", "League One"],
    "Spagna": ["La Liga", "Segunda", "Copa del Rey"],
    "Germania": ["Bundesliga", "DFB"],
    "Francia": ["Ligue 1", "Ligue 2"],
    "Europa": ["Champions", "Europa League", "Conference"]
}

def get_leagues_from_db():
    """
    Recupera le leghe uniche usando la collezione corretta: 'h2h_by_round'
    """
    if db is None: return []
    # Usa h2h_by_round come richiesto
    return sorted(db.h2h_by_round.distinct("league"))

def filter_leagues_by_nation(all_leagues, nation_choice):
    filtered = []
    keywords = NATION_MAP.get(nation_choice, [])
    
    if nation_choice == "Altro":
        all_known = [item for sublist in NATION_MAP.values() for item in sublist]
        for l in all_leagues:
            is_known = False
            for k in all_known:
                if k in l:
                    is_known = True
                    break
            if not is_known:
                filtered.append(l)
    else:
        for l in all_leagues:
            if any(k in l for k in keywords):
                filtered.append(l)
    return filtered

def get_matches_from_round(league_name):
    """
    Estrae le partite dalla collezione corretta: 'h2h_by_round'
    """
    # PUNTIAMO ALLA LIBRERIA GIUSTA: h2h_by_round
    cursor = db.h2h_by_round.find({"league": league_name})
    
    matches_found = []
    
    for doc in cursor:
        round_name = doc.get("round_name", "Giornata ?")
        match_list = doc.get("matches", [])
        
        for m in match_list:
            # Mostra Scheduled e Timed (partite future)
            if m.get("status") == "Scheduled" or m.get("status") == "Timed":
                matches_found.append({
                    "home": m["home"],
                    "away": m["away"],
                    "info": round_name
                })
                
    return matches_found[:25]

def simula_match(casa, trasferta):
    print(f"\n🚀 PREPARAZIONE: {casa} vs {trasferta}")
    
    print("\nScegli l'Algoritmo:")
    print("1. 📊 Statistica Pura")
    print("2. ⚡ Dinamico")
    print("3. 🧠 Tattico")
    print("4. 🎲 Caos")
    print("5. 👑 Master (Consigliato)")
    try:
        a = int(input("Scelta (Invio per 5): ").strip() or 5)
    except: a = 5
    
    print(f"\n⚽ AVVIO SIMULAZIONE...")
    print("..." * 10)
    
    try:
        # Il motore engine_core usa già h2h_by_round internamente
        s_h, s_a, r_h, r_a = predict_match(casa, trasferta, mode=a)
        
        if s_h is None:
            print("❌ Errore: Il motore non ha trovato i dati delle squadre.")
            return

        print("\n📊 --- ELABORAZIONE GOL ---")
        g_h, g_a, xg_h, xg_a, chaos = calculate_goals_from_engine(s_h, s_a, r_h, r_a)
        
        print(f"   xG: {xg_h} - {xg_a}")
        if chaos: print(f"   🎲 {chaos}")
        
        print("\n" + "="*40)
        print(f"🏁 RISULTATO FINALE:")
        print(f"   🏠 {casa}  {g_h}  -  {g_a}  {trasferta} ✈️")
        print("="*40 + "\n")
        
    except Exception as e:
        print(f"❌ Errore simulazione: {e}")

def menu_gerarchico():
    while True:
        print("\n" + "█"*60)
        print("🌍  SELETTORE CAMPIONATI (Source: h2h_by_round)")
        print("█"*60)
        
        nazioni = list(NATION_MAP.keys()) + ["Altro"]
        print("\n📍 SELEZIONA NAZIONE:")
        for i, n in enumerate(nazioni):
            print(f"{i+1}. {n}")
        print("0. Esci")
        
        try:
            raw = input("> ").strip()
            if raw == "0": break
            sel_nac = int(raw) - 1
            if sel_nac < 0 or sel_nac >= len(nazioni): continue
            nazione_scelta = nazioni[sel_nac]
        except: continue

        all_leagues_db = get_leagues_from_db()
        leghe_disponibili = filter_leagues_by_nation(all_leagues_db, nazione_scelta)
        
        if not leghe_disponibili:
            print(f"❌ Nessun campionato trovato per {nazione_scelta}.")
            continue
            
        print(f"\n🏆 CAMPIONATI DISPONIBILI ({nazione_scelta}):")
        for i, l in enumerate(leghe_disponibili):
            print(f"{i+1}. {l}")
        print("0. Indietro")
        
        try:
            sel_leg = int(input("> ")) - 1
            if sel_leg == -1: continue
            if sel_leg < 0 or sel_leg >= len(leghe_disponibili): continue
            lega_scelta = leghe_disponibili[sel_leg]
        except: continue

        partite = get_matches_from_round(lega_scelta)
        
        if not partite:
            print(f"⚠️ Nessuna partita futura trovata in {lega_scelta}.")
            input("Invio...")
            continue
            
        print(f"\n📅 PROSSIME PARTITE ({lega_scelta}):")
        for i, p in enumerate(partite):
            print(f"{i+1}. {p['home']} vs {p['away']} ({p['info']})")
        print("0. Indietro")
        
        try:
            sel_match = int(input("> ")) - 1
            if sel_match == -1: continue
            match = partite[sel_match]
            simula_match(match['home'], match['away'])
            input("Invio per tornare al menu...")
        except: continue

if __name__ == "__main__":
    menu_gerarchico()
