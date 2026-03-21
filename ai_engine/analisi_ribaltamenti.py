"""
Analisi Cambi Pronostici - v3
Traccia OGNI cambio consecutivo nella sequenza delle versioni.
Ogni transizione A->B conta come evento separato.
"""

from pymongo import MongoClient
from collections import defaultdict

MONGO_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/football_simulator_db?retryWrites=true&w=majority&appName=pup-pals-cluster"

client = MongoClient(MONGO_URI)
db = client['football_simulator_db']

DATE_FROM = "2026-03-16"
DATE_TO = "2026-03-21"

print(f"\n{'='*70}")
print(f"ANALISI CAMBI PRONOSTICI: {DATE_FROM} -> {DATE_TO}")
print(f"{'='*70}\n")

# 1. Raccogliere tutte le versioni
versions_cursor = db['prediction_versions'].find({
    'date': {'$gte': DATE_FROM, '$lte': DATE_TO},
    'pronostici': {'$ne': []}
}).sort('created_at', 1)

match_versions = defaultdict(list)
for doc in versions_cursor:
    match_versions[doc['match_key']].append(doc)

# 2. Ottenere esiti
unified_docs = {}
for doc in db['daily_predictions_unified'].find({
    'date': {'$gte': DATE_FROM, '$lte': DATE_TO}
}):
    home = doc.get('home', '').lower().replace(' ', '_')
    away = doc.get('away', '').lower().replace(' ', '_')
    key = f"{doc['date']}_{home}_{away}"
    unified_docs[key] = doc

# 3. Analizzare ogni match — traccia OGNI cambio consecutivo
all_matches = []  # lista di tutti i match con la loro sequenza completa

stable_count = 0
stable_resolved = {"win": 0, "loss": 0}
total_with_versions = 0

for match_key, versions in match_versions.items():
    if len(versions) < 2:
        continue

    total_with_versions += 1

    # Estrai tip principale (non RE) per ogni versione
    version_tips = []
    for v in versions:
        main_tips = [p for p in v.get('pronostici', []) if p.get('tipo') != 'RISULTATO_ESATTO']
        if main_tips:
            tip = main_tips[0]
            version_tips.append({
                'version': v['version'],
                'tipo': tip['tipo'],
                'pronostico': tip['pronostico'],
            })

    if len(version_tips) < 2:
        continue

    # Trova OGNI cambio consecutivo
    changes = []
    for i in range(1, len(version_tips)):
        prev = version_tips[i - 1]
        curr = version_tips[i]
        if prev['tipo'] != curr['tipo'] or prev['pronostico'] != curr['pronostico']:
            changes.append({
                'from_tipo': prev['tipo'],
                'from_pronostico': prev['pronostico'],
                'from_version': prev['version'],
                'to_tipo': curr['tipo'],
                'to_pronostico': curr['pronostico'],
                'to_version': curr['version'],
                'label': f"{prev['tipo']}:{prev['pronostico']}  ->  {curr['tipo']}:{curr['pronostico']}",
            })

    # Trova esito del pronostico FINALE
    unified = unified_docs.get(match_key)
    hit = None
    if unified:
        main_p = [p for p in unified.get('pronostici', []) if p.get('tipo') != 'RISULTATO_ESATTO']
        if main_p and 'hit' in main_p[0]:
            hit = main_p[0]['hit']

    path = " -> ".join(f"{v['tipo']}:{v['pronostico']}" for v in version_tips)
    date = match_key.split('_')[0]
    short_match = match_key.replace(date + '_', '')

    if not changes:
        stable_count += 1
        if hit is True:
            stable_resolved["win"] += 1
        elif hit is False:
            stable_resolved["loss"] += 1
        continue

    all_matches.append({
        'match_key': match_key,
        'short': short_match,
        'date': date,
        'path': path,
        'changes': changes,
        'n_changes': len(changes),
        'hit': hit,
    })

# 4. Scrivi report su file TXT
import os
output_path = os.path.join(os.path.dirname(__file__), 'log', 'analisi_cambi_pronostici.txt')
os.makedirs(os.path.dirname(output_path), exist_ok=True)

lines = []
def w(text=""):
    lines.append(text)

