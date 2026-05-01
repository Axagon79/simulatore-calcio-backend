"""
Process Shield Refunds — Step pipeline notturna.

Trova tutte le transazioni Firestore `shield_attivato` non ancora processate,
verifica esito partita su MongoDB, e accredita refund se almeno uno dei
pronostici sbloccati è sbagliato.

Logica costo: rimborso = quanto pagato (1 credito se abbonato, 3 se gratuito).
Letto da `pronostico_sbloccato.metadata.cost`.

Idempotenza: flag `refund_processed: true` sulla transazione shield originale.
"""

import os
import sys
import re
from datetime import datetime, timedelta

# --- FIX PERCORSI per import config (mongo_db) ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db as mongo_db

# --- FIREBASE ADMIN ---
import firebase_admin
from firebase_admin import credentials, firestore

# Path service account (override via env var GOOGLE_APPLICATION_CREDENTIALS)
SERVICE_ACCOUNT_PATH = os.environ.get(
    'GOOGLE_APPLICATION_CREDENTIALS',
    r'C:\Users\lollo\Desktop\CARTELLE\1\serviceAccount.json'
)

if not firebase_admin._apps:
    if not os.path.exists(SERVICE_ACCOUNT_PATH):
        print(f"ERRORE: service account non trovato in {SERVICE_ACCOUNT_PATH}")
        sys.exit(1)
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    firebase_admin.initialize_app(cred)

fs = firestore.client()


# ==================== HELPER HIT/MISS ====================

def parse_score(real_score):
    """Parsa "2:1" o "2-1" -> dict con campi calcolati."""
    if not real_score:
        return None
    parts = re.split(r'[:\-]', str(real_score).strip())
    if len(parts) != 2:
        return None
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    sign = '1' if h > a else ('X' if h == a else '2')
    return {
        'home': h,
        'away': a,
        'total': h + a,
        'sign': sign,
        'btts': h > 0 and a > 0,
    }


def check_pronostico(pronostico, tipo, parsed):
    """True/False/None - esito del pronostico vs risultato."""
    if not parsed or not pronostico:
        return None
    p = str(pronostico).strip()
    t = (tipo or '').upper()

    if t in ('SEGNO', '1X2 ESITO FINALE', '1X2'):
        return parsed['sign'] == p
    if t in ('DOPPIA_CHANCE', 'DOPPIA CHANCE'):
        if p == '1X': return parsed['sign'] in ('1', 'X')
        if p == 'X2': return parsed['sign'] in ('X', '2')
        if p == '12': return parsed['sign'] in ('1', '2')
        return None
    if t in ('GOL', 'GOAL', 'GOAL/NOGOAL', 'U/O'):
        m = re.match(r'(Over|Under)\s+([\d.]+)', p, re.IGNORECASE)
        if m:
            thr = float(m.group(2))
            return parsed['total'] > thr if m.group(1).lower() == 'over' else parsed['total'] < thr
        lp = p.lower()
        if lp in ('goal', 'si'): return parsed['btts']
        if lp in ('nogoal', 'no'): return not parsed['btts']
        mg = re.match(r'MG\s+(\d+)-(\d+)', p, re.IGNORECASE)
        if mg:
            return int(mg.group(1)) <= parsed['total'] <= int(mg.group(2))
    if t in ('RISULTATO_ESATTO', 'RISULTATO ESATTO'):
        return f"{parsed['home']}:{parsed['away']}" == p.replace('-', ':')
    return None


# ==================== LOOKUP RISULTATO ====================

def find_real_score(home, away, match_date):
    """Cerca real_score in h2h_by_round (campionati) e nelle 2 collezioni coppe."""
    try:
        start = datetime.strptime(match_date, '%Y-%m-%d')
        end = start + timedelta(days=1)
    except ValueError:
        return None

    # 1. Campionati
    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {
            "matches.date_obj": {"$gte": start, "$lt": end},
            "matches.home": home,
            "matches.away": away,
        }},
        {"$project": {
            "_id": 0,
            "real_score": "$matches.real_score",
            "live_score": "$matches.live_score",
            "live_status": "$matches.live_status",
        }},
        {"$limit": 1},
    ]
    docs = list(mongo_db.h2h_by_round.aggregate(pipeline))
    if docs:
        d = docs[0]
        rs = d.get('real_score')
        if not rs and d.get('live_status') == 'Finished':
            rs = d.get('live_score')
        if rs:
            return rs

    # 2. Coppe (formato match_date: DD-MM-YYYY HH:MM)
    y, m, dd = match_date.split('-')
    cup_prefix = f"{dd}-{m}-{y}"
    for coll_name in ('matches_champions_league', 'matches_europa_league'):
        if coll_name not in mongo_db.list_collection_names():
            continue
        cm = mongo_db[coll_name].find_one({
            'match_date': {'$regex': f'^{cup_prefix}'},
            'home_team': home,
            'away_team': away,
        })
        if cm:
            rs = cm.get('real_score') or cm.get('live_score')
            status = (cm.get('status') or '').lower()
            live_status = (cm.get('live_status') or '').lower()
            if rs and (status in ('finished', 'ft') or live_status in ('finished', 'ft')):
                return rs

    return None


# ==================== MAIN ====================

