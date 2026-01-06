import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

"""
CALCOLO RATING SQUADRA - VERSIONE DEFINITIVA
GK ordinati per minutes_90s (come DEF/MID/ATT)
"""


# ==================== CONFIGURAZIONE ====================

DB_NAME = db.name

FORMATION_MAPPING = {
    "3-4-2-1": "3-4-3",
    "4-2-2-2": "4-4-2",
    "4-2-3-1": "4-5-1",
    "4-3-1-2": "4-3-3",
}

DEFAULT_FORMATION = "4-3-3"

# ==================== CONNESSIONE DB ====================


teams_col = db["teams"]
gk_col = db["players_stats_fbref_gk"]
def_col = db["players_stats_fbref_def"]
mid_col = db["players_stats_fbref_mid"]
att_col = db["players_stats_fbref_att"]


# ==================== FUNZIONI ====================

def check_rating_anomalies():
    """Verifica rating anomali"""
    print("\n🔍 CONTROLLO INTEGRITÀ DATI...")
    
    anomalies = []
    collections_config = [
        ("GK", gk_col, "gk_rating.rating_puro"),
        ("DEF", def_col, "def_rating.rating_puro"),
        ("MID", mid_col, "mid_rating.rating_puro"),
        ("ATT", att_col, "att_rating.rating_puro")
    ]
    
    for col_name, collection, rating_field in collections_config:
        bad_ratings = list(collection.find({
            "$or": [
                {rating_field: {"$lt": 4}},
                {rating_field: {"$gt": 10}},
                {rating_field: {"$exists": False}},
                {rating_field: None}
            ]
        }, {"player_name_fbref": 1, "team_name_fbref": 1, "league_name": 1, rating_field: 1, "_id": 0}))
        
        for player in bad_ratings:
            rating_parts = rating_field.split(".")
            rating_value = player.get(rating_parts[0], {})
            if isinstance(rating_value, dict):
                rating_value = rating_value.get(rating_parts[1], "NULL")
            
            anomalies.append({
                "role": col_name,
                "player": player.get("player_name_fbref", "N/A"),
                "squad": player.get("team_name_fbref", "N/A"),
                "league": player.get("league_name", "N/A"),
                "rating": rating_value
            })
    
    if anomalies:
        print("\n" + "="*70)
        print("❌ ERRORE CRITICO: RATING ANOMALI!")
        print("="*70)
        print(f"\n   Trovati {len(anomalies)} giocatori con rating non valido\n")
        
        for i, anom in enumerate(anomalies[:20], 1):
            print(f"   {i:2}. [{anom['role']:3}] {anom['player']:30} | Rating: {anom['rating']}")
        
        if len(anomalies) > 20:
            print(f"\n   ... e altri {len(anomalies) - 20}")
        
        print("\n" + "="*70 + "\n")
        return False
    
    print("   ✅ Tutti i rating validi (4.0 - 10.0)\n")
    return True


def parse_formation(formation_str):
    """Converte modulo in {DIF, MID, ATT}"""
    if not formation_str:
        formation_str = DEFAULT_FORMATION
    
    formation_clean = formation_str.strip()
    
    if formation_clean in FORMATION_MAPPING:
        converted = FORMATION_MAPPING[formation_clean]
        print(f"   📐 Convertito: {formation_clean} → {converted}")
        formation_clean = converted
    
    parts = formation_clean.split("-")
    
    try:
        numbers = [int(p.strip()) for p in parts]
    except (ValueError, AttributeError):
        numbers = [4, 3, 3]
    
    if len(numbers) == 3:
        return {"DIF": numbers[0], "MID": numbers[1], "ATT": numbers[2]}
    else:
        return {"DIF": 4, "MID": 3, "ATT": 3}


