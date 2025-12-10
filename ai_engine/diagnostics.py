import json
import os

# ==============================================================================
# 🎛️ CONFIGURAZIONE SOGLIE (CARICAMENTO DINAMICO DAL MIXER)
# ==============================================================================
TUNING_FILE = "tuning_settings.json"

# Valori di Default (Sicurezza)
THRESHOLDS = {
    '1X2':   {'red': 50.0, 'green': 65.0},
    'UO':    {'red': 55.0, 'green': 70.0},
    'GG':    {'red': 60.0, 'green': 75.0},
    'Exact': {'red': 10.0, 'green': 30.0}
}

def load_thresholds():
    """Carica le soglie dal file tuning_settings.json"""
    potential_paths = [
        "tuning_settings.json", 
        "ai_engine/engine/tuning_settings.json",
        "ai_engine/tuning_settings.json",
        os.path.join(os.path.dirname(__file__), "tuning_settings.json")
    ]
    
    for path in potential_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
                    
                if "THR_1X2_RED" in loaded_data: 
                    THRESHOLDS['1X2']['red'] = loaded_data["THR_1X2_RED"]["valore"]
                if "THR_1X2_GREEN" in loaded_data: 
                    THRESHOLDS['1X2']['green'] = loaded_data["THR_1X2_GREEN"]["valore"]
                if "THR_UO_RED" in loaded_data: 
                    THRESHOLDS['UO']['red'] = loaded_data["THR_UO_RED"]["valore"]
                if "THR_UO_GREEN" in loaded_data: 
                    THRESHOLDS['UO']['green'] = loaded_data["THR_UO_GREEN"]["valore"]
                if "THR_GG_RED" in loaded_data: 
                    THRESHOLDS['GG']['red'] = loaded_data["THR_GG_RED"]["valore"]
                if "THR_GG_GREEN" in loaded_data: 
                    THRESHOLDS['GG']['green'] = loaded_data["THR_GG_GREEN"]["valore"]
                    
                print(f"✅ [DASHBOARD] Soglie caricate da: {path}")
                print(f"   → 1X2: Rosso < {THRESHOLDS['1X2']['red']}% | Verde ≥ {THRESHOLDS['1X2']['green']}%")
                print(f"   → U/O: Rosso < {THRESHOLDS['UO']['red']}% | Verde ≥ {THRESHOLDS['UO']['green']}%")
                print(f"   → GG: Rosso < {THRESHOLDS['GG']['red']}% | Verde ≥ {THRESHOLDS['GG']['green']}%")
                return
            except Exception as e:
                print(f"⚠️ [DASHBOARD] Errore lettura {path}: {e}")
                continue
    
    print("⚠️ [DASHBOARD] File tuning non trovato, uso soglie default.")

load_thresholds()

def get_thr_color_and_label(market, pct):
    """Restituisce colore bootstrap e etichetta in base alle soglie caricate"""
    t = THRESHOLDS.get(market, {'red': 50, 'green': 70})
    if pct < t['red']: return "danger", "🔴 ALLARME", "text-danger"
    if pct >= t['green']: return "success", "🟢 OTTIMO", "text-success"
    return "warning", "🟡 ACCETTABILE", "text-warning"

def get_sign(gh, ga):
    try:
        gh = float(gh); ga = float(ga)
        if gh > ga: return "1"
        elif ga > gh: return "2"
        return "X"
    except: return "-"

def get_under_over(gh, ga):
    try:
        return "Over" if (float(gh) + float(ga)) > 2.5 else "Under"
    except: return "-"

def get_gol_nogol(gh, ga):
    try:
        return "GG" if (float(gh) > 0 and float(ga) > 0) else "NG"
    except: return "-"

