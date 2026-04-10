import os
import sys
import importlib.util
import re
import random
from datetime import datetime
import dateutil.parser
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db
current_rounds_col = db['league_current_rounds']

# ==========================================
# 🛠️ CONFIGURAZIONE DEBUG / TEST
TEST_HOME = ""
TEST_AWAY = ""
DRY_RUN = False     # Se True, non scrive nel DB
# ==========================================

# --- 1. CARICAMENTO CALCOLATORE ---
path_calculators = r'C:\Progetti\simulatore-calcio-backend\ai_engine\calculators'
file_path = os.path.join(path_calculators, "calculator_bvs.py")

try:
    spec = importlib.util.spec_from_file_location("calculator_bvs", file_path)
    calculator_bvs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calculator_bvs)
    
    get_stats_from_ranking = calculator_bvs.get_stats_from_ranking
    calculate_theoretical_odds_professional = calculator_bvs.calculate_theoretical_odds_professional
    get_bvs_classification = calculator_bvs.get_bvs_classification
    calculate_team_bvs_score = calculator_bvs.calculate_team_bvs_score
except Exception as e:
    print(f"❌ Errore critico: {e}")
    sys.exit(1)

h2h_collection = db['h2h_by_round']
teams_collection = db['teams']

# Projection: solo i campi necessari per BVS
BVS_PROJECTION = {
    "_id": 1,
    "league": 1,
    "round_name": 1,
    "matches.home": 1,
    "matches.away": 1,
    "matches.odds": 1,
    "matches.h2h_data.odds": 1,
    "matches.h2h_data.qt_1": 1,
    "matches.h2h_data.qt_X": 1,
    "matches.h2h_data.qt_2": 1,
    "matches.h2h_data.bvs_index": 1,
    "matches.h2h_data.bvs_away": 1,
    "matches.date_obj": 1,
    "matches.date": 1,
    "matches.status": 1,
}

# --- 2. FUNZIONI DI NARRAZIONE (PURE ANALYTICS - NO BETTING JARGON) ---

