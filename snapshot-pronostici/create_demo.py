"""Crea dati demo per testare il report di confronto."""
import json, os

matches_base = [
    {'home': 'Inter', 'away': 'Atalanta', 'match_time': '15:00', 'league': 'Serie A'},
    {'home': 'Napoli', 'away': 'Lecce', 'match_time': '18:00', 'league': 'Serie A'},
    {'home': 'Udinese', 'away': 'Juventus', 'match_time': '20:45', 'league': 'Serie A'},
    {'home': 'Leverkusen', 'away': 'Bayern', 'match_time': '15:30', 'league': 'Bundesliga'},
    {'home': 'Burnley', 'away': 'Bournemouth', 'match_time': '16:00', 'league': 'Premier League'},
    {'home': 'Chelsea', 'away': 'Newcastle', 'match_time': '18:30', 'league': 'Premier League'},
    {'home': 'Ajax', 'away': 'Sparta R.', 'match_time': '21:00', 'league': 'Eredivisie'},
    {'home': 'Bari', 'away': 'Reggiana', 'match_time': '15:00', 'league': 'Serie B'},
    {'home': 'Monza', 'away': 'Palermo', 'match_time': '17:15', 'league': 'Serie B'},
    {'home': 'Real Madrid', 'away': 'Elche', 'match_time': '21:00', 'league': 'La Liga'},
]

