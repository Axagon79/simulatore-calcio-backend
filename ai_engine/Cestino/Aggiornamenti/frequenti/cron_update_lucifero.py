import sys
import os
import re
from datetime import datetime, timedelta
import dateutil.parser 

# ==========================================
# 🛠️ CONFIGURAZIONE DEBUG / TEST
# Scrivi qui i nomi delle squadre per testare una partita specifica.
# Lascia vuoto ("") per l'uso automatico notturno.
# ==========================================
TEST_HOME = "Rayo Vallecano"    
TEST_AWAY = "Getafe CF"  
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

def calcola_forma_rigorosa(team_name, prima_di_data=None, debug=False):
    """Calcola Lucifero (0-25) usando le ultime 6 partite ordinate per data"""
    all_matches = []
    
    # 1. RACCOLTA
    for round_doc in ALL_DOCS:
        for m in round_doc.get('matches', []):
            if m.get('status') == 'Finished' and ':' in m.get('real_score', ''):
                if m.get('home') == team_name or m.get('away') == team_name:
                    # IMPLEMENTAZIONE COERENZA STORICA:
                    # Filtriamo solo le partite giocate PRIMA del match che stiamo analizzando
                    if prima_di_data and get_date_object(m) >= prima_di_data:
                        continue
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
    
    # IMPLEMENTAZIONE OUTPUT TEST DETTAGLIATO:
    if debug:
        print(f"\n🔥 ANALISI LUCIFERO: {team_name}")
    
    for i in range(limit):
        m = last_6[i]
        w = weights[i]
        max_p += (3 * w)
        try:
            gh, ga = map(int, m['real_score'].split(':'))
            is_home = (m['home'] == team_name)
            avversario = m['away'] if is_home else m['home']
            
            punti = 0
            ris_label = "S"
            if gh == ga: 
                punti = 1
                ris_label = "P"
            elif (is_home and gh > ga) or (not is_home and ga > gh): 
                punti = 3
                ris_label = "V"
                
            subtotale = punti * w
            total += subtotale
            
            if debug:
                data_str = get_date_object(m).strftime("%Y-%m-%d %H:%M:%S")
                print(f"   {i+1}° ({data_str}) vs {avversario}: {ris_label} ({m['real_score']}) -> {punti}pt x {w} = {subtotale}")
        except: continue

    if max_p == 0: return 0.0
    res = round((total / max_p) * 25.0, 2)
    
    if debug:
        print(f" ⚡ POTENZA LUCIFERO: {res:.2f}/25.0")
        
    return res

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

        # --- IMPLEMENTAZIONE LOGICA ANCHOR (7 GIORNI) ---
        anchor_index = -1
        oggi = datetime.now()

        for i, r in enumerate(rounds_lega):
            matches = r.get('matches', [])
            open_matches = [m for m in matches if m.get('status') in ['Scheduled', 'Timed']]
            if not open_matches: continue

            finished_matches = [m for m in matches if m.get('status') == 'Finished']
            if finished_matches:
                last_regular_date = max([get_date_object(m) for m in finished_matches])
                limit_date = last_regular_date + timedelta(days=7)
                if any(get_date_object(m) >= oggi and get_date_object(m) <= limit_date for m in open_matches):
                    anchor_index = i
                    break
            else:
                anchor_index = i
                break
        
        if anchor_index == -1: anchor_index = len(rounds_lega) - 1

        # Feedback visivo sulla giornata attiva (Sincronizzata con anchor_index)
        giornata_nome = rounds_lega[anchor_index].get('round_name', 'N/D') if anchor_index < len(rounds_lega) else 'Fine'
        print(f"-> Attuale (Sincronizzata): {giornata_nome}")

        # Definiamo il range di aggiornamento (PRECEDENTE, ATTUALE, SUCCESSIVA)
        start = max(0, anchor_index - 1)
        end = min(len(rounds_lega), anchor_index + 2)
        target = rounds_lega[start:end]

        for r in target:
            matches = r.get('matches', [])
            mod = False
            for m in matches:
                
                if m.get('home') and m.get('away'):
                    
                    # DATA DEL MATCH ANALIZZATO (Per filtro coerenza storico)
                    match_date = get_date_object(m)
                    
                    # CONTROLLO DEBUG TEST
                    is_test = (TEST_HOME and TEST_AWAY and m['home'] == TEST_HOME and m['away'] == TEST_AWAY)

                    # 1. Calcolo valori base (Filtrati per data del match)
                    v_h = calcola_forma_rigorosa(m['home'], prima_di_data=match_date, debug=is_test)
                    v_a = calcola_forma_rigorosa(m['away'], prima_di_data=match_date, debug=is_test)
                    
                    if 'h2h_data' not in m or m['h2h_data'] is None: m['h2h_data'] = {}
                    
                    old_h = m['h2h_data'].get('lucifero_home')
                    old_a = m['h2h_data'].get('lucifero_away')
                    
                    # 2. Recupero Trend attuali dal DB per confronto
                    old_trend_h = m['h2h_data'].get('lucifero_trend_home', [])
                    old_trend_a = m['h2h_data'].get('lucifero_trend_away', [])

                    # 3. Generazione NUOVI Trend potenziali (Filtrati per data del match)
                    storia_home = sorted([match for round_doc in ALL_DOCS for match in round_doc.get('matches', []) 
                                        if (match.get('home') == m['home'] or match.get('away') == m['home']) 
                                        and match.get('status') == 'Finished'
                                        and get_date_object(match) < match_date], 
                                        key=get_date_object, reverse=True)

                    storia_away = sorted([match for round_doc in ALL_DOCS for match in round_doc.get('matches', []) 
                                        if (match.get('home') == m['away'] or match.get('away') == m['away']) 
                                        and match.get('status') == 'Finished'
                                        and get_date_object(match) < match_date], 
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

                        mod = True
                        tot_updates += 1

            if mod:
                db.h2h_by_round.update_one({'_id': r['_id']}, {'$set': {'matches': matches}})

    print(f"\n✅ Aggiornamento completato. Partite modificate: {tot_updates}")

if __name__ == "__main__":
    esegui_aggiornamento()