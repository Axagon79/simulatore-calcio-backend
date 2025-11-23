import os
from pymongo import MongoClient
from dotenv import load_dotenv

# Carica variabili ambiente
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'functions', '.env')
load_dotenv(dotenv_path)
mongo_uri = os.getenv('MONGO_URI')

try:
    client = MongoClient(mongo_uri)
    db = client.get_database()
    
    # CANCELLA TUTTE LE SQUADRE
    result = db.teams.delete_many({})
    
    print(f"🗑️  Cancellate {result.deleted_count} squadre dal database.")
    print("✨ Il database ora è pulito.")

except Exception as e:
    print(f"❌ Errore: {e}")
finally:
    client.close()
