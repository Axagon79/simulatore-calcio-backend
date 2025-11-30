import pymongo

# --- INPUT ---
HOME_TEAM = "Roma" 
AWAY_TEAM = "Inter"
# -------------

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"
client = pymongo.MongoClient(MONGO_URI)
db = client['pup_pals_db']
teams_collection = db['teams']

def smart_search(user_input):
    # 1. Cerca nome esatto
    t = teams_collection.find_one({"name": user_input})
    if t: return t
    # 2. Cerca parziale (case insensitive)
    t = teams_collection.find_one({"name": {"$regex": user_input, "$options": "i"}})
    if t: return t
    # 3. Cerca negli alias
    return teams_collection.find_one({"$or": [{"aliases": user_input}, {"aliases.soccerstats": user_input}]})

def show_preview_with_reality_check(home, away):
    t_h = smart_search(home)
    t_a = smart_search(away)

    if not t_h or not t_a:
        print("❌ Errore: Squadre non trovate.")
        return

    print(f"\n📊 ANALISI MATEMATICA: {t_h['name']} vs {t_a['name']}")
    print("="*60)

    # DATI CASA
    h_stats = t_h.get('ranking', {}).get('homeStats', {})
    h_played = h_stats.get('played', 0)
    h_gf = h_stats.get('goalsFor', 0)
    h_ga = h_stats.get('goalsAgainst', 0)
    
    h_att_score = t_h.get('scores', {}).get('attack_home', 3.5)
    h_def_score = t_h.get('scores', {}).get('defense_home', 3.5)

    print(f"🏠 {t_h['name']} (in Casa)")
    print(f"   Stats Reali: {h_played} partite | {h_gf} gol fatti | {h_ga} gol subiti")
    print(f"   Media Reale: Segna {h_gf/h_played:.2f} a partita | Subisce {h_ga/h_played:.2f} a partita")
    print(f"   👉 VOTO ATTACCO: {h_att_score} / 7")
    print(f"   👉 VOTO DIFESA:  {h_def_score} / 7")
    print("-" * 60)

    # DATI TRASFERTA
    a_stats = t_a.get('ranking', {}).get('awayStats', {})
    a_played = a_stats.get('played', 0)
    a_gf = a_stats.get('goalsFor', 0)
    a_ga = a_stats.get('goalsAgainst', 0)

    a_att_score = t_a.get('scores', {}).get('attack_away', 3.5)
    a_def_score = t_a.get('scores', {}).get('defense_away', 3.5)

    print(f"✈️  {t_a['name']} (in Trasferta)")
    print(f"   Stats Reali: {a_played} partite | {a_gf} gol fatti | {a_ga} gol subiti")
    print(f"   Media Reale: Segna {a_gf/a_played:.2f} a partita | Subisce {a_ga/a_played:.2f} a partita")
    print(f"   👉 VOTO ATTACCO: {a_att_score} / 7")
    print(f"   👉 VOTO DIFESA:  {a_def_score} / 7")
    print("="*60)

    # CONFRONTO DIRETTO
    print("\n🧠 IL CERVELLO VEDE:")
    delta = h_att_score - a_def_score
    print(f"   Attacco {t_h['name']} ({h_att_score}) vs Difesa {t_a['name']} ({a_def_score})")
    print(f"   Differenza: {delta:+.2f}")
    
    if a_ga/a_played > 1.5:
        print(f"   ⚠️ NOTA: {t_a['name']} sta subendo più di 1.5 gol a partita fuori casa!")
        print("      Ecco perché il voto difesa è basso.")

if __name__ == "__main__":
    show_preview_with_reality_check(HOME_TEAM, AWAY_TEAM)
