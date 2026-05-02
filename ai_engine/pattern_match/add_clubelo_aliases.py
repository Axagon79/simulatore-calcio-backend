"""
Aggiunge alias ClubElo alla collezione `teams` per le squadre Football-Data
che non avevano match diretto.

Ogni alias e' verificato manualmente (vedi find_elo_by_country.py).
NON aggiunge match incerti (Ajaccio GFCO, Karabakh, ecc).

Uso:
    python -m ai_engine.pattern_match.add_clubelo_aliases --dry-run   # mostra cosa farebbe
    python -m ai_engine.pattern_match.add_clubelo_aliases --apply     # applica
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import db


# Tuple: (nome canonico team nel DB, lista di alias da aggiungere)
# Verificato manualmente con find_elo_by_country.py + ricerca DB filtrata.
#
# Beerschot VA escluso: non esiste in tutto il DB Belgium.
ALIASES_BY_TEAM: list[tuple[str, list[str]]] = [
    ("AZ Alkmaar",        ["Alkmaar"]),
    ("Adana Demirspor",   ["Ad. Demirspor", "Adana Demirspor"]),
    ("Almere City FC",    ["Almere"]),
    ("Athletic Club",     ["Bilbao"]),
    ("Atletico Madrid",   ["Ath Madrid", "Atletico"]),
    ("Fortuna Sittard",   ["For Sittard"]),
    ("Holstein Kiel",     ["Holstein"]),
    ("NAC Breda",         ["Breda"]),
    ("Nottm Forest",      ["Forest"]),
    ("Sporting Braga",    ["Sp Braga"]),
    ("Sporting Gijón",    ["Sp Gijon"]),
    ("Rayo Vallecano",    ["Vallecano"]),
    ("Werder Brema",      ["Werder"]),
]


def find_team_in_db(team_name: str):
    """Cerca team per nome canonico esatto."""
    return db.teams.find_one({"name": team_name})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Mostra modifiche senza applicarle")
    parser.add_argument("--apply", action="store_true", help="Applica davvero")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specificare --dry-run o --apply")
        return 1

    actions = []
    not_found = []
    already_present = []

    for team_name, alias_list in ALIASES_BY_TEAM:
        doc = find_team_in_db(team_name)
        if not doc:
            not_found.append(team_name)
            continue
        aliases = doc.get("aliases", []) or []
        for alias in alias_list:
            if alias in aliases:
                already_present.append((team_name, alias))
                continue
            actions.append({
                "team_name": doc.get("name"),
                "team_id": doc.get("_id"),
                "alias": alias,
                "current_aliases": aliases,
            })

    print("=" * 80)
    print(f"DRY-RUN" if args.dry_run else "APPLY")
    print("=" * 80)

    print(f"\n[OK] Da modificare: {len(actions)}")
    for a in actions:
        print(f"  team='{a['team_name']}' + alias '{a['alias']}'")
        print(f"      aliases attuali: {a['current_aliases']}")

    if already_present:
        print(f"\n[SKIP] Alias gia' presente: {len(already_present)}")
        for team, alias in already_present:
            print(f"  {team}: '{alias}' gia c'e")

    if not_found:
        print(f"\n[ERR] Team non trovato in db.teams: {len(not_found)}")
        for n in not_found:
            print(f"  {n}")

    if args.apply and actions:
        print("\n[APPLY] Eseguo modifiche...")
        for a in actions:
            res = db.teams.update_one(
                {"_id": a["team_id"]},
                {"$addToSet": {"aliases": a["alias"]}}
            )
            print(f"  {a['team_name']:25s} + '{a['alias']}' -> matched={res.matched_count} modified={res.modified_count}")
        print(f"\n[DONE] {len(actions)} alias aggiunti.")
    elif args.dry_run:
        print("\n[DRY-RUN] Nessuna modifica scritta. Lancia con --apply per eseguire.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
