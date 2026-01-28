import os

# Percorso cartella principale
FOLDER = r'C:\Progetti\simulatore-calcio-frontend\squadre'

def rinomina_stemmi():
    print("🚀 Rinomina stemmi: rimuovo i nomi tra parentesi...\n")
    
    totale = 0
    rinominati = 0
    
    # Scorri tutte le sottocartelle
    for root, dirs, files in os.walk(FOLDER):
        for filename in files:
            if not filename.endswith('.png'):
                continue
            
            totale += 1
            
            # Se ha le parentesi, rinomina
            if '(' in filename and ')' in filename:
                # Estrai solo l'ID (tutto prima della parentesi)
                nuovo_nome = filename.split('(')[0].strip() + '.png'
                
                old_path = os.path.join(root, filename)
                new_path = os.path.join(root, nuovo_nome)
                
                # Evita sovrascritture
                if os.path.exists(new_path):
                    print(f"⚠️  Già esiste: {nuovo_nome}")
                    continue
                
                os.rename(old_path, new_path)
                rinominati += 1
                
                # Mostra cartella relativa per chiarezza
                cartella = os.path.basename(root)
                print(f"✅ {cartella}: {filename} → {nuovo_nome}")
    
    print(f"\n{'='*50}")
    print(f"📊 Riepilogo:")
    print(f"   📁 File totali: {totale}")
    print(f"   ✅ Rinominati: {rinominati}")
    print(f"   ⏭️  Già ok: {totale - rinominati}")
    print(f"{'='*50}")

if __name__ == "__main__":
    rinomina_stemmi()