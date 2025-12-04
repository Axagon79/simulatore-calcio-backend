import os
import sys
import subprocess
import time
from datetime import datetime

# ------------------------------------------------------------------------------
# CONFIGURAZIONE PERCORSI
# ------------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Assumendo update_manager.py in ai_engine/
AI_ENGINE_DIR = CURRENT_DIR 
FREQUENT_DIR = os.path.join(AI_ENGINE_DIR, "Aggiornamenti", "frequenti")

# ------------------------------------------------------------------------------
# LISTA DEI TASK (Sequenza precisa 1-11)
# Formato: (Nome_File, Titolo_Display, Spiegazione_Impatto)
# ------------------------------------------------------------------------------

SCRAPER_SEQUENCE = [
    ("scraper_results_fbref.py", "📊 [1/11] Risultati & xG (FBref)", "Mancano risultati recenti e xG"),
    ("scraper_quote_storiche_betexplorer.py", "💰 [2/11] Quote Storiche", "Calcolo Affidabilità/BVS impossibile"),
    ("scraper_soccerstats_ranking_unified.py", "🏆 [3/11] Classifica & Gol", "Calcolo Forza Attacco/Difesa sballato"),
    
    ("fbref_scraper_att.py", "⚽ [4/11] Stats Attaccanti", "Analisi attacco imprecisa"),
    ("fbref_scraper_mid.py", "🧠 [5/11] Stats Centrocampisti", "Analisi centrocampo imprecisa"),
    ("fbref_scraper_def.py", "🛡️ [6/11] Stats Difensori", "Analisi difesa imprecisa"),
    ("scraper_gk_fbref.py", "🧤 [7/11] Stats Portieri", "Analisi portieri imprecisa"),
    
    ("scraper_tm_multi_campionato.py", "🚑 [8/11] Infortuni (TM)", "Si rischia di puntare su assenti"),
    ("scraper_calendario_h2h_TF_completo.py", "📅 [9/11] Calendario H2H", "Analisi scontri diretti incompleta"),
    
    ("scraper_fixtures.py", "📆 [10/11] Partite Future", "Il motore non saprà cosa simulare"),
    ("scraper_odds_oddsmath.py", "💎 [11/11] Quote Future", "Manca confronto con bookmaker"),
]

# ------------------------------------------------------------------------------
# FUNZIONI DI SERVIZIO
# ------------------------------------------------------------------------------

def run_single_script(filename, description):
    full_path = os.path.join(FREQUENT_DIR, filename)
    print("\n" + "-"*70)
    print(f"▶ {description}")
    
    if not os.path.exists(full_path):
        return False, "File non trovato"

    start_time = time.time()
    try:
        # Eseguiamo lo script e catturiamo output
        result = subprocess.run(
            [sys.executable, full_path], 
            check=True, capture_output=True, text=True, encoding='utf-8', errors='replace'
        )
        # Stampiamo l'output positivo
        print(result.stdout)
        print(f"   ✅ COMPLETATO in {time.time() - start_time:.2f}s")
        return True, None
        
    except subprocess.CalledProcessError as e:
        print(e.stdout) # Stampa quello che ha fatto prima di morire
        print("   🔴 ERRORE:")
        print(e.stderr) # Stampa l'errore tecnico
        
        # Analisi errore semplificata
        err_msg = "Errore Generico"
        if "ModuleNotFoundError" in e.stderr: err_msg = "Modulo mancante (fix_imports?)"
        elif "Timeout" in e.stderr: err_msg = "Timeout Connessione"
        elif "Connection" in e.stderr: err_msg = "Errore di Rete"
        
        return False, err_msg
    except Exception as e:
        return False, str(e)

def main():
    print("\n" + "="*80)
    print("🎩 DIRETTORE D'ORCHESTRA 2.1: REPORT + IMPATTO")
    print("="*80)

    report = []

    for filename, desc, impact in SCRAPER_SEQUENCE:
        ok, err_msg = run_single_script(filename, desc)
        report.append({
            "file": filename,
            "status": "✅ OK" if ok else "❌ KO",
            "error": err_msg,
            "impact": impact
        })
        if ok: time.sleep(2)

    # --- REPORT FINALE ---
    print("\n\n" + "="*90)
    print("📊 REPORT AGGIORNAMENTO")
    print("="*90)
    # Intestazione Tabella
    print(f"{'STATO':<6} | {'FILE (Script)':<35} | {'IMPATTO (Se fallisce)'}")
    print("-" * 90)

    failures = []
    for item in report:
        print(f"{item['status']:<6} | {item['file']:<35} | {item['impact']}")
        if item['status'] == "❌ KO":
            failures.append(item)

    # --- DETTAGLIO ERRORI E COMANDI ---
    if failures:
        print("\n" + "="*90)
        print("⚠️  ANALISI FALLIMENTI")
        print("="*90)
        for fail in failures:
            print(f"🔴 {fail['file']}")
            print(f"   └─ Errore tecnico: {fail['error']}")
            print(f"   └─ Conseguenza: {fail['impact']}")
            # Comando copia-incolla
            rel_path = os.path.join("ai_engine", "Aggiornamenti", "frequenti", fail['file'])
            print(f"   └─ Per riprovare: python {rel_path}")
            print("-" * 40)
    else:
        print("\n✨ SISTEMA PERFETTAMENTE AGGIORNATO!")

    print("\n")

if __name__ == "__main__":
    main()
