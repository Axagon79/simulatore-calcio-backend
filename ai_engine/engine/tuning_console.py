import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PERCORSO_TUNING = os.path.join(BASE_DIR, "tuning_settings.json")

def carica_settaggi():
    with open(PERCORSO_TUNING, "r", encoding="utf-8") as f:
        return json.load(f)

def salva_settaggi(data):
    with open(PERCORSO_TUNING, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def reset_default():
    data = carica_settaggi()
    # mappa chiave -> valore di default
    default_valori = {
        "PESO_RATING_ROSA": 1.0,
        "PESO_FORMA_RECENTE": 1.0,
        "PESO_MOTIVAZIONE": 1.0,
        "PESO_FATTORE_CAMPO": 1.0,
        "PESO_STORIA_H2H": 1.0,
        "PESO_BVS_QUOTE": 1.0,
        "PESO_AFFIDABILITA": 1.0,
        "PESO_VALORE_ROSA": 1.0,
        "DIVISORE_MEDIA_GOL": 2.0,
        "POTENZA_FAVORITA_WINSHIFT": 0.40,
        "IMPATTO_DIFESA_TATTICA": 15.0,
        "TETTO_MAX_GOL_ATTESI": 3.8
    }
    for k, v in default_valori.items():
        if k in data:
            data[k]["valore"] = v
    salva_settaggi(data)
    print("🔁 Tutte le manopole riportate ai valori di default.")

def console_interattiva():
    data = carica_settaggi()
    print("\n🎛️ MIXER TUNING – Valori attuali:\n")
    for chiave, info in data.items():
        print(f"- {chiave}: {info['valore']}  ({info['descrizione']})")

    print("\nLascia vuoto per non cambiare una manopola.\n")

    for chiave, info in data.items():
        attuale = info["valore"]
        nuovo = input(f"{chiave} [{attuale}] = ").strip()
        if nuovo == "":
            continue
        try:
            info["valore"] = float(nuovo)
        except ValueError:
            print("  ⚠️ Valore non valido, mantengo il precedente.")

    salva = input("\nVuoi salvare questi settaggi? (s/N) ").strip().lower()
    if salva == "s":
        salva_settaggi(data)
        print("💾 Settaggi salvati.")
    else:
        print("❌ Modifiche annullate (nulla salvato).")

if __name__ == "__main__":
    print("1) Modifica manopole")
    print("2) Ripristina valori di default")
    scelta = input("Scelta: ").strip()
    if scelta == "2":
        reset_default()
    else:
        console_interattiva()