def generate_html_report(filename, algos_indices, all_algos, data_by_algo, matches_list_ignored=None):
    load_thresholds()
    
    algo_stats = {}
    league_stats = {}
    market_stats = {'1X2': {'w':0, 't':0}, 'Exact': {'w':0, 't':0}, 'UO': {'w':0, 't':0}, 'GG': {'w':0, 't':0}}
    bookie_stats = {'w': 0, 't': 0}
    
    for idx in algos_indices:
        name = all_algos[idx-1]
        rows = data_by_algo[name]
        a_stats = {'1X2': 0, 'Exact': 0, 'UO': 0, 'GG': 0, 'Total': 0}
        
        for item in rows:
            m = item['match']
            if not m['has_real']: continue
            
            league = m['league']
            if league not in league_stats: league_stats[league] = {'w': 0, 't': 0}
            
            ph, pa = item['pred_gh'], item['pred_ga']
            rh, ra = m['real_gh'], m['real_ga']
            p_sign = get_sign(ph, pa)
            r_sign = get_sign(rh, ra)
            
            a_stats['Total'] += 1
            league_stats[league]['t'] += 1
            
            if p_sign == r_sign:
                a_stats['1X2'] += 1
                market_stats['1X2']['w'] += 1
                league_stats[league]['w'] += 1
            market_stats['1X2']['t'] += 1

            if idx == algos_indices[0] and m.get('odds') and '1' in m.get('odds'):
                try:
                    q1 = float(m['odds'].get('1', 99))
                    q2 = float(m['odds'].get('2', 99))
                    qx = float(m['odds'].get('X', 99))
                    min_q = min(q1, qx, q2)
                    fav_sign = '1' if q1 == min_q else ('2' if q2 == min_q else 'X')
                    bookie_stats['t'] += 1
                    if fav_sign == r_sign: bookie_stats['w'] += 1
                except: pass

            try:
                if float(ph) == float(rh) and float(pa) == float(ra):
                    a_stats['Exact'] += 1
                    market_stats['Exact']['w'] += 1
            except: pass
            market_stats['Exact']['t'] += 1

            if get_under_over(ph, pa) == get_under_over(rh, ra):
                a_stats['UO'] += 1
                market_stats['UO']['w'] += 1
            market_stats['UO']['t'] += 1

            if get_gol_nogol(ph, pa) == get_gol_nogol(rh, ra):
                a_stats['GG'] += 1
                market_stats['GG']['w'] += 1
            market_stats['GG']['t'] += 1

        t = a_stats['Total'] if a_stats['Total'] > 0 else 1
        algo_stats[name] = {
            '1X2': round(a_stats['1X2']/t*100, 1),
            'Exact': round(a_stats['Exact']/t*100, 1),
            'UO': round(a_stats['UO']/t*100, 1),
            'GG': round(a_stats['GG']/t*100, 1),
            'TotalMatch': a_stats['Total']
        }

    chart_labels = list(algo_stats.keys())
    data_1x2 = [algo_stats[k]['1X2'] for k in chart_labels]
    data_uo = [algo_stats[k]['UO'] for k in chart_labels]
    data_gg = [algo_stats[k]['GG'] for k in chart_labels]
    total_matches = sum([x['TotalMatch'] for x in algo_stats.values()])

    html = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 Report Simulazioni AI</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap-icons/1.10.5/font/bootstrap-icons.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {{--primary-gradient: linear-gradient(135deg, #667eea 0%, #764ba2 100%);}}
        body {{background: linear-gradient(to bottom, #f8f9fa 0%, #e9ecef 100%); font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;}}
        .card {{border: none; box-shadow: 0 4px 15px rgba(0,0,0,0.08); border-radius: 16px; margin-bottom: 24px; transition: transform 0.2s;}}
        .card:hover {{transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.12);}}
        .header-bg {{background: var(--primary-gradient); color: white; padding: 3rem 0; margin-bottom: 40px; box-shadow: 0 4px 20px rgba(102, 126, 234, 0.4);}}
        .header-bg h1 {{font-weight: 800; font-size: 2.5rem; text-shadow: 0 2px 10px rgba(0,0,0,0.2);}}
        .stat-value {{font-size: 2.5rem; font-weight: 800; background: var(--primary-gradient); -webkit-background-clip: text; -webkit-text-fill-color: transparent;}}
        .nav-tabs {{border-bottom: 2px solid #e2e8f0; margin-bottom: 30px;}}
        .nav-tabs .nav-link {{color: #718096; border: none; padding: 12px 24px; font-weight: 600; transition: all 0.2s;}}
        .nav-tabs .nav-link:hover {{color: #667eea;}}
        .nav-tabs .nav-link.active {{color: #667eea; background: linear-gradient(to bottom, rgba(102, 126, 234, 0.1), transparent); border-bottom: 3px solid #667eea;}}
        .badge-custom {{font-size: 0.85em; padding: 0.5em 1em; font-weight: 600; border-radius: 8px;}}
        .table-hover tbody tr:hover {{background-color: rgba(102, 126, 234, 0.05);}}
        .algo-header {{border-left: 5px solid #667eea; padding-left: 20px; margin: 35px 0 20px 0; font-weight: 700;}}
        .threshold-badge {{font-size: 1.1em; padding: 0.6em 1.2em; border-radius: 12px; font-weight: 700; box-shadow: 0 2px 8px rgba(0,0,0,0.1);}}
        .bookie-card {{background: linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%); border: none;}}
        .progress {{height: 24px; border-radius: 12px; background-color: #e2e8f0;}}
        .progress-bar {{transition: width 0.6s ease; font-weight: 600; display: flex; align-items: center; justify-content: center;}}
    </style>
</head>
<body>
<div class="header-bg text-center">
    <div class="container">
        <h1><i class="bi bi-bar-chart-fill me-3"></i>Simulatore Calcio AI</h1>
        <p class="lead mb-0">Report Analitico Completo - Performance Algoritmi & Mercati</p>
    </div>
</div>

<div class="container-fluid px-4" style="max-width: 1400px;">
    <ul class="nav nav-tabs" id="mainTabs">
        <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#dash"><i class="bi bi-graph-up me-2"></i>Dashboard</button></li>
        <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#leagues"><i class="bi bi-globe me-2"></i>Campionati</button></li>
        <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#details"><i class="bi bi-table me-2"></i>Dettaglio</button></li>
    </ul>

    <div class="tab-content">
        <div class="tab-pane fade show active" id="dash">
            <div class="row g-4">
                <div class="col-lg-8">
                    <div class="card p-4">
                        <h5 class="fw-bold mb-4"><i class="bi bi-bar-chart-line text-primary me-2"></i>Confronto Performance</h5>
                        <canvas id="algoChart" height="100"></canvas>
                    </div>
                </div>
                <div class="col-lg-4">
                    <div class="card bookie-card p-4 mb-3 text-dark">
                        <h6 class="fw-bold mb-2"><i class="bi bi-trophy-fill me-2"></i>Bookmaker Baseline</h6>
                        <div class="stat-value text-dark">{round(bookie_stats['w']/bookie_stats['t']*100, 1) if bookie_stats['t']>0 else 0}%</div>
                        <small class="fw-semibold">Favorita: {bookie_stats['w']}/{bookie_stats['t']}</small>
                    </div>
                    <div class="card p-4 mb-3">
                        <h6 class="fw-bold mb-3"><i class="bi bi-sliders text-info me-2"></i>Tue Soglie</h6>
                        <ul class="list-group list-group-flush">"""
    
    for mkt, vals in market_stats.items():
        tot = vals['t'] if vals['t'] > 0 else 1
        pct = round(vals['w']/tot*100, 1)
        color_cls, label_txt, text_cls = get_thr_color_and_label(mkt, pct)
        html += f"""
                            <li class="list-group-item d-flex justify-content-between align-items-center px-0 border-0">
                                <div><div class="fw-bold">{mkt}</div><small class="{text_cls} fw-semibold">{label_txt}</small></div>
                                <span class="badge threshold-badge bg-{color_cls}">{pct}%</span>
                            </li>"""

    html += f"""
                        </ul>
                    </div>
                    <div class="card p-4" style="background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); color: white;">
                        <small class="fw-semibold" style="opacity: 0.9;">PARTITE ANALIZZATE</small>
                        <div class="display-4 fw-bold">{total_matches}</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="tab-pane fade" id="leagues">
            <div class="card p-4">
                <h4 class="fw-bold mb-4"><i class="bi bi-flag-fill text-primary me-2"></i>Performance Campionati</h4>
                <div class="table-responsive">
                    <table class="table table-hover align-middle">
                        <thead class="table-dark">
                            <tr><th>Campionato</th><th class="text-center">Partite</th><th class="text-center">1X2 OK</th><th class="text-center">%</th><th style="width: 30%;">Valutazione</th></tr>
                        </thead>
                        <tbody>"""
    
    for league, stats in sorted(league_stats.items(), key=lambda x: x[1]['w']/max(x[1]['t'], 1), reverse=True):
        tot = stats['t'] if stats['t'] > 0 else 1
        pct = round(stats['w']/tot*100, 1)
        color_cls, _, _ = get_thr_color_and_label('1X2', pct)
        html += f"""
                            <tr>
                                <td><strong>{league}</strong></td>
                                <td class="text-center">{stats['t']}</td>
                                <td class="text-center"><span class="badge bg-secondary">{stats['w']}</span></td>
                                <td class="text-center"><span class="fw-bold fs-5">{pct}%</span></td>
                                <td><div class="progress"><div class="progress-bar bg-{color_cls}" style="width: {pct}%">{pct}%</div></div></td>
                            </tr>"""

    html += """
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <div class="tab-pane fade" id="details">"""
    
    for idx in algos_indices:
        algo_name = all_algos[idx-1]
        rows = data_by_algo[algo_name]
        algo_pct = algo_stats[algo_name]['1X2']
        color_algo, _, _ = get_thr_color_and_label('1X2', algo_pct)
        
        html += f"""
            <div class="card p-4 mb-4">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h3 class="algo-header m-0"><i class="bi bi-cpu-fill me-2"></i>{algo_name.upper()}</h3>
                    <div>
                        <span class="badge bg-{color_algo} me-2" style="font-size: 1.1em; padding: 0.6em 1em;">1X2: {algo_pct}%</span>
                        <span class="badge bg-secondary">{algo_stats[algo_name]['TotalMatch']} partite</span>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover table-sm">
                        <thead class="table-light">
                            <tr><th>Lega</th><th>Partita</th><th>Quote</th><th>Reale</th><th>Previsto</th><th>1X2</th><th>Exact</th><th>U/O</th><th>GG</th><th>Bookie</th></tr>
                        </thead>
                        <tbody>"""
        
        for item in rows:
            m = item['match']
            ph, pa = item['pred_gh'], item['pred_ga']
            p_sign = get_sign(ph, pa)

            odds_html = '<span class="text-muted">-</span>'
            bk_badge = '<span class="text-muted">-</span>'
            
            if m.get('odds') and '1' in m.get('odds'):
                try:
                    q1 = float(m['odds']['1'])
                    qx = float(m['odds']['X'])
                    q2 = float(m['odds']['2'])
                    mq = min(q1, qx, q2)
                    fs = '1' if q1==mq else ('2' if q2==mq else 'X')
                    s1 = f"<strong>{q1:.2f}</strong>" if fs=='1' else f"{q1:.2f}"
                    sx = f"<strong>{qx:.2f}</strong>" if fs=='X' else f"{qx:.2f}"
                    s2 = f"<strong>{q2:.2f}</strong>" if fs=='2' else f"{q2:.2f}"
                    odds_html = f'<small class="text-muted">{s1}|{sx}|{s2}</small>'
                    if m['has_real']:
                        rs = get_sign(m['real_gh'], m['real_ga'])
                        bk_badge = '<span class="badge bg-success"><i class="bi bi-check-lg"></i></span>' if fs==rs else f'<span class="badge bg-danger"><i class="bi bi-x-lg"></i> {rs}</span>'
                except: pass

            b_1x2 = b_ex = b_uo = b_gg = '<span class="text-muted">-</span>'
            
            if m['has_real']:
                rh, ra = m['real_gh'], m['real_ga']
                win = (p_sign == get_sign(rh, ra))
                icon = '<i class="bi bi-check-circle-fill"></i>' if win else '<i class="bi bi-x-circle-fill"></i>'
                b_1x2 = f'<span class="badge bg-{"success" if win else "danger"} badge-custom">{icon}</span>'
                
                try: win = (float(ph)==float(rh) and float(pa)==float(ra))
                except: win=False
                b_ex = '<span class="badge bg-success badge-custom"><i class="bi bi-bullseye"></i></span>' if win else '<span class="badge bg-light text-muted border">-</span>'
                
                win = (get_under_over(ph, pa) == get_under_over(rh, ra))
                icon = '<i class="bi bi-check-circle-fill"></i>' if win else '<i class="bi bi-x-circle-fill"></i>'
                b_uo = f'<span class="badge bg-{"success" if win else "danger"} badge-custom">{icon}</span>'
                
                win = (get_gol_nogol(ph, pa) == get_gol_nogol(rh, ra))
                icon = '<i class="bi bi-check-circle-fill"></i>' if win else '<i class="bi bi-x-circle-fill"></i>'
                b_gg = f'<span class="badge bg-{"success" if win else "danger"} badge-custom">{icon}</span>'

            real_s = m['real_score_str'] if m['has_real'] else '<span class="text-muted">-</span>'

            html += f"""
                            <tr>
                                <td><small class="badge bg-secondary">{m['league']}</small></td>
                                <td><div class="fw-bold">{m['home']} - {m['away']}</div><small class="text-muted">{m['date_str']}</small></td>
                                <td>{odds_html}</td>
                                <td class="fw-bold text-primary text-center">{real_s}</td>
                                <td class="fw-bold text-center">{ph}-{pa}</td>
                                <td class="text-center">{b_1x2}</td>
                                <td class="text-center">{b_ex}</td>
                                <td class="text-center">{b_uo}</td>
                                <td class="text-center">{b_gg}</td>
                                <td class="text-center">{bk_badge}</td>
                            </tr>"""
        
        html += "</tbody></table></div></div>"

    html += f"""
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
const ctx = document.getElementById('algoChart').getContext('2d');
const g1 = ctx.createLinearGradient(0, 0, 0, 400);
g1.addColorStop(0, 'rgba(102, 126, 234, 0.8)'); g1.addColorStop(1, 'rgba(102, 126, 234, 0.2)');
const g2 = ctx.createLinearGradient(0, 0, 0, 400);
g2.addColorStop(0, 'rgba(255, 159, 64, 0.8)'); g2.addColorStop(1, 'rgba(255, 159, 64, 0.2)');
const g3 = ctx.createLinearGradient(0, 0, 0, 400);
g3.addColorStop(0, 'rgba(75, 192, 192, 0.8)'); g3.addColorStop(1, 'rgba(75, 192, 192, 0.2)');

new Chart(ctx, {{
    type: 'bar',
    data: {{
        labels: {json.dumps(chart_labels)},
        datasets: [
            {{label: '1X2 %', data: {json.dumps(data_1x2)}, backgroundColor: g1, borderColor: 'rgba(102, 126, 234, 1)', borderWidth: 2, borderRadius: 8}},
            {{label: 'U/O %', data: {json.dumps(data_uo)}, backgroundColor: g2, borderColor: 'rgba(255, 159, 64, 1)', borderWidth: 2, borderRadius: 8}},
            {{label: 'GG %', data: {json.dumps(data_gg)}, backgroundColor: g3, borderColor: 'rgba(75, 192, 192, 1)', borderWidth: 2, borderRadius: 8}}
        ]
    }},
    options: {{
        responsive: true,
        plugins: {{
            legend: {{position: 'top', labels: {{font: {{size: 13, weight: 'bold'}}, padding: 15, usePointStyle: true}}}},
            tooltip: {{backgroundColor: 'rgba(0, 0, 0, 0.8)', padding: 12, cornerRadius: 8}}
        }},
        scales: {{y: {{beginAtZero: true, max: 100, ticks: {{callback: v => v + '%'}}}}, x: {{ticks: {{font: {{weight: '600'}}}}}}}}
    }}
}});
</script>
</body>
</html>"""
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"\n{'='*70}")
    print(f"✅ DASHBOARD GENERATA: {filename}")
    print(f"📊 Algoritmi: {len(algo_stats)} | ⚽ Partite: {total_matches} | 🌍 Campionati: {len(league_stats)}")
    print(f"{'='*70}\n")