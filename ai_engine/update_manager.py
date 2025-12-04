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
CALCULATORS_DIR = os.path.join(AI_ENGINE_DIR, "calculators") # ⭐ Aggiunto path calcolatori

# ------------------------------------------------------------------------------
# LISTA DEI TASK (Sequenza precisa 1-12)
# Formato: (Nome_File, Titolo_Display, Spiegazione_Impatto, Cartella_Opzionale)
# ------------------------------------------------------------------------------

SCRAPER_SEQUENCE = [
      ("scraper_results_fbref.py", "📊 [1/12] Risultati & xG (FBref)", "Mancano risultati recenti e xG", FREQUENT_DIR),
      ("scraper_quote_storiche_betexplorer.py", "💰 [2/12] Quote Storiche", "Calcolo Affidabilità/BVS impossibile", FREQUENT_DIR),
      ("scraper_soccerstats_ranking_unified.py", "🏆 [3/12] Classifica & Gol", "Calcolo Forza Attacco/Difesa sballato", FREQUENT_DIR),
    
      ("fbref_scraper_att.py", "⚽ [4/12] Stats Attaccanti", "Analisi attacco imprecisa", FREQUENT_DIR),
      ("fbref_scraper_mid.py", "🧠 [5/12] Stats Centrocampisti", "Analisi centrocampo imprecisa", FREQUENT_DIR),
      ("fbref_scraper_def.py", "🛡️ [6/12] Stats Difensori", "Analisi difesa imprecisa", FREQUENT_DIR),
      ("scraper_gk_fbref.py", "🧤 [7/12] Stats Portieri", "Analisi portieri imprecisa", FREQUENT_DIR),
    
      ("scraper_tm_multi_campionato.py", "🚑 [8/12] Infortuni (TM)", "Si rischia di puntare su assenti", FREQUENT_DIR),
      ("scraper_calendario_h2h_TF_completo.py", "📅 [9/12] Calendario H2H", "Analisi scontri diretti incompleta", FREQUENT_DIR),
    
    # ⭐ LASCIO ATTIVO SOLO QUESTO PER IL TEST:
    ("calculate_h2h_v2.py", "🧠 [9b/12] Elaborazione H2H Pro", "Mancano medie gol e punteggi storici", CALCULATORS_DIR),
    
      ("scraper_fixtures.py", "📆 [10/12] Partite Future", "Il motore non saprà cosa simulare", FREQUENT_DIR),
      ("scraper_odds_oddsmath.py", "💎 [11/12] Quote Future", "Manca confronto con bookmaker", FREQUENT_DIR),
]

# ------------------------------------------------------------------------------
# FUNZIONI DI SERVIZIO
# ------------------------------------------------------------------------------

def run_single_script(filename, description, folder_path):
    # ⭐ Ora accetta folder_path specifico per ogni file
    full_path = os.path.join(folder_path, filename)
    print("\n" + "-"*70)
    print(f"▶ {description}")
    
    if not os.path.exists(full_path):
        print(f"❌ Errore: File non trovato in {full_path}")
        return False, "File non trovato"

    # Definiamo start_time PRIMA del blocco try
    start_time = time.time()
    
    try:
        # --- SETUP AMBIENTE UTF-8 ---
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # ----------------------------

        # Esecuzione script (output diretto a video)
        subprocess.run(
            [sys.executable, full_path], 
            check=True, capture_output=False, text=True, encoding='utf-8', errors='replace',
            env=env
        )
        
        # Se arriva qui, significa che non ci sono stati errori (check=True)
        elapsed = time.time() - start_time
        print(f"   ✅ COMPLETATO in {elapsed:.2f}s")
        return True, None
        
    except subprocess.CalledProcessError as e:
        # Se lo script fallisce (exit code != 0)
        print("   🔴 ERRORE SCRIPT (Vedi output sopra)")
        return False, "Script fallito (Exit Code != 0)"
        
    except Exception as e:
        # Altri errori imprevisti
        return False, str(e)

def main():
    print("\n" + "="*80)
    print("🎩 DIRETTORE D'ORCHESTRA 3.0: ORA CON H2H PRO")
    print("="*80)

    report = []

    for filename, desc, impact, folder in SCRAPER_SEQUENCE:
        ok, err_msg = run_single_script(filename, desc, folder)
        report.append({
            "file": filename,
            "status": "✅ OK" if ok else "❌ KO",
            "error": err_msg,
            "impact": impact,
            "folder": folder
        })
        # Pausa estetica solo se è andato tutto bene
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
            # Comando copia-incolla intelligente
            rel_path = os.path.relpath(os.path.join(fail['folder'], fail['file']), os.getcwd())
            print(f"   └─ Per riprovare: python {rel_path}")
            print("-" * 40)
    else:
        print("\n✨ SISTEMA PERFETTAMENTE AGGIORNATO (INCLUSO H2H)!")

    print("\n")

if __name__ == "__main__":
    main()