def get_team_aliases(team_doc):
    """Estrae tutti i possibili nomi della squadra"""
    aliases = [team_doc.get("name")]
    
    if "aliases" in team_doc and isinstance(team_doc["aliases"], list):
        aliases.extend(team_doc["aliases"])
    
    if "aliases_transfermarkt" in team_doc:
        aliases.append(team_doc["aliases_transfermarkt"])
    
    return list(set([a for a in aliases if a]))


def get_gk_by_minutes(league, team_aliases):
    """
    ⭐ AGGIORNATO: Recupera GK ordinati per MINUTES_90S (non rating)
    """
    players = list(gk_col.find(
        {
            "team_name_fbref": {"$in": team_aliases},
            "league_name": league,
            "gk_rating.rating_puro": {"$gte": 4, "$lte": 10, "$ne": None},
            "minutes_90s": {"$gte": 0, "$ne": None}  # ⭐ Filtra anche per minuti
        },
        {"player_name_fbref": 1, "gk_rating.rating_puro": 1, "minutes_90s": 1, "_id": 0}
    ).sort("minutes_90s", -1))  # ⭐ ORDINA PER MINUTI (non rating!)
    
    result = []
    for p in players:
        result.append({
            "player": p.get("player_name_fbref", "N/A"),
            "rating": p.get("gk_rating", {}).get("rating_puro", 0),
            "minutes_90s": p.get("minutes_90s", 0)  # ⭐ Ora ha minuti reali
        })
    
    return result


def get_players_by_minutes(league, role_collection, rating_field, team_aliases):
    """Recupera giocatori ordinati per minutes_90s"""
    players = list(role_collection.find(
        {
            "team_name_fbref": {"$in": team_aliases},
            "league_name": league,
            f"{rating_field}.rating_puro": {"$gte": 4, "$lte": 10, "$ne": None},
            "minutes_90s": {"$gte": 0, "$ne": None}
        },
        {"player_name_fbref": 1, rating_field: 1, "minutes_90s": 1, "_id": 0}
    ).sort("minutes_90s", -1))
    
    result = []
    for p in players:
        rating_obj = p.get(rating_field, {})
        result.append({
            "player": p.get("player_name_fbref", "N/A"),
            "rating": rating_obj.get("rating_puro", 0) if isinstance(rating_obj, dict) else 0,
            "minutes_90s": p.get("minutes_90s", 0)
        })
    
    return result


def calculate_bench_rating(base_rating, minutes_90s, max_minutes_90s):
    """Calcola rating effettivo panchinari"""
    if max_minutes_90s == 0 or max_minutes_90s is None:
        max_minutes_90s = 0.1
    
    minutes_percentage = minutes_90s / max_minutes_90s
    multiplier = 0.8 + (0.2 * minutes_percentage)
    return base_rating * multiplier


