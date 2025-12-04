import sys
import os
from datetime import datetime, timedelta

# --- FIX PERCORSI ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)  # ai_engine
sys.path.insert(0, parent_dir)

from config import db

# CONFIGURAZIONE (Deve combaciare col tuo DB)
SOURCE_COLLECTION = "raw_h2h_data_v2"  # <--- La collezione che hai scelto di tenere

def parse_date(date_str):
    formats = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def calculate_match_points(winner, home_name_db, away_name_db, home_pos, away_pos):
    # ... (Logica identica al tuo calcolatore PRO) ...
    
    if not home_pos: home_pos = 10
    if not away_pos: away_pos = 10

    is_home_winner = winner.lower() in home_name_db.lower() or home_name_db.lower() in winner.lower()
    is_away_winner = winner.lower() in away_name_db.lower() or away_name_db.lower() in winner.lower()
    
    points_h = 0.0
    points_a = 0.0

    if is_home_winner:
        difficulty_mult = 1.0 + (home_pos - away_pos) * 0.02
        difficulty_mult = max(0.5, min(1.5, difficulty_mult))
        points_h = 3.0 * difficulty_mult
        
    elif is_away_winner:
        difficulty_mult = 1.0 + (away_pos - home_pos) * 0.02
        difficulty_mult = max(0.5, min(1.5, difficulty_mult))
        points_a = 3.0 * difficulty_mult
        
    elif winner == "Draw" or winner == "-":
        bonus_h = (home_pos - away_pos) * 0.05
        points_h = (1.0 + bonus_h) * 0.9
        points_h = max(0.2, min(2.0, points_h))

        bonus_a = (away_pos - home_pos) * 0.05
        points_a = (1.0 + bonus_a) * 1.1
        points_a = max(0.2, min(2.0, points_a))
        
    return points_h, points_a

def test_confronto(squadra_A, squadra_B):
    print(f"\n🥊 CONFRONTO SIMULATO: {squadra_A} (Casa) vs {squadra_B} (Trasferta)")
    print("=" * 60)
    
    # 1. Trova i dati grezzi
    doc = db[SOURCE_COLLECTION].find_one({
        "$or": [
            {"team_a": squadra_A, "team_b": squadra_B},
            {"team_a": squadra_B, "team_b": squadra_A},
        ]
    })
    
    if not doc:
        print("❌ Nessun dato storico trovato tra queste due squadre.")
        return

    matches = doc.get("matches", [])
    print(f"📚 Trovate {len(matches)} partite nello storico totale.")
    
    w_score_h = 0.0
    w_score_a = 0.0
    valid_matches = 0
    
    current_date = datetime.now()
    cutoff_20y = current_date - timedelta(days=365*20)
    cutoff_5y = current_date - timedelta(days=365*5)

    print("\n📝 DETTAGLIO CALCOLO PARTITA PER PARTITA:")
    print("-" * 60)
    
    for m in matches:
        if m.get("score") == "-:-": continue
        
        d_obj = parse_date(m.get("date"))
        if not d_obj or d_obj < cutoff_20y: continue
        
        # Peso temporale
        time_weight = 1.0 if d_obj >= cutoff_5y else 0.5
        time_str = "RECENTE (x1.0)" if time_weight == 1.0 else "VECCHIA (x0.5)"
        
        # Dati storici
        hist_h = m.get("home_team")
        hist_a = m.get("away_team")
        h_pos = m.get("home_pos", 10)
        a_pos = m.get("away_pos", 10)
        winner = m.get("winner")
        score = m.get("score")
        
        # Calcolo punti grezzi
        pts_h, pts_a = calculate_match_points(winner, hist_h, hist_a, h_pos, a_pos)
        
        # Assegnazione a Squadra A o B
        punti_A_partita = 0
        punti_B_partita = 0
        
        # Se A era in casa
        if squadra_A in hist_h: 
            punti_A_partita = pts_h * time_weight
            punti_B_partita = pts_a * time_weight
            desc = f"{hist_h}({h_pos}) vs {hist_a}({a_pos})"
        # Se A era fuori
        elif squadra_A in hist_a:
            punti_A_partita = pts_a * time_weight
            punti_B_partita = pts_h * time_weight
            desc = f"{hist_h}({h_pos}) vs {hist_a}({a_pos})"
        
        w_score_h += punti_A_partita
        w_score_a += punti_B_partita
        valid_matches += 1
        
        print(f"📅 {m.get('date')} | {score} | {desc:<30} | Win: {winner}")
        print(f"   -> Punti {squadra_A}: {punti_A_partita:.2f} | Punti {squadra_B}: {punti_B_partita:.2f} [{time_str}]")

    print("-" * 60)
    
    # Risultato Finale
    if (w_score_h + w_score_a) == 0:
        norm_h, norm_a = 5.0, 5.0
    else:
        norm_h = (w_score_h / (w_score_h + w_score_a)) * 10
        norm_a = (w_score_a / (w_score_h + w_score_a)) * 10
        
    print(f"\n📊 RISULTATO H2H CALCULATOR:")
    print(f"   {squadra_A} Score: {norm_h:.2f} / 10")
    print(f"   {squadra_B} Score: {norm_a:.2f} / 10")
    
    delta = norm_h - norm_a
    print(f"\n💡 INTERPRETAZIONE:")
    if abs(delta) < 1:
        print("   Equilibrio Sostanziale.")
    elif delta > 1:
        print(f"   Vantaggio Storico per {squadra_A} (+{delta:.2f})")
    else:
        print(f"   Vantaggio Storico per {squadra_B} (+{abs(delta):.2f})")

# --- ESEGUI IL TEST ---
if __name__ == "__main__":
    # Cambia i nomi qui per testare altre coppie
    # Assicurati di usare i nomi ESATTI o molto simili a quelli nel DB (es. "A. Cerignola", "Altamura")
    test_confronto("Benevento", "Giugliano")