def main():
    print("\n" + "=" * 60)
    print("PROCESS SHIELD REFUNDS")
    print("=" * 60)
    print(f"Avvio: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")

    # 1. Trova tutte le shield_attivato non processate
    shields_query = fs.collection('wallet_transactions').where('type', '==', 'shield_attivato').stream()
    shields = [doc for doc in shields_query if not doc.to_dict().get('refund_processed')]
    print(f"Shield non processati: {len(shields)}\n")

    if not shields:
        print("Nessun shield da processare. Fine.\n")
        return

    processed = 0
    refunded_credits = 0
    errors = []

    for shield_doc in shields:
        shield = shield_doc.to_dict()
        shield_id = shield_doc.id
        user_id = shield.get('user_id')
        match_key = (shield.get('metadata') or {}).get('match_key')

        if not user_id or not match_key:
            errors.append(f"{shield_id}: user_id o match_key mancante")
            continue

        try:
            # 2. Trova pronostico_sbloccato correlata
            sblocco_query = (
                fs.collection('wallet_transactions')
                .where('user_id', '==', user_id)
                .where('type', '==', 'pronostico_sbloccato')
                .where('metadata.match_key', '==', match_key)
                .limit(1)
                .stream()
            )
            sblocchi = list(sblocco_query)
            if not sblocchi:
                shield_doc.reference.update({
                    'refund_processed': True,
                    'refund_skipped_reason': 'no_pronostico_sbloccato_trovato',
                })
                errors.append(f"{shield_id}: pronostico_sbloccato non trovato per {match_key}")
                continue

            sblocco_doc = sblocchi[0]
            sblocco = sblocco_doc.to_dict()
            metadata = sblocco.get('metadata') or {}
            cost = metadata.get('cost', abs(sblocco.get('credits_delta', 0) or 0))
            snapshot = metadata.get('snapshot_at_purchase') or []

            # 3. Estrai (home, away, date) da match_key
            mk = re.match(r'^(\d{4}-\d{2}-\d{2})_(.+?)_(.+)$', match_key)
            if not mk:
                shield_doc.reference.update({
                    'refund_processed': True,
                    'refund_skipped_reason': 'match_key_formato_non_valido',
                })
                errors.append(f"{shield_id}: match_key formato invalido '{match_key}'")
                continue

            match_date, home, away = mk.group(1), mk.group(2), mk.group(3)

            # 4. Cerca real_score
            real_score = find_real_score(home, away, match_date)
            if not real_score:
                # Partita non finita ancora -> skip silenzioso
                continue

            parsed = parse_score(real_score)
            if not parsed:
                errors.append(f"{shield_id}: score '{real_score}' non parsabile")
                continue

            # 5. Verifica esiti pronostici
            almeno_uno_sbagliato = False
            for p in snapshot:
                hit = check_pronostico(p.get('pronostico'), p.get('tipo'), parsed)
                if hit is False:
                    almeno_uno_sbagliato = True
                    break

            # 6. Decisione refund
            if almeno_uno_sbagliato and cost > 0:
                user_ref = fs.collection('users').document(user_id)
                refund_ref = fs.collection('wallet_transactions').document()
                transaction = fs.transaction()

                @firestore.transactional
                def do_refund(tx):
                    user_snap = user_ref.get(transaction=tx)
                    current = user_snap.to_dict() if user_snap.exists else {}
                    new_credits = (current.get('credits') or 0) + cost
                    new_shields = current.get('shields') or 0

                    tx.set(user_ref, {'credits': new_credits}, merge=True)
                    tx.set(refund_ref, {
                        'user_id': user_id,
                        'type': 'shield_restituito',
                        'description': f"Rimborso shield: {home} vs {away}",
                        'credits_delta': cost,
                        'shields_delta': 0,
                        'amount_eur': 0,
                        'balance_after': {'credits': new_credits, 'shields': new_shields},
                        'metadata': {
                            'match_key': match_key,
                            'refund_for_shield_tx': shield_id,
                            'refund_for_sblocco_tx': sblocco_doc.id,
                        },
                        'created_at': firestore.SERVER_TIMESTAMP,
                    })
                    tx.update(shield_doc.reference, {
                        'refund_processed': True,
                        'refund_amount': cost,
                        'refund_tx_id': refund_ref.id,
                    })
                    return new_credits

                new_balance = do_refund(transaction)
                refunded_credits += cost
                print(f"  +{cost} crediti a {user_id[:12]}... per {home} vs {away} (saldo: {new_balance})")
            else:
                reason = 'cost_zero' if almeno_uno_sbagliato else 'pronostico_centrato'
                shield_doc.reference.update({
                    'refund_processed': True,
                    'refund_amount': 0,
                    'refund_skipped_reason': reason,
                })
                print(f"  OK {home} vs {away}: {reason}")

            processed += 1

        except Exception as e:
            print(f"  ERRORE su {shield_id}: {e}")
            errors.append(f"{shield_id}: {e}")

    # Riepilogo
    print()
    print("=" * 60)
    print(f"Shield processati: {processed}/{len(shields)}")
    print(f"Crediti rimborsati totali: {refunded_credits}")
    if errors:
        print(f"Errori: {len(errors)}")
        for e in errors[:10]:
            print(f"    - {e}")
    print("=" * 60)


if __name__ == "__main__":
    main()
