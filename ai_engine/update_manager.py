import os
import sys
import subprocess
import time
from datetime import datetime, timedelta
def kill_chrome_zombies():
    """Uccide tutti i processi Chrome/chromedriver orfani (Windows)"""
    killed = 0
    for proc_name in ['chrome.exe', 'chromedriver.exe']:
        try:
            result = subprocess.run(
                ['taskkill', '/F', '/IM', proc_name, '/T'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = [l for l in result.stdout.strip().split('\n') if l.strip()]
                killed += len(lines)
        except Exception:
            pass
    if killed:
        print(f"   🧹 Cleanup: ~{killed} processi Chrome/chromedriver terminati")
    else:
        print(f"   🧹 Cleanup: nessun Chrome zombie trovato")


# (FA L AGGIORNAMENTO COMPLETO FREQUENTE)
# ------------------------------------------------------------------------------
# (FA L AGGIORNAMENTO COMPLETO FREQUENTE) CONFIGURAZIONE PERCORSI (Adattata alla tua lista esistente)
# ------------------------------------------------------------------------------

# Percorso base del progetto (Fisso)
BASE_PROJECT_DIR = r"C:\Progetti\simulatore-calcio-backend"

# Qui definisco le variabili ESATTAMENTE con i nomi che usi nella lista sotto.
# Così non devi cambiare nulla nella lista.

FREQUENT_DIR = os.path.join(BASE_PROJECT_DIR, "ai_engine", "Aggiornamenti", "frequenti")

CALCULATORS_DIR = os.path.join(BASE_PROJECT_DIR, "ai_engine", "calculators")

FP_CALCULATORS_DIR = os.path.join(BASE_PROJECT_DIR, "functions_python", "ai_engine", "calculators")

# (Questa serve solo se qualche funzione vecchia la usa ancora)
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------------------
# LISTA DEI TASK (Sequenza precisa 1-13)
# Formato: (Nome_File, Titolo_Display, Spiegazione_Impatto, Cartella_Opzionale)
# ------------------------------------------------------------------------------

SCRAPER_SEQUENCE = [

      # ( FA GLI AGGIORNAMENTI PER LE COPPE EUROPEE )
      ("update_cups_data.py", "🥇 [1/22] Classifica Coppa Europea", "Mancano i dati delle coppe europee", FREQUENT_DIR),

      # ( FA AGGIORNAMENTO STAGIONALE MEDIE GOL CAMPIONATI )
      ("aggiorna_media_gol_partita_tutti_campionati.py", "📊 [2/22] Media Gol Partita (Campionati)", "Mancano media gol per campionato", FREQUENT_DIR),

      ("scraper_results_fbref.py", "📊 [3/22] Risultati & xG (FBref)", "Mancano risultati recenti e xG", FREQUENT_DIR),

      ("scrape_lucifero_betexplorer_safe.py", "🔥 [4/22] Affidabilità squadre (BetExplorer)", "Affidabilità assente", FREQUENT_DIR),


      ("scraper_soccerstats_ranking_unified.py", "🏆 [5/22] Classifica & Gol", "Calcolo Forza Attacco/Difesa sballato", FREQUENT_DIR),

      ("fbref_scraper_att.py", "⚽ [6/22] Stats Attaccanti", "Analisi attacco imprecisa", FREQUENT_DIR),
      ("fbref_scraper_mid.py", "🧠 [7/22] Stats Centrocampisti", "Analisi centrocampo imprecisa", FREQUENT_DIR),
      ("fbref_scraper_def.py", "🛡️ [8/22] Stats Difensori", "Analisi difesa imprecisa", FREQUENT_DIR),
      ("scraper_gk_fbref.py", "🧤 [9/22] Stats Portieri", "Analisi portieri imprecisa", FREQUENT_DIR),

      # ⚠️ DISABILITATO (2026-02-09): impiega ~116 min e scrive solo in players_availability_tm
      # che al momento NON viene letta da nessun file di produzione (né calculators, né frontend).
      # Riabilitare quando verrà integrata nei pronostici.
      # ("scraper_tm_multi_campionato.py", "🚑 [10/22] Infortuni (TM)", "Si rischia di puntare su assenti", FREQUENT_DIR),
      ("scraper_calendario_h2h_TF_completo.py", "📅 [11/22] Calendario H2H", "Analisi scontri diretti incompleta", FREQUENT_DIR),

      # ⭐ ( FA AGGIORNAMENTO ORARI E DATE )
      ("scraper_date_orari_nowgoal.py", "📅 [12/22] Date & Orari (NowGoal)", "Date e orari potrebbero essere sbagliati", FREQUENT_DIR),

      # ⭐ Questo sta nella cartella calculators
      ("calculate_h2h_v2.py", "🧠 [13/22] Elaborazione H2H Pro", "Mancano medie gol e punteggi storici", CALCULATORS_DIR),



      # ⭐ NUOVO SCRIPT AGGIUNTO QUI ALLA FINE NELLA CARTELLA FREQUENTI
      ("nowgoal_scraper.py", "🚀 [14/22] Quote H2H Arricchite (NowGoal)", "Mancano le quote precise nel CSV", FREQUENT_DIR),

      # ⭐ NUOVO SCRIPT DI DEBUG PER FIX MATCHING QUOTE NOWGOAL
      ("nowgoal_scraper_single.py", "🚀 [15/22] Fix Quote H2H Debug (NowGoal)", "Mancano le quote precise nel CSV", FREQUENT_DIR),

      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE SOLO IL LUCIFERO
      ("cron_update_lucifero.py", "🔥 [16/22] Aggiorna Solo Lucifero (Debug)", "Aggiorna solo il punteggio Lucifero", FREQUENT_DIR),

      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE SOLO IL BVS
      ("db_updater_bvs.py", "💎 [17/22] Aggiorna Solo BVS (Debug)", "Aggiorna solo il punteggio BVS", FREQUENT_DIR),

      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE SOLO LE CLASSIFICHE
      ("scraper_classifiche_standings.py", "🏆 [18/22] Aggiorna Solo Classifiche (Debug)", "Aggiorna solo le classifiche", FREQUENT_DIR),

      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE IL DNA System (ATT/DEF/TEC/VAL) e le FORMAZIONI
      ("run_all_injectors.py", "🎩 [19/22] Aggiorna DNA System Completo (Debug)", "Aggiorna ATT/DEF/TEC/VAL e FORMAZIONI", FREQUENT_DIR),

      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE IL FATT. CAMPO
      ("update_fattore_campo.py", "🏟️ [20/22] Aggiorna Fattore Campo (Debug)", "Aggiorna il fattore campo per tutte le partite", FREQUENT_DIR),

      # NUOVO SCRIPT DI DEBUG PER AGGIORNARE L'AFFIDABILITÀ
      ("update_affidabilità.py", "🔥 [21/22] Aggiorna Affidabilità (Debug)", "Aggiorna l'affidabilità delle squadre", FREQUENT_DIR),

      # ⭐ NUOVO SCRIPT DI DEBUG PER AGGIORNARE SOLO I RISULTATI
      ("per_agg_pianificato_update_results_only.py", "🔄 [22/23] Aggiorna Solo Risultati (Debug)", "Aggiorna solo i risultati senza toccare altro", FREQUENT_DIR),

      # ⭐ SCRAPER QUOTE O/U + GG/NG DA SNAI (Selenium)
      ("scrape_snai_odds.py", "🎰 [23/27] Quote O/U + GG/NG (SNAI)", "Mancano quote Over/Under e Goal/NoGoal", FREQUENT_DIR),

      # ⭐ SCRAPER H2H SPORTRADAR PER COPPE UCL/UEL (se ci sono partite coppa oggi, altrimenti skip)
      ("scrape_sportradar_h2h.py", "⚽ [24/27] H2H Sportradar Coppe", "Mancano dati H2H Sportradar per partite coppa", FREQUENT_DIR),

      # ⭐ GENERAZIONE PRONOSTICI GIORNALIERI (DEVE girare DOPO tutti gli aggiornamenti dati + quote)
      ("run_daily_predictions.py", "🔮 [25/29] Pronostici Giornalieri", "Pronostici non generati o con quote mancanti", FP_CALCULATORS_DIR),

      # ⭐ SYNC QUOTE SNAI → SANDBOX (recupera quote mancanti da h2h_by_round + produzione)
      ("sync_snai_odds_to_sandbox.py", "🧪 [26/31] Sync Quote SNAI → Sandbox", "Sandbox potrebbe avere quote SNAI mancanti", CURRENT_DIR),

      # ⭐ SISTEMA S — PRONOSTICI SANDBOX (stessi algoritmi di A, con tuning separato)
      ("run_daily_predictions_sandbox.py", "🧪 [27/31] Pronostici Sandbox", "Pronostici sandbox non generati", FP_CALCULATORS_DIR),

      # ⭐ REPORT TRACK RECORD (genera JSON + TXT con statistiche pronostici vs risultati)
      ("generate_track_record_report.py", "📊 [28/31] Report Track Record", "Report statistiche non generato", CURRENT_DIR),

      # ⭐ CALCOLO PROFIT/LOSS post-match (aggiorna esito + P/L per ogni pronostico)
      ("calculate_profit_loss.py", "💰 [29/31] Calcolo Profit/Loss", "Profit/loss non calcolati per pronostici passati", CURRENT_DIR),

      # ⭐ SISTEMA C — PRONOSTICI MONTE CARLO (100 cicli, Master mode 5, collection separata)
      ("run_daily_predictions_engine_c.py", "🎲 [30/31] Pronostici Sistema C (MC)", "Pronostici Monte Carlo non generati", FP_CALCULATORS_DIR),

      # ⭐ MIXTURE OF EXPERTS — Orchestratore (legge A+C+S, applica routing, scrive in unified)
      ("orchestrate_experts.py", "🎼 [31/32] Orchestrazione MoE", "Pronostici unified non generati", FP_CALCULATORS_DIR),

      # ⭐ ANALISI MATCH — Genera analisi free per ogni pronostico unified (22 checker contraddizioni)
      ("generate_match_analysis.py", "🔍 [32/32] Analisi Match (contraddizioni)", "Analisi match non generate", FP_CALCULATORS_DIR),
]


# ------------------------------------------------------------------------------
# FUNZIONI DI SERVIZIO
# ------------------------------------------------------------------------------

def run_single_script(filename, description, folder_path):
    # Costruiamo il path completo
    full_path = os.path.join(folder_path, filename)
    print("\n" + "-"*70)
    print(f"▶ {description}")
    
    # Controllo esistenza file
    if not os.path.exists(full_path):
        print(f"❌ Errore: File non trovato in {full_path}")
        return False, "File non trovato", 0.0

    start_time = time.time()
    
    try:
        # --- SETUP AMBIENTE UTF-8 ---
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        # ----------------------------

        # Costruzione del comando base
        cmd = [sys.executable, full_path]
        
        # SBLOCCO AUTOMATICO: Se è il calcolatore H2H, passiamo "all" per saltare il menu
        if filename == "calculate_h2h_v2.py":
            cmd.append("all")

        # Esecuzione script
        subprocess.run(
            cmd, 
            check=True, 
            capture_output=False, 
            text=True, 
            encoding='utf-8', 
            errors='replace',
            env=env
        )
        
        elapsed = time.time() - start_time
        print(f"   ✅ COMPLETATO in {elapsed:.2f}s")
        return True, None, elapsed
        
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start_time
        print("   🔴 ERRORE SCRIPT (Vedi output sopra)")
        return False, "Script fallito (Exit Code != 0)", elapsed
        
    except Exception as e:
        return False, str(e), 0.0


def main():
    print("\n" + "="*80)
    print("🎩 DIRETTORE D'ORCHESTRA 3.3: CON CRONOMETRO & DIAGNOSTICA")
    print("="*80)

    # Cleanup Chrome zombie prima di iniziare
    print("\n🧹 Pulizia Chrome zombie...")
    kill_chrome_zombies()

    report = []
    total_start_time = time.time() # Start Cronometro Globale

    # Script da eseguire in parallelo (stessa fonte fbref.com, indipendenti tra loro)
    PARALLEL_FBREF = {"fbref_scraper_att.py", "fbref_scraper_mid.py", "fbref_scraper_def.py", "scraper_gk_fbref.py"}
    # SNAI scraper: 3 istanze parallele, ognuna processa 1/3 delle leghe
    PARALLEL_SNAI = "scrape_snai_odds.py"
    SNAI_NUM_GROUPS = 3

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'log')
    os.makedirs(log_dir, exist_ok=True)

    i = 0
    while i < len(SCRAPER_SEQUENCE):
        filename, desc, impact, folder = SCRAPER_SEQUENCE[i]

        # --- GRUPPO PARALLELO FBREF ---
        if filename in PARALLEL_FBREF:
            parallel_tasks = []
            while i < len(SCRAPER_SEQUENCE) and SCRAPER_SEQUENCE[i][0] in PARALLEL_FBREF:
                parallel_tasks.append(SCRAPER_SEQUENCE[i])
                i += 1

            print(f"\n🔀 LANCIO PARALLELO: {len(parallel_tasks)} fbref scrapers contemporanei")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            processes = []
            log_files = []
            base_port = 9222
            for idx, (pf, pd, pi, pfolder) in enumerate(parallel_tasks):
                full_path = os.path.join(pfolder, pf)
                print(f"   🚀 Avvio: {pf} (porta Chrome: {base_port + idx})")
                p_start = time.time()
                proc_env = env.copy()
                proc_env["CHROME_DEBUG_PORT"] = str(base_port + idx)
                log_path = os.path.join(log_dir, f"fbref_{pf.replace('.py','')}.txt")
                lf = open(log_path, 'w', encoding='utf-8')
                log_files.append(lf)
                proc = subprocess.Popen(
                    [sys.executable, full_path],
                    env=proc_env,
                    stdout=lf,
                    stderr=lf
                )
                processes.append((pf, pd, pi, pfolder, proc, p_start))

            print(f"   ⏳ Attendo completamento di tutti e {len(processes)}...")
            for pf, pd, pi, pfolder, proc, p_start in processes:
                proc.wait()
                elapsed = time.time() - p_start
                ok = (proc.returncode == 0)
                err_msg = None if ok else f"Exit code {proc.returncode}"
                print(f"   {'✅' if ok else '❌'} {pf} completato in {elapsed/60:.1f}min")
                report.append({
                    "file": pf,
                    "status": "✅ OK" if ok else "❌ KO",
                    "error": err_msg,
                    "impact": pi,
                    "folder": pfolder,
                    "duration": elapsed
                })

            for lf in log_files:
                lf.close()
            print(f"🔀 GRUPPO PARALLELO FBREF COMPLETATO")
            time.sleep(2)

        # --- GRUPPO PARALLELO SNAI (3 istanze, 1/3 leghe ciascuna) ---
        elif filename == PARALLEL_SNAI:
            i += 1
            full_path = os.path.join(folder, filename)
            print(f"\n🔀 LANCIO PARALLELO: {SNAI_NUM_GROUPS} istanze SNAI (8 leghe ciascuna)")

            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            processes = []
            log_files = []
            group_start = time.time()

            for grp in range(SNAI_NUM_GROUPS):
                print(f"   🚀 Avvio: SNAI gruppo {grp}")
                proc_env = env.copy()
                proc_env["SNAI_LEAGUE_GROUP"] = str(grp)
                log_path = os.path.join(log_dir, f"snai_group_{grp}.txt")
                lf = open(log_path, 'w', encoding='utf-8')
                log_files.append(lf)
                proc = subprocess.Popen(
                    [sys.executable, full_path],
                    env=proc_env,
                    stdout=lf,
                    stderr=lf
                )
                processes.append((f"snai_group_{grp}", desc, impact, folder, proc, time.time()))
                # Sfasa di 5s per non colpire snai.it simultaneamente
                if grp < SNAI_NUM_GROUPS - 1:
                    time.sleep(5)

            print(f"   ⏳ Attendo completamento di tutti e {len(processes)} gruppi SNAI...")
            for pf, pd, pi, pfolder, proc, p_start in processes:
                proc.wait()
                elapsed = time.time() - p_start
                ok = (proc.returncode == 0)
                err_msg = None if ok else f"Exit code {proc.returncode}"
                print(f"   {'✅' if ok else '❌'} {pf} completato in {elapsed/60:.1f}min")

            total_snai_elapsed = time.time() - group_start
            # Un solo record nel report per l'intero gruppo SNAI
            all_ok = all(proc.returncode == 0 for _, _, _, _, proc, _ in processes)
            report.append({
                "file": f"{filename} (x{SNAI_NUM_GROUPS} parallelo)",
                "status": "✅ OK" if all_ok else "❌ KO",
                "error": None if all_ok else "Uno o più gruppi falliti",
                "impact": impact,
                "folder": folder,
                "duration": total_snai_elapsed
            })

            for lf in log_files:
                lf.close()
            print(f"🔀 GRUPPO PARALLELO SNAI COMPLETATO in {total_snai_elapsed/60:.1f}min")
            time.sleep(2)

        else:
            # Esecuzione sequenziale normale
            ok, err_msg, duration = run_single_script(filename, desc, folder)
            report.append({
                "file": filename,
                "status": "✅ OK" if ok else "❌ KO",
                "error": err_msg,
                "impact": impact,
                "folder": folder,
                "duration": duration
            })
            if ok: time.sleep(2)
            i += 1

    total_duration_sec = time.time() - total_start_time
    total_duration_str = str(timedelta(seconds=int(total_duration_sec))) # Converte in HH:MM:SS

    # --- REPORT FINALE ---
    print("\n\n" + "="*100)
    print(f"📊 REPORT AGGIORNAMENTO - DURATA TOTALE: {total_duration_str}")
    print("="*100)
    print(f"{'STATO':<6} | {'DURATA':<10} | {'FILE (Script)':<35} | {'IMPATTO (Se fallisce)'}")
    print("-" * 100)

    failures = []
    for item in report:
        dur_min = item['duration'] / 60
        dur_str = f"{dur_min:.1f}min"
        print(f"{item['status']:<6} | {dur_str:<10} | {item['file']:<35} | {item['impact']}")
        if item['status'] == "❌ KO":
            failures.append(item)


    # --- DETTAGLIO ERRORI E SOLUZIONI ---
    if failures:
        print("\n" + "="*90)
        print("⚠️  ANALISI FALLIMENTI & SOLUZIONI")
        print("="*90)
        for fail in failures:
            try:
                rel_path = os.path.relpath(os.path.join(fail['folder'], fail['file']), BASE_PROJECT_DIR)
            except ValueError:
                rel_path = os.path.join(fail['folder'], fail['file'])

            print(f"🔴 {fail['file']}")
            print(f"   └─ Errore: {fail['error']}")
            print(f"   └─ Conseguenza: {fail['impact']}")
            print(f"   └─ 🔧 SOLUZIONE RAPIDA: Copia e lancia questo comando:")
            print(f"      python {rel_path}")
            print("-" * 60)
            
        print("\n❌ L'aggiornamento ha avuto dei problemi. Controlla i comandi sopra.")
    else:
        print(f"\n✨ SISTEMA PERFETTAMENTE AGGIORNATO IN {total_duration_str}!")

    # Cleanup Chrome zombie alla fine
    print("\n🧹 Pulizia Chrome finale...")
    kill_chrome_zombies()

    # Report mensile — solo il primo del mese
    from datetime import datetime as _dt
    if _dt.now().day == 1:
        print("\n📊 Primo del mese — lancio report mensile automatico...")
        try:
            report_script = os.path.join(r"C:\Progetti", "report_mensile_auto.py")
            report_result = subprocess.run(
                [sys.executable, report_script],
                cwd=r"C:\Progetti",
                capture_output=True, text=True, timeout=900
            )
            if report_result.returncode == 0:
                print("   ✅ Report mensile completato!")
            else:
                print(f"   ❌ Report mensile fallito: {report_result.stderr[:300]}")
            if report_result.stdout:
                for line in report_result.stdout.strip().split('\n')[-5:]:
                    print(f"   {line}")
        except Exception as e:
            print(f"   ❌ Report mensile errore: {e}")

    print("\n")


if __name__ == "__main__":
    main()
