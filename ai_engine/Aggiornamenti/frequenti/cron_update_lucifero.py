import sys
import os
import re
from datetime import datetime
import dateutil.parser 

# ==========================================
# 🛠️ CONFIGURAZIONE DEBUG / TEST
# Scrivi qui i nomi delle squadre per testare una partita specifica.
# Lascia vuoto ("") per l'uso automatico notturno.
# ==========================================
TEST_HOME = ""    
TEST_AWAY = ""  
# ==========================================


# --- SETUP PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from config import db
except ImportError:
    print("❌ Errore: config.py non trovato.")
    sys.exit(1)

print(f"[{datetime.now()}] ⚖️ Avvio Aggiornamento Lucifero RIGOROSO")
if TEST_HOME and TEST_AWAY:
    print(f"🔎 MODALITÀ TEST ATTIVA: Cerco match {TEST_HOME} vs {TEST_AWAY}...")

# --- CARICAMENTO STORICO ---
ALL_DOCS = list(db.h2h_by_round.find({}))

def get_date_object(match):
    """Helper per ordinare le date in modo preciso"""
    if 'date_obj' in match and match['date_obj']:
        if isinstance(match['date_obj'], datetime): return match['date_obj']
        try: return dateutil.parser.parse(str(match['date_obj']))
        except: pass
    if 'date' in match and match['date']:
        try: return datetime.strptime(match['date'], "%d/%m/%Y")
        except: pass
    return datetime(1900, 1, 1)

def calcola_forma_rigorosa(team_name):
    """Calcola Lucifero (0-25) usando le ultime 6 partite ordinate per data"""
    all_matches = []
    
    # 1. RACCOLTA
    for round_doc in ALL_DOCS:
        for m in round_doc.get('matches', []):
            if m.get('status') == 'Finished' and ':' in m.get('real_score', ''):
                if m.get('home') == team_name or m.get('away') == team_name:
                    all_matches.append(m)
    
    if not all_matches: return 0.0

    # 2. ORDINAMENTO TEMPORALE (Dal più recente)
    all_matches.sort(key=get_date_object, reverse=True)
    
    # 3. SELEZIONE E CALCOLO
    last_6 = all_matches[:6]
    weights = [6, 5, 4, 3, 2, 1]
    total = 0
    max_p = 0
    limit = min(len(last_6), 6)
    
    for i in range(limit):
        m = last_6[i]
        w = weights[i]
        max_p += (3 * w)
        try:
            gh, ga = map(int, m['real_score'].split(':'))
            is_home = (m['home'] == team_name)
            punti = 0
            if gh == ga: punti = 1
            elif (is_home and gh > ga) or (not is_home and ga > gh): punti = 3
            total += (punti * w)
        except: continue

    if max_p == 0: return 0.0
    return round((total / max_p) * 25.0, 2)

def genera_trend_lucifero(team_name, all_matches_sorted):
    """
    Genera i 5 valori storici di Lucifero tornando indietro nel tempo.
    all_matches_sorted deve essere già ordinata dal più recente.
    """
    trend = []
    # Vogliamo 5 snapshot (oggi, -1 partita, -2, -3, -4)
    for offset in range(5):
        # Prendiamo lo storico "tagliando" le partite più recenti in base all'offset
        sub_history = all_matches_sorted[offset:] 
        
        if not sub_history:
            trend.append(0.0)
            continue
            
        # Logica di calcolo identica a calcola_forma_rigorosa ma su sub_history
        last_6 = sub_history[:6]
        weights = [6, 5, 4, 3, 2, 1]
        total = 0
        max_p = 0
        limit = min(len(last_6), 6)
        
        for i in range(limit):
            m = last_6[i]
            w = weights[i]
            max_p += (3 * w)
            try:
                gh, ga = map(int, m['real_score'].split(':'))
                is_home = (m['home'] == team_name)
                punti = 1 if gh == ga else (3 if (is_home and gh > ga) or (not is_home and ga > gh) else 0)
                total += (punti * w)
            except: continue
        
        valore = round((total / max_p) * 25.0, 2) if max_p > 0 else 0.0
        # Normalizziamo subito in percentuale 0-100 per il frontend
        trend.append(round((valore / 25.0) * 100, 1))
        
    return trend # Restituisce es. [90.5, 88.0, 82.1, 85.0, 70.2]