def calculate_team_rating(team_name, verbose=True, bulk_cache=None):
    """Calcola rating squadra usando Bulk Cache se disponibile"""
    if verbose:
        print(f"\n{'='*70}\n⚽ CALCOLO RATING: {team_name}\n{'='*70}")
    
    team = None
    # 1. RICERCA TEAM (BULK O DB)
    if bulk_cache and "TEAMS" in bulk_cache:
        for t in bulk_cache["TEAMS"]:
            # --- FIX ALIAS BLINDATO ---
            aliases = t.get("aliases", [])
            match_found = False
            
            # 1. Controlla Nome Esatto
            if t.get("name") == team_name:
                match_found = True
            
            # 2. Controlla Alias (Lista o Dizionario)
            elif isinstance(aliases, list):
                if team_name in aliases: match_found = True
            elif isinstance(aliases, dict):
                if team_name == aliases.get("soccerstats"): match_found = True
            
            if match_found:
                # Sostituisci 'target_team' con il nome della variabile usata nel tuo file (es. team, squad, ecc.)
                # Esempio:
                target_team = t 
                break
            # --------------------------
    else:
        team = teams_col.find_one({"name": team_name}) or teams_col.find_one({"aliases": team_name})

    if not team:
        if verbose: print(f"\n❌ SQUADRA '{team_name}' NON TROVATA\n")
        return None

    
    formation_str = team.get("formation", DEFAULT_FORMATION)
    league = team.get("league", "N/A")
            # ⭐ SERIE C SPECIALE
    if "Serie C" in league:
        strength_09 = team.get("stats", {}).get("strengthScore09", 5.0)

        rating_0_10 = strength_09 * 0.9
        
        # CONVERSIONE A 5-25
        rating_5_25 = 5 + (rating_0_10 * 2)
        rating_5_25 = max(5, min(25, rating_5_25))
        
        print(f"\n======================================================================")
        print(f"⚽ CALCOLO RATING: {team_name}")
        print(f"======================================================================")
        print(f"\n📋 {league}")
        print(f"   📊 strengthScore09: {strength_09:.2f}/9")
        print(f"   🎯 RATING: {rating_0_10:.2f}/10 → {rating_5_25:.2f}/25")
        print(f"{'='*70}\n")
        
        return {
            "team": team_name,
            "league": league,
            "formation": "4-3-3",
            "rating_0_10": round(rating_0_10, 2),
            "rating_5_25": round(rating_5_25, 2)
        }



    team_aliases = get_team_aliases(team)
    
    print(f"\n📋 Lega: {league}")
    print(f"🏷️  Alias: {', '.join(team_aliases)}")
    
    formation = parse_formation(formation_str)
    print(f"   → DEF:{formation['DIF']} MID:{formation['MID']} ATT:{formation['ATT']}")
    
    # 2. RECUPERO GIOCATORI (BULK O DB)
    if bulk_cache and "ROSE" in bulk_cache:
        def filter_bulk(role):
            players = [p for p in bulk_cache["ROSE"][role] if p.get("team_name_fbref") in team_aliases]
            return sorted(players, key=lambda x: x.get("minutes_90s", 0), reverse=True)
        
        all_gk = [{"player": p["player_name_fbref"], "rating": p.get("gk_rating", {}).get("rating_puro", 0), "minutes_90s": p.get("minutes_90s", 0)} for p in filter_bulk("GK")]
        all_def = [{"player": p["player_name_fbref"], "rating": p.get("def_rating", {}).get("rating_puro", 0), "minutes_90s": p.get("minutes_90s", 0)} for p in filter_bulk("DEF")]
        all_mid = [{"player": p["player_name_fbref"], "rating": p.get("mid_rating", {}).get("rating_puro", 0), "minutes_90s": p.get("minutes_90s", 0)} for p in filter_bulk("MID")]
        all_att = [{"player": p["player_name_fbref"], "rating": p.get("att_rating", {}).get("rating_puro", 0), "minutes_90s": p.get("minutes_90s", 0)} for p in filter_bulk("ATT")]
    else:
        all_gk = get_gk_by_minutes(league, team_aliases)
        all_def = get_players_by_minutes(league, def_col, "def_rating", team_aliases)
        all_mid = get_players_by_minutes(league, mid_col, "mid_rating", team_aliases)
        all_att = get_players_by_minutes(league, att_col, "att_rating", team_aliases)
    
    print(f"\n👥 Giocatori:")
    print(f"   GK:  {len(all_gk)} (per minuti)")  # ⭐ CAMBIATO testo
    print(f"   DIF: {len(all_def)} (richiesti: {formation['DIF']})")
    print(f"   MID: {len(all_mid)} (richiesti: {formation['MID']})")
    print(f"   ATT: {len(all_att)} (richiesti: {formation['ATT']})")
    
    # 3. Portiere mancante
    if len(all_gk) == 0:
        print(f"\n   ⚠️  PORTIERE MANCANTE → media campo")
        all_field = all_def + all_mid + all_att
        if len(all_field) == 0:
            print(f"   ❌ Nessun giocatore\n")
            return None
        
        avg_rating = sum(p["rating"] for p in all_field) / len(all_field)
        all_gk = [{"player": "GK (media)", "rating": avg_rating, "minutes_90s": 0}]
        print(f"   → GK virtuale: {avg_rating:.2f}")
    
    # 4. Titolari
    starters = []
    
    starters.append({
        "role": "GK",
        "player": all_gk[0]["player"],
        "rating": all_gk[0]["rating"],
        "minutes_90s": all_gk[0]["minutes_90s"]  # ⭐ Ora mostra minuti reali
    })
    
    for i in range(min(formation["DIF"], len(all_def))):
        starters.append({
            "role": "DIF",
            "player": all_def[i]["player"],
            "rating": all_def[i]["rating"],
            "minutes_90s": all_def[i]["minutes_90s"]
        })
    
    for i in range(min(formation["MID"], len(all_mid))):
        starters.append({
            "role": "MID",
            "player": all_mid[i]["player"],
            "rating": all_mid[i]["rating"],
            "minutes_90s": all_mid[i]["minutes_90s"]
        })
    
    for i in range(min(formation["ATT"], len(all_att))):
        starters.append({
            "role": "ATT",
            "player": all_att[i]["player"],
            "rating": all_att[i]["rating"],
            "minutes_90s": all_att[i]["minutes_90s"]
        })
    
        # 5. PANCHINA (con rimpiazzi se necessario)
    bench = []
    
    # Traccia chi è già stato usato (titolari + panchina)
    used_players = set([p["player"] for p in starters])
    
    # === PORTIERE RISERVA ===
    if len(all_gk) > 1:
        bench_gk = all_gk[1]
        max_gk_minutes = all_gk[0]["minutes_90s"]
        
        bench.append({
            "role": "GK",
            "player": bench_gk["player"],
            "rating": bench_gk["rating"],
            "minutes_90s": bench_gk["minutes_90s"],
            "effective_rating": calculate_bench_rating(
                bench_gk["rating"],
                bench_gk["minutes_90s"],
                max_gk_minutes
            )
        })
        used_players.add(bench_gk["player"])
    
    # === DIFENSORI PANCHINA (2 richiesti) ===
    bench_def_needed = 2
    bench_def_start = formation["DIF"]
    bench_def_count = 0
    
    # Prendi difensori disponibili
    if len(all_def) > bench_def_start:
        max_def_minutes = max([p["minutes_90s"] for p in all_def])
        for i in range(bench_def_start, min(bench_def_start + bench_def_needed, len(all_def))):
            if all_def[i]["player"] not in used_players:
                bench.append({
                    "role": "DIF",
                    "player": all_def[i]["player"],
                    "rating": all_def[i]["rating"],
                    "minutes_90s": all_def[i]["minutes_90s"],
                    "effective_rating": calculate_bench_rating(
                        all_def[i]["rating"],
                        all_def[i]["minutes_90s"],
                        max_def_minutes
                    )
                })
                used_players.add(all_def[i]["player"])
                bench_def_count += 1
    
    # Se mancano difensori, prendi centrocampisti extra
    if bench_def_count < bench_def_needed:
        missing_def = bench_def_needed - bench_def_count
        print(f"   ⚠️  Panchina: mancano {missing_def} DIF → prendo MID extra")
        
        extra_mid_start = formation["MID"] + (bench_def_needed - bench_def_count)  # Dopo quelli già usati
        max_mid_minutes = max([p["minutes_90s"] for p in all_mid]) if all_mid else 0.1
        
        for i in range(len(all_mid)):
            if bench_def_count >= bench_def_needed:
                break
            if all_mid[i]["player"] not in used_players:
                bench.append({
                    "role": "DIF (da MID)",
                    "player": all_mid[i]["player"],
                    "rating": all_mid[i]["rating"],
                    "minutes_90s": all_mid[i]["minutes_90s"],
                    "effective_rating": calculate_bench_rating(
                        all_mid[i]["rating"],
                        all_mid[i]["minutes_90s"],
                        max_mid_minutes
                    )
                })
                used_players.add(all_mid[i]["player"])
                bench_def_count += 1
    
    # === CENTROCAMPISTI PANCHINA (2 richiesti) ===
    bench_mid_needed = 2
    bench_mid_start = formation["MID"]
    bench_mid_count = 0
    
    # Prendi centrocampisti disponibili
    if len(all_mid) > bench_mid_start:
        max_mid_minutes = max([p["minutes_90s"] for p in all_mid])
        for i in range(bench_mid_start, min(bench_mid_start + bench_mid_needed, len(all_mid))):
            if all_mid[i]["player"] not in used_players:
                bench.append({
                    "role": "MID",
                    "player": all_mid[i]["player"],
                    "rating": all_mid[i]["rating"],
                    "minutes_90s": all_mid[i]["minutes_90s"],
                    "effective_rating": calculate_bench_rating(
                        all_mid[i]["rating"],
                        all_mid[i]["minutes_90s"],
                        max_mid_minutes
                    )
                })
                used_players.add(all_mid[i]["player"])
                bench_mid_count += 1
    
    # Se mancano centrocampisti, prendi difensori extra
    if bench_mid_count < bench_mid_needed:
        missing_mid = bench_mid_needed - bench_mid_count
        print(f"   ⚠️  Panchina: mancano {missing_mid} MID → prendo DIF extra")
        
        max_def_minutes = max([p["minutes_90s"] for p in all_def]) if all_def else 0.1
        
        for i in range(len(all_def)):
            if bench_mid_count >= bench_mid_needed:
                break
            if all_def[i]["player"] not in used_players:
                bench.append({
                    "role": "MID (da DIF)",
                    "player": all_def[i]["player"],
                    "rating": all_def[i]["rating"],
                    "minutes_90s": all_def[i]["minutes_90s"],
                    "effective_rating": calculate_bench_rating(
                        all_def[i]["rating"],
                        all_def[i]["minutes_90s"],
                        max_def_minutes
                    )
                })
                used_players.add(all_def[i]["player"])
                bench_mid_count += 1
    
    # === ATTACCANTI PANCHINA (2 richiesti) ===
    bench_att_needed = 2
    bench_att_start = formation["ATT"]
    bench_att_count = 0
    
    # Prendi attaccanti disponibili
    if len(all_att) > bench_att_start:
        max_att_minutes = max([p["minutes_90s"] for p in all_att])
        for i in range(bench_att_start, min(bench_att_start + bench_att_needed, len(all_att))):
            if all_att[i]["player"] not in used_players:
                bench.append({
                    "role": "ATT",
                    "player": all_att[i]["player"],
                    "rating": all_att[i]["rating"],
                    "minutes_90s": all_att[i]["minutes_90s"],
                    "effective_rating": calculate_bench_rating(
                        all_att[i]["rating"],
                        all_att[i]["minutes_90s"],
                        max_att_minutes
                    )
                })
                used_players.add(all_att[i]["player"])
                bench_att_count += 1
    
    # Se mancano attaccanti, prendi centrocampisti extra
    if bench_att_count < bench_att_needed:
        missing_att = bench_att_needed - bench_att_count
        print(f"   ⚠️  Panchina: mancano {missing_att} ATT → prendo MID extra")
        
        max_mid_minutes = max([p["minutes_90s"] for p in all_mid]) if all_mid else 0.1
        
        for i in range(len(all_mid)):
            if bench_att_count >= bench_att_needed:
                break
            if all_mid[i]["player"] not in used_players:
                bench.append({
                    "role": "ATT (da MID)",
                    "player": all_mid[i]["player"],
                    "rating": all_mid[i]["rating"],
                    "minutes_90s": all_mid[i]["minutes_90s"],
                    "effective_rating": calculate_bench_rating(
                        all_mid[i]["rating"],
                        all_mid[i]["minutes_90s"],
                        max_mid_minutes
                    )
                })
                used_players.add(all_mid[i]["player"])
                bench_att_count += 1
    
    if len(bench) < 7:
        print(f"\n   ⚠️  Panchina incompleta: {len(bench)}/7 (anche con rimpiazzi)")
            # Calcola somme titolari e panchina
    starters_sum = sum([p["rating"] for p in starters])
    bench_sum = sum([p["effective_rating"] for p in bench])


    
            # 6. RATING FINALE (nuova formula)
    
    # Conta titolari effettivi
    num_starters = len(starters)
    if num_starters < 11:
        print(f"\n   ⚠️  {num_starters}/11 titolari → normalizzo")
        starters_sum = (starters_sum / num_starters) * 11
    
    # Medie
    media_titolari_normale = starters_sum / 11
    media_titolari_alzata = starters_sum / 10
    media_panchina = bench_sum / 7 if len(bench) > 0 else 0
    
    # Due calcoli
    calcolo_1 = (media_titolari_alzata + media_panchina) / 2
    calcolo_2 = (media_titolari_normale * 10 + media_panchina * 1) / 11
    
    # Rating finale (0-10)
    team_rating_0_10 = (calcolo_1 + calcolo_2) / 2

    # CONVERSIONE A 5-25
    team_rating_5_25 = 5 + (team_rating_0_10 * 2)

    # CAP: minimo 5, massimo 25
    team_rating_5_25 = max(5, min(25, team_rating_5_25))
    
        # ... (codice precedente fino al calcolo del rating) ...
    
    # 7. OUTPUT (UNICA VERSIONE)
    print(f"\n👥 TITOLARI ({num_starters}/11):")
    for p in starters:
        print(f"   {p['role']:12} | {p['player']:30} | {p['rating']:.2f} | Min: {p['minutes_90s']:.1f}")
    
    if bench:
        print(f"\n🪑 PANCHINA ({len(bench)}/7):")
        for p in bench:
            print(f"   {p['role']:12} | {p['player']:30} | {p['rating']:.2f} → {p['effective_rating']:.2f} | Min: {p['minutes_90s']:.1f}")
    
    total_sum = starters_sum + bench_sum

    print(f"\n📊 RATING:")
    print(f"   Somma titolari: {starters_sum:.2f}")
    print(f"   Media titolari (normale): {media_titolari_normale:.2f}")
    print(f"   Media titolari (alzata /10): {media_titolari_alzata:.2f}")
    print(f"   Somma panchina: {bench_sum:.2f}")
    print(f"   Media panchina: {media_panchina:.2f}")
    print(f"   Calcolo 1: {calcolo_1:.2f}")
    print(f"   Calcolo 2: {calcolo_2:.2f}")
    print(f"   🎯 RATING SQUADRA: {team_rating_0_10:.2f}/10 → {team_rating_5_25:.2f}/25")
    print(f"{'='*70}\n")

    
    return {
    "team": team_name,
    "league": league,
    "formation": formation_str,
    "rating_0_10": round(team_rating_0_10, 2),      # ← Mantengo per debug
    "rating_5_25": round(team_rating_5_25, 2),      # ← NUOVO!
    "total_sum": round(total_sum, 2),
    "starters": starters,
    "bench": bench
}


# ==================== TEST ====================

if __name__ == "__main__":
    if not check_rating_anomalies():
        print("❌ Correggi rating anomali!\n")
        exit(1)
    
    test_teams = ["Lecce", "Como"]
    
    print("\n" + "="*70)
    print("🧪 TEST RATING SQUADRE")
    print("="*70)
    
    results = []
    for team in test_teams:
        result = calculate_team_rating(team)
        if result:
            results.append(result)
    
    if results:
        print("\n" + "="*70)
        print("📊 RIEPILOGO")
        print("="*70)
        for r in sorted(results, key=lambda x: x["rating_5_25"], reverse=True):
            print(f"   {r['team']:20} | {r['formation']:8} | ⭐ {r['rating_5_25']:.2f}/25 (base: {r['rating_0_10']:.2f}/10)")
        print("="*70 + "\n")
