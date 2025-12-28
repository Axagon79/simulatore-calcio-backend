"""
📚 CONFIDENCE GLOSSARY - Dizionario Spiegazioni Metriche (VERSIONE PRATICA)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Spiegazioni CHIARE e PRATICHE per scommettitori.
Ogni metrica spiega: COSA SIGNIFICA + COSA FARE

USAGE:
    from confidence_glossary import GLOSSARY
    explanation = GLOSSARY['gol_casa']
"""


GLOSSARY = {
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🎯 INTRODUZIONE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'intro': {
        'title': '📊 Come funziona questo Report',
        'text': '''Questo report mostra i risultati di {num_sim} simulazioni della partita.
        <br><br><strong>Cosa vuol dire?</strong>
        <br>L'algoritmo ha "giocato" questa partita {num_sim} volte per capire 
        cosa succede più spesso.
        <br><br><strong>Più simulazioni = risultati più affidabili</strong>
        <br>• 500+ simulazioni = Ottimo ✅
        <br>• 100-500 simulazioni = Buono ⚠️
        <br>• Meno di 100 = Poco affidabile ❌'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🏠 CATEGORIA GOL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'gol_casa': {
        'title': '🏠 Gol Casa - Confidence {confidence}%',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>Nelle {num_sim} simulazioni, la squadra di casa ha segnato:
        <br>• <strong>Media: {avg_gol} gol</strong>
        <br>• Risultato più frequente: {most_common} gol ({pct}% delle volte)
        <br><br>Il Confidence di {confidence}% indica quanto questi risultati sono <strong>costanti</strong>.
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• <span style="color: #28a745;">✅ Confidence ≥ 70%</span> = I gol casa sono <strong>PREVEDIBILI</strong>
        <br>  → <strong>SCOMMETTI</strong> su multigol casa, risultati esatti con {most_common} gol casa
        <br>• <span style="color: #ffc107;">⚠️ Confidence 40-70%</span> = I gol casa <strong>VARIANO MOLTO</strong>
        <br>  → Rischio medio, valuta attentamente
        <br>• <span style="color: #dc3545;">❌ Confidence < 40%</span> = I gol casa sono <strong>IMPREVEDIBILI</strong>
        <br>  → <strong>NON SCOMMETTERE</strong> su mercati legati ai gol casa
        <br><br><strong>📏 Std Dev: {std}</strong> (quanto variano i gol tra le simulazioni)
        <br>• Sotto 1.0 = Molto stabile ✅
        <br>• Tra 1.0-2.0 = Abbastanza variabile ⚠️
        <br>• Sopra 2.0 = Molto variabile ❌'''
    },
    
    'gol_ospite': {
        'title': '✈️ Gol Ospite - Confidence {confidence}%',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>Nelle {num_sim} simulazioni, la squadra ospite ha segnato:
        <br>• <strong>Media: {avg_gol} gol</strong>
        <br>• Risultato più frequente: {most_common} gol ({pct}% delle volte)
        <br><br>Il Confidence di {confidence}% indica quanto questi risultati sono <strong>costanti</strong>.
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• <span style="color: #28a745;">✅ Confidence ≥ 70%</span> = I gol ospite sono <strong>PREVEDIBILI</strong>
        <br>  → <strong>SCOMMETTI</strong> su multigol ospite, risultati esatti con {most_common} gol ospite
        <br>• <span style="color: #ffc107;">⚠️ Confidence 40-70%</span> = I gol ospite <strong>VARIANO MOLTO</strong>
        <br>  → Rischio medio, valuta attentamente
        <br>• <span style="color: #dc3545;">❌ Confidence < 40%</span> = I gol ospite sono <strong>IMPREVEDIBILI</strong>
        <br>  → <strong>NON SCOMMETTERE</strong> su mercati legati ai gol ospite
        <br><br><strong>📏 Std Dev: {std}</strong> (quanto variano i gol tra le simulazioni)
        <br>• Sotto 1.0 = Molto stabile ✅
        <br>• Tra 1.0-2.0 = Abbastanza variabile ⚠️
        <br>• Sopra 2.0 = Molto variabile ❌'''
    },
    
    'gol_totale': {
        'title': '⚽ Totale Gol - Confidence {confidence}%',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>Nelle {num_sim} simulazioni, il totale gol (casa + ospite) è stato:
        <br>• <strong>Media: {avg_total} gol totali</strong>
        <br>• Risultato più frequente: {most_common} gol totali ({pct}% delle volte)
        <br><br>Il Confidence di {confidence}% indica quanto questo totale è <strong>stabile</strong>.
        <br><br><strong>💡 COME SCOMMETTERE UNDER/OVER:</strong>
        <br>• <span style="color: #28a745;">✅ Confidence ≥ 70%</span> = Il totale gol è <strong>PREVEDIBILE</strong>
        <br>  → <strong>SCOMMETTI</strong> su Under/Over 2.5 (se media {avg_total} gol)
        <br>  → Se media < 2.5 → UNDER 2.5
        <br>  → Se media > 2.5 → OVER 2.5
        <br>• <span style="color: #ffc107;">⚠️ Confidence 40-70%</span> = Il totale gol <strong>VARIA MOLTO</strong>
        <br>  → Rischio medio su Under/Over
        <br>• <span style="color: #dc3545;">❌ Confidence < 40%</span> = Il totale gol è <strong>IMPREVEDIBILE</strong>
        <br>  → <strong>EVITA</strong> Under/Over
        <br><br><strong>📏 Std Dev: {std}</strong> (quanto varia il totale gol)
        <br>• Sotto 1.5 = Molto stabile ✅
        <br>• Tra 1.5-2.5 = Abbastanza variabile ⚠️
        <br>• Sopra 2.5 = Molto variabile ❌'''
    },
    
    'varianza_ratio': {
        'title': '📊 Varianza Casa vs Ospite',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>Confronta quanto sono <strong>imprevedibili</strong> i gol di casa rispetto all'ospite.
        <br><br><strong>Ratio: {ratio}</strong>
        <br>• Ratio > 1.5 = Casa molto più imprevedibile dell'ospite
        <br>• Ratio 0.7-1.5 = Simili
        <br>• Ratio < 0.7 = Ospite molto più imprevedibile della casa
        <br><br><strong>💡 CONSIGLIO:</strong>
        <br>Scommetti sulla squadra più <strong>prevedibile</strong> (quella con varianza minore)'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🏆 CATEGORIA SEGNI 1X2
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'segno_1': {
        'title': '1️⃣ Segno 1 (Vittoria Casa)',
        'text': '''<strong>📊 RISULTATI SIMULAZIONI:</strong>
        <br>• La casa ha vinto in <strong>{pct}%</strong> delle {num_sim} simulazioni
        <br>• Confidence: <strong>{confidence}%</strong>
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• <span style="color: #28a745;">✅ Se {pct}% ≥ 50% e Confidence ≥ 70%</span>
        <br>  → <strong>SCOMMETTI</strong> sulla vittoria casa (segno 1)
        <br>• <span style="color: #ffc107;">⚠️ Se {pct}% tra 30-50%</span>
        <br>  → Partita equilibrata, valuta bene
        <br>• <span style="color: #dc3545;">❌ Se {pct}% < 30%</span>
        <br>  → <strong>EVITA</strong> segno 1, casa sfavorita'''
    },
    
    'segno_x': {
        'title': '❌ Segno X (Pareggio)',
        'text': '''<strong>📊 RISULTATI SIMULAZIONI:</strong>
        <br>• Pareggio in <strong>{pct}%</strong> delle {num_sim} simulazioni
        <br>• Confidence: <strong>{confidence}%</strong>
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• <span style="color: #28a745;">✅ Se {pct}% ≥ 35% e Confidence ≥ 70%</span>
        <br>  → <strong>SCOMMETTI</strong> sul pareggio (segno X)
        <br>• <span style="color: #ffc107;">⚠️ Se {pct}% tra 25-35%</span>
        <br>  → Pareggio possibile ma non probabile
        <br>• <span style="color: #dc3545;">❌ Se {pct}% < 25%</span>
        <br>  → <strong>EVITA</strong> segno X, pareggio improbabile
        <br><br><strong>⚠️ NOTA:</strong> Il pareggio è sempre più difficile da prevedere'''
    },
    
    'segno_2': {
        'title': '2️⃣ Segno 2 (Vittoria Ospite)',
        'text': '''<strong>📊 RISULTATI SIMULAZIONI:</strong>
        <br>• L'ospite ha vinto in <strong>{pct}%</strong> delle {num_sim} simulazioni
        <br>• Confidence: <strong>{confidence}%</strong>
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• <span style="color: #28a745;">✅ Se {pct}% ≥ 50% e Confidence ≥ 70%</span>
        <br>  → <strong>SCOMMETTI</strong> sulla vittoria ospite (segno 2)
        <br>• <span style="color: #ffc107;">⚠️ Se {pct}% tra 30-50%</span>
        <br>  → Partita equilibrata, valuta bene
        <br>• <span style="color: #dc3545;">❌ Se {pct}% < 30%</span>
        <br>  → <strong>EVITA</strong> segno 2, ospite sfavorito'''
    },
    
    'segno_vincente': {
        'title': '👑 Segno Più Probabile',
        'text': '''<strong>📊 SEGNO VINCENTE:</strong> <strong style="font-size: 1.5em;">{segno}</strong>
        <br>• Uscito in <strong>{pct}%</strong> delle simulazioni
        <br>• Confidence: <strong>{confidence}%</strong>
        <br><br><strong>💡 INTERPRETAZIONE:</strong>
        <br>• <span style="color: #28a745;">✅ Confidence ≥ 80%</span> = Esito <strong>MOLTO PROBABILE</strong>
        <br>  → <strong>SCOMMESSA CONSIGLIATA</strong>
        <br>• <span style="color: #28a745;">✅ Confidence 70-80%</span> = Esito <strong>PROBABILE</strong>
        <br>  → Scommessa buona
        <br>• <span style="color: #ffc107;">⚠️ Confidence 50-70%</span> = Esito <strong>INCERTO</strong>
        <br>  → Partita equilibrata, rischio medio
        <br>• <span style="color: #dc3545;">❌ Confidence < 50%</span> = Esito <strong>IMPREVEDIBILE</strong>
        <br>  → <strong>EVITA</strong> scommesse 1X2, partita troppo incerta'''
    },
    
    'margini_vittoria': {
        'title': '📊 Margini di Vittoria',
        'text': '''<strong>📊 QUANDO VINCE, DI QUANTO VINCE?</strong>
        <br>• <strong>Casa:</strong> Quando vince, lo fa mediamente per <strong>{home_margin} gol</strong>
        <br>• <strong>Ospite:</strong> Quando vince, lo fa mediamente per <strong>{away_margin} gol</strong>
        <br><br><strong>💡 INTERPRETAZIONE:</strong>
        <br>• Margine > 2.0 = Vittorie <strong>NETTE</strong> (es. 3-0, 4-1)
        <br>• Margine 1.0-2.0 = Vittorie di <strong>CORTO MUSO</strong> (es. 2-1, 2-0)
        <br>• Margine < 1.0 = Vittorie <strong>RISICATE</strong> (es. 1-0)
        <br><br><strong>💡 CONSIGLIO:</strong>
        <br>Se il margine è alto, considera anche <strong>Handicap</strong> e <strong>Over gol squadra</strong>'''
    },
    
    'dominanza_top10': {
        'title': '🎯 Dominanza nei TOP 10 Risultati',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>Dei 10 risultati esatti più probabili, quanti hanno lo stesso segno (1, X o 2)?
        <br><br><strong>Dominanza: {dominanza}%</strong>
        <br>• {count_1} risultati con segno 1 (casa vince)
        <br>• {count_x} risultati con segno X (pareggio)
        <br>• {count_2} risultati con segno 2 (ospite vince)
        <br><br><strong>💡 INTERPRETAZIONE:</strong>
        <br>• <span style="color: #28a745;">✅ Dominanza ≥ 60%</span> = Un segno <strong>DOMINA</strong>
        <br>  → Esito molto chiaro, scommetti sul segno dominante
        <br>• <span style="color: #ffc107;">⚠️ Dominanza 40-60%</span> = Segni <strong>MISTI</strong>
        <br>  → Partita equilibrata
        <br>• <span style="color: #dc3545;">❌ Dominanza < 40%</span> = Segni <strong>SPARPAGLIATI</strong>
        <br>  → Partita molto incerta, evita 1X2
        <br><br><strong>ESEMPIO:</strong>
        <br>Se 7 risultati su 10 sono vittorie casa (2-0, 1-0, 3-1, ecc.)
        <br>→ Dominanza = 70% → Casa molto favorita'''
    },
    
    'anomalia_segni': {
        'title': '⚠️ ATTENZIONE: Anomalia Rilevata!',
        'text': '''<strong>🚨 SITUAZIONE CONTRADDITTORIA:</strong>
        <br>{anomaly_message}
        <br><br><strong>💡 COSA SIGNIFICA:</strong>
        <br>C'è una <strong>incoerenza</strong> tra:
        <br>• La probabilità generale del segno (bassa)
        <br>• La sua posizione nei risultati esatti (alta)
        <br><br><strong>⚠️ CONSEGUENZE:</strong>
        <br>• Il Confidence del segno vincente è stato <strong>ridotto dell'8%</strong>
        <br>• Le previsioni potrebbero essere <strong>meno affidabili</strong>
        <br><br><strong>💡 CONSIGLIO:</strong>
        <br>• <span style="color: #dc3545;">⚠️ Procedi con CAUTELA</span>
        <br>• Considera scommesse <strong>DOPPIE</strong> (es. 1X o X2)
        <br>• Potrebbero esserci <strong>SORPRESE</strong>
        <br>• Riduci le puntate su questa partita'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ⚽ CATEGORIA GG/NOGOL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'gg_ng': {
        'title': '⚽ Goal/NoGoal',
        'text': '''<strong>📊 RISULTATI SIMULAZIONI:</strong>
        <br>• <strong>GG (entrambe segnano):</strong> {prob_gg}% delle volte
        <br>• <strong>NG (almeno una non segna):</strong> {prob_ng}% delle volte
        <br>• <strong>Confidence:</strong> {confidence}%
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br><br><strong>SCOMMETTI GG (Goal):</strong>
        <br>• <span style="color: #28a745;">✅ Se Prob GG ≥ 60% e Confidence ≥ 70%</span>
        <br>  → <strong>SCOMMESSA CONSIGLIATA</strong> su GG
        <br>• <span style="color: #ffc107;">⚠️ Se Prob GG 50-60%</span>
        <br>  → GG possibile ma incerto
        <br><br><strong>SCOMMETTI NG (NoGoal):</strong>
        <br>• <span style="color: #28a745;">✅ Se Prob GG ≤ 40% e Confidence ≥ 70%</span>
        <br>  → <strong>SCOMMESSA CONSIGLIATA</strong> su NG
        <br>• <span style="color: #ffc107;">⚠️ Se Prob GG 40-50%</span>
        <br>  → NG possibile ma incerto
        <br><br><strong>EVITA GG/NG:</strong>
        <br>• <span style="color: #dc3545;">❌ Se Confidence < 40%</span>
        <br>  → Troppo imprevedibile
        <br><br><strong>📏 Std Dev: {std}</strong> (stabilità della previsione)
        <br>• Sotto 0.4 = Molto stabile ✅
        <br>• 0.4-0.5 = Abbastanza stabile ⚠️
        <br>• Sopra 0.5 = Instabile ❌'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 📊 CATEGORIA UNDER/OVER
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'under_over': {
        'title': '📊 Under/Over',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>Prevede se il totale gol sarà SOPRA (Over) o SOTTO (Under) una soglia.
        <br><br><strong>🎯 SOGLIE PRINCIPALI:</strong>
        <br>• <strong>U/O 1.5:</strong> Almeno 2 gol o massimo 1 gol
        <br>• <strong>U/O 2.5:</strong> Almeno 3 gol o massimo 2 gol (LA PIÙ USATA)
        <br>• <strong>U/O 3.5:</strong> Almeno 4 gol o massimo 3 gol
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>Guarda la <strong>soglia più affidabile</strong> indicata sotto.
        <br><br>Se la <strong>media gol totali è {avg_total}</strong>:
        <br>• {avg_total} < 2.5 → Scommetti <strong>UNDER 2.5</strong>
        <br>• {avg_total} > 2.5 → Scommetti <strong>OVER 2.5</strong>
        <br><br><strong>✅ SCOMMETTI solo se:</strong>
        <br>• Confidence soglia ≥ 70%
        <br>• La media è chiaramente sopra o sotto (non 2.4-2.6)
        <br><br><strong>❌ EVITA se:</strong>
        <br>• Confidence < 50%
        <br>• La media è vicina alla soglia (es. 2.4 per U/O 2.5)'''
    },
    
    'soglia_affidabile': {
        'title': '🎯 Soglia Più Affidabile',
        'text': '''<strong>🏆 MIGLIOR SCOMMESSA UNDER/OVER:</strong>
        <br><br><strong>{threshold}</strong> con Confidence <strong>{confidence}%</strong>
        <br><br><strong>💡 PERCHÉ QUESTA SOGLIA:</strong>
        <br>È la soglia con il Confidence più alto, quindi la previsione
        più <strong>stabile</strong> e <strong>affidabile</strong>.
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• Confronta la <strong>media gol totali</strong> con questa soglia
        <br>• Se media < soglia → Scommetti UNDER
        <br>• Se media > soglia → Scommetti OVER
        <br><br><strong>ESEMPIO:</strong>
        <br>Se soglia più affidabile = U/O 2.5 e media = 1.8 gol
        <br>→ <strong>SCOMMETTI UNDER 2.5</strong>'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🎲 CATEGORIA MULTIGOL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'multigol': {
        'title': '🎲 Multigol',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>Prevede un <strong>intervallo di gol</strong> per ciascuna squadra.
        <br><br><strong>🏠 CASA - Range: {home_range}</strong>
        <br>• Confidence: <strong>{home_conf}%</strong>
        <br>• Uscito in <strong>{home_occ}</strong> simulazioni su {num_sim}
        <br><br><strong>✈️ OSPITE - Range: {away_range}</strong>
        <br>• Confidence: <strong>{away_conf}%</strong>
        <br>• Uscito in <strong>{away_occ}</strong> simulazioni su {num_sim}
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• <span style="color: #28a745;">✅ Confidence ≥ 70%</span>
        <br>  → <strong>SCOMMETTI</strong> sul multigol indicato
        <br>• <span style="color: #ffc107;">⚠️ Confidence 50-70%</span>
        <br>  → Scommessa rischiosa
        <br>• <span style="color: #dc3545;">❌ Confidence < 50%</span>
        <br>  → <strong>EVITA</strong> multigol
        <br><br><strong>ESEMPIO:</strong>
        <br>Range Casa 1-3 con 85% Confidence
        <br>→ La casa segnerà tra 1 e 3 gol nell'85% dei casi
        <br>→ <strong>SCOMMESSA CONSIGLIATA</strong>'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🏅 RISULTATI ESATTI
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'concentrazione_top3': {
        'title': '🎯 Concentrazione TOP 3',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>I 3 risultati esatti più probabili coprono il <strong>{pct}%</strong> delle simulazioni.
        <br><br><strong>💡 INTERPRETAZIONE:</strong>
        <br>• <span style="color: #28a745;">✅ Alta (≥ 50%)</span> = Partita <strong>PREVEDIBILE</strong>
        <br>  → Pochi risultati molto probabili
        <br>  → <strong>CONSIDERA</strong> scommesse su risultati esatti
        <br>• <span style="color: #ffc107;">⚠️ Media (30-50%)</span> = Partita <strong>MEDIAMENTE PREVEDIBILE</strong>
        <br>  → Risultati abbastanza sparsi
        <br>• <span style="color: #dc3545;">❌ Bassa (< 30%)</span> = Partita <strong>IMPREVEDIBILE</strong>
        <br>  → Moltissimi risultati possibili
        <br>  → <strong>EVITA</strong> risultati esatti
        <br><br><strong>ESEMPIO:</strong>
        <br>Concentrazione 60% = I primi 3 risultati (es. 1-0, 2-1, 1-1)
        <br>coprono il 60% delle simulazioni
        <br>→ Partita molto prevedibile'''
    },
    
    'entropia': {
        'title': '🔬 Entropia (Livello di Caos)',
        'text': '''<strong>📊 COSA SIGNIFICA:</strong>
        <br>Misura quanto sono <strong>sparsi</strong> i risultati possibili.
        <br><br><strong>Entropia: {entropy}</strong>
        <br><br><strong>💡 INTERPRETAZIONE:</strong>
        <br>• <span style="color: #28a745;">✅ Bassa (< 2.5)</span> = <strong>POCHI RISULTATI CONCENTRATI</strong>
        <br>  → Partita prevedibile
        <br>  → Considera risultati esatti e combo
        <br>• <span style="color: #ffc107;">⚠️ Media (2.5-3.5)</span> = <strong>RISULTATI DISTRIBUITI</strong>
        <br>  → Partita equilibrata
        <br>• <span style="color: #dc3545;">❌ Alta (> 3.5)</span> = <strong>MOLTI RISULTATI SPARSI</strong>
        <br>  → Partita imprevedibile
        <br>  → <strong>EVITA</strong> risultati esatti
        <br><br><strong>IN PAROLE SEMPLICI:</strong>
        <br>Più bassa = più sicuri su pochi risultati
        <br>Più alta = moltissimi risultati possibili'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🎰 MERCATI ESOTICI
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'pari_dispari': {
        'title': '🎲 Pari/Dispari',
        'text': '''<strong>📊 RISULTATI SIMULAZIONI:</strong>
        <br>• <strong>Dispari:</strong> {pct_dispari}% delle volte
        <br>• <strong>Pari:</strong> {pct_pari}% delle volte
        <br>• <strong>Confidence:</strong> {confidence}%
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• <span style="color: #28a745;">✅ Se % ≥ 60% e Confidence ≥ 70%</span>
        <br>  → <strong>SCOMMETTI</strong> sul risultato più probabile
        <br>• <span style="color: #ffc107;">⚠️ Se % 50-60%</span>
        <br>  → Molto equilibrato, quota bassa
        <br>• <span style="color: #dc3545;">❌ Se Confidence < 40%</span>
        <br>  → <strong>EVITA</strong>, mercato troppo aleatorio
        <br><br><strong>⚠️ ATTENZIONE:</strong>
        <br>Mercato molto <strong>volatile</strong> e difficile da prevedere.
        <br>Scommetti solo se hai Confidence molto alto (≥ 75%)'''
    },
    
    'clean_sheet': {
        'title': '🛡️ Clean Sheet (Porta Inviolata)',
        'text': '''<strong>📊 PROBABILITÀ PORTA INVIOLATA:</strong>
        <br><br><strong>🏠 CASA mantiene la porta inviolata:</strong>
        <br>• Probabilità: <strong>{home_pct}%</strong>
        <br>• (= L'ospite NON segna)
        <br><br><strong>✈️ OSPITE mantiene la porta inviolata:</strong>
        <br>• Probabilità: <strong>{away_pct}%</strong>
        <br>• (= La casa NON segna)
        <br><br><strong>Confidence Clean Sheet: {confidence}%</strong>
        <br><br><strong>💡 COME SCOMMETTERE:</strong>
        <br>• <span style="color: #28a745;">✅ Se % ≥ 40% e Confidence ≥ 70%</span>
        <br>  → <strong>SCOMMETTI</strong> "Squadra X a segno: NO"
        <br>  → Oppure scommetti NoGoal (NG)
        <br>• <span style="color: #ffc107;">⚠️ Se % 20-40%</span>
        <br>  → Clean Sheet possibile ma non probabile
        <br>• <span style="color: #dc3545;">❌ Se % < 20%</span>
        <br>  → <strong>EVITA</strong>, squadra segnerà quasi sicuramente
        <br><br><strong>ESEMPIO:</strong>
        <br>Casa clean sheet 45% con Confidence 75%
        <br>→ <strong>SCOMMETTI</strong> "Ospite a segno: NO"'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🔬 METRICHE AVANZATE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'correlazione': {
        'title': '🔗 Correlazione Gol Casa-Ospite',
        'text': '''<strong>📊 CORRELAZIONE: {correlation}</strong>
        <br><br><strong>🤔 COSA SIGNIFICA "CORRELAZIONE"?</strong>
        <br>Indica se quando una squadra segna, anche l'altra tende a segnare.
        <br><br><strong>💡 INTERPRETAZIONE:</strong>
        <br><br><span style="color: #28a745;">✅ CORRELAZIONE POSITIVA FORTE (+0.3 a +1.0):</span>
        <br>→ Quando una segna, anche l'altra tende a segnare
        <br>→ <strong>PARTITE APERTE</strong> con tanti gol
        <br>→ <strong>SCOMMETTI:</strong> GG (Goal), Over 2.5, risultati tipo 2-2, 2-1, 3-2
        <br><br><span style="color: #17a2b8;">📊 CORRELAZIONE POSITIVA DEBOLE (0 a +0.3):</span>
        <br>→ Leggera tendenza a segnare entrambe
        <br>→ Partite abbastanza equilibrate
        <br>→ Valuta caso per caso
        <br><br><span style="color: #ffc107;">⚠️ CORRELAZIONE NEGATIVA DEBOLE (-0.3 a 0):</span>
        <br>→ Quando una segna molto, l'altra segna meno
        <br>→ Partite più tattiche
        <br>→ <strong>CONSIDERA:</strong> NoGoal (NG), Under 2.5
        <br><br><span style="color: #dc3545;">❌ CORRELAZIONE NEGATIVA FORTE (-1.0 a -0.3):</span>
        <br>→ Quando una domina, l'altra non segna
        <br>→ <strong>PARTITE CHIUSE</strong> con una squadra dominante
        <br>→ <strong>SCOMMETTI:</strong> NG (NoGoal), Under 2.5, risultati tipo 2-0, 0-1, 3-0
        <br>→ Considera Clean Sheet della squadra forte'''
    },
    
    'varianza_avanzata': {
        'title': '📊 Varianza (Imprevedibilità)',
        'text': '''<strong>📊 VARIANZA:</strong>
        <br>• <strong>Casa:</strong> {var_home}
        <br>• <strong>Ospite:</strong> {var_away}
        <br>• <strong>Ratio:</strong> {ratio}
        <br><br><strong>💡 COSA SIGNIFICA:</strong>
        <br>La varianza misura quanto sono <strong>imprevedibili</strong> i gol di una squadra.
        <br><br><strong>Varianza alta = Gol molto variabili = Imprevedibile</strong>
        <br>Varianza bassa = Gol stabili = Prevedibile
        <br><br><strong>💡 COME USARLA:</strong>
        <br>• Se Ratio > 1.5 → Casa più imprevedibile
        <br>  → <strong>SCOMMETTI</strong> su mercati legati all'ospite
        <br>• Se Ratio < 0.7 → Ospite più imprevedibile
        <br>  → <strong>SCOMMETTI</strong> su mercati legati alla casa
        <br>• Se Ratio 0.7-1.5 → Simili
        <br>  → Entrambe ugualmente (im)prevedibili'''
    },
    
    'skewness': {
        'title': '📐 Skewness (Dove sono i gol)',
        'text': '''<strong>📊 SKEWNESS (ASIMMETRIA):</strong>
        <br>• <strong>Casa:</strong> {skew_home}
        <br>• <strong>Ospite:</strong> {skew_away}
        <br><br><strong>💡 COSA SIGNIFICA IN PAROLE SEMPLICI:</strong>
        <br><br><strong>Skewness POSITIVO (> 0.5):</strong>
        <br>→ Più risultati con <strong>TANTI GOL</strong>
        <br>→ La squadra tende a segnare molto quando segna
        <br>→ <strong>CONSIDERA:</strong> Over gol squadra, risultati alti
        <br><br><strong>Skewness VICINO A ZERO (-0.5 a +0.5):</strong>
        <br>→ Gol <strong>DISTRIBUITI NORMALMENTE</strong>
        <br>→ Squadra equilibrata
        <br><br><strong>Skewness NEGATIVO (< -0.5):</strong>
        <br>→ Più risultati con <strong>POCHI GOL</strong>
        <br>→ La squadra tende a segnare poco
        <br>→ <strong>CONSIDERA:</strong> Under gol squadra, risultati bassi
        <br><br><strong>⚠️ NOTA:</strong> Metrica avanzata, utile per scommesse particolari'''
    },
    
    'kurtosis': {
        'title': '📊 Kurtosis (Risultati Estremi)',
        'text': '''<strong>📊 KURTOSIS (CURTOSI):</strong>
        <br>• <strong>Casa:</strong> {kurt_home}
        <br>• <strong>Ospite:</strong> {kurt_away}
        <br><br><strong>💡 COSA SIGNIFICA:</strong>
        <br>Indica se ci sono molti <strong>risultati estremi</strong> (es. 5-0, 0-4).
        <br><br><strong>Kurtosis ALTA (> 3):</strong>
        <br>→ Molti <strong>RISULTATI ESTREMI</strong>
        <br>→ La squadra o domina o crolla
        <br>→ Partite molto imprevedibili
        <br>→ <strong>ATTENZIONE:</strong> Possibili sorprese
        <br><br><strong>Kurtosis NORMALE (0 a 3):</strong>
        <br>→ <strong>DISTRIBUZIONE STANDARD</strong>
        <br>→ Risultati normali
        <br><br><strong>Kurtosis BASSA (< 0):</strong>
        <br>→ Pochi risultati estremi
        <br>→ Risultati molto <strong>COSTANTI</strong>
        <br>→ Squadra prevedibile
        <br><br><strong>⚠️ NOTA:</strong> Metrica molto tecnica, usala solo se esperto'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 🌍 CONFIDENCE GLOBALE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'confidence_globale': {
        'title': '🌍 Confidence Globale - QUANTO FIDARSI',
        'text': '''<strong>🎯 CONFIDENCE GLOBALE: {global_conf}%</strong>
        <br><br><strong>💡 COSA SIGNIFICA:</strong>
        <br>È la <strong>media</strong> di tutti i Confidence delle categorie (Gol, Segni, GG/NG, ecc.).
        <br><br>Indica quanto le simulazioni sono <strong>coerenti</strong> e <strong>affidabili</strong>
        <br>su TUTTI i mercati di scommessa.
        <br><br><strong>📊 SCALA DI AFFIDABILITÀ:</strong>
        <br><br><span style="color: #28a745;">🎯 ≥ 80%</span> = Previsione <strong>MOLTO AFFIDABILE</strong>
        <br>→ <strong>SCOMMETTI CON FIDUCIA</strong> sui mercati indicati
        <br>→ Le simulazioni sono molto coerenti
        <br>→ Considera anche scommesse multiple
        <br><br><span style="color: #28a745;">✅ 70-80%</span> = Previsione <strong>AFFIDABILE</strong>
        <br>→ <strong>BUONA OCCASIONE</strong> per scommettere
        <br>→ Concentrati sui mercati con Confidence alto
        <br><br><span style="color: #ffc107;">⚠️ 50-70%</span> = Previsione con <strong>INCERTEZZA MODERATA</strong>
        <br>→ <strong>PROCEDI CON CAUTELA</strong>
        <br>→ Scommetti solo sui mercati più affidabili
        <br>→ Evita scommesse multiple
        <br>→ Riduci le puntate
        <br><br><span style="color: #dc3545;">❌ < 50%</span> = Previsione <strong>POCO AFFIDABILE</strong>
        <br>→ <strong>EVITA DI SCOMMETTERE</strong> su questa partita
        <br>→ Le simulazioni sono troppo incoerenti
        <br>→ Partita molto imprevedibile
        <br><br><strong>🎯 CONSIGLIO GENERALE:</strong>
        <br>Usa questo valore per decidere SE scommettere su questa partita.
        <br>Se è basso, cerca altre partite più prevedibili.'''
    },
    
    'mercato_piu_affidabile': {
        'title': '🏆 Mercato Più Affidabile - DOVE SCOMMETTERE',
        'text': '''<strong>🏆 MIGLIOR MERCATO: {market_name}</strong>
        <br><strong>Confidence: {confidence}%</strong>
        <br><br><strong>💡 COSA SIGNIFICA:</strong>
        <br>È il tipo di scommessa dove le simulazioni sono <strong>più coerenti</strong>.
        <br><br><strong>✅ COSA FARE:</strong>
        <br>• <strong>CONCENTRA</strong> le tue scommesse su questo mercato
        <br>• Su questo mercato hai le <strong>probabilità migliori</strong>
        <br>• Le previsioni sono più <strong>affidabili</strong>
        <br><br><strong>ESEMPI:</strong>
        <br>• Se mercato = GOL → Scommetti su Multigol, Over/Under
        <br>• Se mercato = SEGNI → Scommetti su 1X2
        <br>• Se mercato = GG/NG → Scommetti su Goal/NoGoal
        <br>• Se mercato = UNDER/OVER → Scommetti su Under/Over 2.5
        <br>• Se mercato = MULTIGOL → Scommetti su range gol squadre'''
    },
    
    'mercato_meno_affidabile': {
        'title': '⚠️ Mercato Meno Affidabile - COSA EVITARE',
        'text': '''<strong>⚠️ MERCATO RISCHIOSO: {market_name}</strong>
        <br><strong>Confidence: {confidence}%</strong>
        <br><br><strong>💡 COSA SIGNIFICA:</strong>
        <br>È il tipo di scommessa dove le simulazioni <strong>variano di più</strong>.
        <br><br><strong>❌ COSA FARE:</strong>
        <br>• <strong>EVITA</strong> scommesse su questo mercato
        <br>• Le previsioni sono <strong>meno affidabili</strong>
        <br>• Rischio di perdita più alto
        <br><br><strong>⚠️ ATTENZIONE:</strong>
        <br>Anche se vedi quote alte su questo mercato, il rischio
        è maggiore perché i risultati sono molto <strong>incoerenti</strong>.
        <br><br><strong>💡 CONSIGLIO:</strong>
        <br>Concentrati sul <strong>mercato più affidabile</strong> indicato sopra.'''
    },
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 📊 CONFIDENCE CATEGORIE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    'confidence_categoria': {
        'title': '📊 Confidence Categoria',
        'text': '''<strong>📊 CONFIDENCE {category_name}: {confidence}%</strong>
        <br><br><strong>💡 COSA SIGNIFICA:</strong>
        <br>Indica quanto sono <strong>affidabili</strong> le previsioni per questa
        <br>specifica categoria di scommesse.
        <br><br><strong>✅ ≥ 70%</strong> = Categoria affidabile, scommetti qui
        <br><strong>⚠️ 40-70%</strong> = Categoria incerta, valuta bene
        <br><strong>❌ < 40%</strong> = Categoria poco affidabile, evita'''
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 📋 FUNZIONI HELPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_explanation(key, **kwargs):
    """
    Ottieni spiegazione con valori dinamici sostituiti.
    
    Args:
        key: Chiave del glossario
        **kwargs: Valori da sostituire nel testo (es. confidence=78, avg_gol=1.5)
        
    Returns:
        dict: {'title': ..., 'text': ...} con valori sostituiti
    """
    
    if key not in GLOSSARY:
        return {'title': 'N/A', 'text': 'Spiegazione non disponibile'}
    
    entry = GLOSSARY[key].copy()
    
    # Sostituisci i placeholder con i valori reali
    for placeholder, value in kwargs.items():
        entry['title'] = entry['title'].replace(f'{{{placeholder}}}', str(value))
        entry['text'] = entry['text'].replace(f'{{{placeholder}}}', str(value))
    
    return entry


def get_tooltip_icon(key, **kwargs):
    """
    Genera icona tooltip da aggiungere accanto a un valore.
    
    Returns:
        str: HTML dell'icona con tooltip
    """
    
    explanation = get_explanation(key, **kwargs)
    
    # Escape per attributo HTML
    text_escaped = explanation['text'].replace('"', '&quot;').replace("'", '&#39;')
    
    return f'''<span class="info-icon" title="{explanation['title']}" 
    data-explanation="{text_escaped}">ℹ️</span>'''


def get_explanation_box(key, **kwargs):
    """
    Genera box di spiegazione completo da inserire sopra una sezione.
    
    Returns:
        str: HTML del box
    """
    
    explanation = get_explanation(key, **kwargs)
    
    return f'''
    <div class="explanation-box" style="background: #e3f2fd; border-left: 4px solid #2196f3; 
    padding: 15px; margin: 20px 0; border-radius: 8px;">
        <h4 style="color: #1976d2; margin-bottom: 10px; font-size: 1.1em;">
            {explanation['title']}
        </h4>
        <div style="color: #333; line-height: 1.6;">
            {explanation['text']}
        </div>
    </div>
    '''