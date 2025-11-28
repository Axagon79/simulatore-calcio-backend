import pymongo

# sorgente: Mongo locale
LOCAL_URI = "mongodb://localhost:27017/"
local_client = pymongo.MongoClient(LOCAL_URI)
local_db = local_client["simulatore_calcio"]
local_coll = local_db["players_availability_tm"]

# destinazione: tuo cluster online
REMOTE_URI = "mongodb+srv://Database_User:LPmYAZkzEVxjSaAd@pup-pals-cluster.y1h2r.mongodb.net/pup_pals_db?retryWrites=true&w=majority"
remote_client = pymongo.MongoClient(REMOTE_URI)
remote_db = remote_client["pup_pals_db"]
remote_coll = remote_db["players_availability_tm"]

def main():
    batch_size = 1000

    total = local_coll.count_documents({})
    print(f"Documenti totali da copiare: {total}")

    cursor = local_coll.find({})
    buffer_docs = []
    copied = 0

    for doc in cursor:
        # rimuovi l'_id locale per farlo rigenerare nel cluster
        doc.pop("_id", None)
        buffer_docs.append(doc)

        if len(buffer_docs) >= batch_size:
            remote_coll.insert_many(buffer_docs, ordered=False)
            copied += len(buffer_docs)
            print(f"Copiati finora: {copied}/{total}")
            buffer_docs = []

    if buffer_docs:
        remote_coll.insert_many(buffer_docs, ordered=False)
        copied += len(buffer_docs)
        print(f"Copiati finora: {copied}/{total}")

    print("✅ Copia completata.")

if __name__ == "__main__":
    main()
