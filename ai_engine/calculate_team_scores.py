import pymongo
import statistics

# CONFIGURAZIONE DB
MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"

client = pymongo.MongoClient(MONGO_URI)
db = client["pup_pals_db"]
teams = db["teams"]

MAX_SCORE = 9.0  # scala finale 0-9


def compute_value_score_continuous(val, min_val, max_val):
    """
    Punteggio CONTINUO da valore rosa, normalizzato sul campionato.
    La squadra con valore minimo ha ~1.0, quella con valore massimo 9.0,
    le altre in mezzo con decimali.
    """
    if val is None or val <= 0:
        return 1.0  # evitiamo 0 se manca/è strano

    if max_val <= min_val:
        # tutti hanno lo stesso valore: punteggio medio
        return MAX_SCORE / 2.0

    # min-max scaling in [0,1]   ( (val - min) / (max-min) ) [web:247][web:250]
    norm = (val - min_val) / (max_val - min_val)
    if norm < 0:
        norm = 0.0
    if norm > 1:
        norm = 1.0

    # porta in [1,9] continuo
    score = 1.0 + norm * (MAX_SCORE - 1.0)
    return round(score, 4)  # teniamo qualche decimale in più per precisione


def compute_age_multiplier(age, ages):
    """
    Moltiplicatore età in base a:
    - A_min  = età media più bassa (rosa più giovane)
    - A_max  = età media più alta (rosa più vecchia)
    - A_mean = media delle età

    Regole:
    - A_mean = 1.0 (nessun effetto)
    - A_min  = 0.5 ( -50% )
    - A_max  = 1.5 ( +50% )
    Interpolazione lineare tra questi estremi.
    """
    if age is None or age <= 0:
        return 1.0

    ages_valid = [a for a in ages if isinstance(a, (int, float)) and a > 0]
    if len(ages_valid) < 2:
        return 1.0

    A_min = min(ages_valid)
    A_max = max(ages_valid)
    A_mean = statistics.mean(ages_valid)

    if A_max <= A_min:
        return 1.0

    # Giovane: sotto la media -> 1.0 .. 0.5
    if age < A_mean and A_mean > A_min:
        gioventu_norm = (A_mean - age) / (A_mean - A_min)
        if gioventu_norm < 0:
            gioventu_norm = 0.0
        if gioventu_norm > 1:
            gioventu_norm = 1.0
        mult = 1.0 - 0.5 * gioventu_norm
        return round(mult, 4)

    # Vecchia: sopra la media -> 1.0 .. 1.5
    if age > A_mean and A_max > A_mean:
        vecchiaia_norm = (age - A_mean) / (A_max - A_mean)
        if vecchiaia_norm < 0:
            vecchiaia_norm = 0.0
        if vecchiaia_norm > 1:
            vecchiaia_norm = 1.0
        mult = 1.0 + 0.5 * vecchiaia_norm
        return round(mult, 4)

    # Esattamente (o quasi) alla media
    return 1.0


def rescale_raw_strengths(raw_values):
    """
    Riscalamento min-max dei rawStrength in [0, MAX_SCORE].
    Se tutti uguali, restituisce tutti MAX_SCORE/2.
    raw_values: dict _id -> rawStrength
    """
    # QUI: usiamo i valori del dizionario, non le chiavi
    vals = [v for v in raw_values.values() if isinstance(v, (int, float))]
    if not vals:
        return None, None, {}

    raw_min = min(vals)
    raw_max = max(vals)

    scaled = {}
    if raw_max == raw_min:
        # tutte identiche: metà scala
        for _id, v in raw_values.items():
            scaled[_id] = round(MAX_SCORE / 2.0, 2)
        return raw_min, raw_max, scaled

    for _id, v in raw_values.items():
        # min-max scaling in [0, MAX_SCORE]
        norm = (v - raw_min) / (raw_max - raw_min)
        if norm < 0:
            norm = 0.0
        if norm > 1:
            norm = 1.0
        scaled_val = norm * MAX_SCORE
        scaled[_id] = round(scaled_val, 2)

    return raw_min, raw_max, scaled



def main():
    print("🧮 Calcolo punteggi squadre (0-9) da valore rosa + età media con doppia normalizzazione...")

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

        values = [t.get("stats", {}).get("marketValue", 0) for t in league_teams]
        ages = [t.get("stats", {}).get("avgAge", 0) for t in league_teams]

        values_valid = [v for v in values if isinstance(v, (int, float)) and v > 0]
        ages_valid = [a for a in ages if isinstance(a, (int, float)) and a > 0]

        if not values_valid or not ages_valid:
            print("   ⚠️ Mancano dati sufficienti (valore/età) per questo campionato, salto.")
            continue

        min_val, max_val = min(values_valid), max(values_valid)
        A_min, A_max = min(ages_valid), max(ages_valid)
        A_mean = statistics.mean(ages_valid)

        print(f"   Valore rosa: min={min_val:,.0f}€, max={max_val:,.0f}€")
        print(f"   Età media:   min={A_min:.1f}, media={A_mean:.1f}, max={A_max:.1f}")

        # 1) Calcolo valueScore continuo + ageMultiplier + rawStrength (può superare 9)
        raw_strengths = {}   # _id -> rawStrength
        per_team_data = {}   # cache per seconda passata

        for team in league_teams:
            stats = team.get("stats", {})
            val = stats.get("marketValue")
            age = stats.get("avgAge")

            value_score = compute_value_score_continuous(val, min_val, max_val)
            age_mult = compute_age_multiplier(age, ages_valid)
            raw_strength = value_score * age_mult  # può essere > 9 o < 1

            raw_strengths[team["_id"]] = raw_strength
            per_team_data[team["_id"]] = (team, value_score, age_mult, raw_strength)

        # 2) Riscalamento dei rawStrength in [0, MAX_SCORE]
        raw_min, raw_max, scaled_strengths = rescale_raw_strengths(raw_strengths)
        if raw_min is None:
            print("   ⚠️ Errore nel riscalamento rawStrength, salto campionato.")
            continue

        print(f"   RawStrength: min={raw_min:.2f}, max={raw_max:.2f} -> riscalati in 0-{MAX_SCORE:.0f}")

        # 3) Scrittura nel DB e stampa
        for _id, (team, value_score, age_mult, raw_strength) in per_team_data.items():
            final_score = scaled_strengths.get(_id, MAX_SCORE / 2.0)

            update_fields = {
                "stats.valueScore09": round(value_score, 2),    # solo valore, continuo
                "stats.ageMultiplier": round(age_mult, 4),      # 0.5 - 1.5
                "stats.rawStrength": round(raw_strength, 4),    # valore grezzo, può superare 9
                "stats.strengthScore09": float(final_score),    # 0-9 riscalato per il motore
            }

            teams.update_one(
                {"_id": _id},
                {"$set": update_fields}
            )
            total_updated += 1

            name = team.get("name", "???")
            print(
                f"   ✅ {name[:20]:<20} | ValScore={value_score:.2f} "
                f"| AgeMult={age_mult:.2f} | Raw={raw_strength:.2f} | Final={final_score:.2f}"
            )

    print(f"\n✅ Completato. Aggiornate {total_updated} squadre.")


if __name__ == "__main__":
    main()
