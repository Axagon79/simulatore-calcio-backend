"""
APPLICA DATE & ORARI + STATO PARTITA — Script interattivo
Legge le differenze trovate dallo step 12 (scraper_date_orari_nowgoal.py)
e permette di applicarle selettivamente al database.
Include anche la gestione dello stato partita (posticipata, annullata, ecc.)
"""
import os
import sys
import json
import re
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

PENDING_PATH = os.path.join(os.path.dirname(current_dir), "date_orari", "date_orari_pending.json")

# Stati predefiniti per le partite
MATCH_STATUSES = [
    ("Postp.", "Posticipata"),
    ("Cancelled", "Annullata"),
    ("Suspended", "Sospesa"),
    ("Abandoned", "Abbandonata"),
    ("Walkover", "Walkover / Vittoria a tavolino"),
]


def to_ita(date_str):
    """YYYY-MM-DD → DD/MM/YYYY per visualizzazione."""
    if not date_str or date_str == 'N/A':
        return date_str or 'N/A'
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return date_str


def from_ita(date_str):
    """Accetta vari formati (DD/MM/YYYY, DD-MM-YYYY, DDMMYYYY, DD.MM.YYYY) → YYYY-MM-DD."""
    if not date_str:
        return date_str
    # Rimuovi separatori e prova come 8 cifre
    digits = re.sub(r'[/\-.]', '', date_str)
    if len(digits) == 8 and digits.isdigit():
        try:
            return datetime.strptime(digits, "%d%m%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Prova formati con separatori
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


class ExitScript(Exception):
    """Eccezione per uscire dallo script in qualsiasi punto."""
    pass


def safe_input(prompt):
    """Input che intercetta Q/q per uscire dallo script."""
    val = input(prompt).strip()
    if val.upper() == 'Q':
        raise ExitScript()
    return val


def ask_date(prompt, default_ita):
    """Chiede una data con validazione e conferma. Ritorna YYYY-MM-DD o None se annullato."""
    while True:
        val = safe_input(f"{prompt} [{default_ita}]: ")
        if val == '0':
            return None
        if not val:
            return from_ita(default_ita)
        result = from_ita(val)
        if not result:
            print("    ⚠️ Formato non valido. Usa GG/MM/AAAA (es. 20/04/2026)")
            continue
        # Se l'input non era già nel formato pulito, chiedi conferma
        result_ita = to_ita(result)
        if val != result_ita:
            conferma = safe_input(f"    → Intendi {result_ita}? (S/N): ").upper()
            if conferma != 'S':
                continue
        return result


def ask_time(prompt, default_time):
    """Chiede un orario con validazione e conferma. Ritorna HH:MM o None se annullato."""
    while True:
        val = safe_input(f"{prompt} [{default_time}]: ")
        if val == '0':
            return None
        if not val:
            return default_time
        # Accetta HHMM o HH:MM
        digits = val.replace(':', '')
        if len(digits) == 4 and digits.isdigit():
            formatted = f"{digits[:2]}:{digits[2:]}"
            if val != formatted:
                conferma = safe_input(f"    → Intendi {formatted}? (S/N): ").upper()
                if conferma != 'S':
                    continue
            return formatted
        if re.match(r'^\d{1,2}:\d{2}$', val):
            return val
        # Solo ore (es. "20" → "20:00")
        if re.match(r'^\d{1,2}$', val) and 0 <= int(val) <= 23:
            formatted = f"{int(val):02d}:00"
            conferma = safe_input(f"    → Intendi {formatted}? (S/N): ").upper()
            if conferma == 'S':
                return formatted
            continue
        print("    ⚠️ Formato non valido. Usa HH:MM (es. 20:45)")


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
            print(f"      DATA ORIGINALE (Step 11): {to_ita(c['old_date'])}")
            print(f"      DATA NOWGOAL (Step 12):   {to_ita(c['new_date'])}")
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
        # _id può essere ObjectId o stringa
        try:
            rid = ObjectId(round_id)
        except Exception:
            rid = round_id

        new_date_obj = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        db.h2h_by_round.update_one(
            {"_id": rid, "matches.home": home, "matches.away": away},
            {"$set": {
                "matches.$.date_obj": new_date_obj,
                "matches.$.match_time": new_time,
            }}
        )
        # Stato speciale
        if m_status:
            db.h2h_by_round.update_one(
                {"_id": rid, "matches.home": home, "matches.away": away},
                {"$set": {"matches.$.match_status_detail": m_status}}
            )
        else:
            db.h2h_by_round.update_one(
                {"_id": rid, "matches.home": home, "matches.away": away},
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
    """Correzione manuale: nazione → campionato → giornata → partita → data/orario.
    [0] ad ogni livello per tornare indietro."""

    while True:
        print(f"\n{'='*80}")
        print("✏️  CORREZIONE MANUALE DATE/ORARI")
        print(f"{'='*80}")

        # 1. Nazione
        countries = db.h2h_by_round.distinct("country")
        countries = sorted([c for c in countries if c])

        print(f"\nNazioni disponibili:\n")
        for i, c in enumerate(countries):
            print(f"  [{i+1}] {c}")
        print(f"\n  [0] Torna al menu principale")
        print()

        idx = safe_input("Scegli nazione (numero): ")
        if idx == '0':
            return
        try:
            country = countries[int(idx) - 1]
        except (ValueError, IndexError):
            print("Scelta non valida.")
            continue

        # 2. Campionato
        while True:
            leagues = db.h2h_by_round.distinct("league", {"country": country})
            leagues = sorted([l for l in leagues if l])

            print(f"\nCampionati {country}:\n")
            for i, l in enumerate(leagues):
                print(f"  [{i+1}] {l}")
            print(f"\n  [0] Indietro (nazioni)")
            print()

            idx = safe_input("Scegli campionato (numero): ")
            if idx == '0':
                break
            try:
                league = leagues[int(idx) - 1]
            except (ValueError, IndexError):
                print("Scelta non valida.")
                continue

            # 3. Giornata
            while True:
                def _round_sort_key(r):
                    """Estrae il numero dalla giornata per ordinamento numerico."""
                    m = re.match(r'(\d+)', r.get('round_name') or '0')
                    return int(m.group(1)) if m else 0

                rounds = sorted(
                    list(db.h2h_by_round.find(
                        {"country": country, "league": league},
                        {"round_name": 1, "_id": 1}
                    )),
                    key=_round_sort_key
                )

                if not rounds:
                    print(f"Nessuna giornata trovata per {league}")
                    break

                print(f"\nGiornate {league}:\n")
                for i, r in enumerate(rounds):
                    rname = r.get("round_name") or "N/A"
                    print(f"  [{i+1}] {rname}")
                print(f"\n  [0] Indietro (campionati)")
                print()

                idx = safe_input("Scegli giornata (numero): ")
                if idx == '0':
                    break
                try:
                    round_doc = rounds[int(idx) - 1]
                except (ValueError, IndexError):
                    print("Scelta non valida.")
                    continue

                # Carica il doc completo con i matches
                full_doc = db.h2h_by_round.find_one({"_id": round_doc["_id"]})
                matches = full_doc.get("matches", [])
                round_id = str(full_doc["_id"])

                if not matches:
                    print("Nessuna partita in questa giornata.")
                    continue

                # 4. Partita
                while True:
                    print(f"\nPartite {round_doc.get('round_name', '')}:\n")
                    for i, m in enumerate(matches):
                        date_obj = m.get("date_obj")
                        date_str = date_obj.strftime("%d/%m/%Y") if hasattr(date_obj, "strftime") else "N/A"
                        time_str = m.get("match_time", "N/A")
                        status = m.get("status", "")
                        score = m.get("real_score", "")
                        extra = f" [{status}]" if status else ""
                        extra += f" {score}" if score else ""
                        print(f"  [{i+1}] {m['home']} vs {m['away']}  |  {date_str} {time_str}{extra}")
                    print(f"\n  [0] Indietro (giornate)")
                    print()

                    idx = safe_input("Scegli partita (numero): ")
                    if idx == '0':
                        break
                    try:
                        match = matches[int(idx) - 1]
                    except (ValueError, IndexError):
                        print("Scelta non valida.")
                        continue

                    # 5. Mostra dati attuali e chiedi nuovi
                    old_date_obj = match.get("date_obj")
                    old_date_db = old_date_obj.strftime("%Y-%m-%d") if hasattr(old_date_obj, "strftime") else str(old_date_obj)[:10] if old_date_obj else "N/A"
                    old_date_ita = to_ita(old_date_db)
                    old_time = match.get("match_time", "N/A")

                    print(f"\n  Partita: {match['home']} vs {match['away']}")
                    print(f"  Data attuale: {old_date_ita}")
                    print(f"  Orario attuale: {old_time}")
                    print(f"\n  Inserisci i nuovi valori (invio per mantenere, 0 per annullare):")

                    new_date = ask_date("  Nuova data (GG/MM/AAAA)", old_date_ita)
                    if new_date is None:
                        print("  Annullato.")
                        continue
                    new_time = ask_time("  Nuovo orario (HH:MM)", old_time)
                    if new_time is None:
                        print("  Annullato.")
                        continue

                    if new_date == old_date_db and new_time == old_time:
                        print("\n  Nessuna modifica (valori identici).")
                        continue

                    print(f"\n  Riepilogo: {match['home']} vs {match['away']}")
                    print(f"  {old_date_ita} {old_time}  →  {to_ita(new_date)} {new_time}")
                    conferma = safe_input("\n  Confermi? (S/N): ").upper()
                    if conferma != 'S':
                        print("  Annullato.")
                        continue

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


def apply_status_change(round_id, home, away, league, new_status):
    """Applica solo il cambio di stato a una partita (senza toccare date/orari)."""
    # _id può essere ObjectId o stringa
    try:
        rid = ObjectId(round_id)
    except Exception:
        rid = round_id

    if new_status:
        # Imposta lo stato
        db.h2h_by_round.update_one(
            {"_id": rid, "matches.home": home, "matches.away": away},
            {"$set": {"matches.$.match_status_detail": new_status}}
        )
        db.daily_predictions_unified.update_many(
            {"home": home, "away": away, "league": league},
            {"$set": {"match_status_detail": new_status}}
        )
        print(f"    ✅ Stato impostato: {new_status}")
    else:
        # Rimuovi lo stato
        db.h2h_by_round.update_one(
            {"_id": rid, "matches.home": home, "matches.away": away},
            {"$unset": {"matches.$.match_status_detail": ""}}
        )
        db.daily_predictions_unified.update_many(
            {"home": home, "away": away, "league": league, "match_status_detail": {"$exists": True}},
            {"$unset": {"match_status_detail": ""}}
        )
        print(f"    ✅ Stato rimosso (partita ripristinata a normale)")


def change_match_status():
    """Cambia lo stato di una partita: posticipata, annullata, sospesa, ecc.
    Navigazione: Nazione → Campionato → Giornata → Partita → Stato."""

    while True:
        print(f"\n{'='*80}")
        print("🔄 CAMBIA STATO PARTITA")
        print(f"{'='*80}")

        # 1. Nazione
        countries = db.h2h_by_round.distinct("country")
        countries = sorted([c for c in countries if c])

        print(f"\nNazioni disponibili:\n")
        for i, c in enumerate(countries):
            print(f"  [{i+1}] {c}")
        print(f"\n  [0] Torna al menu principale")
        print()

        idx = safe_input("Scegli nazione (numero): ")
        if idx == '0':
            return
        try:
            country = countries[int(idx) - 1]
        except (ValueError, IndexError):
            print("Scelta non valida.")
            continue

        # 2. Campionato
        while True:
            leagues = db.h2h_by_round.distinct("league", {"country": country})
            leagues = sorted([l for l in leagues if l])

            print(f"\nCampionati {country}:\n")
            for i, l in enumerate(leagues):
                print(f"  [{i+1}] {l}")
            print(f"\n  [0] Indietro (nazioni)")
            print()

            idx = safe_input("Scegli campionato (numero): ")
            if idx == '0':
                break
            try:
                league = leagues[int(idx) - 1]
            except (ValueError, IndexError):
                print("Scelta non valida.")
                continue

            # 3. Giornata
            while True:
                def _round_sort_key(r):
                    m = re.match(r'(\d+)', r.get('round_name') or '0')
                    return int(m.group(1)) if m else 0

                rounds = sorted(
                    list(db.h2h_by_round.find(
                        {"country": country, "league": league},
                        {"round_name": 1, "_id": 1}
                    )),
                    key=_round_sort_key
                )

                if not rounds:
                    print(f"Nessuna giornata trovata per {league}")
                    break

                print(f"\nGiornate {league}:\n")
                for i, r in enumerate(rounds):
                    rname = r.get("round_name") or "N/A"
                    print(f"  [{i+1}] {rname}")
                print(f"\n  [0] Indietro (campionati)")
                print()

                idx = safe_input("Scegli giornata (numero): ")
                if idx == '0':
                    break
                try:
                    round_doc = rounds[int(idx) - 1]
                except (ValueError, IndexError):
                    print("Scelta non valida.")
                    continue

                full_doc = db.h2h_by_round.find_one({"_id": round_doc["_id"]})
                matches = full_doc.get("matches", [])
                round_id = str(full_doc["_id"])

                if not matches:
                    print("Nessuna partita in questa giornata.")
                    continue

                # 4. Partita
                while True:
                    print(f"\nPartite {round_doc.get('round_name', '')}:\n")
                    for i, m in enumerate(matches):
                        date_obj = m.get("date_obj")
                        date_str = date_obj.strftime("%d/%m/%Y") if hasattr(date_obj, "strftime") else "N/A"
                        time_str = m.get("match_time", "N/A")
                        status_detail = m.get("match_status_detail", "")
                        tag = f" ⚠️ [{status_detail}]" if status_detail else ""
                        print(f"  [{i+1}] {m['home']} vs {m['away']}  |  {date_str} {time_str}{tag}")
                    print(f"\n  [0] Indietro (giornate)")
                    print()

                    idx = safe_input("Scegli partita (numero): ")
                    if idx == '0':
                        break
                    try:
                        match = matches[int(idx) - 1]
                    except (ValueError, IndexError):
                        print("Scelta non valida.")
                        continue

                    # 5. Mostra stato attuale e scegli nuovo
                    current_status = match.get("match_status_detail")
                    print(f"\n  Partita: {match['home']} vs {match['away']}")
                    if current_status:
                        print(f"  Stato attuale: ⚠️ {current_status}")
                    else:
                        print(f"  Stato attuale: ✅ Normale (nessuno stato speciale)")

                    print(f"\n  Scegli nuovo stato:\n")
                    for i, (code, label) in enumerate(MATCH_STATUSES):
                        marker = " ← attuale" if code == current_status else ""
                        print(f"    [{i+1}] {label} ({code}){marker}")
                    print(f"    [L] Testo libero")
                    if current_status:
                        print(f"    [R] Rimuovi stato (ripristina a normale)")
                    print(f"    [0] Annulla")
                    print()

                    scelta = safe_input("  Scelta: ").upper()
                    if scelta == '0':
                        continue

                    new_status = None
                    if scelta == 'R' and current_status:
                        new_status = None  # rimuovi
                        label_display = "RIMOSSO (normale)"
                    elif scelta == 'L':
                        new_status = safe_input("  Scrivi lo stato: ").strip()
                        if not new_status:
                            print("  Annullato.")
                            continue
                        label_display = new_status
                    else:
                        try:
                            idx_s = int(scelta) - 1
                            new_status = MATCH_STATUSES[idx_s][0]
                            label_display = f"{MATCH_STATUSES[idx_s][1]} ({new_status})"
                        except (ValueError, IndexError):
                            print("  Scelta non valida.")
                            continue

                    # Per stati che implicano rinvio, chiedi cosa fare con la data
                    new_date = None
                    new_time = None
                    date_action = None
                    if new_status in ('Postp.', 'Suspended') and scelta != 'R':
                        old_date_obj = match.get("date_obj")
                        old_date_db = old_date_obj.strftime("%Y-%m-%d") if hasattr(old_date_obj, "strftime") else "N/A"
                        old_date_ita = to_ita(old_date_db)
                        old_time = match.get("match_time", "N/A")

                        print(f"\n  Data attuale: {old_date_ita} {old_time}")
                        print(f"\n  Cosa vuoi fare con la data?")
                        print(f"    [1] Inserisci nuova data/orario")
                        print(f"    [2] Data da destinarsi (TBD)")
                        print(f"    [3] Lascia la data com'è")
                        print(f"    [0] Annulla tutto")
                        print()

                        date_choice = safe_input("  Scelta: ")
                        if date_choice == '0':
                            print("  Annullato.")
                            continue
                        elif date_choice == '1':
                            date_action = 'manual'
                            new_date = ask_date("  Nuova data (GG/MM/AAAA)", old_date_ita)
                            if new_date is None:
                                print("  Annullato.")
                                continue
                            new_time = ask_time("  Nuovo orario (HH:MM)", old_time)
                            if new_time is None:
                                print("  Annullato.")
                                continue
                        elif date_choice == '2':
                            date_action = 'tbd'
                        else:
                            date_action = 'keep'

                    # Conferma riepilogo
                    if scelta == 'R':
                        print(f"\n  Stato: ⚠️ {current_status}  →  ✅ Normale")
                    elif current_status:
                        print(f"\n  Stato: ⚠️ {current_status}  →  ⚠️ {label_display}")
                    else:
                        print(f"\n  Stato: ✅ Normale  →  ⚠️ {label_display}")

                    if date_action == 'manual':
                        print(f"  Data: →  {to_ita(new_date)} {new_time}")
                    elif date_action == 'tbd':
                        print(f"  Data: →  Da destinarsi (TBD)")

                    conferma = safe_input("  Confermi? (S/N): ").upper()
                    if conferma != 'S':
                        print("  Annullato.")
                        continue

                    # Applica stato
                    apply_status_change(round_id, match['home'], match['away'], league, new_status)

                    # Applica cambio data se richiesto
                    if date_action == 'manual' and new_date and new_time:
                        old_date_obj = match.get("date_obj")
                        old_date_db = old_date_obj.strftime("%Y-%m-%d") if hasattr(old_date_obj, "strftime") else "N/A"
                        change = {
                            "league": league,
                            "home": match["home"],
                            "away": match["away"],
                            "new_date": new_date,
                            "new_time": new_time,
                            "status": new_status,
                            "round_id": round_id,
                        }
                        apply_change(change)
                    elif date_action == 'tbd':
                        # Salva "TBD" come orario per indicare data da destinarsi
                        try:
                            rid = ObjectId(round_id)
                        except Exception:
                            rid = round_id
                        db.h2h_by_round.update_one(
                            {"_id": rid, "matches.home": match['home'], "matches.away": match['away']},
                            {"$set": {"matches.$.match_time": "TBD"}}
                        )
                        db.daily_predictions_unified.update_many(
                            {"home": match['home'], "away": match['away'], "league": league},
                            {"$set": {"match_time": "TBD"}}
                        )
                        print(f"    ✅ Orario impostato a TBD")

                    # Aggiorna in memoria locale
                    if new_status:
                        match['match_status_detail'] = new_status
                    elif 'match_status_detail' in match:
                        del match['match_status_detail']
                    print(f"\n✅ Stato aggiornato!")


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

    scelta = safe_input("Scelta: ").upper()

    if scelta == 'N':
        return

    if scelta == 'P':
        show_changes(changes)
        return

    if scelta == 'T':
        show_changes(changes)
        conferma = safe_input("Confermi di applicare TUTTE? (S/N): ").upper()
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
                print(f"  DATA ORIGINALE (Step 11): {to_ita(c['old_date'])}")
                print(f"  DATA NOWGOAL (Step 12):   {to_ita(c['new_date'])}")
            if c['old_time'] != c['new_time']:
                print(f"  ORARIO ORIGINALE: {c['old_time'] or 'N/A'}")
                print(f"  ORARIO NOWGOAL:   {c['new_time']}")

            risposta = safe_input("  (S=applica NowGoal / N=scarta / M=inserisci manualmente): ").upper()
            if risposta == 'S':
                apply_change(c)
                applied += 1
            elif risposta == 'M':
                default_date_ita = to_ita(c['old_date'] or c['new_date'])
                default_time = c['old_time'] or c['new_time']
                print(f"    Inserisci i dati corretti (invio = valore tra parentesi):")
                manual_date = ask_date("    Data (GG/MM/AAAA)", default_date_ita)
                if manual_date is None:
                    skipped += 1
                    print("    ❌ Annullato")
                    continue
                manual_time = ask_time("    Orario (HH:MM)", default_time)
                if manual_time is None:
                    skipped += 1
                    print("    ❌ Annullato")
                    continue
                c['new_date'] = manual_date
                c['new_time'] = manual_time
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

    print("  [1] Correzione manuale date/orari (scegli campionato e partita)")
    if has_pending:
        print(f"  [2] Modifiche in attesa dallo Step 12 ({pending_count} pending)")
    else:
        print("  [2] Modifiche in attesa dallo Step 12 (nessuna)")
    print("  [3] Cambia stato partita (posticipata, annullata, ecc.)")
    print("  [N] Esci")
    print()

    scelta = safe_input("Scelta: ").upper()

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

    if scelta == '3':
        change_match_status()
        return

    print("Scelta non valida.")


if __name__ == "__main__":
    try:
        main()
    except ExitScript:
        print("\n\n👋 Uscita dallo script.")
    except KeyboardInterrupt:
        print("\n\n👋 Uscita dallo script.")