# MATTINO: 10 partite, 12 tip
mattino_p = [
    {**matches_base[0], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.6, 'confidence': 71, 'stake': 1, 'source': 'A+S'}]},
    {**matches_base[1], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 1.5', 'quota': 1.35, 'confidence': 84, 'stake': 1, 'source': 'C_screm'}]},
    {**matches_base[2], 'tips': [{'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.65, 'confidence': 54, 'stake': 1, 'source': 'C'}]},
    {**matches_base[3], 'tips': [
        {'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.53, 'confidence': 85, 'stake': 6, 'source': 'C'},
        {'tipo': 'GOL', 'pronostico': 'Over 3.5', 'quota': 1.8, 'confidence': 66, 'stake': 3, 'source': 'C'},
    ]},
    {**matches_base[4], 'tips': [{'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.95, 'confidence': 64, 'stake': 3, 'source': 'C'}]},
    {**matches_base[5], 'tips': [{'tipo': 'SEGNO', 'pronostico': '1', 'quota': 1.8, 'confidence': 44, 'stake': 1, 'source': 'C'}]},
    {**matches_base[6], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.45, 'confidence': 76, 'stake': 1, 'source': 'A+S'}]},
    {**matches_base[8], 'tips': [{'tipo': 'GOL', 'pronostico': 'Goal', 'quota': 1.75, 'confidence': 74, 'stake': 4, 'source': 'C'}]},
    {**matches_base[9], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.4, 'confidence': 75, 'stake': 1, 'source': 'A+S'}]},
]
mattino_ar = [
    {**matches_base[7], 'tips': [{'tipo': 'SEGNO', 'pronostico': 'X', 'quota': 3.1, 'confidence': 55, 'stake': 4, 'source': 'MC_xdraw'}]},
]

# INTERMEDIO: Chelsea rimosso (NO BET), Sampdoria aggiunto, quote aggiornate
intermedio_p = [
    {**matches_base[0], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.55, 'confidence': 73, 'stake': 1, 'source': 'A+S'}]},
    {**matches_base[1], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 1.5', 'quota': 1.32, 'confidence': 86, 'stake': 1, 'source': 'C_screm'}]},
    {**matches_base[2], 'tips': [{'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.7, 'confidence': 52, 'stake': 1, 'source': 'C'}]},
    {**matches_base[3], 'tips': [
        {'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.55, 'confidence': 83, 'stake': 5, 'source': 'C'},
        {'tipo': 'GOL', 'pronostico': 'Over 3.5', 'quota': 1.75, 'confidence': 68, 'stake': 3, 'source': 'C'},
    ]},
    {**matches_base[4], 'tips': [{'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.9, 'confidence': 66, 'stake': 3, 'source': 'C'}]},
    {**matches_base[6], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.5, 'confidence': 74, 'stake': 1, 'source': 'A+S'}]},
    {**matches_base[8], 'tips': [{'tipo': 'GOL', 'pronostico': 'Goal', 'quota': 1.72, 'confidence': 76, 'stake': 4, 'source': 'C'}]},
    {**matches_base[9], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.38, 'confidence': 77, 'stake': 1, 'source': 'A+S'}]},
    {'home': 'Sampdoria', 'away': 'Venezia', 'match_time': '19:30', 'league': 'Serie B',
     'tips': [{'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.86, 'confidence': 76, 'stake': 5, 'source': 'C'}]},
]
intermedio_ar = [
    {**matches_base[7], 'tips': [{'tipo': 'SEGNO', 'pronostico': 'X', 'quota': 3.2, 'confidence': 53, 'stake': 4, 'source': 'MC_xdraw'}]},
]

# SERALE: Monza rimosso, quote finali
serale_p = [
    {**matches_base[0], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.52, 'confidence': 74, 'stake': 2, 'source': 'A+S'}]},
    {**matches_base[1], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 1.5', 'quota': 1.3, 'confidence': 88, 'stake': 1, 'source': 'C_screm'}]},
    {**matches_base[2], 'tips': [{'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.72, 'confidence': 50, 'stake': 1, 'source': 'C'}]},
    {**matches_base[3], 'tips': [
        {'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.57, 'confidence': 81, 'stake': 5, 'source': 'C'},
        {'tipo': 'GOL', 'pronostico': 'Over 3.5', 'quota': 1.7, 'confidence': 70, 'stake': 3, 'source': 'C'},
    ]},
    {**matches_base[4], 'tips': [{'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.85, 'confidence': 68, 'stake': 4, 'source': 'C'}]},
    {**matches_base[6], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.48, 'confidence': 75, 'stake': 2, 'source': 'A+S'}]},
    {**matches_base[9], 'tips': [{'tipo': 'GOL', 'pronostico': 'Over 2.5', 'quota': 1.35, 'confidence': 78, 'stake': 2, 'source': 'A+S'}]},
    {'home': 'Sampdoria', 'away': 'Venezia', 'match_time': '19:30', 'league': 'Serie B',
     'tips': [{'tipo': 'SEGNO', 'pronostico': '2', 'quota': 1.82, 'confidence': 78, 'stake': 5, 'source': 'C'}]},
]
serale_ar = [
    {**matches_base[7], 'tips': [{'tipo': 'SEGNO', 'pronostico': 'X', 'quota': 3.3, 'confidence': 51, 'stake': 3, 'source': 'MC_xdraw'}]},
]

def save_snapshot(label, time_str, pron, ar):
    snap = {
        'timestamp': f'2026-03-14T{time_str}:00',
        'label': label,
        'date': 'test-demo',
        'riepilogo': {
            'pronostici': {'partite': len(pron), 'tip': sum(len(m['tips']) for m in pron)},
            'alto_rendimento': {'partite': len(ar), 'tip': sum(len(m['tips']) for m in ar)},
        },
        'pronostici': [{**m, 'decision': ''} for m in pron],
        'alto_rendimento': [{**m, 'decision': ''} for m in ar],
    }
    d = f'report/test-demo/{label}'
    os.makedirs(d, exist_ok=True)
    path = f'{d}/snapshot_{time_str.replace(":", "")}.json'
    with open(path, 'w') as f:
        json.dump(snap, f, indent=2)
    print(f'  Salvato {label} ({time_str}) -> {path}')

save_snapshot('mattino', '08:30', mattino_p, mattino_ar)
save_snapshot('intermedio', '15:00', intermedio_p, intermedio_ar)
save_snapshot('serale', '23:30', serale_p, serale_ar)
print('Demo data creata!')
