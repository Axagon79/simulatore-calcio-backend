"""Step pipeline notturna: chiama endpoint Node per processare refund shield."""
import os
import sys
import urllib.request
import json

API_BASE = "https://api-6b34yfzjia-uc.a.run.app"

def main():
    print("\n" + "="*60)
    print("Process Shield Refunds — chiamata endpoint Node")
    print("="*60)
    url = f"{API_BASE}/wallet/process-shield-refunds"
    try:
        req = urllib.request.Request(url, method='POST', headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=300) as response:
            data = json.loads(response.read())
            print(f"OK — refunds elaborati: {data.get('processed', 0)}")
            print(f"Crediti rimborsati totali: {data.get('credits_refunded', 0)}")
            if data.get('errors'):
                print(f"WARNING: {len(data['errors'])} errori")
                for e in data['errors'][:5]:
                    print(f"  - {e}")
    except Exception as e:
        print(f"ERRORE chiamata endpoint: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
