import os
import sys
from config import db  # Assicurati che config sia nel path

# --- CONFIGURAZIONE ---
rankings_collection = db['classifiche']

def remove_team_id_field():
    print("🧹 AVVIO PULIZIA: Rimozione del campo 'team_id' dalle classifiche...")
    
    try:
        # L'operazione deve agire su ogni elemento dell'array 'table'
        # Usiamo il posizionale '$[]' per colpire tutti gli oggetti dentro l'array
        result = rankings_collection.update_many(
            {}, 
            {"$unset": {"table.$[].team_id": ""}}
        )
        
        print(f"✅ OPERAZIONE COMPLETATA")
        print(f"📊 Documenti (campionati) modificati: {result.modified_count}")
        print(f"💡 Il campo 'team_id' è stato rimosso da tutte le squadre.")

    except Exception as e:
        print(f"❌ Errore durante la pulizia: {e}")

if __name__ == "__main__":
    # Chiediamo conferma prima di procedere dato che è un'azione distruttiva
    conferma = input("⚠️ Sei sicuro di voler cancellare 'team_id' da tutte le classifiche? (s/n): ")
    if conferma.lower() == 's':
        remove_team_id_field()
    else:
        print("Operazione annullata.")