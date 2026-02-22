"""
Verifica nomi squadre MLS: BetExplorer + NowGoal vs collection teams MongoDB.
Per ogni nome, cerca match in name/aliases/aliases_transfermarkt.
Se non trovato, suggerisce candidati fuzzy.

Uso:
  python verify_mls_names.py            # solo report
  python verify_mls_names.py --add      # aggiunge alias mancanti (interattivo)
  python verify_mls_names.py --auto     # aggiunge alias automaticamente (best match score>=80)
"""
import sys
import os
import re
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db

teams_col = db.teams
LEAGUE = "Major League Soccer"

# ============================================================
# NOMI BETEXPLORER (30 squadre MLS)
# ============================================================
BETEXPLORER_NAMES = [
    "Atlanta Utd",
    "Austin FC",
    "CF Montreal",
    "Charlotte",
    "Chicago Fire",
    "Columbus Crew",
    "DC United",
    "FC Cincinnati",
    "FC Dallas",
    "Houston Dynamo",
    "Inter Miami",
    "Los Angeles FC",
    "Minnesota United",
    "Nashville SC",
    "New England Revolution",
    "New York Red Bulls",
    "Orlando City",
    "Philadelphia Union",
    "Portland Timbers",
    "Real Salt Lake",
    "San Diego FC",
    "San Jose Earthquakes",
    "Sporting Kansas City",
    "St. Louis City",
    "Toronto FC",
    "Vancouver Whitecaps",
    "Colorado Rapids",
    "Los Angeles Galaxy",
    "New York City",
    "Seattle Sounders",
]

# ============================================================
# NOMI NOWGOAL (30 squadre MLS)
# ============================================================
NOWGOAL_NAMES = [
    "Atlanta United",
    "Austin FC",
    "CF Montreal",
    "Charlotte FC",
    "Chicago Fire",
    "Colorado Rapids",
    "Columbus Crew",
    "DC United",
    "FC Cincinnati",
    "FC Dallas",
    "Houston Dynamo",
    "Inter Miami CF",
    "Los Angeles FC",
    "Los Angeles Galaxy",
    "Minnesota United FC",
    "Nashville",
    "New England Revolution",
    "New York City FC",
    "New York Red Bulls",
    "Orlando City",
    "Philadelphia Union",
    "Portland Timbers",
    "Real Salt Lake",
    "San Diego FC",
    "San Jose Earthquakes",
    "Seattle Sounders",
    "Sporting Kansas City",
    "St. Louis City",
    "Toronto FC",
    "Vancouver Whitecaps",
]