def get_bvs_narrative(fase, is_linear, gap_reale, fav_stat, qt_1, qt_2, q_reale_fav, qt_fav):
    """
    Genera una narrazione tecnica.
    CORREZIONE: Ora specifica SEMPRE il soggetto (fav_stat) per non lasciare dubbi su chi deve vincere.
    """
    
    # 0. CHECK EQUILIBRIO (Gap Squadre < 0.50)
    gap_squadre = abs(qt_1 - qt_2)
    if gap_squadre < 0.50:
        phrases = [
            f"⚖️ Match in Stallo: I dati tecnici delle due squadre sono speculari. Impossibile stabilire una favorita.",
            f"⚖️ Equilibrio Totale: Le metriche dei nostri algoritmi indicano un equilibrio totale. Esito incerto.",
            f"⚖️ Nessuna Dominante: Gara da tripla, gli indicatori non si sbilanciano né sull'1 né sul 2.",
            f"⚖️ Forbice Stretta: Partita di difficile lettura, si consiglia di considerare alternative al 1X2."
        ]
        return random.choice(phrases)

    # 1. GESTIONE FASCIA ALTA (Discrepanza Positiva)
    if fase == "PURO" and 1.70 <= q_reale_fav <= 2.20:
        if qt_fav < 1.65 and gap_reale >= 15.0:
            phrases = [
                f"💎 Analisi Divergente: La nostra stima tecnica sul segno {fav_stat} è favorevole.",
                f"💎 Occasione Notevole: I dati indicano una superiorità del segno {fav_stat} da tenere in considerazione.",
                f"💎 Vantaggio Tecnico: I nostri modelli danno una buona certezza sulla forza reale del segno {fav_stat}.",
                f"💎 Segnale Forte: Nonostante l'incertezza statistica, i nostri indicatori confermano una buona solidità del {fav_stat}."
            ]
        else:
            phrases = [
                f"🛡️ Prudenza: I dati per il {fav_stat} sono buoni, ma la stabilità dei dati non è sufficiente per un segno fisso.",
                f"🛡️ Segnale Parziale: C'è un vantaggio statistico per il {fav_stat}, ma serve una copertura (Doppia Chance).",
                f"🛡️ Margine Ridotto: Il vantaggio del {fav_stat} è presente ma minimo, non giustifica un'esposizione piena.",
                f"🛡️ Cautela: La statistica sul {fav_stat} è favorevole, ma il contesto della gara suggerisce protezione."
            ]
        return random.choice(phrases)

    # 2. GESTIONE FASCIA ESTREMA (Alta Volatilità)
    if fase == "PURO" and q_reale_fav > 2.20:
         if qt_fav < 2.00 and gap_reale > 25.0:
             phrases = [
                f"🚀 Opportunità Estrema: Analisi controcorrente. I dati vedono il {fav_stat} favorito dove altri vedono un'impresa.",
                f"🚀 Discrepanza Enorme: I nostri algoritmi calcolano una probabilità per il segno {fav_stat} molto più alta del previsto.",
                f"🚀 Colpo Tecnico: Partita difficile, ma il vantaggio matematico sul {fav_stat} è sorprendentemente alto.",
                f"🚀 Visione Alternativa: I nostri modelli indicano una probabilità alta per il segno {fav_stat}, in netto contrasto con l'opinione comune."
             ]
         else:
             phrases = [
                f"⛔ Rischio Eccessivo: Anche se il {fav_stat} è favorito dai dati, i nostri indicatori indicano un rischio sorpesa per il segno.",
                f"⛔ Volatilità Alta: Le metriche del {fav_stat} non sono abbastanza solide per un segno fisso.",
                f"⛔ Azzardo: Situazione troppo instabile per puntare sul {fav_stat}. Probabile trappola."
            ]
         return random.choice(phrases)

    # 🟢 3. ZONA SICURA (Lineare)
    if fase == "PURO" and is_linear:
        phrases = [
            f"✅ Alta Affidabilità: Tutti gli indicatori tecnici confermano la solidità del segno {fav_stat}.",
            f"✅ Convergenza: I nostri calcoli sul {fav_stat} coincidono perfettamente con le aspettative generali.",
            f"✅ Luce Verde: Nessuna anomalia rilevata. Il favorito ({fav_stat}) ha un buon rapporto rischio/beneficio.",
            f"✅ Stabilità: Ottima coerenza tra i nostri indicatori e il potenziale per il segno {fav_stat}."
        ]
    
    # ALTRI CASI
    elif fase == "PURO" and not is_linear and gap_reale < 0:
        phrases = [
            f"📉 Rendimento Minimo: Il segno {fav_stat} è corretto, ma si consiglia prudenza.",
            f"📉 Svantaggio: Il rapporto rischio/beneficio non è favorevole per il segno {fav_stat}.",
            f"📉 Saturazione: Pronostico {fav_stat} probabile, valutare il rapporto rischio/beneficio."
        ]
        return random.choice(phrases)

    elif fase == "SEMI":
        # QUI C'ERA L'ERRORE: ORA SPECIFICHIAMO {fav_stat}
        phrases = [
            f"⚠️ Accordo Parziale: Il segno {fav_stat} è favorito, ma i dati suggeriscono cautela.",
            f"⚠️ Segnale Misto: Vittoria del {fav_stat} probabile, ma le metriche dei nostri algoritmi suggeriscono cautela, consiglio alla prudenza."
        ]
        return random.choice(phrases)
    
    else: 
        phrases = [
            f"⛔ Dati Discordanti: I modelli matematici non trovano consenso sull'esito finale. Evitare 1X2",
            f"⛔ Analisi Complessa: Le metriche delle due squadre sono troppo irregolari. Evitare 1X2."
        ]
        return random.choice(phrases)

    

def get_round_number_from_text(text):
    match = re.search(r'(\d+)', str(text))
    return int(match.group(1)) if match else 0

def find_target_rounds(league_docs, league_name=None):
    """Trova i 3 round target (prec/attuale/succ) usando league_current_rounds come ancora."""
    if not league_docs: return []
    sorted_docs = sorted(league_docs, key=lambda d: get_round_number_from_text(d.get('round_name', '0')))

    anchor_index = -1

    # Metodo primario: leggi current_round da league_current_rounds
    if league_name:
        cr_doc = current_rounds_col.find_one({"league": league_name})
        if cr_doc and cr_doc.get("current_round") is not None:
            current_round = cr_doc["current_round"]
            for i, doc in enumerate(sorted_docs):
                if get_round_number_from_text(doc.get('round_name', '0')) == current_round:
                    anchor_index = i
                    break

    # Fallback: media date
    if anchor_index == -1:
        now = datetime.now()
        min_diff = float('inf')
        for i, doc in enumerate(sorted_docs):
            dates = []
            for m in doc.get('matches', []):
                d_raw = m.get('date_obj') or m.get('date')
                try:
                    if d_raw:
                        d = d_raw if isinstance(d_raw, datetime) else dateutil.parser.parse(d_raw)
                        dates.append(d.replace(tzinfo=None))
                except: pass
            if dates:
                avg_date = sum([d.timestamp() for d in dates]) / len(dates)
                diff = abs(now.timestamp() - avg_date)
                if diff < min_diff: min_diff = diff; anchor_index = i

    if anchor_index == -1: return []
    start_idx = max(0, anchor_index - 1)
    end_idx = min(len(sorted_docs), anchor_index + 2)
    return sorted_docs[start_idx:end_idx]

