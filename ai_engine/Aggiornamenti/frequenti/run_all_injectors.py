import os
import sys
import time
import importlib

# 1. CONFIGURAZIONE PERCORSI
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
# Risaliamo alla root del progetto
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(CURRENT_DIR)))
CALCULATORS_PATH = os.path.join(PROJECT_ROOT, "ai_engine", "calculators")

# Aggiungiamo i percorsi per trovare i moduli
sys.path.append(CURRENT_DIR)
sys.path.append(PROJECT_ROOT)
sys.path.append(CALCULATORS_PATH)

from config import db

DRY_RUN = False  # Se True, solo download + calcolo, nessuna scrittura DB


def load_targeted_rounds():
    """
    Scarica i round target (prec/attuale/succ) UNA SOLA VOLTA.
    Restituisce la lista di documenti h2h_by_round completi.
    """
    from injector_dna_tec_e_formazioni import find_target_rounds

    h2h_col = db["h2h_by_round"]

    print("   📥 Fase 1: selezione round (query leggera)...")
    light_docs = list(h2h_col.find({}, {"_id": 1, "league": 1, "matches.date": 1, "matches.date_obj": 1}))
    by_league = {}
    for doc in light_docs:
        lg = doc.get("league")
        if lg:
            by_league.setdefault(lg, []).append(doc)

    target_ids = []
    for lg_name, lg_docs in by_league.items():
        target = find_target_rounds(lg_docs, league_name=lg_name)
        target_ids.extend([d["_id"] for d in target])

    print(f"   📥 Fase 2: caricamento {len(target_ids)} round completi...")
    rounds = list(h2h_col.find({"_id": {"$in": target_ids}}))
    print(f"   📋 {len(by_league)} campionati → {len(rounds)} giornate mirate")
    return rounds


def run_all():
    start_time = time.time()
    print(f"\n{'='*70}")
    print(f"🎻 DIRETTORE D'ORCHESTRA - AVVIO AUTOMAZIONE DNA SYSTEM")
    print(f"📅 Data: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    try:
        # --- DOWNLOAD ROUND UNA SOLA VOLTA ---
        print("\n📦 Caricamento round condiviso (1 download per tutti gli injectors)...")
        shared_rounds = load_targeted_rounds()

        # --- FASE 1: ATTACCO E DIFESA ---
        print("\n🔹 [1/4] Caricamento 'injector_att_def_dna'...")
        try:
            inj_att_def = importlib.import_module("injector_att_def_dna")

            if hasattr(inj_att_def, 'run_injection_att_def'):
                inj_att_def.run_injection_att_def(interactive=False, preloaded_rounds=shared_rounds)
            else:
                if hasattr(inj_att_def, 'run_injection_v3'):
                    inj_att_def.run_injection_v3()

            print("✅ Fase 1 (ATT/DEF) completata.")
        except Exception as e:
            print(f"❌ ERRORE CRITICO FASE 1: {e}")

        # --- FASE 2: TECNICA E FORMAZIONI ---
        print("\n🔹 [2/4] Caricamento 'injector_dna_tec_e_formazioni'...")
        try:
            inj_tec = importlib.import_module("injector_dna_tec_e_formazioni")

            if hasattr(inj_tec, 'run_injection'):
                inj_tec.run_injection(interactive=False, preloaded_rounds=shared_rounds)
            else:
                print("❌ Errore: Funzione 'run_injection' non trovata in injector_dna_tec_e_formazioni.")

            print("✅ Fase 2 (TEC/FORM) completata.")
        except ImportError:
            print(f"❌ ERRORE IMPORT FASE 2: Non trovo il file 'injector_dna_tec_e_formazioni.py'.")
        except Exception as e:
            print(f"❌ ERRORE CRITICO FASE 2: {e}")

        # --- FASE 3: VALORE ROSA ---
        print("\n🔹 [3/4] Caricamento 'injector_dna_val'...")
        try:
            inj_val = importlib.import_module("injector_dna_val")

            if hasattr(inj_val, 'run_injection_val'):
                inj_val.run_injection_val(interactive=False, preloaded_rounds=shared_rounds)
                print("✅ Fase 3 (VAL) completata.")
            else:
                print("⚠️ Funzione 'run_injection_val' non trovata.")
        except ImportError:
            print("⚠️ Modulo 'injector_dna_val' non trovato (saltato).")
        except Exception as e:
            print(f"❌ ERRORE CRITICO FASE 3: {e}")

        # --- FASE 4: FORMAZIONI NO-FBREF (Serie C + Liga Portugal 2 + 1. Lig) ---
        print("\n🔹 [4/4] Formazioni No-FBref (Sportradar)...")
        try:
            from scrape_sportradar_serie_c import scrape_all_teams, inject_formations
            scrape_all_teams()
            inject_formations()
            print("✅ Fase 4 (No-FBref Sportradar) completata.")
        except ImportError:
            print("⚠️ Modulo 'scrape_sportradar_serie_c' non trovato (saltato).")
        except Exception as e:
            print(f"❌ ERRORE FASE 4: {e}")

        # --- RIEPILOGO FINALE ---
        end_time = time.time()
        elapsed = end_time - start_time
        print(f"\n{'='*70}")
        print(f"🏆 SEQUENZA COMPLETATA IN {elapsed:.2f} secondi.")
        print(f"{'='*70}")

    except Exception as e:
        print(f"\n❌ ERRORE GENERALE DI SISTEMA: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_all()
