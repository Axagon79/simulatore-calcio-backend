import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from config import db

#!/usr/bin/env python3
"""
Script per esplorare completamente il database MongoDB
Esegui: python scan_full_database.py
"""

from pprint import pprint
from datetime import datetime


def main():
    try:
        print("🔌 Connessione al cluster MongoDB...")

        # Test connessione
        client.admin.command('ping')
        print("✅ Connessione riuscita!\n")
        print("="*80)

        # Lista tutti i database
        db_list = client.list_database_names()
        print(f"\n📊 DATABASE TROVATI ({len(db_list)}):")
        print("-"*80)
        for db_name in db_list:
            print(f"  - {db_name}")

        print("\n" + "="*80)

        # Per ogni database, analizza le collezioni
        report = []

        for db_name in db_list:
            # Salta database di sistema
            if db_name in ['admin', 'local', 'config']:
                continue

            collections = db.list_collection_names()

            print(f"\n🗄️  DATABASE: {db_name}")
            print("="*80)
            print(f"Collezioni trovate: {len(collections)}\n")

            db_info = {
                "database": db_name,
                "collections": []
            }

            for coll_name in collections:
                coll = db[coll_name]
                count = coll.count_documents({})

                coll_info = {
                    "name": coll_name,
                    "count": count,
                    "fields": []
                }

                print(f"  📁 {coll_name:<35} | Documenti: {count:>6}")

                # Mostra un documento di esempio (se esistono)
                if count > 0:
                    sample = coll.find_one()
                    print(f"     └─ Struttura documento:")

                    if sample:
                        for key in sample.keys():
                            value = sample[key]
                            value_type = type(value).__name__

                            # Preview del valore
                            if isinstance(value, (str, int, float, bool)):
                                value_preview = str(value)[:50]
                            elif isinstance(value, dict):
                                value_preview = f"{{...}} ({len(value)} keys)"
                            elif isinstance(value, list):
                                value_preview = f"[...] ({len(value)} items)"
                            else:
                                value_preview = str(value)[:30]

                            print(f"        • {key:<25} ({value_type:<10}): {value_preview}")

                            coll_info["fields"].append({
                                "field": key,
                                "type": value_type,
                                "preview": value_preview
                            })

                    print()

                db_info["collections"].append(coll_info)

            report.append(db_info)
            print("-"*80)

        # Genera un report testuale
        print("\n\n📝 REPORT RIASSUNTIVO")
        print("="*80)

        for db_info in report:
            print(f"\n🗄️  {db_info['database']}")
            total_docs = sum(c['count'] for c in db_info['collections'])
            print(f"   Total documenti: {total_docs}")
            print(f"   Collezioni:")

            for coll in db_info['collections']:
                print(f"     • {coll['name']:<30} ({coll['count']} docs)")

        print("\n" + "="*80)
        print("\n💡 ANALISI:")
        print("-"*80)

        # Identifica database del social vs simulatore
        for db_info in report:
            db_name = db_info['database']
            collections = [c['name'] for c in db_info['collections']]

            # Cerca indizi del tipo di database
            social_keywords = ['user', 'post', 'comment', 'like', 'follow', 'pet', 'animal']
            football_keywords = ['team', 'match', 'player', 'league', 'fixture']

            social_score = sum(1 for kw in social_keywords if any(kw in c.lower() for c in collections))
            football_score = sum(1 for kw in football_keywords if any(kw in c.lower() for c in collections))

            if social_score > football_score:
                print(f"\n🐾 {db_name} → Probabilmente SOCIAL NETWORK (vecchio progetto)")
                print(f"   Collezioni sospette: {', '.join(collections)}")
            elif football_score > 0:
                print(f"\n⚽ {db_name} → Probabilmente SIMULATORE CALCIO (progetto attuale)")
                print(f"   Collezioni rilevanti: {', '.join(collections)}")
            else:
                print(f"\n❓ {db_name} → Non chiaro")

        print("\n" + "="*80)
        print(f"\n✅ Scansione completata - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        client.close()

    except pymongo.errors.ServerSelectionTimeoutError:
        print("❌ ERRORE: Impossibile connettersi al server MongoDB")
        print("   • Verifica la connection string")
        print("   • Controlla la connessione internet")
        print("   • Verifica che l'IP sia nella whitelist di MongoDB Atlas")
    except Exception as e:
        print(f"❌ ERRORE: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()