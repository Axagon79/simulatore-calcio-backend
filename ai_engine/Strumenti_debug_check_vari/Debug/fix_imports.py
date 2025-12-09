import os


#(** SCRIPT DI EMERGENZA PER CORREGGERE GLI ERRORI DI IMPORTAZIONE DEI MODULI PYTHON )
#( AGGIUNGE AUTOMATICAMENTE LE CARTELLE 'AI_ENGINE' E 'ENGINE' AL PERCORSO DI SISTEMA )
#( VERIFICA LA PRESENZA DEI FILE ESSENZIALI PRIMA DI AVVIARE GLI ALTRI SCRIPT **)


# Cartella target
TARGET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Aggiornamenti", "frequenti")

# Il blocco di codice magico da inserire
NEW_BLOCK = """import os
import sys

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db
"""

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Se il file ha già il fix, saltiamo
    if "# --- FIX PERCORSI UNIVERSALE ---" in content:
        print(f"⏭️  Già fixato: {os.path.basename(filepath)}")
        return

    # Strategia: Cerchiamo "from config import db" e tutto quello che c'è prima
    # Spesso è:
    # sys.path.append(...)
    # from config import db
    
    lines = content.splitlines()
    new_lines = []
    
    found_config = False
    for line in lines:
        # Rimuoviamo le vecchie righe di path
        if "sys.path.append" in line and "os.path.dirname" in line:
            continue
        if "from config import db" in line:
            # Al posto di questa riga, inseriamo tutto il blocco nuovo
            new_lines.append(NEW_BLOCK)
            found_config = True
        else:
            new_lines.append(line)

    if found_config:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(new_lines))
        print(f"✅ FIXATO: {os.path.basename(filepath)}")
    else:
        print(f"⚠️  Non ho trovato 'from config import db' in {os.path.basename(filepath)}")

def main():
    print(f"🛠️  Avvio FIX IMPORT automatico in: {TARGET_DIR}")
    if not os.path.exists(TARGET_DIR):
        print("❌ Cartella non trovata!")
        return

    for filename in os.listdir(TARGET_DIR):
        if filename.endswith(".py") and filename != "__init__.py":
            fix_file(os.path.join(TARGET_DIR, filename))

    print("\n🏁 Finito. Ora lancia update_manager.py!")

if __name__ == "__main__":
    main()
