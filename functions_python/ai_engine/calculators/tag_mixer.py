"""
Tag Mixer — Tagga i pronostici unified che matchano i 74 pattern (14 genitori + 60 ibridi).
Esporta anche PATTERNS (85 = 74 + 11 salvati) usato da generate_bollette_2.py per il pool bollette.
Gira dopo tag_elite.py nella pipeline. Aggiunge: mixer (bool), mixer_patterns (lista ID).
"""

import os
import sys
from datetime import datetime, timedelta


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
        'conf60+': confidence >= 60,
        'conf70+': confidence >= 70,
        'conf80+': confidence >= 80,
        'conf85+': confidence >= 85,
        'q1.30-1.39': 1.30 <= quota <= 1.39,
        'q1.30-1.49': 1.30 <= quota <= 1.49,
        'q1.50-1.79': 1.50 <= quota <= 1.79,
        'q1.60-1.79': 1.60 <= quota <= 1.79,  # aggiunto 18/04/2026 per pattern V
        'q_lt1.60': quota < 1.60,
        'q3.00-3.99': 3.00 <= quota <= 3.99,
        'src_A': source == 'A',
        'src_C_screm': source == 'C_screm',
        'src_C': source == 'C',
        'route_scrematura': routing == 'scrematura_segno',
        'route_union': routing == 'union',
        'route_single': routing == 'single',
        'route_consensus_both': routing == 'consensus_both',
        'tipo_GOL': tipo == 'GOL',
        'tipo_SEGNO': tipo == 'SEGNO',
        'tipo_DC': tipo == 'DOPPIA_CHANCE',
        'pron_Goal': pronostico == 'Goal',
        'pron_1': pronostico == '1',
        'pron_Over1.5': pronostico == 'Over 1.5',
        'st3.0+': stars >= 3.0,
        'st3.0-3.5': 3.0 <= stars < 3.5,
        'st3.5+': stars >= 3.5,
        'st3.6-3.9': 3.6 <= stars <= 3.9,
        'st4.0+': stars >= 4.0,  # aggiunto 18/04/2026 per pattern V
        'conf80-100': 80 <= confidence <= 100,  # aggiunto 18/04/2026 per pattern V (alias di conf80+ ma esplicito)
        'edge20-50': 20 < edge <= 50,
        'edge50+': edge > 50,
    }


# ============================================================
# MIXER_PATTERNS: 74 pattern per la pagina Mixer (G+H)
# PATTERNS: 85 pattern per il pool bollette (G+H+S)
# ============================================================
MIXER_PATTERNS = {
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

    # --- 12 PATTERN V (aggiunti 18/04/2026) ---
    # Estratti da hybrid_pattern_mixer_v2 sui SEGNO (storico 2026-02-18 -> 2026-04-18, 1490 SEGNO valutati)
    # Tutti AFFIDABILI: HR>=70%, N>=20, quote >=1.50. Yield medio +24%.
    # 0 sovrapposizione gerarchica con G/H esistenti (lavorano su st4.0+, q1.60-1.79, conf80-100, conf85+).
    # Vedi memoria: disabilitazione-regole-segno.md
    'V01': {'pron_1', 'src_C', 'st4.0+'},                       # HR 79%, N=28, +9.4u, Yield +33.6%
    'V02': {'conf80-100', 'pron_1'},                            # HR 78%, N=23, +7.3u
    'V03': {'conf70+', 'q1.60-1.79', 'src_C', 'tipo_SEGNO'},    # HR 77%, N=26, +7.5u
    'V04': {'conf85+', 'src_C'},                                # HR 73%, N=22, +5.9u
    'V05': {'pron_1', 'q1.60-1.79', 'src_C', 'st3.0+'},         # HR 76%, N=42, +10.9u
    'V06': {'pron_1', 'st4.0+'},                                # HR 74%, N=31, +8.0u
    'V07': {'q1.60-1.79', 'src_C', 'st3.0+', 'tipo_SEGNO'},     # HR 74%, N=61, +13.6u
    'V08': {'conf85+', 'st3.0+'},                               # HR 71%, N=28, +5.8u
    'V09': {'q1.60-1.79', 'src_C', 'st3.0-3.5', 'tipo_SEGNO'},  # HR 73%, N=22, +4.2u
    'V10': {'pron_1', 'q1.60-1.79', 'src_C'},                   # HR 72%, N=54, +10.3u
    'V11': {'q1.60-1.79', 'src_C', 'tipo_SEGNO'},               # HR 70%, N=74, +12.0u
    'V12': {'conf50-59', 'q1.60-1.79', 'src_C'},                # HR 71%, N=21, +3.4u
}

