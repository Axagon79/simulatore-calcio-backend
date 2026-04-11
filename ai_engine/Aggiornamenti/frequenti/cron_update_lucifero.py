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
TEST_HOME = ""
TEST_AWAY = ""
# ==========================================

NUM_GIORNATE = 10  # Quante giornate scaricare per lega (ultime N)
DRY_RUN = False     # Se True, non scrive nel DB — solo stampa differenze

# FIX PERCORSI
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)

if ai_engine_dir not in sys.path: sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path: sys.path.insert(0, project_root)

try:
    from config import db
except ImportError:
    print("❌ Errore: config.py non trovato.")
    sys.exit(1)

_start_time = datetime.now()
print(f"[{_start_time}] ⚖️ Avvio Aggiornamento Lucifero RIGOROSO {'(DRY RUN)' if DRY_RUN else ''}")
if TEST_HOME and TEST_AWAY:
    print(f"🔎 MODALITÀ TEST ATTIVA: Cerco match {TEST_HOME} vs {TEST_AWAY}...")

# --- PROJECTION: solo i campi necessari ---
# NOTA: NON usare projection selettiva qui — lo script riscrive l'intero array
# matches con $set, quindi campi esclusi dalla projection verrebbero cancellati
# (es. odds, home_mongo_id, match_time, ecc.)


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


def get_round_num(r):
    nums = re.findall(r'\d+', str(r.get('_id', ''))) or re.findall(r'\d+', str(r.get('round_name', '')))
    return int(nums[0]) if nums else 999


def calcola_forma_rigorosa(team_name, team_history, prima_di_data=None, debug=False):
    """
    Calcola Lucifero (0-25) usando le ultime 6 partite ordinate per data.
    team_history: lista di match già filtrata per questa squadra, ordinata dal più recente.
    """
    if prima_di_data:
        matches = [m for m in team_history if get_date_object(m) < prima_di_data]
    else:
        matches = team_history

    if not matches: return 0.0

    last_6 = matches[:6]
    weights = [6, 5, 4, 3, 2, 1]
    total = 0
    max_p = 0
    limit = min(len(last_6), 6)

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


def genera_trend_lucifero(team_name, team_history):
    """
    Genera i 5 valori storici di Lucifero tornando indietro nel tempo.
    team_history: lista di match già filtrata e ordinata dal più recente.
    """
    trend = []
    for offset in range(5):
        sub_history = team_history[offset:]

        if not sub_history:
            trend.append(0.0)
            continue

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
        trend.append(round((valore / 25.0) * 100, 1))

    return trend


def build_team_history_cache(round_docs):
    """
    Costruisce una cache {team_name: [match1, match2, ...]} con le partite finite,
    ordinate dal più recente. Una sola scansione per tutti i documenti.
    """
    team_matches = {}
    for round_doc in round_docs:
        for m in round_doc.get('matches', []):
            if m.get('status') == 'Finished' and ':' in m.get('real_score', ''):
                for team in [m.get('home'), m.get('away')]:
                    if team:
                        if team not in team_matches:
                            team_matches[team] = []
                        team_matches[team].append(m)

    # Ordina ogni lista dal più recente
    for team in team_matches:
        team_matches[team].sort(key=get_date_object, reverse=True)

    return team_matches


# --- LOOP AGGIORNAMENTO ---
def esegui_aggiornamento():
    leghe = db.h2h_by_round.distinct("league")
    tot_updates = 0

    print(f"🌍 Campionati da analizzare: {len(leghe)}")

    for lega in leghe:
        print(f"🏆 Controllo: {lega}...", end=" ")

        # --- ANCHOR: legge la giornata corrente dal DB ---
        current_round_doc = db['league_current_rounds'].find_one({"league": lega})
        current_round = current_round_doc.get('current_round') if current_round_doc else None

        # Scarica le ultime NUM_GIORNATE giornate di questa lega
        all_league_docs = list(db.h2h_by_round.find(
            {"league": lega}
        ))

        if not all_league_docs:
            print(" (Nessuna giornata)")
            continue

        all_league_docs.sort(key=get_round_num)

        # Trova anchor_index
        anchor_index = -1
        if current_round:
            for i, r in enumerate(all_league_docs):
                if get_round_num(r) == current_round:
                    anchor_index = i
                    break

        # Fallback: ultima giornata con risultati
        if anchor_index == -1:
            for i in range(len(all_league_docs) - 1, -1, -1):
                if any(m.get('status') == 'Finished' for m in all_league_docs[i].get('matches', [])):
                    anchor_index = i
                    break
        if anchor_index == -1: anchor_index = len(all_league_docs) - 1

        giornata_nome = all_league_docs[anchor_index].get('round_name', 'N/D')
        print(f"-> Attuale: {giornata_nome}")

        # Costruisci cache partite per squadra (una sola scansione su tutte le giornate della lega)
        team_cache = build_team_history_cache(all_league_docs)

        # Le 3 giornate da aggiornare (precedente, attuale, successiva)
        start_update = max(0, anchor_index - 1)
        end_update = min(len(all_league_docs), anchor_index + 2)
        target = all_league_docs[start_update:end_update]

        for r in target:
            matches = r.get('matches', [])
            mod = False
            for m in matches:
                if m.get('home') and m.get('away'):
                    match_date = get_date_object(m)
                    is_test = (TEST_HOME and TEST_AWAY and m['home'] == TEST_HOME and m['away'] == TEST_AWAY)

                    # Storico filtrato per data del match
                    history_home = [x for x in team_cache.get(m['home'], []) if get_date_object(x) < match_date]
                    history_away = [x for x in team_cache.get(m['away'], []) if get_date_object(x) < match_date]

                    v_h = calcola_forma_rigorosa(m['home'], history_home, debug=is_test)
                    v_a = calcola_forma_rigorosa(m['away'], history_away, debug=is_test)

                    if 'h2h_data' not in m or m['h2h_data'] is None: m['h2h_data'] = {}

                    old_h = m['h2h_data'].get('lucifero_home')
                    old_a = m['h2h_data'].get('lucifero_away')
                    old_trend_h = m['h2h_data'].get('lucifero_trend_home', [])
                    old_trend_a = m['h2h_data'].get('lucifero_trend_away', [])

                    new_trend_h = genera_trend_lucifero(m['home'], history_home)
                    new_trend_a = genera_trend_lucifero(m['away'], history_away)

                    if (old_h != v_h or old_a != v_a or
                        old_trend_h != new_trend_h or old_trend_a != new_trend_a):

                        if DRY_RUN:
                            print(f"   🔄 {m['home']} vs {m['away']}: lucH {old_h}→{v_h} | lucA {old_a}→{v_a} | trendH {old_trend_h}→{new_trend_h} | trendA {old_trend_a}→{new_trend_a}")
                        else:
                            m['h2h_data']['lucifero_home'] = v_h
                            m['h2h_data']['lucifero_away'] = v_a
                            m['h2h_data']['lucifero_trend_home'] = new_trend_h
                            m['h2h_data']['lucifero_trend_away'] = new_trend_a
                            mod = True

                        tot_updates += 1

            if mod and not DRY_RUN:
                db.h2h_by_round.update_one({'_id': r['_id']}, {'$set': {'matches': matches}})

    print(f"\n✅ {'DRY RUN' if DRY_RUN else 'Aggiornamento'} completato. Partite {'da modificare' if DRY_RUN else 'modificate'}: {tot_updates}")
    print(f"⏱️ Tempo: {(datetime.now() - _start_time).total_seconds():.1f}s")

if __name__ == "__main__":
    esegui_aggiornamento()