# --- LOOP AGGIORNAMENTO ---
def esegui_aggiornamento():
    leghe = db.h2h_by_round.distinct("league")
    tot_updates = 0

    def get_round_num(r):
        nums = re.findall(r'\d+', str(r.get('_id', ''))) or re.findall(r'\d+', str(r.get('round_name', '')))
        return int(nums[0]) if nums else 999

    print(f"🌍 Campionati da analizzare: {len(leghe)}")

    for lega in leghe:
        # Stampiamo SEMPRE il nome della lega che stiamo elaborando
        print(f"🏆 Controllo: {lega}...", end=" ") 
        
        rounds_lega = [r for r in ALL_DOCS if r.get('league') == lega]
        rounds_lega.sort(key=get_round_num)
        
        if not rounds_lega: 
            print(" (Nessuna giornata)")
            continue

        # Trova la giornata attuale
        current_index = -1
        for i, r in enumerate(rounds_lega):
            matches = r.get('matches', [])
            if any(m.get('status') != 'Finished' for m in matches):
                current_index = i
                break
        
        if current_index == -1: current_index = len(rounds_lega) - 1

        # Definisci il range
        start = max(0, current_index - 1)
        end = min(len(rounds_lega), current_index + 2)
        target = rounds_lega[start:end]
        
        # Feedback visivo sulla giornata attiva
        giornata_nome = rounds_lega[current_index].get('round_name', 'N/D') if current_index < len(rounds_lega) else 'Fine'
        print(f"-> Attuale: {giornata_nome}")

        for r in target:
            matches = r.get('matches', [])
            mod = False
            for m in matches:
                
                if m.get('home') and m.get('away'):

                    # 1. Calcolo valori base attuali
                    v_h = calcola_forma_rigorosa(m['home'])
                    v_a = calcola_forma_rigorosa(m['away'])
                    
                    if 'h2h_data' not in m or m['h2h_data'] is None: m['h2h_data'] = {}
                    
                    old_h = m['h2h_data'].get('lucifero_home')
                    old_a = m['h2h_data'].get('lucifero_away')
                    
                    # 2. Recupero Trend attuali dal DB per confronto
                    old_trend_h = m['h2h_data'].get('lucifero_trend_home', [])
                    old_trend_a = m['h2h_data'].get('lucifero_trend_away', [])

                    # 3. Generazione NUOVI Trend potenziali
                    storia_home = sorted([match for round_doc in ALL_DOCS for match in round_doc.get('matches', []) 
                                        if (match.get('home') == m['home'] or match.get('away') == m['home']) 
                                        and match.get('status') == 'Finished'], 
                                        key=get_date_object, reverse=True)

                    storia_away = sorted([match for round_doc in ALL_DOCS for match in round_doc.get('matches', []) 
                                        if (match.get('home') == m['away'] or match.get('away') == m['away']) 
                                        and match.get('status') == 'Finished'], 
                                        key=get_date_object, reverse=True)

                    new_trend_h = genera_trend_lucifero(m['home'], storia_home)
                    new_trend_a = genera_trend_lucifero(m['away'], storia_away)

                    # 4. CONDIZIONE DI AGGIORNAMENTO (Logica Tripla)
                    if (old_h != v_h or old_a != v_a or 
                        old_trend_h != new_trend_h or old_trend_a != new_trend_a):
                        
                        m['h2h_data']['lucifero_home'] = v_h
                        m['h2h_data']['lucifero_away'] = v_a
                        m['h2h_data']['lucifero_trend_home'] = new_trend_h
                        m['h2h_data']['lucifero_trend_away'] = new_trend_a

                        if TEST_HOME:
                            print("\n" + "="*50)
                            print(f"📊 AGGIORNAMENTO RILEVATO PER {m['home']} vs {m['away']}:")
                            print(f"   🏠 Trend: {new_trend_h}")
                            print(f"   ✈️ Trend: {new_trend_a}")
                            print("="*50 + "\n")

                        mod = True
                        tot_updates += 1

                    # --- DEBUG PER L'UTENTE (Con formattazione .2f) ---
                    if TEST_HOME and TEST_AWAY:
                        if m['home'] == TEST_HOME and m['away'] == TEST_AWAY:
                            print("\n" + "="*50)
                            print(f"🧐 VERIFICA PARTITA TROVATA: {TEST_HOME} vs {TEST_AWAY}")
                            print(f"   📅 Giornata: {r.get('round_name')}")
                            # Qui usiamo :.2f per forzare due decimali (es. 13.10)
                            print(f"   🏠 {TEST_HOME}: {v_h:.2f} / 25.00")
                            print(f"   ✈️ {TEST_AWAY}: {v_a:.2f} / 25.00")
                            print("="*50 + "\n")
                    # --------------------------

            if mod:
                db.h2h_by_round.update_one({'_id': r['_id']}, {'$set': {'matches': matches}})
                # print(f"      ✅ Aggiornata: {r.get('round_name')}") # Decommenta se vuoi vedere ogni singola giornata

    print(f"\n✅ Aggiornamento completato. Partite modificate: {tot_updates}")

if __name__ == "__main__":
    esegui_aggiornamento()