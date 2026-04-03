"""
APPLICA DATE & ORARI — Script interattivo
Legge le differenze trovate dallo step 12 (scraper_date_orari_nowgoal.py)
e permette di applicarle selettivamente al database.
"""
import os
import sys
import json
from datetime import datetime
from bson import ObjectId

# Fix percorsi
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_dir = os.path.dirname(os.path.dirname(current_dir))
project_root = os.path.dirname(ai_engine_dir)
if ai_engine_dir not in sys.path:
    sys.path.insert(0, ai_engine_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from config import db

PENDING_PATH = os.path.join(project_root, "log", "date_orari_pending.json")


def load_pending():
    if not os.path.exists(PENDING_PATH):
        return None
    with open(PENDING_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def show_changes(changes):
    """Mostra tutte le differenze trovate."""
    print(f"\n{'='*80}")
    print(f"📋 MODIFICHE IN ATTESA: {len(changes)}")
    print(f"{'='*80}\n")
    for i, c in enumerate(changes):
        print(f"  [{i+1}] {c['league']} | {c['home']} vs {c['away']}")
        if c['old_date'] != c['new_date']:
            print(f"      DATA ORIGINALE (Step 11): {c['old_date'] or 'N/A'}")
            print(f"      DATA NOWGOAL (Step 12):   {c['new_date']}")
        if c['old_time'] != c['new_time']:
            print(f"      ORARIO ORIGINALE: {c['old_time'] or 'N/A'}")
            print(f"      ORARIO NOWGOAL:   {c['new_time']}")
        if c.get('status'):
            print(f"      STATO: {c['status']}")
        print()


def apply_change(c):
    """Applica una singola modifica al DB."""
    home = c['home']
    away = c['away']
    league = c['league']
    new_date = c['new_date']
    new_time = c['new_time']
    m_status = c.get('status')
    round_id = c.get('round_id')

    # 1. Aggiorna in h2h_by_round
    if round_id:
        new_date_obj = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        db.h2h_by_round.update_one(
            {"_id": ObjectId(round_id), "matches.home": home, "matches.away": away},
            {"$set": {
                "matches.$.date_obj": new_date_obj,
                "matches.$.match_time": new_time,
            }}
        )
        # Stato speciale
        if m_status:
            db.h2h_by_round.update_one(
                {"_id": ObjectId(round_id), "matches.home": home, "matches.away": away},
                {"$set": {"matches.$.match_status_detail": m_status}}
            )
        else:
            db.h2h_by_round.update_one(
                {"_id": ObjectId(round_id), "matches.home": home, "matches.away": away},
                {"$unset": {"matches.$.match_status_detail": ""}}
            )

    # 2. Propaga in unified e prediction_versions
    for coll_name in ['daily_predictions_unified', 'prediction_versions']:
        db[coll_name].update_many(
            {"home": home, "away": away, "league": league},
            {"$set": {"date": new_date, "match_time": new_time}}
        )

    # 3. Stato speciale in unified
    if m_status:
        db.daily_predictions_unified.update_many(
            {"home": home, "away": away, "league": league},
            {"$set": {"match_status_detail": m_status}}
        )
    else:
        db.daily_predictions_unified.update_many(
            {"home": home, "away": away, "league": league, "match_status_detail": {"$exists": True}},
            {"$unset": {"match_status_detail": ""}}
        )

    print(f"    ✅ Applicata: {home} vs {away} → {new_date} {new_time}")


def manual_correction():
    """Correzione manuale: nazione → campionato → giornata → partita → data/orario."""

    print(f"\n{'='*80}")
    print("✏️  CORREZIONE MANUALE DATE/ORARI")
    print(f"{'='*80}")

    # 1. Nazione
    countries = db.h2h_by_round.distinct("country")
    countries = sorted([c for c in countries if c])

    print(f"\nNazioni disponibili:\n")
    for i, c in enumerate(countries):
        print(f"  [{i+1}] {c}")
    print()

    idx = input("Scegli nazione (numero): ").strip()
    try:
        country = countries[int(idx) - 1]
    except (ValueError, IndexError):
        print("Scelta non valida.")
        return

    # 2. Campionato
    leagues = db.h2h_by_round.distinct("league", {"country": country})
    leagues = sorted([l for l in leagues if l])

    print(f"\nCampionati {country}:\n")
    for i, l in enumerate(leagues):
        print(f"  [{i+1}] {l}")
    print()

    idx = input("Scegli campionato (numero): ").strip()
    try:
        league = leagues[int(idx) - 1]
    except (ValueError, IndexError):
        print("Scelta non valida.")
        return

    # 3. Giornata
    rounds = list(db.h2h_by_round.find(
        {"country": country, "league": league},
        {"round_name": 1, "_id": 1}
    ).sort("round_name", 1))

    if not rounds:
        print(f"Nessuna giornata trovata per {league}")
        return

    print(f"\nGiornate {league}:\n")
    for i, r in enumerate(rounds):
        rname = r.get("round_name") or "N/A"
        print(f"  [{i+1}] {rname}")
    print()

    idx = input("Scegli giornata (numero): ").strip()
    try:
        round_doc = rounds[int(idx) - 1]
    except (ValueError, IndexError):
        print("Scelta non valida.")
        return

    # Carica il doc completo con i matches
    full_doc = db.h2h_by_round.find_one({"_id": round_doc["_id"]})
    matches = full_doc.get("matches", [])
    round_id = str(full_doc["_id"])

    if not matches:
        print("Nessuna partita in questa giornata.")
        return

    # 4. Partita
    print(f"\nPartite {round_doc.get('round_name', '')}:\n")
    for i, m in enumerate(matches):
        date_obj = m.get("date_obj")
        date_str = date_obj.strftime("%Y-%m-%d") if hasattr(date_obj, "strftime") else str(date_obj)[:10] if date_obj else "N/A"
        time_str = m.get("match_time", "N/A")
        status = m.get("status", "")
        score = m.get("real_score", "")
        extra = f" [{status}]" if status else ""
        extra += f" {score}" if score else ""
        print(f"  [{i+1}] {m['home']} vs {m['away']}  |  {date_str} {time_str}{extra}")
    print()

    idx = input("Scegli partita (numero): ").strip()
    try:
        match = matches[int(idx) - 1]
    except (ValueError, IndexError):
        print("Scelta non valida.")
        return

    # 5. Mostra dati attuali e chiedi nuovi
    old_date_obj = match.get("date_obj")
    old_date = old_date_obj.strftime("%Y-%m-%d") if hasattr(old_date_obj, "strftime") else str(old_date_obj)[:10] if old_date_obj else "N/A"
    old_time = match.get("match_time", "N/A")

    print(f"\n  Partita: {match['home']} vs {match['away']}")
    print(f"  Data attuale: {old_date}")
    print(f"  Orario attuale: {old_time}")
    print(f"\n  Inserisci i nuovi valori (invio per mantenere il valore attuale):")

    new_date = input(f"  Nuova data (YYYY-MM-DD) [{old_date}]: ").strip()
    new_time = input(f"  Nuovo orario (HH:MM) [{old_time}]: ").strip()

    new_date = new_date if new_date else old_date
    new_time = new_time if new_time else old_time

    if new_date == old_date and new_time == old_time:
        print("\n  Nessuna modifica (valori identici).")
        return

    print(f"\n  Riepilogo: {match['home']} vs {match['away']}")
    print(f"  {old_date} {old_time}  →  {new_date} {new_time}")
    conferma = input("\n  Confermi? (S/N): ").strip().upper()
    if conferma != 'S':
        print("  Annullato.")
        return

    # 6. Applica
    change = {
        "league": league,
        "home": match["home"],
        "away": match["away"],
        "new_date": new_date,
        "new_time": new_time,
        "status": None,
        "round_id": round_id,
    }
    apply_change(change)
    print(f"\n✅ Correzione applicata!")


def pending_menu(data):
    """Sotto-menu per gestire le modifiche pending dallo step 12."""
    changes = data['changes']

    print(f"\n{'='*80}")
    print(f"⚠️  MODIFICHE IN ATTESA: {len(changes)} (del {data.get('timestamp', '?')})")
    print(f"{'='*80}\n")

    print("  [T] Applica TUTTE le modifiche")
    print("  [S] Scegli quali applicare (una per una)")
    print("  [P] Mostra il pending senza fare nulla")
    print("  [N] Torna indietro")
    print()

    scelta = input("Scelta: ").strip().upper()

    if scelta == 'N':
        return

    if scelta == 'P':
        show_changes(changes)
        return

    if scelta == 'T':
        show_changes(changes)
        conferma = input("Confermi di applicare TUTTE? (S/N): ").strip().upper()
        if conferma != 'S':
            print("Annullato.")
            return
        print(f"\nApplico tutte le {len(changes)} modifiche...\n")
        for c in changes:
            apply_change(c)
        os.remove(PENDING_PATH)
        print(f"\n✅ Tutte le {len(changes)} modifiche applicate. File pending rimosso.")
        return

    if scelta == 'S':
        show_changes(changes)
        applied = 0
        skipped = 0
        for i, c in enumerate(changes):
            print(f"\n[{i+1}/{len(changes)}] {c['league']} | {c['home']} vs {c['away']}")
            if c['old_date'] != c['new_date']:
                print(f"  DATA ORIGINALE (Step 11): {c['old_date'] or 'N/A'}")
                print(f"  DATA NOWGOAL (Step 12):   {c['new_date']}")
            if c['old_time'] != c['new_time']:
                print(f"  ORARIO ORIGINALE: {c['old_time'] or 'N/A'}")
                print(f"  ORARIO NOWGOAL:   {c['new_time']}")

            risposta = input("  (S=applica NowGoal / N=scarta / M=inserisci manualmente): ").strip().upper()
            if risposta == 'S':
                apply_change(c)
                applied += 1
            elif risposta == 'M':
                print(f"    Inserisci i dati corretti (invio = valore tra parentesi):")
                manual_date = input(f"    Data (YYYY-MM-DD) [{c['old_date'] or c['new_date']}]: ").strip()
                manual_time = input(f"    Orario (HH:MM) [{c['old_time'] or c['new_time']}]: ").strip()
                c['new_date'] = manual_date if manual_date else (c['old_date'] or c['new_date'])
                c['new_time'] = manual_time if manual_time else (c['old_time'] or c['new_time'])
                apply_change(c)
                applied += 1
            else:
                skipped += 1
                print("    ❌ Scartata (si tiene l'originale)")

        os.remove(PENDING_PATH)
        print(f"\n✅ Applicate: {applied} | Scartate: {skipped}. File pending rimosso.")
        return

    print("Scelta non valida.")


def main():
    data = load_pending()
    has_pending = data and data.get('changes') and len(data['changes']) > 0
    pending_count = len(data['changes']) if has_pending else 0

    print(f"\n{'='*80}")
    print("📅 GESTIONE DATE & ORARI")
    print(f"{'='*80}\n")

    print("  [1] Correzione manuale (scegli campionato e partita)")
    if has_pending:
        print(f"  [2] Modifiche in attesa dallo Step 12 ({pending_count} pending)")
    else:
        print("  [2] Modifiche in attesa dallo Step 12 (nessuna)")
    print("  [N] Esci")
    print()

    scelta = input("Scelta: ").strip().upper()

    if scelta == 'N':
        print("Uscita.")
        return

    if scelta == '1':
        manual_correction()
        return

    if scelta == '2':
        if not has_pending:
            print("\n✅ Nessuna modifica in attesa.")
            return
        pending_menu(data)
        return

    print("Scelta non valida.")


if __name__ == "__main__":
    main()