def find_team(name):
    """Cerca un team per name, aliases o aliases_transfermarkt (esatto + case-insensitive)."""
    return teams_col.find_one({
        "league": LEAGUE,
        "$or": [
            {"name": name},
            {"aliases": name},
            {"aliases_transfermarkt": name},
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
            {"aliases": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        ]
    })


def find_fuzzy_candidates(name, limit=5):
    """Cerca candidati fuzzy nella stessa lega (substring, inizio, parole chiave)."""
    all_teams = list(teams_col.find({"league": LEAGUE}, {"name": 1, "aliases": 1, "aliases_transfermarkt": 1}))

    candidates = []
    name_lower = name.lower()
    # Parole chiave (es. "Houston" da "Houston Dynamo")
    keywords = [w for w in name_lower.split() if len(w) > 2 and w not in ("fc", "cf", "sc", "utd", "city", "united")]

    for t in all_teams:
        score = 0
        team_name = t.get("name", "")
        all_names = [team_name] + t.get("aliases", [])
        if t.get("aliases_transfermarkt"):
            all_names.append(t["aliases_transfermarkt"])

        for n in all_names:
            n_lower = n.lower()
            # Match esatto
            if n_lower == name_lower:
                score = 100
                break
            # Substring bidirezionale
            if name_lower in n_lower or n_lower in name_lower:
                score = max(score, 80)
            # Parole chiave
            for kw in keywords:
                if kw in n_lower:
                    score = max(score, 70)

        if score > 0:
            candidates.append((score, team_name, t.get("aliases", []), t["_id"]))

    candidates.sort(key=lambda x: -x[0])
    return candidates[:limit]


def check_names(source_label, names):
    """Verifica una lista di nomi. Ritorna (found, missing)."""
    found = []
    missing = []

    print(f"\n{'=' * 80}")
    print(f"  {source_label} — {len(names)} squadre")
    print(f"{'=' * 80}")

    for name in names:
        team = find_team(name)
        if team:
            match_type = "name" if team["name"].lower() == name.lower() else "alias"
            found.append((name, team["name"], match_type))
            print(f"  ✅ {name:30s} → {team['name']} (match: {match_type})")
        else:
            candidates = find_fuzzy_candidates(name)
            missing.append((name, candidates))
            print(f"  ❌ {name:30s} → NON TROVATO")
            if candidates:
                for score, cand_name, cand_aliases, _ in candidates[:3]:
                    aliases_str = f" (aliases: {', '.join(cand_aliases[:3])})" if cand_aliases else ""
                    print(f"     💡 ({score}%): {cand_name}{aliases_str}")

    print(f"\n  Risultato: {len(found)}/{len(names)} trovati | {len(missing)} mancanti")
    return found, missing


def add_aliases_interactive(all_missing):
    """Modalità interattiva: chiede conferma per ogni alias."""
    print(f"\n{'=' * 80}")
    print(f"  AGGIUNTA ALIAS INTERATTIVA — {len(all_missing)} nomi mancanti")
    print(f"{'=' * 80}")

    added = 0
    skipped = 0

    for source, name, candidates in all_missing:
        print(f"\n  [{source}] Nome: '{name}'")

        if not candidates:
            print(f"  ⚠️  Nessun candidato. Squadra potrebbe mancare dal DB.")
            skipped += 1
            continue

        print(f"  Candidati:")
        for i, (score, cand_name, cand_aliases, cand_id) in enumerate(candidates):
            aliases_str = f" [{', '.join(cand_aliases[:5])}]" if cand_aliases else ""
            print(f"    {i+1}. {cand_name} (score: {score}%){aliases_str}")

        choice = input(f"  Associare '{name}' a quale? (1-{len(candidates)}, s=salta, q=esci): ").strip().lower()

        if choice == 'q':
            print("  Uscita.")
            break
        elif choice == 's' or choice == '':
            skipped += 1
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(candidates):
                _, selected_name, _, selected_id = candidates[idx]
                teams_col.update_one({"_id": selected_id}, {"$addToSet": {"aliases": name}})
                print(f"  ✅ Alias '{name}' aggiunto a '{selected_name}'")
                added += 1
            else:
                skipped += 1
        except ValueError:
            skipped += 1

    print(f"\n  TOTALE: {added} aggiunti | {skipped} saltati")
    return added


def add_aliases_auto(all_missing, min_score=80):
    """Modalità automatica: aggiunge alias se best match ha score >= min_score."""
    print(f"\n{'=' * 80}")
    print(f"  AGGIUNTA ALIAS AUTOMATICA (soglia: {min_score}%) — {len(all_missing)} nomi")
    print(f"{'=' * 80}")

    added = 0
    skipped = 0

    for source, name, candidates in all_missing:
        if candidates and candidates[0][0] >= min_score:
            score, selected_name, _, selected_id = candidates[0]
            teams_col.update_one({"_id": selected_id}, {"$addToSet": {"aliases": name}})
            print(f"  ✅ [{source}] '{name}' → '{selected_name}' (score: {score}%)")
            added += 1
        else:
            best = f" (best: {candidates[0][1]} {candidates[0][0]}%)" if candidates else ""
            print(f"  ⏭️  [{source}] '{name}' — score troppo basso{best}")
            skipped += 1

    print(f"\n  TOTALE: {added} aggiunti | {skipped} saltati (sotto soglia)")
    return added


def main():
    add_mode = "--add" in sys.argv
    auto_mode = "--auto" in sys.argv

    print("=" * 80)
    print("  VERIFICA NOMI MLS: BetExplorer + NowGoal vs MongoDB teams")
    print(f"  Lega: {LEAGUE}")
    if auto_mode:
        print("  MODALITA: AUTO (aggiunge alias con score>=80%)")
    elif add_mode:
        print("  MODALITA: INTERATTIVA (chiede conferma)")
    else:
        print("  MODALITA: SOLO REPORT")
    print("=" * 80)

    # Conta squadre MLS nel DB
    mls_count = teams_col.count_documents({"league": LEAGUE})
    print(f"\n  Squadre MLS nel DB: {mls_count}")

    if mls_count == 0:
        print("  ⚠️  NESSUNA squadra MLS nel database! Controlla il campo 'league'.")
        # Mostra campionati simili
        leagues = teams_col.distinct("league", {"league": {"$regex": "league|soccer|mls", "$options": "i"}})
        if leagues:
            print(f"  Campionati simili trovati: {leagues}")
        return

    # Verifica BetExplorer
    be_found, be_missing = check_names("BETEXPLORER", BETEXPLORER_NAMES)

    # Verifica NowGoal
    ng_found, ng_missing = check_names("NOWGOAL", NOWGOAL_NAMES)

    # Unifica i mancanti (evita duplicati)
    all_missing = []
    seen = set()
    for name, candidates in be_missing:
        if name not in seen:
            all_missing.append(("BE", name, candidates))
            seen.add(name)
    for name, candidates in ng_missing:
        if name not in seen:
            all_missing.append(("NG", name, candidates))
            seen.add(name)

    # Report finale
    print(f"\n{'=' * 80}")
    print(f"  RIEPILOGO")
    print(f"  BetExplorer: {len(be_found)}/{len(BETEXPLORER_NAMES)} OK")
    print(f"  NowGoal:     {len(ng_found)}/{len(NOWGOAL_NAMES)} OK")
    print(f"  Alias da aggiungere (unici): {len(all_missing)}")
    print(f"{'=' * 80}")

    if not all_missing:
        print("\n🎉 Tutti i nomi sono già nel database!")
        return

    # Aggiunta alias
    if auto_mode:
        add_aliases_auto(all_missing)
    elif add_mode:
        add_aliases_interactive(all_missing)
    else:
        print("\n💡 Per aggiungere gli alias:")
        print("   python verify_mls_names.py --add     (interattivo)")
        print("   python verify_mls_names.py --auto    (automatico, score>=80%)")


if __name__ == "__main__":
    main()
