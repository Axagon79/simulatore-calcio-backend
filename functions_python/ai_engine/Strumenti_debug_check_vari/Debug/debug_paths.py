import os
import sys

# 1. Dove sono io?
current_script = os.path.abspath(__file__)
current_dir = os.path.dirname(current_script)

print(f"📍 SCRIPT PATH: {current_script}")
print(f"📂 CARTELLA CORRENTE: {current_dir}")

# 2. Cosa c'è in questa cartella?
print("\n📜 FILE NELLA CARTELLA 'ai_engine':")
try:
    files = os.listdir(current_dir)
    found_engine = False
    for f in files:
        if "engine_core" in f:
            print(f"   ✅ TROVATO: {f}")
            found_engine = True
        else:
            print(f"   - {f}")
            
    if not found_engine:
        print("\n❌ ATTENZIONE: 'engine_core.py' NON È QUI!")
        print("   Devi spostarlo dalla cartella 'ai_engine/engine' (o altrove) a qui.")
except Exception as e:
    print(f"Errore lettura cartella: {e}")

# 3. Test Importazione
print("\n🧪 TENTATIVO IMPORTAZIONE:")
sys.path.insert(0, current_dir)
try:
    import engine_core
    print("✅ SUCCESS: Import 'engine_core' riuscito!")
except ImportError as e:
    print(f"❌ FAIL: {e}")
