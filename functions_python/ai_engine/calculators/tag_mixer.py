"""
Tag Mixer — Tagga i pronostici unified che matchano i 74 pattern (14 genitori + 60 ibridi).
Gira dopo tag_elite.py nella pipeline. Aggiunge: mixer (bool), mixer_patterns (lista ID).
"""

import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    print("ERRORE: MONGO_URI non trovata")
    sys.exit(1)

client = MongoClient(MONGO_URI)
db = client['football_simulator_db']
coll = db['daily_predictions_unified']

today = datetime.now()
dates = [(today + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]


# ============================================================
# Condizioni atomiche
# ============================================================
def _check(p):
    """Restituisce un dict di condizioni booleane per il pronostico."""
    tipo = p.get('tipo', '')
    quota = p.get('quota', 0) or 0
    confidence = p.get('confidence', 0) or 0
    stars = p.get('stars', 0) or 0
    source = p.get('source', '')
    pronostico = p.get('pronostico', '')
    routing = p.get('routing_rule', '')
    edge = p.get('edge', 0) or 0

    return {
        'conf50-59': 50 <= confidence <= 59,
        'conf60-69': 60 <= confidence <= 69,
        'conf70-79': 70 <= confidence <= 79,
        'q1.30-1.49': 1.30 <= quota <= 1.49,
        'q1.50-1.79': 1.50 <= quota <= 1.79,
        'q3.00-3.99': 3.00 <= quota <= 3.99,
        'src_C_screm': source == 'C_screm',
        'src_C': source == 'C',
        'route_scrematura': routing == 'scrematura_segno',
        'route_union': routing == 'union',
        'route_single': routing == 'single',
        'tipo_GOL': tipo == 'GOL',
        'tipo_SEGNO': tipo == 'SEGNO',
        'pron_Goal': pronostico == 'Goal',
        'pron_1': pronostico == '1',
        'st3.6-3.9': 3.6 <= stars <= 3.9,
        'edge20-50': 20 < edge <= 50,
        'edge50+': edge > 50,
    }


# ============================================================
# 74 pattern: ogni pattern e un set di condizioni che devono essere TUTTE vere
# G = genitore (14), H = ibrido (60)
# ============================================================
PATTERNS = {
    # --- 14 GENITORI ---
    'G01': {'conf50-59', 'src_C_screm'},
    'G02': {'conf50-59', 'q1.50-1.79'},
    'G03': {'pron_Goal', 'q1.30-1.49'},
    'G04': {'conf60-69', 'q1.30-1.49'},
    'G05': {'route_union'},
    'G06': {'pron_1', 'st3.6-3.9'},
    'G07': {'conf70-79', 'q1.50-1.79'},
    'G08': {'src_C_screm', 'route_scrematura'},
    'G09': {'src_C', 'st3.6-3.9'},
    'G10': {'edge20-50', 'q1.50-1.79'},
    'G11': {'conf60-69', 'edge50+'},
    'G12': {'conf60-69', 'src_C'},
    'G13': {'q3.00-3.99', 'route_single'},
    'G14': {'edge50+', 'tipo_SEGNO'},

    # --- 60 IBRIDI ---
    'H01': {'conf50-59', 'route_scrematura'},
    'H02': {'conf60-69', 'src_C_screm'},
    'H03': {'q1.30-1.49', 'src_C'},
    'H04': {'q1.30-1.49', 'st3.6-3.9'},
    'H05': {'route_union', 'tipo_GOL'},
    'H06': {'conf50-59', 'q1.50-1.79', 'src_C_screm'},
    'H07': {'conf50-59', 'q1.50-1.79', 'route_scrematura'},
    'H08': {'conf50-59', 'q1.50-1.79', 'tipo_GOL'},
    'H09': {'conf50-59', 'route_scrematura', 'src_C_screm'},
    'H10': {'conf50-59', 'src_C_screm', 'tipo_GOL'},
    'H11': {'conf50-59', 'route_scrematura', 'tipo_GOL'},
    'H12': {'conf60-69', 'q1.30-1.49', 'st3.6-3.9'},
    'H13': {'conf60-69', 'q1.50-1.79', 'route_single'},
    'H14': {'conf60-69', 'src_C_screm', 'tipo_GOL'},
    'H15': {'conf60-69', 'pron_1', 'src_C'},
    'H16': {'conf60-69', 'pron_1', 'route_single'},
    'H17': {'conf70-79', 'q1.30-1.49', 'src_C'},
    'H18': {'conf70-79', 'q1.30-1.49', 'st3.6-3.9'},
    'H19': {'conf70-79', 'edge20-50', 'pron_1'},
    'H20': {'q1.30-1.49', 'src_C', 'tipo_GOL'},
    'H21': {'pron_Goal', 'q1.30-1.49', 'src_C'},
    'H22': {'q1.30-1.49', 'src_C', 'st3.6-3.9'},
    'H23': {'pron_Goal', 'q1.30-1.49', 'tipo_GOL'},
    'H24': {'q1.30-1.49', 'st3.6-3.9', 'tipo_GOL'},
    'H25': {'pron_Goal', 'q1.30-1.49', 'st3.6-3.9'},
    'H26': {'q1.50-1.79', 'src_C_screm', 'tipo_GOL'},
    'H27': {'q1.50-1.79', 'route_scrematura', 'tipo_GOL'},
    'H28': {'edge20-50', 'q1.50-1.79', 'route_single'},
    'H29': {'edge20-50', 'q1.50-1.79', 'tipo_SEGNO'},
    'H30': {'edge20-50', 'pron_1', 'q1.50-1.79'},
    'H31': {'conf50-59', 'q1.50-1.79', 'route_scrematura', 'src_C_screm'},
    'H32': {'conf50-59', 'q1.50-1.79', 'src_C_screm', 'tipo_GOL'},
    'H33': {'conf50-59', 'q1.50-1.79', 'route_scrematura', 'tipo_GOL'},
    'H34': {'conf50-59', 'route_scrematura', 'src_C_screm', 'tipo_GOL'},
    'H35': {'conf60-69', 'q1.30-1.49', 'st3.6-3.9', 'tipo_GOL'},
    'H36': {'conf60-69', 'q1.50-1.79', 'route_single', 'src_C'},
    'H37': {'conf60-69', 'q1.50-1.79', 'src_C', 'tipo_SEGNO'},
    'H38': {'conf60-69', 'q1.50-1.79', 'route_single', 'tipo_SEGNO'},
    'H39': {'conf60-69', 'pron_1', 'route_single', 'src_C'},
    'H40': {'conf60-69', 'pron_1', 'src_C', 'tipo_SEGNO'},
    'H41': {'conf60-69', 'pron_1', 'route_single', 'tipo_SEGNO'},
    'H42': {'conf70-79', 'q1.30-1.49', 'src_C', 'tipo_GOL'},
    'H43': {'conf70-79', 'pron_Goal', 'q1.30-1.49', 'src_C'},
    'H44': {'conf70-79', 'q1.30-1.49', 'st3.6-3.9', 'tipo_GOL'},
    'H45': {'conf70-79', 'edge20-50', 'pron_1', 'src_C'},
    'H46': {'conf70-79', 'edge20-50', 'pron_1', 'route_single'},
    'H47': {'conf70-79', 'edge20-50', 'pron_1', 'tipo_SEGNO'},
    'H48': {'pron_Goal', 'q1.30-1.49', 'src_C', 'tipo_GOL'},
    'H49': {'q1.30-1.49', 'src_C', 'st3.6-3.9', 'tipo_GOL'},
    'H50': {'pron_Goal', 'q1.30-1.49', 'src_C', 'st3.6-3.9'},
    'H51': {'pron_Goal', 'q1.30-1.49', 'st3.6-3.9', 'tipo_GOL'},
    'H52': {'q1.50-1.79', 'route_scrematura', 'src_C_screm', 'tipo_GOL'},
    'H53': {'edge20-50', 'q1.50-1.79', 'route_single', 'src_C'},
    'H54': {'edge20-50', 'q1.50-1.79', 'src_C', 'tipo_SEGNO'},
    'H55': {'pron_1', 'q1.50-1.79', 'src_C', 'st3.6-3.9'},
    'H56': {'edge20-50', 'pron_1', 'q1.50-1.79', 'src_C'},
    'H57': {'edge20-50', 'q1.50-1.79', 'route_single', 'tipo_SEGNO'},
    'H58': {'pron_1', 'q1.50-1.79', 'route_single', 'st3.6-3.9'},
    'H59': {'edge20-50', 'pron_1', 'q1.50-1.79', 'route_single'},
    'H60': {'edge20-50', 'pron_1', 'q1.50-1.79', 'tipo_SEGNO'},
}


def get_matched_mixer_patterns(p):
    """Restituisce la lista di pattern ID che il pronostico matcha."""
    if p.get('pronostico') == 'NO BET':
        return []

    flags = _check(p)
    matched = []
    for pat_id, conditions in PATTERNS.items():
        if all(flags.get(c, False) for c in conditions):
            matched.append(pat_id)
    return matched


def main():
    print(f"=== TAG MIXER — {today.strftime('%Y-%m-%d %H:%M')} ===")
    print(f"Date da processare: {dates}")
    print(f"Pattern totali: {len(PATTERNS)} (14 genitori + 60 ibridi)")

    total_tagged = 0
    total_matches = 0

    for date in dates:
        docs = list(coll.find({"date": date}, {"_id": 1, "home": 1, "away": 1, "pronostici": 1}))
        if not docs:
            continue

        date_tagged = 0
        for doc in docs:
            pronostici = doc.get('pronostici', [])
            changed = False

            for p in pronostici:
                matched = get_matched_mixer_patterns(p)
                is_mixer = len(matched) > 0
                old_mixer = p.get('mixer', False)
                old_patterns = p.get('mixer_patterns', [])

                p['mixer'] = is_mixer
                p['mixer_patterns'] = sorted(matched)

                if is_mixer != old_mixer or sorted(matched) != old_patterns:
                    changed = True
                if is_mixer:
                    total_tagged += 1
                    date_tagged += 1

            if changed:
                coll.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"pronostici": pronostici}}
                )
                total_matches += 1

        print(f"  {date}: {len(docs)} partite, {date_tagged} pronostici mixer")

    print(f"\nTotale: {total_tagged} pronostici mixer in {total_matches} partite aggiornate")
    client.close()


if __name__ == '__main__':
    main()
