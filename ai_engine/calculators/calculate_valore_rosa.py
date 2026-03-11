import statistics
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import db  # ← CENTRALIZZATO!

teams = db["teams"]

MAX_SCORE = 10.0  # Punteggio massimo teorico

def compute_value_score_split(val, min_val, max_val, mean_val):
    """
    Calcola il punteggio:
    - Valore Minimo -> 1.0 (Così i moltiplicatori funzionano!)
    - Valore Medio  -> 4.5
    - Valore Massimo -> 9.0
    """
    if val is None or val < 0:
        return 1.0  # Base minima di sicurezza

    # Caso limite: tutti uguali
    if max_val <= min_val:
        return 4.5

    # SOTTO LA MEDIA: scala da 1.0 a 4.5
    if val <= mean_val:
        if mean_val == min_val:
            return 4.5
        
        # Percentuale di distanza (0=minimo, 1=media)
        pct = (val - min_val) / (mean_val - min_val)
        
        # Formula: parte da 1.0 e aggiunge fino ad arrivare a 4.5
        # (4.5 - 1.0 = 3.5 di spazio)
        return 1.0 + (pct * 4.0)

    # SOPRA LA MEDIA: scala da 4.5 a 9.0 (uguale a prima)
    else:
        if max_val == mean_val:
            return 4.5
        pct = (val - mean_val) / (max_val - mean_val)
        return 5.0 + (pct * 5.0)



def compute_age_multiplier(age, ages):
    """
    Logica lineare richiesta:
    - Età Media  -> 1.0 (invariato)
    - Età Minima -> 0.5 (tolgo 50%)
    - Età Massima -> 1.5 (aggiungo 50%)
    """
    if age is None or age <= 0:
        return 1.0

    ages_valid = [a for a in ages if isinstance(a, (int, float)) and a > 0]
    if len(ages_valid) < 2:
        return 1.0

    A_min = min(ages_valid)
    A_max = max(ages_valid)
    A_mean = statistics.mean(ages_valid)

    # Protezione divisione per zero
    if A_max <= A_min:
        return 1.0

    # Caso GIOVANE (sotto media): scende linearmente da 1.0 a 0.5
    if age <= A_mean:
        if A_mean == A_min: # Evita divisione per zero
            return 1.0
        # Quanto sono lontano dalla media verso il basso?
        distanza_norm = (A_mean - age) / (A_mean - A_min)
        # Se sono al minimo (distanza=1), tolgo 0.5. Se sono alla media (distanza=0), tolgo 0.
        mult = 1.0 - (0.3 * distanza_norm)
        
        # Sicurezza per non andare sotto 0.5 (es. se age < A_min per qualche errore dati)
        if mult < 3.0: mult = 3.0
        return round(mult, 4)

    # Caso VECCHIO (sopra media): sale linearmente da 1.0 a 1.5
    else:
        if A_max == A_mean: # Evita divisione per zero
            return 1.0
        # Quanto sono lontano dalla media verso l'alto?
        distanza_norm = (age - A_mean) / (A_max - A_mean)
        # Se sono al massimo (distanza=1), aggiungo 0.5.
        mult = 1.0 + (0.3 * distanza_norm)

        # Sicurezza per non andare sopra 1.5
        if mult > 1.5: mult = 1.5
        return round(mult, 4)

# // aggiunto per: logica bulk - Funzione core per calcolo ibrido
def compute_team_value_logic(val, age, values_valid, ages_valid):
    """Esegue la logica di calcolo del punteggio finale basata sulle liste della lega"""
    if not values_valid or not ages_valid:
        return 1.0, 1.0, 3.0

    min_val, max_val = min(values_valid), max(values_valid)
    mean_val = statistics.mean(values_valid)

    # 1. Calcolo Base (0-9 con media a 4.5)
    value_score = compute_value_score_split(val, min_val, max_val, mean_val)
    
    # 2. Calcolo Moltiplicatore Età (0.5 - 1.5)
    age_mult = compute_age_multiplier(age, ages_valid)
    
    # 3. Punteggio Finale
    final_score = value_score * age_mult

    if final_score > 10.0:
        final_score = 10.0
    if final_score < 3.0:
        final_score = 3.0
        
    return round(value_score, 2), round(age_mult, 4), round(final_score, 2)