# --- 11 SALVATI DA BOLLETTE (S01-S11) — solo per pool bollette, NON per pagina Mixer ---
_BOLLETTE_EXTRA = {
    'S01': {'conf70+', 'q1.30-1.39'},                                # HYB_080: 86.7% HR, +20.22u
    'S02': {'conf60+', 'q1.30-1.39', 'st3.0-3.5'},                   # HYB_102: 84.6% HR, +16.29u
    'S03': {'q1.30-1.39', 'route_consensus_both', 'st3.0-3.5'},      # HYB_101: 83.3% HR, +15.94u
    'S04': {'conf70-79', 'pron_Over1.5'},                             # HYB_145: 100% HR, +14.03u
    'S05': {'pron_Over1.5', 'route_consensus_both'},                  # HYB_079: 100% HR, +8.18u
    'S06': {'q1.30-1.49', 'st3.5+'},                                 # HYB_038: 100% HR, +11.68u
    'S07': {'tipo_GOL', 'conf70+', 'st3.5+', 'q_lt1.60'},            # B24: 100% HR, +9.33u
    'S08': {'tipo_GOL', 'q1.30-1.39', 'conf60+'},                    # B18: 88.9% HR, +2.79u
    'S09': {'tipo_DC', 'route_consensus_both', 'st3.0+'},             # B12: 72.7% HR, +5.84u
    'S10': {'src_A', 'st3.5+'},                                      # HYB_060: 100% HR, +3.13u
    'S11': {'q1.30-1.39', 'src_A'},                                  # HYB_144: 100% HR, +1.48u
}

# PATTERNS = tutti (85) — usato da generate_bollette_2.py
PATTERNS = {**MIXER_PATTERNS, **_BOLLETTE_EXTRA}


def get_matched_mixer_patterns(p):
    """Restituisce la lista di pattern ID che il pronostico matcha.
    Logica gerarchica (introdotta 18/04/2026): se due pattern matchano e uno è
    sottoinsieme dell'altro, viene tenuto solo quello piu' specifico (con piu' condizioni).
    """
    if p.get('pronostico') == 'NO BET':
        return []

    flags = _check(p)
    matched_ids = []
    for pat_id, conditions in MIXER_PATTERNS.items():
        if all(flags.get(c, False) for c in conditions):
            matched_ids.append(pat_id)

    # Filtro gerarchico: rimuovi i pattern che sono sottoinsieme propri di un altro pattern matchato
    filtered = []
    for pid in matched_ids:
        cond_pid = MIXER_PATTERNS[pid]
        is_absorbed = False
        for other_id in matched_ids:
            if other_id == pid:
                continue
            cond_other = MIXER_PATTERNS[other_id]
            # pid e' assorbito se le sue condizioni sono un sottoinsieme proprio di other
            if cond_pid.issubset(cond_other) and cond_pid != cond_other:
                is_absorbed = True
                break
        if not is_absorbed:
            filtered.append(pid)

    return filtered


def main():
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

    print(f"=== TAG MIXER — {today.strftime('%Y-%m-%d %H:%M')} ===")
    print(f"Date da processare: {dates}")
    print(f"Pattern mixer: {len(MIXER_PATTERNS)} (14 genitori + 60 ibridi) | Bollette: {len(PATTERNS)} (+{len(_BOLLETTE_EXTRA)} salvati)")

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
