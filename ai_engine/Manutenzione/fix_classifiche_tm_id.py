"""
fix_classifiche_tm_id.py
Riconcilia i transfermarkt_id mancanti nella collection 'classifiche'
usando i dati di 'h2h_by_round' come fonte autorevole.
"""
import os, sys

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

def fix_missing_tm_ids():
    """Per ogni squadra senza tm_id in classifiche, cerca il match in h2h_by_round."""

    # 1. Costruisci mappa nome→tm_id da h2h_by_round (tutte le leghe)
    print("📋 Costruzione mappa nomi da h2h_by_round...")
    name_to_tmid = {}  # (league, nome_normalizzato) → tm_id
    raw_name_map = {}  # (league, nome_normalizzato) → nome originale

    def norm(s):
        import unicodedata
        s = unicodedata.normalize('NFD', s)
        s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
        return s.lower().strip()

    all_rounds = db['h2h_by_round'].find({}, {'league': 1, 'matches.home': 1, 'matches.away': 1, 'matches.home_tm_id': 1, 'matches.away_tm_id': 1})
    for doc in all_rounds:
        league = doc.get('league', '')
        for m in doc.get('matches', []):
            home = m.get('home', '')
            away = m.get('away', '')
            h_id = m.get('home_tm_id')
            a_id = m.get('away_tm_id')
            if home and h_id:
                key = (league, norm(home))
                name_to_tmid[key] = h_id
                raw_name_map[key] = home
            if away and a_id:
                key = (league, norm(away))
                name_to_tmid[key] = a_id
                raw_name_map[key] = away

    print(f"   ✅ {len(name_to_tmid)} coppie (lega, squadra) → tm_id")

    # 2. Scorri classifiche e fix dove manca
    classifiche = list(db['classifiche'].find({}))
    fixed = 0
    not_found = []

    for doc in classifiche:
        league = doc.get('league', '')
        table = doc.get('table', [])
        updated = False

        for i, row in enumerate(table):
            if row.get('transfermarkt_id'):
                continue  # già presente

            team_name = row.get('team', '')
            team_norm = norm(team_name)

            # Tentativo 1: match esatto per (league, nome_normalizzato)
            key = (league, team_norm)
            tm_id = name_to_tmid.get(key)

            # Tentativo 2: substring match nella stessa lega
            if not tm_id:
                for (l, n), tid in name_to_tmid.items():
                    if l != league:
                        continue
                    if len(team_norm) > 3 and len(n) > 3:
                        if team_norm in n or n in team_norm:
                            tm_id = tid
                            break

            # Tentativo 3: primo token significativo (>3 char)
            if not tm_id:
                tokens = [t for t in team_norm.split() if len(t) > 3]
                if tokens:
                    first_token = tokens[0]
                    candidates = [(l, n, tid) for (l, n), tid in name_to_tmid.items() if l == league and first_token in n]
                    if len(candidates) == 1:
                        tm_id = candidates[0][2]

            if tm_id:
                table[i]['transfermarkt_id'] = tm_id
                updated = True
                fixed += 1
                match_name = raw_name_map.get((league, team_norm), '?')
                print(f"   ✅ {league}: \"{team_name}\" → tm_id={tm_id}")
            else:
                not_found.append((league, team_name))

        if updated:
            db['classifiche'].update_one({'_id': doc['_id']}, {'$set': {'table': table}})

    print(f"\n{'='*50}")
    print(f"🏁 COMPLETATO: {fixed} squadre corrette")
    if not_found:
        print(f"⚠️  {len(not_found)} squadre ancora senza tm_id:")
        for league, name in not_found:
            print(f"   ❌ {league}: \"{name}\"")

if __name__ == '__main__':
    fix_missing_tm_ids()
