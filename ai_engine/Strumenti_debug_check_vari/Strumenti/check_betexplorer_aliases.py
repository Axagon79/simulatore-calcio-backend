"""
Script di verifica alias BetExplorer vs collection teams MongoDB.
Per ogni nome BetExplorer, cerca in name/aliases/aliases_transfermarkt.
Se non trovato, suggerisce candidati fuzzy dalla stessa lega.

Uso: python check_betexplorer_aliases.py
     python check_betexplorer_aliases.py --add   (aggiunge alias mancanti dopo conferma)
"""
import sys
import os
import re
sys.path.insert(0, r"C:\Progetti\simulatore-calcio-backend")
from config import db

teams_col = db.teams

# ============================================================
# NOMI BETEXPLORER DA VERIFICARE
# Formato: (nome_betexplorer, campionato_db)
# ============================================================
BETEXPLORER_NAMES = [
    # League of Ireland Premier Division
    ("Derry City", "League of Ireland Premier Division"),
    ("Drogheda", "League of Ireland Premier Division"),
    ("Waterford", "League of Ireland Premier Division"),
    ("Shelbourne", "League of Ireland Premier Division"),
    ("Shamrock Rovers", "League of Ireland Premier Division"),
    ("St. Patricks", "League of Ireland Premier Division"),
    ("Bohemians", "League of Ireland Premier Division"),
    ("Dundalk", "League of Ireland Premier Division"),
    ("Sligo Rovers", "League of Ireland Premier Division"),
    ("Galway", "League of Ireland Premier Division"),
]


def find_team(name, league):
    """Cerca un team per name, aliases o aliases_transfermarkt."""
    return teams_col.find_one({
        "league": league,
        "$or": [
            {"name": name},
            {"aliases": name},
            {"aliases_transfermarkt": name},
            # case-insensitive
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
            {"aliases": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
        ]
    })


def find_fuzzy_candidates(name, league, limit=5):
    """Cerca candidati fuzzy nella stessa lega (substring match)."""
    # Prendi tutte le squadre della lega
    all_teams = list(teams_col.find({"league": league}, {"name": 1, "aliases": 1, "aliases_transfermarkt": 1}))

    candidates = []
    name_lower = name.lower()

    for t in all_teams:
        score = 0
        team_name = t.get("name", "")
        all_names = [team_name] + t.get("aliases", [])
        if t.get("aliases_transfermarkt"):
            all_names.append(t["aliases_transfermarkt"])

        for n in all_names:
            n_lower = n.lower()
            # Match esatto (gia' trovato prima, ma per sicurezza)
            if n_lower == name_lower:
                score = 100
                break
            # Substring: il nome BetExplorer e' contenuto
            if name_lower in n_lower or n_lower in name_lower:
                score = max(score, 80)
            # Prime 4 lettere uguali
            if len(name_lower) >= 4 and len(n_lower) >= 4 and name_lower[:4] == n_lower[:4]:
                score = max(score, 60)
            # Almeno 3 lettere iniziali
            if len(name_lower) >= 3 and len(n_lower) >= 3 and name_lower[:3] == n_lower[:3]:
                score = max(score, 40)

        if score > 0:
            candidates.append((score, team_name, t.get("aliases", []), t["_id"]))

    candidates.sort(key=lambda x: -x[0])
    return candidates[:limit]


def main():
    add_mode = "--add" in sys.argv

    print("=" * 80)
    print("  VERIFICA ALIAS BETEXPLORER vs MongoDB teams")
    if add_mode:
        print("  MODALITA: AGGIUNTA ALIAS (--add)")
    else:
        print("  MODALITA: SOLO REPORT (usa --add per aggiungere)")
    print("=" * 80)

    found = []
    missing = []

    for name, league in BETEXPLORER_NAMES:
        team = find_team(name, league)

        if team:
            match_type = "name" if team["name"].lower() == name.lower() else "alias"
            found.append((name, league, team["name"], match_type))
            print(f"  ✅ {name:25s} → {team['name']} (match: {match_type})")
        else:
            candidates = find_fuzzy_candidates(name, league)
            missing.append((name, league, candidates))
            print(f"  ❌ {name:25s} → NON TROVATO")
            if candidates:
                for score, cand_name, cand_aliases, _ in candidates[:3]:
                    aliases_str = f" (aliases: {', '.join(cand_aliases[:3])})" if cand_aliases else ""
                    print(f"     💡 Suggerimento ({score}%): {cand_name}{aliases_str}")

    # --- REPORT ---
    print("\n" + "=" * 80)
    print(f"  RISULTATO: {len(found)}/{len(BETEXPLORER_NAMES)} trovati | {len(missing)} mancanti")
    print("=" * 80)

    if not missing:
        print("\n🎉 Tutti i nomi BetExplorer sono gia' nel database!")
        return

    # --- AGGIUNTA ALIAS ---
    if add_mode and missing:
        print("\n🔧 AGGIUNTA ALIAS MANCANTI:")
        print("-" * 80)

        added = 0
        skipped = 0

        for name, league, candidates in missing:
            print(f"\n  Nome BetExplorer: '{name}' ({league})")

            if not candidates:
                print(f"  ⚠️  Nessun candidato trovato nella lega. Squadra potrebbe mancare del tutto.")
                skipped += 1
                continue

            print(f"  Candidati:")
            for i, (score, cand_name, cand_aliases, cand_id) in enumerate(candidates):
                aliases_str = f" [{', '.join(cand_aliases[:5])}]" if cand_aliases else ""
                print(f"    {i+1}. {cand_name} (score: {score}%){aliases_str}")

            choice = input(f"  Associare '{name}' a quale candidato? (1-{len(candidates)}, s=salta, q=esci): ").strip().lower()

            if choice == 'q':
                print("  Uscita.")
                break
            elif choice == 's' or choice == '':
                print(f"  ⏭️  Saltato")
                skipped += 1
                continue

            try:
                idx = int(choice) - 1
                if 0 <= idx < len(candidates):
                    _, selected_name, _, selected_id = candidates[idx]
                    teams_col.update_one(
                        {"_id": selected_id},
                        {"$addToSet": {"aliases": name}}
                    )
                    print(f"  ✅ Alias '{name}' aggiunto a '{selected_name}'")
                    added += 1
                else:
                    print(f"  ⏭️  Indice non valido, saltato")
                    skipped += 1
            except ValueError:
                print(f"  ⏭️  Input non valido, saltato")
                skipped += 1

        print(f"\n" + "=" * 80)
        print(f"  ALIAS AGGIUNTI: {added} | SALTATI: {skipped}")
        print("=" * 80)

    elif missing and not add_mode:
        print("\n💡 Per aggiungere gli alias mancanti, esegui:")
        print("   python check_betexplorer_aliases.py --add")


if __name__ == "__main__":
    main()
