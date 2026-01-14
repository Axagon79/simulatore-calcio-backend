import os
import sys
# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db


teams_collection = db['teams']


def calculate_all():
    print("🚀 AVVIO CALCOLO TOTALE (ATTACCO + DIFESA)...")
    
    leagues = teams_collection.distinct("league")
    total_updated = 0


    for league in leagues:
        if not league: continue
        teams = list(teams_collection.find({"league": league}))
        if not teams: continue


        print(f"\n🏆 {league} ({len(teams)} squadre)")


        # --- 1. CALCOLO MEDIE LEGA ---
        tot_gf_h, tot_ga_h, tot_gp_h = 0, 0, 0
        tot_gf_a, tot_ga_a, tot_gp_a = 0, 0, 0


        for t in teams:
            r = t.get("ranking", {})
            h = r.get("homeStats", {})
            a = r.get("awayStats", {})


            # Accumulo Casa
            tot_gf_h += h.get("goalsFor", 0)
            tot_ga_h += h.get("goalsAgainst", 0)
            tot_gp_h += h.get("played", 0)
            
            # Accumulo Trasferta
            tot_gf_a += a.get("goalsFor", 0)
            tot_ga_a += a.get("goalsAgainst", 0)
            tot_gp_a += a.get("played", 0)


        # Medie Gol
        avg_gf_h = tot_gf_h / tot_gp_h if tot_gp_h > 0 else 1.0
        avg_ga_h = tot_ga_h / tot_gp_h if tot_gp_h > 0 else 1.0
        
        avg_gf_a = tot_gf_a / tot_gp_a if tot_gp_a > 0 else 1.0
        avg_ga_a = tot_ga_a / tot_gp_a if tot_gp_a > 0 else 1.0
        
        print(f"   📊 Media Gol Lega: Casa {avg_gf_h:.2f} | Trasferta {avg_gf_a:.2f}")


        # --- 2. CALCOLO E AGGIORNAMENTO SQUADRE ---
        for t in teams:
            r = t.get("ranking", {})
            h = r.get("homeStats", {})
            a = r.get("awayStats", {})


            # --- CASA ---
            gp_h = h.get("played", 0)
            gf_h = h.get("goalsFor", 0); ga_h = h.get("goalsAgainst", 0)
            
            if gp_h > 0:
                # Attacco Casa
                att_h_ratio = (gf_h / gp_h) / avg_gf_h
                pct_att_h = max(0, min(100, 50 + (att_h_ratio - 1) * 50))
                
                # Difesa Casa (Inverso: meno subisci meglio è)
                my_ga_avg = ga_h / gp_h
                if my_ga_avg == 0: my_ga_avg = 0.1 # Evita divisione zero
                def_h_ratio = my_ga_avg / avg_ga_h
                pct_def_h = max(0, min(100, 50 - (def_h_ratio - 1) * 50))
            else:
                pct_att_h = 50; pct_def_h = 50 # Default neutro


            # --- TRASFERTA ---
            gp_a = a.get("played", 0)
            gf_a = a.get("goalsFor", 0); ga_a = a.get("goalsAgainst", 0)
            
            if gp_a > 0:
                # Attacco Trasferta
                att_a_ratio = (gf_a / gp_a) / avg_gf_a
                pct_att_a = max(0, min(100, 50 + (att_a_ratio - 1) * 50))
                
                # Difesa Trasferta
                my_ga_avg_a = ga_a / gp_a
                if my_ga_avg_a == 0: my_ga_avg_a = 0.1
                def_a_ratio = my_ga_avg_a / avg_ga_a
                pct_def_a = max(0, min(100, 50 - (def_a_ratio - 1) * 50))
            else:
                pct_att_a = 50; pct_def_a = 50


            # ========================================
            # CONVERSIONE NUOVI RANGE (0-15 ATT, 0-10 DIF)
            # ========================================
            scores = {
                "attack_home": round((pct_att_h / 100) * 15, 2),    # ← 0-15 invece di 0-7
                "defense_home": round((pct_def_h / 100) * 10, 2),   # ← 0-10 invece di 0-7
                "attack_away": round((pct_att_a / 100) * 15, 2),    # ← 0-15 invece di 0-7
                "defense_away": round((pct_def_a / 100) * 10, 2)    # ← 0-10 invece di 0-7
            }


            # POTENZA TOTALE 0-25 (invece di 0-14)
            scores['home_power'] = round(scores['attack_home'] + scores['defense_home'], 2)
            scores['away_power'] = round(scores['attack_away'] + scores['defense_away'], 2)


            # Scrittura nel DB
            teams_collection.update_one(
                {"_id": t["_id"]},
                {"$set": {"scores": scores}}
            )
            total_updated += 1


    print(f"\n✅ AGGIORNAMENTO COMPLETATO! {total_updated} squadre hanno nuovi punteggi.")


if __name__ == "__main__":
    calculate_all()
    
    # 🔍 DEBUG: Verifica cosa è stato scritto nel DB
    print("\n" + "="*60)
    print("🔍 VERIFICA DATI SCRITTI NEL DB:")
    
    atalanta = teams_collection.find_one({"name": "Atalanta"})
    if atalanta:
        scores = atalanta.get('scores', {})
        print(f"   Atalanta attack_home: {scores.get('attack_home', 'N/A')}")
        print(f"   Atalanta defense_home: {scores.get('defense_home', 'N/A')}")
        print(f"   Atalanta home_power: {scores.get('home_power', 'N/A')}")
    else:
        print("   ❌ Atalanta NON trovata!")
    
    cagliari = teams_collection.find_one({"name": "Cagliari"})
    if cagliari:
        scores = cagliari.get('scores', {})
        print(f"   Cagliari attack_away: {scores.get('attack_away', 'N/A')}")
        print(f"   Cagliari defense_away: {scores.get('defense_away', 'N/A')}")
        print(f"   Cagliari away_power: {scores.get('away_power', 'N/A')}")
    else:
        print("   ❌ Cagliari NON trovata!")
    
    print("="*60)

