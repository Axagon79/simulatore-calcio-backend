"""
🎨 CONFIDENCE HTML BUILDER - Generatore Report HTML Confidence
════════════════════════════════════════════════════════════════

Genera report HTML interattivo dedicato alle analisi di confidence.
Separato dal report principale per migliore organizzazione.

USAGE:
    from confidence_html_builder import ConfidenceHTMLBuilder
    
    builder = ConfidenceHTMLBuilder()
    builder.generate_report(
        matches=analyzer.matches,
        output_path="confidence_report.html"
    )
"""

from datetime import datetime

from .confidence_glossary import get_explanation_box
class ConfidenceHTMLBuilder:
    """Builder per generare HTML report confidence"""
    
    def __init__(self):
        self.algo_names = {
            1: "Statistico Puro",
            2: "Dinamico",
            3: "Tattico",
            4: "Caos",
            5: "Master"
        }
    
    def generate_report(self, matches, output_path):
        """
        Genera report HTML completo per confidence analysis.
        
        Args:
            matches: Lista di partite con dati confidence
            output_path: Path del file HTML da creare
        """
        
        if not matches:
            print("⚠️  Nessuna partita da analizzare per confidence!")
            return
        
        html_content = self._build_html_structure(matches)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def _build_html_structure(self, matches):
        """Costruisce la struttura HTML completa"""
        
        html = self._get_html_header()
        html += self._get_navigation_tabs(matches)
        html += '<div class="content">'
        
        # Per ogni partita
        for match_idx, match in enumerate(matches, 1):
            html += self._build_match_section(match, match_idx)
        
        html += '</div>'
        html += self._get_html_footer()
        
        return html
    
    def _get_html_header(self):
        """Ritorna header HTML con CSS"""
        
        return f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 Confidence Analysis Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}
        
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .nav-tabs {{
            display: flex;
            gap: 10px;
            padding: 20px 40px;
            background: #f8f9fa;
            border-bottom: 2px solid #e0e0e0;
            overflow-x: auto;
            flex-wrap: wrap;
        }}
        
        .nav-tab {{
            padding: 12px 24px;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            border: 2px solid transparent;
            white-space: nowrap;
        }}
        
        .nav-tab:hover {{
            background: #667eea;
            color: white;
            transform: translateY(-2px);
        }}
        
        .nav-tab.active {{
            background: #667eea;
            color: white;
            border-color: #5568d3;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .algo-section {{
            display: none;
        }}
        
        .algo-section.active {{
            display: block;
            animation: fadeIn 0.3s;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .section-title {{
            font-size: 1.8em;
            color: #667eea;
            margin: 30px 0 20px 0;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 12px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }}
        
        .metric-card:hover {{
            transform: translateY(-5px);
        }}
        
        .metric-card h4 {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .metric-card .value {{
            font-size: 2.5em;
            font-weight: bold;
            margin: 10px 0;
        }}
        
        .metric-card .subvalue {{
            font-size: 1em;
            opacity: 0.8;
        }}
        
        .alert-box {{
            background: #fff3cd;
            border-left: 5px solid #ffc107;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
        }}
        
        .alert-box.danger {{
            background: #f8d7da;
            border-left-color: #dc3545;
        }}
        
        .alert-box h4 {{
            color: #856404;
            margin-bottom: 10px;
        }}
        
        .alert-box.danger h4 {{
            color: #721c24;
        }}
        
        .stats-table {{
            width: 100%;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            margin-bottom: 30px;
        }}
        
        .stats-table th {{
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
        }}
        
        .stats-table td {{
            padding: 15px;
            border-bottom: 1px solid #f0f0f0;
        }}
        
        .stats-table tr:hover {{
            background: #f8f9fa;
        }}
        
        .badge {{
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }}
        
        .badge-high {{
            background: #28a745;
            color: white;
        }}
        
        .badge-medium {{
            background: #ffc107;
            color: #333;
        }}
        
        .badge-low {{
            background: #dc3545;
            color: white;
        }}
        
        .comparison-section {{
            background: linear-gradient(135deg, #20c997 0%, #17a2b8 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-top: 40px;
        }}
        
        .comparison-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        
        .comparison-item {{
            background: rgba(255,255,255,0.2);
            padding: 20px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .match-header-box {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 30px;
        }}
        
        .match-header-box h2 {{
            color: #667eea;
        }}

        .explanation-box {{
            background: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 15px;
            margin: 20px 0;
            border-radius: 8px;
        }}

        .explanation-box h4 {{
            color: #1976d2;
            margin-bottom: 10px;
            font-size: 1.1em;
        }}

        .explanation-box div {{
            color: #333;
            line-height: 1.6;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Confidence Analysis Report</h1>
            <p>Analisi dettagliata affidabilità previsioni Monte Carlo</p>
            <p style="opacity: 0.7; margin-top: 10px;">Generato: {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</p>
        </div>
"""
    
    def _get_navigation_tabs(self, matches):
        """Genera tabs di navigazione tra algoritmi"""
        
        # Estrai tutti gli algoritmi usati
        all_algos = set()
        for match in matches:
            all_algos.update(match['algorithms'].keys())
        
        all_algos = sorted(all_algos)
        
        html = '<div class="nav-tabs">'
        
        for idx, algo_id in enumerate(all_algos):
            active_class = "active" if idx == 0 else ""
            algo_name = self.algo_names.get(algo_id, f"Algoritmo {algo_id}")
            html += f'<div class="nav-tab {active_class}" onclick="switchTab(\'algo_{algo_id}\')">📌 {algo_name}</div>'
        
        if len(all_algos) > 1:
            html += '<div class="nav-tab" onclick="switchTab(\'comparison\')">🌐 Confronto Multi-Algoritmo</div>'
        
        html += '</div>'
        
        return html
    
    def _build_match_section(self, match, match_idx):
        """Costruisce sezione HTML per una singola partita"""
        
        html = f"""
        <div class="match-header-box">
            <h2>⚽ {match['home_team']} vs {match['away_team']}</h2>
            <p style="color: #666; margin-top: 5px;">🏆 {match['league']} | 📅 {match['date']}</p>
"""
        
        if match.get('real_result'):
            html += f"""
            <p style="margin-top: 10px;"><strong>Risultato Reale:</strong> 
            <span style="background: #28a745; color: white; padding: 5px 15px; border-radius: 5px; font-weight: bold;">{match['real_result']}</span></p>
"""
        
        html += '</div>'
        
        # Per ogni algoritmo
        for algo_idx, (algo_id, data) in enumerate(match['algorithms'].items()):
            active_class = "active" if algo_idx == 0 else ""
            html += self._build_algorithm_section(algo_id, data, active_class)
        
        # Sezione confronto (se più di 1 algoritmo)
        if len(match['algorithms']) > 1:
            html += self._build_comparison_section(match)
        
        return html
    
    def _build_algorithm_section(self, algo_id, data, active_class):
        """Costruisce sezione per un singolo algoritmo"""
        
        stats = data['stats']
        conf = stats.get('confidence', {})
        
        if not conf:
            return ""
        
        algo_name = self.algo_names.get(algo_id, f"Algoritmo {algo_id}")
        
        html = f"""
        <div class="algo-section {active_class}" id="algo_{algo_id}">
            <h3 class="section-title">📌 {algo_name} - {stats['total_simulations']} simulazioni</h3>
"""
        
        # Sezioni
        html += self._build_gol_section(conf)
        html += self._build_segni_section(conf)
        html += self._build_gg_ng_section(conf)
        html += self._build_under_over_section(conf)
        html += self._build_multigol_section(conf)
        html += self._build_exact_scores_section(conf)
        html += self._build_exotic_section(conf)
        html += self._build_advanced_section(conf)
        html += self._build_global_summary(conf)
        
        html += '</div>'
        
        return html
    
    def _build_gol_section(self, conf):
        """Sezione GOL"""

        gol = conf.get('gol', {})
        if not gol:
            return ""

        # Box spiegazione
        explanation = get_explanation_box('intro', num_sim=500)

        return f"""
        <div class="section-title" style="font-size: 1.4em; margin-top: 20px;">🎯 CATEGORIA GOL</div>
        {explanation}
        <div class="metric-grid">
            <div class="metric-card">
                <h4>Gol Casa</h4>
                <div class="value">{gol['home']['confidence']}%</div>
                <div class="subvalue">Std Dev: {gol['home']['std']}</div>
            </div>
        </div>

        {get_explanation_box('gol_casa', confidence=gol['home']['confidence'], std=gol['home']['std'], num_sim=500, avg_gol='1.5', most_common='2', pct='35')}

        <div class="metric-grid">
            <div class="metric-card">
                <h4>Gol Ospite</h4>
                <div class="value">{gol['away']['confidence']}%</div>
                <div class="subvalue">Std Dev: {gol['away']['std']}</div>
            </div>
            <div class="metric-card">
                <h4>Totale Gol</h4>
                <div class="value">{gol['total']['confidence']}%</div>
                <div class="subvalue">Std Dev: {gol['total']['std']}</div>
            </div>
            <div class="metric-card">
                <h4>Varianza</h4>
                <div class="value">{gol['variance_comparison']}</div>
                <div class="subvalue">Ratio: {gol['variance_ratio']}</div>
            </div>
        </div>
        
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
            <strong>📊 Confidence Categoria GOL:</strong> 
            <span style="font-size: 1.5em; color: #667eea; font-weight: bold;">{gol['category_confidence']}%</span>
        </div>
"""
    
    def _build_segni_section(self, conf):
        """Sezione SEGNI 1X2"""

        segni = conf.get('segni', {})
        if not segni:
            return ""

        html = f"""
        <div class="section-title" style="font-size: 1.4em;">🏆 CATEGORIA SEGNI 1X2</div>
        {get_explanation_box('segni_1x2')}
        <div class="metric-grid">
            <div class="metric-card">
                <h4>Segno 1 (Casa)</h4>
                <div class="value">{segni['sign_1']['confidence']}%</div>
                <div class="subvalue">Probabilità: {segni['sign_1']['percentage']}%</div>
            </div>
            <div class="metric-card">
                <h4>Segno X (Pareggio)</h4>
                <div class="value">{segni['sign_x']['confidence']}%</div>
                <div class="subvalue">Probabilità: {segni['sign_x']['percentage']}%</div>
            </div>
            <div class="metric-card">
                <h4>Segno 2 (Ospite)</h4>
                <div class="value">{segni['sign_2']['confidence']}%</div>
                <div class="subvalue">Probabilità: {segni['sign_2']['percentage']}%</div>
            </div>
            <div class="metric-card" style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%);">
                <h4>Segno Vincente</h4>
                <div class="value">{segni['most_probable']}</div>
                <div class="subvalue">Confidence: {segni['most_probable_confidence']}%</div>
            </div>
        </div>

        {get_explanation_box('segno_vincente', segno=segni['most_probable'], pct=segni['sign_1']['percentage'], confidence=segni['most_probable_confidence'])}
        
        <table class="stats-table">
            <thead>
                <tr>
                    <th>Metrica</th>
                    <th>Valore</th>
                    <th>Note</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Margine vittoria Casa</strong></td>
                    <td>{segni['margins']['home_wins_avg']} gol</td>
                    <td>Media scarto quando vince casa</td>
                </tr>
                <tr>
                    <td><strong>Margine vittoria Ospite</strong></td>
                    <td>{segni['margins']['away_wins_avg']} gol</td>
                    <td>Media scarto quando vince ospite</td>
                </tr>
                <tr>
                    <td><strong>Dominanza nei TOP 10</strong></td>
                    <td>{segni['top10_distribution']['dominance_pct']}%</td>
                    <td>Concentrazione segno più frequente</td>
                </tr>
            </tbody>
        </table>

        {get_explanation_box('dominanza_top10', dominanza=segni['top10_distribution']['dominance_pct'], count_1=segni['top10_distribution']['sign_1_count'], count_x=segni['top10_distribution']['sign_x_count'], count_2=segni['top10_distribution']['sign_2_count'])}
        
        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h4 style="margin-bottom: 15px;">📍 Distribuzione Segni nei TOP 10 Risultati:</h4>
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px;">
                <div>
                    <strong>Segno 1:</strong> {segni['top10_distribution']['sign_1_count']} risultati<br>
                    <small>Posizioni: {', '.join(['#' + str(p) for p in segni['top10_distribution']['sign_1_positions']]) if segni['top10_distribution']['sign_1_positions'] else 'Nessuna'}</small>
                </div>
                <div>
                    <strong>Segno X:</strong> {segni['top10_distribution']['sign_x_count']} risultati<br>
                    <small>Posizioni: {', '.join(['#' + str(p) for p in segni['top10_distribution']['sign_x_positions']]) if segni['top10_distribution']['sign_x_positions'] else 'Nessuna'}</small>
                </div>
                <div>
                    <strong>Segno 2:</strong> {segni['top10_distribution']['sign_2_count']} risultati<br>
                    <small>Posizioni: {', '.join(['#' + str(p) for p in segni['top10_distribution']['sign_2_positions']]) if segni['top10_distribution']['sign_2_positions'] else 'Nessuna'}</small>
                </div>
            </div>
        </div>
"""
        
        if segni['anomaly']['detected']:
            html += f"""
        <div class="alert-box danger">
            <h4>⚠️ ANOMALIA RILEVATA</h4>
            <p>{segni['anomaly']['message']}</p>
            <p style="margin-top: 10px;"><em>→ Confidence del segno vincente ridotta dell'8%</em></p>
        </div>
"""
        
        html += f"""
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
            <strong>📊 Confidence Categoria SEGNI:</strong> 
            <span style="font-size: 1.5em; color: #667eea; font-weight: bold;">{segni['category_confidence']}%</span>
        </div>
"""
        
        return html
    
    def _build_gg_ng_section(self, conf):
        """Sezione GG/NG"""

        gg_ng = conf.get('gg_ng', {})
        if not gg_ng:
            return ""

        prob_ng = 100 - gg_ng['prob_gg']

        return f"""
        <div class="section-title" style="font-size: 1.4em;">⚽ CATEGORIA GG/NOGOL</div>
        {get_explanation_box('gg_ng', prob_gg=gg_ng['prob_gg'], prob_ng=prob_ng, confidence=gg_ng['confidence'], std=gg_ng['std'])}
        <div class="metric-grid">
            <div class="metric-card">
                <h4>Confidence GG/NG</h4>
                <div class="value">{gg_ng['confidence']}%</div>
                <div class="subvalue">Std Dev: {gg_ng['std']}</div>
            </div>
            <div class="metric-card">
                <h4>Probabilità GG</h4>
                <div class="value">{gg_ng['prob_gg']}%</div>
                <div class="subvalue">{"Entrambe segnano" if gg_ng['prob_gg'] > 50 else "Almeno una non segna"}</div>
            </div>
        </div>
        
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
            <strong>📊 Confidence Categoria GG/NG:</strong> 
            <span style="font-size: 1.5em; color: #667eea; font-weight: bold;">{gg_ng['confidence']}%</span>
        </div>
"""
    
    def _build_under_over_section(self, conf):
        """Sezione UNDER/OVER"""

        uo = conf.get('under_over', {})
        most_reliable = conf.get('most_reliable_uo', {})

        if not uo:
            return ""

        html = f"""
        <div class="section-title" style="font-size: 1.4em;">📊 CATEGORIA UNDER/OVER</div>
        {get_explanation_box('under_over', avg_total='2.5')}
        <div class="metric-grid">
"""
        
        for threshold, data_uo in uo.items():
            html += f"""
            <div class="metric-card">
                <h4>{threshold}</h4>
                <div class="value">{data_uo['confidence']}%</div>
                <div class="subvalue">Std Dev: {data_uo['std']}</div>
            </div>
"""
        
        html += '</div>'
        
        if most_reliable:
            html += f"""
        <div class="alert-box">
            <h4>🎯 Soglia più affidabile</h4>
            <p><strong>{most_reliable.get('threshold', 'N/A')}</strong> con confidence di <strong>{most_reliable.get('confidence', 0)}%</strong></p>
        </div>
"""
        
        categories = conf.get('categories', {})
        if 'under_over' in categories:
            html += f"""
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
            <strong>📊 Confidence Categoria UNDER/OVER:</strong> 
            <span style="font-size: 1.5em; color: #667eea; font-weight: bold;">{categories['under_over']}%</span>
        </div>
"""
        
        return html
    
    def _build_multigol_section(self, conf):
        """Sezione MULTIGOL"""

        multigol = conf.get('multigol', {})
        if not multigol:
            return ""

        categories = conf.get('categories', {})

        return f"""
        <div class="section-title" style="font-size: 1.4em;">🎲 CATEGORIA MULTIGOL</div>
        {get_explanation_box('multigol', home_range=multigol['home']['range'], home_conf=multigol['home']['confidence'], home_occ=multigol['home']['occurrences'], away_range=multigol['away']['range'], away_conf=multigol['away']['confidence'], away_occ=multigol['away']['occurrences'], num_sim=500)}
        <div class="metric-grid">
            <div class="metric-card">
                <h4>Range Casa</h4>
                <div class="value">{multigol['home']['range']} gol</div>
                <div class="subvalue">Confidence: {multigol['home']['confidence']}%</div>
                <div class="subvalue">{multigol['home']['occurrences']} occorrenze</div>
            </div>
            <div class="metric-card">
                <h4>Range Ospite</h4>
                <div class="value">{multigol['away']['range']} gol</div>
                <div class="subvalue">Confidence: {multigol['away']['confidence']}%</div>
                <div class="subvalue">{multigol['away']['occurrences']} occorrenze</div>
            </div>
        </div>
        
        <div style="background: #e7f3ff; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
            <strong>📊 Confidence Categoria MULTIGOL:</strong> 
            <span style="font-size: 1.5em; color: #667eea; font-weight: bold;">{categories.get('multigol', 0)}%</span>
        </div>
"""
    
    def _build_exact_scores_section(self, conf):
        """Sezione RISULTATI ESATTI"""

        exact = conf.get('exact_scores_analysis', {})
        if not exact:
            return ""

        return f"""
        <div class="section-title" style="font-size: 1.4em;">🏅 ANALISI RISULTATI ESATTI</div>
        {get_explanation_box('concentrazione_top3', pct=exact['concentration_top3'])}
        {get_explanation_box('entropia', entropy=exact['entropy'])}
        <div class="metric-grid">
            <div class="metric-card">
                <h4>Concentrazione TOP 3</h4>
                <div class="value">{exact['concentration_top3']}%</div>
                <div class="subvalue">{"Alta prevedibilità" if exact['concentration_top3'] > 40 else "Bassa prevedibilità"}</div>
            </div>
            <div class="metric-card">
                <h4>Entropia</h4>
                <div class="value">{exact['entropy']}</div>
                <div class="subvalue">{"Distribuzione concentrata" if exact['entropy'] < 3 else "Distribuzione sparsa"}</div>
            </div>
        </div>
"""
    
    def _build_exotic_section(self, conf):
        """Sezione MERCATI ESOTICI"""
        
        exotic = conf.get('exotic', {})
        if not exotic:
            return ""
        
        return f"""
        <div class="section-title" style="font-size: 1.4em;">🎰 MERCATI ESOTICI</div>
        <div class="metric-grid">
            <div class="metric-card">
                <h4>Pari/Dispari</h4>
                <div class="value">{exotic['pari_dispari']['confidence']}%</div>
                <div class="subvalue">Dispari: {exotic['pari_dispari']['pct_dispari']}%</div>
                <div class="subvalue">Std Dev: {exotic['pari_dispari']['std']}</div>
            </div>
            <div class="metric-card">
                <h4>Clean Sheet</h4>
                <div class="value">{exotic['clean_sheet']['confidence']}%</div>
                <div class="subvalue">Casa: {exotic['clean_sheet']['home_pct']}%</div>
                <div class="subvalue">Ospite: {exotic['clean_sheet']['away_pct']}%</div>
            </div>
        </div>
"""
    
    def _build_advanced_section(self, conf):
        """Sezione METRICHE AVANZATE"""
        
        advanced = conf.get('advanced', {})
        if not advanced:
            return ""
        
        correlation = advanced.get('correlation_home_away', 0)
        
        if correlation > 0.3:
            corr_text = "Positiva forte → Entrambe segnano insieme"
        elif correlation > 0:
            corr_text = "Positiva debole → Leggera tendenza a segnare insieme"
        elif correlation > -0.3:
            corr_text = "Negativa debole → Quando una segna, l'altra tende a segnare meno"
        else:
            corr_text = "Negativa forte → Netta inversione: una domina, l'altra no"
        
        return f"""
        <div class="section-title" style="font-size: 1.4em;">🔬 METRICHE STATISTICHE AVANZATE</div>
        
        <table class="stats-table">
            <thead>
                <tr>
                    <th>Metrica</th>
                    <th>Casa</th>
                    <th>Ospite</th>
                    <th>Interpretazione</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td><strong>Varianza</strong></td>
                    <td>{advanced['variance']['home']}</td>
                    <td>{advanced['variance']['away']}</td>
                    <td>{"Casa più imprevedibile" if advanced['variance']['home'] > advanced['variance']['away'] else "Ospite più imprevedibile"} (Ratio: {advanced['variance']['ratio']})</td>
                </tr>
                <tr>
                    <td><strong>Skewness</strong></td>
                    <td>{advanced['skewness']['home']}</td>
                    <td>{advanced['skewness']['away']}</td>
                    <td>{"Destra (più valori alti)" if advanced['skewness']['home'] > 0 else "Sinistra (più valori bassi)"} per Casa</td>
                </tr>
                <tr>
                    <td><strong>Kurtosis</strong></td>
                    <td>{advanced['kurtosis']['home']}</td>
                    <td>{advanced['kurtosis']['away']}</td>
                    <td>{"Code pesanti (risultati estremi)" if advanced['kurtosis']['home'] > 3 else "Distribuzione normale"} per Casa</td>
                </tr>
            </tbody>
        </table>
        
        {get_explanation_box('correlazione', correlation=correlation)}
        
        <div class="alert-box">
            <h4>🔗 Correlazione Gol Casa-Ospite</h4>
            <p style="font-size: 1.3em; font-weight: bold; margin: 10px 0;">{correlation}</p>
            <p>{corr_text}</p>
        </div>
"""
    def _build_global_summary(self, conf):
        """Riepilogo globale"""

        categories = conf.get('categories', {})
        global_conf = conf.get('global_confidence', 0)
        most_reliable = conf.get('most_reliable_market', {})
        least_reliable = conf.get('least_reliable_market', {})

        return f"""
        <div class="comparison-section">
            <h3 style="font-size: 1.8em; margin-bottom: 20px;">🌍 CONFIDENCE GLOBALE - RIEPILOGO</h3>
            
            {get_explanation_box('confidence_globale', global_conf=global_conf)}
            
            <div class="comparison-grid">
                <div class="comparison-item">
                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">GOL</div>
                    <div style="font-size: 2em; font-weight: bold;">{categories.get('gol', 0)}%</div>
                </div>
                <div class="comparison-item">
                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">SEGNI</div>
                    <div style="font-size: 2em; font-weight: bold;">{categories.get('segni', 0)}%</div>
                </div>
                <div class="comparison-item">
                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">GG/NG</div>
                    <div style="font-size: 2em; font-weight: bold;">{categories.get('gg_ng', 0)}%</div>
                </div>
                <div class="comparison-item">
                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">UNDER/OVER</div>
                    <div style="font-size: 2em; font-weight: bold;">{categories.get('under_over', 0)}%</div>
                </div>
                <div class="comparison-item">
                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">MULTIGOL</div>
                    <div style="font-size: 2em; font-weight: bold;">{categories.get('multigol', 0)}%</div>
                </div>
                <div class="comparison-item" style="background: rgba(255,255,255,0.4); border: 2px solid white;">
                    <div style="font-size: 0.9em; opacity: 0.9; margin-bottom: 8px;">🎯 GLOBALE</div>
                    <div style="font-size: 2.5em; font-weight: bold;">{global_conf}%</div>
                </div>
            </div>
            
            <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid rgba(255,255,255,0.3);">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <div style="font-size: 0.9em; opacity: 0.9;">📊 Mercato PIÙ affidabile</div>
                        <div style="font-size: 1.5em; font-weight: bold; margin-top: 5px;">{most_reliable.get('name', 'N/A')} ({most_reliable.get('confidence', 0)}%)</div>
                    </div>
                    <div>
                        <div style="font-size: 0.9em; opacity: 0.9;">⚠️ Mercato MENO affidabile</div>
                        <div style="font-size: 1.5em; font-weight: bold; margin-top: 5px;">{least_reliable.get('name', 'N/A')} ({least_reliable.get('confidence', 0)}%)</div>
                    </div>
                </div>
            </div>
        </div>
    """
    def _build_comparison_section(self, match):
        """Sezione confronto multi-algoritmo"""
        
        html = """
        <div class="algo-section" id="comparison">
            <h3 class="section-title">🌐 Confronto Multi-Algoritmo</h3>
            
            <table class="stats-table">
                <thead>
                    <tr>
                        <th>Categoria</th>
    """
        for algo_id in match['algorithms'].keys():
            algo_name = self.algo_names.get(algo_id, f"Algo {algo_id}")
            html += f'<th>{algo_name}</th>'
        
        html += '<th>📊 Media</th></tr></thead><tbody>'
        
        # Categorie da confrontare
        categories = ['gol', 'segni', 'gg_ng', 'under_over', 'multigol']
        category_names = {
            'gol': 'GOL',
            'segni': 'SEGNI 1X2',
            'gg_ng': 'GG/NOGOL',
            'under_over': 'UNDER/OVER',
            'multigol': 'MULTIGOL'
        }
        
        for cat_key in categories:
            cat_name = category_names[cat_key]
            html += f'<tr><td><strong>{cat_name}</strong></td>'
            
            values = []
            for algo_id, data in match['algorithms'].items():
                conf_data = data['stats'].get('confidence', {})
                val = conf_data.get('categories', {}).get(cat_key, 0)
                values.append(val)
                
                badge = "badge-high" if val > 80 else ("badge-medium" if val > 65 else "badge-low")
                html += f'<td><span class="badge {badge}">{val}%</span></td>'
            
            avg_val = sum(values) / len(values) if values else 0
            avg_badge = "badge-high" if avg_val > 80 else ("badge-medium" if avg_val > 65 else "badge-low")
            html += f'<td><span class="badge {avg_badge}">{avg_val:.1f}%</span></td></tr>'
        
        # Riga GLOBALE
        html += '<tr style="background: #f0f0f0; font-weight: bold;"><td><strong>🎯 GLOBALE</strong></td>'
        
        global_values = []
        for algo_id, data in match['algorithms'].items():
            val = data['stats'].get('confidence', {}).get('global_confidence', 0)
            global_values.append(val)
            html += f'<td><strong>{val}%</strong></td>'
        
        global_avg = sum(global_values) / len(global_values) if global_values else 0
        html += f'<td><strong>{global_avg:.1f}%</strong></td></tr></tbody></table>'
        
        html += f"""
        <div class="alert-box">
            <h4>💡 Interpretazione</h4>
            <p><strong>Confidence Globale Media (tutti algoritmi):</strong> {global_avg:.1f}%</p>
            <p style="margin-top: 10px;">{"🎯 Previsione molto affidabile!" if global_avg > 80 else ("✅ Previsione affidabile" if global_avg > 70 else "⚠️ Previsione con incertezza moderata")}</p>
        </div>
        </div>
    """
        return html

    def _get_html_footer(self):
        """Footer HTML con JavaScript"""
        
        return f"""
        <div style="background: #f8f9fa; padding: 30px; text-align: center; color: #666; border-top: 1px solid #e0e0e0;">
            <p><strong>📊 Confidence Analysis Report</strong></p>
            <p>Generato il {datetime.now().strftime("%d/%m/%Y alle %H:%M:%S")}</p>
        </div>
    </div>

    <script>
        function switchTab(tabId) {{
            // Nascondi tutte le sezioni
            document.querySelectorAll('.algo-section').forEach(section => {{
                section.classList.remove('active');
            }});
            
            // Rimuovi active da tutti i tab
            document.querySelectorAll('.nav-tab').forEach(tab => {{
                tab.classList.remove('active');
            }});
            
            // Mostra sezione selezionata
            document.querySelectorAll('#' + tabId).forEach(section => {{
                section.classList.add('active');
            }});
            
            // Attiva tab cliccato
            event.target.classList.add('active');
        }}
    </script>
    </body>
    </html>
"""