# // aggiunto per: logica bulk - Interfaccia per Engine Core
def get_value_score_live_bulk(team_name, league_name, bulk_cache):
    """
    Calcola il valore rosa in tempo reale usando il bulk_cache.
    """
    if not bulk_cache or "TEAMS" not in bulk_cache:
        return 5.0 # Fallback neutro

    league_teams = [t for t in bulk_cache["TEAMS"] if t.get("league") == league_name]
    if not league_teams:
        return 5.0

    values_valid = [t.get("stats", {}).get("marketValue") or 0 for t in league_teams if (t.get("stats", {}).get("marketValue") or 0) > 0]
    ages_valid = [t.get("stats", {}).get("avgAge") or 0 for t in league_teams if (t.get("stats", {}).get("avgAge") or 0) > 0]
    
    # RICERCA TARGET TEAM (FIX ALIAS BLINDATO)
    target_team = None
    for t in league_teams:
        # 1. Nome Esatto
        if t.get("name") == team_name:
            target_team = t; break
        
        # 2. Check Alias (Lista o Dizionario)
        aliases = t.get("aliases", [])
        if isinstance(aliases, list):
            if team_name in aliases: target_team = t; break
        elif isinstance(aliases, dict):
            if team_name in aliases.values(): target_team = t; break
            
    if not target_team: return 5.0
    
    val = target_team.get("stats", {}).get("marketValue", 0)
    age = target_team.get("stats", {}).get("avgAge", 0)
    
    _, _, final_score = compute_team_value_logic(val, age, values_valid, ages_valid)
    return final_score

def main():
    print("🧮 Calcolo punteggi squadre (0-9) con logica Mean=4.5 e Age +/- 50%...")

    cursor = teams.find({
        "stats.marketValue": {"$exists": True},
        "stats.avgAge": {"$exists": True},
    })

    # Raggruppa per campionato
    leagues = {}
    for team in cursor:
        league = team.get("league")
        if not league:
            continue
        leagues.setdefault(league, []).append(team)

    total_updated = 0

    for league, league_teams in leagues.items():
        print(f"\n🏆 Campionato: {league}")

        values_valid = [t.get("stats", {}).get("marketValue", 0) for t in league_teams if isinstance(t.get("stats", {}).get("marketValue"), (int, float)) and t.get("stats", {}).get("marketValue", 0) > 0]
        ages_valid = [t.get("stats", {}).get("avgAge", 0) for t in league_teams if isinstance(t.get("stats", {}).get("avgAge"), (int, float)) and t.get("stats", {}).get("avgAge", 0) > 0]

        if not values_valid or not ages_valid:
            print("   ⚠️ Mancano dati sufficienti, salto.")
            continue

        # // modificato per: logica bulk - Calcolo medie per log (preservato ordine originale)
        min_val, max_val = min(values_valid), max(values_valid)
        mean_val = statistics.mean(values_valid)
        A_min, A_max = min(ages_valid), max(ages_valid)
        A_mean = statistics.mean(ages_valid)

        print(f"   Valore: min={min_val:,.0f}, Avg={mean_val:,.0f} (->4.5), max={max_val:,.0f}")
        print(f"   Età:    min={A_min:.1f} (x0.5), Avg={A_mean:.1f} (x1.0), max={A_max:.1f} (x1.5)")

        for team in league_teams:
            stats = team.get("stats", {})
            val = stats.get("marketValue", 0)
            age = stats.get("avgAge", 0)

            # // modificato per: logica bulk - Uso della nuova funzione core
            value_score, age_mult, final_score = compute_team_value_logic(val, age, values_valid, ages_valid)

            update_fields = {
                "stats.valueScore09": value_score,
                "stats.ageMultiplier": age_mult,
                "stats.strengthScore09": final_score,
            }

            teams.update_one(
                {"_id": team["_id"]},
                {"$set": update_fields}
            )
            total_updated += 1

            name = team.get("name", "???")
            print(
                f"   ✅ {name[:20]:<20} | Val={val:,.0f} -> Score={value_score:.2f} "
                f"| Età={age:.1f} -> x{age_mult:.2f} | FINAL={final_score:.2f}"
            )

    print(f"\n✅ Completato. Aggiornate {total_updated} squadre.")

if __name__ == "__main__":
    main()