def calculate_match_index_display(p_h, p_a, fase, diff_perc, is_linear):
    base = (abs(p_h) + abs(p_a)) / 2
    bonus = 2.0 if fase == "PURO" else (0.5 if fase == "SEMI" else -3.0)
    penale = diff_perc / 5
    if not is_linear: penale += 2.0
    return round(max(-6, min(7, base + bonus - penale)), 2)

def get_trust_letter(score):
    if score >= 5.0: return "A"
    if score >= 2.5: return "B"
    if score >= 0.0: return "C"
    if score >= -2.0: return "D"
    return "E"

# --- 3. LOOP PRINCIPALE ---
def update_bvs_system():
    _start_time = datetime.now()
    print(f"[{_start_time.strftime('%H:%M:%S')}] 🏁 AVVIO BVS (Analisi Tecnica Pura)")
    t_home = TEST_HOME.strip()
    t_away = TEST_AWAY.strip()
    TEST_MODE = bool(t_home and t_away)

    if TEST_MODE:
        print(f"⚠️  MODALITÀ TEST: {t_home} vs {t_away}")
    else:
        print("ℹ️  MODALITÀ AUTOMATICA: Prec / Attuale / Succ")

    # Cache teams in memoria (una sola query)
    all_teams = list(teams_collection.find({}))
    bulk_cache = {"TEAMS": all_teams}
    print(f"   📦 Cache teams: {len(all_teams)} squadre caricate")

    leagues = h2h_collection.distinct("league")
    total_updated = 0
    test_match_found = False

    for league in leagues:
        if not TEST_MODE: print(f"\n🏆 {league}...", end="")
        league_docs = list(h2h_collection.find({"league": league}, BVS_PROJECTION))
        
        target_docs = league_docs if TEST_MODE else find_target_rounds(league_docs, league_name=league)
        if not target_docs: continue

        for doc in target_docs:
            matches = doc.get('matches', [])
            modificato = False
            
            for m in matches:
                home = m['home']
                away = m['away']

                if TEST_MODE:
                    if home != t_home or away != t_away: continue 
                    test_match_found = True
                    print(f"\n\n🎯 PARTITA TROVATA: {home} vs {away}")

                h2h_data = m.get('h2h_data', {})
                
                odds_obj = {}
                if h2h_data.get('odds') and h2h_data['odds'].get('1'):
                    odds_obj = h2h_data['odds']
                elif m.get('odds') and m['odds'].get('1'):
                    odds_obj = m['odds']

                if not odds_obj.get('1'): 
                    if TEST_MODE: print(f"   ❌ No Dati Esterni.")
                    continue
                
                stats_h = get_stats_from_ranking(home, bulk_cache=bulk_cache)
                stats_a = get_stats_from_ranking(away, bulk_cache=bulk_cache)
                if not stats_h or not stats_a: continue

                try:
                    theoretical = calculate_theoretical_odds_professional(stats_h, stats_a)
                    if not theoretical: continue
                    qt_1, qt_X, qt_2 = theoretical

                    qr_1 = float(odds_obj.get('1'))
                    qr_X = float(odds_obj.get('X'))
                    qr_2 = float(odds_obj.get('2'))
                    
                    # BVS CORE
                    class_data = get_bvs_classification(qt_1, qt_X, qt_2, qr_1, qr_X, qr_2)
                    score_h, _ = calculate_team_bvs_score('1', class_data, qr_1, qr_X, qr_2)
                    score_a, _ = calculate_team_bvs_score('2', class_data, qr_1, qr_X, qr_2)

                    fase = class_data['tipo']
                    is_lin = class_data['is_linear']
                    diff_abs = class_data['diff_perc']
                    
                    fav_sign = class_data['base_t']
                    q_teorica_fav = class_data['quote_map_t'][fav_sign]
                    q_reale_fav = class_data['quote_map_r'][fav_sign]
                    
                    # Calcolo Gap Reale (Lo usiamo solo internamente per classificare)
                    if q_teorica_fav > 0:
                        gap_reale = ((q_reale_fav - q_teorica_fav) / q_teorica_fav) * 100
                    else: gap_reale = 0
                        
                    match_idx = calculate_match_index_display(score_h, score_a, fase, diff_abs, is_lin)
                    
                    # Identifica parametro statistico della favorita
                    qt_fav = qt_1 if fav_sign == '1' else qt_2

                    # NARRAZIONE
                    advice_text = get_bvs_narrative(fase, is_lin, gap_reale, fav_sign, qt_1, qt_2, q_reale_fav, qt_fav)

                    # TIP MARKET INTELLIGENTE (SENZA PARLARE DI QUOTE)
                    gap_squadre = abs(qt_1 - qt_2)
                    
                    if gap_squadre < 0.50:
                         tip_m = "MATCH TROPPO EQUILIBRATO (NO BET)"
                         tip_s = "---"
                    elif fase == "PURO":
                        
                        # A. Fascia Intermedia (1.70 - 2.20)
                        if 1.70 <= q_reale_fav <= 2.20:
                             if qt_fav < 1.65 and gap_reale >= 15.0:
                                 tip_m = f"OPPORTUNITÀ NETTA: {fav_sign} (GAP TECNICO +{gap_reale:.0f}%)"
                             else:
                                 tip_m = f" {fav_sign} CON COPERTURA (DC)"
                        
                        # B. Fascia Alta (> 2.20)
                        elif q_reale_fav > 2.20:
                             if qt_fav < 2.00 and gap_reale > 25.0:
                                 tip_m = f"OPPORTUNITÀ ESTREMA: {fav_sign} (GAP TECNICO +{gap_reale:.0f}%)"
                                 tip_s = fav_sign
                             else:
                                 tip_m = "RISCHIO ECCESSIVO (NO BET 1X2)"
                                 tip_s = "---"
                        
                        # C. Fascia Bassa (< 1.70)
                        elif not is_lin: 
                            if gap_reale > 0: tip_m = f"VANTAGGIO TECNICO: {fav_sign} (GAP +{gap_reale:.0f}%)"
                            else: tip_m = f"RENDIMENTO BASSO: {fav_sign} (GAP {gap_reale:.0f}%)"
                        else:
                            tip_m = f"SEGNO {fav_sign}" 
                        
                        # Gestione Tip Sign
                        if "CON COPERTURA" in tip_m or "RISCHIO ECCESSIVO" in tip_m:
                            tip_s = fav_sign 
                        else:
                            tip_s = fav_sign

                    elif fase == "NON_BVS":
                        tip_m = "NO BET 1X2 -> VALUTARE GOL/OVER"
                        tip_s = "---"
                    else: # SEMI
                        tip_m = f"SEGNO {fav_sign} O DC"
                        tip_s = fav_sign

                    if TEST_MODE:
                        print(f"   📊 Cons: {tip_m}")
                        print(f"   🗣️  NARRAZIONE: {advice_text}")

                    new_vals = {
                        "qt_1": round(qt_1, 2), "qt_X": round(qt_X, 2), "qt_2": round(qt_2, 2),
                        "bvs_index": round(score_h, 2), "bvs_away": round(score_a, 2),
                        "bvs_match_index": match_idx,
                        "classification": fase, "is_linear": is_lin,
                        "diff_perc": round(diff_abs, 1), "gap_reale": round(gap_reale, 1),
                        "tip_sign": tip_s, "tip_market": tip_m,
                        "trust_home_letter": get_trust_letter(score_h),
                        "trust_away_letter": get_trust_letter(score_a),
                    }

                    if DRY_RUN:
                        # Confronta con valori esistenti nel DB
                        for k, v in new_vals.items():
                            old_v = h2h_data.get(k)
                            if old_v is not None and old_v != v:
                                print(f"   ⚠️ {home} vs {away}: {k} {old_v}→{v}")
                    else:
                        new_vals["bvs_advice"] = advice_text
                        new_vals["last_bvs_update"] = datetime.now()
                        h2h_data.update(new_vals)
                        modificato = True
                    total_updated += 1
                    
                except Exception as e:
                    if TEST_MODE: print(f"   ❌ ECCEZIONE: {e}")
                    continue
            
            if modificato and not DRY_RUN:
                h2h_collection.update_one({'_id': doc['_id']}, {'$set': {'matches': matches}})
                if TEST_MODE: return 

    elapsed = (datetime.now() - _start_time).total_seconds()
    print(f"\n{'='*50}\n✅ AGGIORNAMENTO COMPLETATO. Partite calcolate: {total_updated}\n⏱️ Tempo: {elapsed:.1f}s\n{'='*50}")

if __name__ == "__main__":
    update_bvs_system()