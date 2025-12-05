from pymongo import MongoClient

print("Tentativo 1: localhost...")
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    print(client.server_info()['version'])
    print("✅ Connesso con localhost!")
except Exception as e:
    print(f"❌ Fallito localhost: {e}")

print("\nTentativo 2: 127.0.0.1...")
try:
    client = MongoClient("mongodb://127.0.0.1:27017/", serverSelectionTimeoutMS=2000)
    print(client.server_info()['version'])
    print("✅ Connesso con 127.0.0.1!")
except Exception as e:
    print(f"❌ Fallito 127.0.0.1: {e}")