w(f"{'='*80}")
w(f"ANALISI CAMBI PRONOSTICI: {DATE_FROM} -> {DATE_TO}")
w(f"{'='*80}")
w()

# Stabili
stable_total = stable_resolved["win"] + stable_resolved["loss"]
stable_hr = (stable_resolved["win"] / stable_total * 100) if stable_total > 0 else 0
w(f"STABILI (nessun cambio): {stable_count} partite")
w(f"  Risolti: {stable_total} | Win: {stable_resolved['win']} | Loss: {stable_resolved['loss']} | Hit rate: {stable_hr:.1f}%")
w()

# Ordina per data, poi per numero di cambi
all_matches.sort(key=lambda m: (m['date'], -m['n_changes']))

changed_total = len(all_matches)
total_changes = sum(m['n_changes'] for m in all_matches)
w(f"CON CAMBI: {changed_total} partite, {total_changes} cambi totali")
w(f"{'='*80}")
w()

# === TABELLA COMPLETA ===
w(f"{'PARTITA':<45} {'DATA':<12} {'CAMBI':<6} {'ESITO':<8}")
w(f"{'-'*45} {'-'*12} {'-'*6} {'-'*8}")
for m in all_matches:
    status = "WIN" if m['hit'] is True else ("LOSS" if m['hit'] is False else "PENDING")
    name = m['short'].replace('_', ' ').title()
    if len(name) > 44:
        name = name[:41] + "..."
    w(f"{name:<45} {m['date']:<12} {m['n_changes']:<6} {status:<8}")
w()

# === DETTAGLIO PER PARTITA ===
w(f"{'='*80}")
w("DETTAGLIO COMPLETO PER PARTITA")
w(f"{'='*80}")
w()

for m in all_matches:
    status = "WIN" if m['hit'] is True else ("LOSS" if m['hit'] is False else "PENDING")
    name = m['short'].replace('_', ' ').title()
    w(f"  {m['date']} | {name} | {m['n_changes']} cambi | {status}")
    w(f"  Sequenza: {m['path']}")
    for j, c in enumerate(m['changes'], 1):
        w(f"    cambio {j}: {c['label']}  ({c['from_version']} -> {c['to_version']})")
    w()

# === FREQUENZA TRANSIZIONI ===
w(f"{'='*80}")
w("FREQUENZA TRANSIZIONI (ogni singolo cambio)")
w(f"{'='*80}")
w()

transition_counts = defaultdict(lambda: {"total": 0, "win": 0, "loss": 0, "pending": 0})
for m in all_matches:
    for c in m['changes']:
        transition_counts[c['label']]["total"] += 1
        if m['hit'] is True:
            transition_counts[c['label']]["win"] += 1
        elif m['hit'] is False:
            transition_counts[c['label']]["loss"] += 1
        else:
            transition_counts[c['label']]["pending"] += 1

w(f"{'TRANSIZIONE':<55} {'TOT':<5} {'W':<4} {'L':<4} {'P':<4}")
w(f"{'-'*55} {'-'*5} {'-'*4} {'-'*4} {'-'*4}")
for label, data in sorted(transition_counts.items(), key=lambda x: -x[1]["total"]):
    w(f"{label:<55} {data['total']:<5} {data['win']:<4} {data['loss']:<4} {data['pending']:<4}")
w()

# === RIEPILOGO ===
w(f"{'='*80}")
w("RIEPILOGO")
w(f"{'='*80}")
w()
w(f"  Totale partite con 2+ versioni: {total_with_versions}")
w(f"  Stabili: {stable_count} ({stable_hr:.1f}% hit rate su {stable_total} risolti)")
w(f"  Con cambi: {changed_total} partite, {total_changes} singoli cambi")

all_wins = sum(1 for m in all_matches if m['hit'] is True)
all_losses = sum(1 for m in all_matches if m['hit'] is False)
all_resolved = all_wins + all_losses
if all_resolved > 0:
    w(f"  Hit rate partite cambiate: {all_wins}W/{all_losses}L = {all_wins / all_resolved * 100:.1f}%")
w()

# Scrivi file
with open(output_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"Report salvato in: {output_path}")
print(f"  {changed_total} partite con cambi, {stable_count} stabili")

client.close()
