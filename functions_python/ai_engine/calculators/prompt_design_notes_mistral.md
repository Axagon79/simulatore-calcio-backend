# Documentazione ufficiale Mistral — Prompting Capabilities
> Fonte: https://docs.mistral.ai/guides/prompting-capabilities/
> Queste indicazioni sono specifiche per il modello Mistral (mistral-medium-2508)

---

## 1. System Prompt e User Prompt

Il **system prompt** viene fornito all'inizio della conversazione. Definisce il contesto generale e le istruzioni per il comportamento del modello ed è in genere gestito dallo sviluppatore.

Il **user prompt** viene fornito durante la conversazione per dare al modello un contesto specifico o istruzioni per l'interazione in corso.

Come sviluppatore, puoi comunque utilizzare user prompt per fornire contesto o istruzioni aggiuntive durante la conversazione, se necessario.

```json
{
    "role": "system",
    "content": "system_prompt"
},
{
    "role": "user",
    "content": "user_prompt"   
}
```

> **Per noi**: noi già facciamo così — regole nel system, dati + istruzioni fascia nel user. Corretto.

---

## 2. Fornire uno scopo

Chiamato anche gioco di ruolo, è il primo passo nella creazione di un prompt e corrisponde alla definizione di uno **scopo chiaro**. Un approccio comune è quello di iniziare con una definizione concisa di ruolo e compito, ad esempio:

*"Tu sei un \<ruolo\>, il tuo compito è \<compito\>."*

Questa tecnica semplice ma efficace aiuta a indirizzare il modello verso un ambito e un compito specifici, assicurando che comprenda rapidamente il contesto e il risultato atteso.

> **Per noi**: una riga sola. "Sei un tipster professionista con esperienza trentennale nelle scommesse calcistiche. Il tuo compito è scegliere, da una selezione di partite, quelle giuste per comporre bollette vincenti."

---

## 3. Struttura

Quando si forniscono istruzioni, è importante **organizzarle gerarchicamente o con una struttura chiara**, ad esempio suddividendole in sezioni e sottosezioni distinte. La richiesta deve essere **chiara e completa**.

Una regola pratica utile è immaginare di scrivere per qualcuno che non ha alcuna conoscenza pregressa: questa persona dovrebbe essere in grado di comprendere ed eseguire il compito semplicemente leggendo la richiesta.

Esempio di una richiesta ben strutturata:
```
Sei un modello di rilevamento lingua, il tuo compito è rilevare la lingua del testo fornito.

# Lingue disponibili
Seleziona la lingua dalla seguente lista:
- Inglese: "en"
- Francese: "fr"
- Spagnolo: "es"
- Tedesco: "de"
Qualsiasi lingua non elencata deve essere classificata come "altro" con codice "on".

# Formato risposta
La tua risposta deve seguire questo formato:
{"language_iso": <codice_lingua>}

# Esempi
Di seguito alcuni esempi di input e output attesi:

## Inglese
Utente: Hello, how are you?
Risposta: {"language_iso": "en"}

## Francese
Utente: Bonjour, comment allez-vous?
Risposta: {"language_iso": "fr"}
```

Struttura perfetta:
1. Ruolo in una riga
2. `# Categorie` — lista chiara delle opzioni
3. `# Formato risposta` — formato output in una riga
4. `# Esempi` — esempi concreti input → output

**Scomporre in step**: se il task è complesso, dividerlo in passaggi semplici e sequenziali. Il modello ragiona meglio passo-passo che tutto insieme.

> **Per noi**: schema `# Ruolo` → `# Contesto` → `# Regole` → `# Formato Output` → `# Esempi`. Step chiari tipo "Step 1: seleziona, Step 2: combina, Step 3: verifica vincoli".

---

## 4. Formattazione

La formattazione è fondamentale per creare prompt efficaci. Consente di **evidenziare esplicitamente** diverse sezioni, rendendo la struttura intuitiva sia per il modello che per gli sviluppatori. I tag in stile **Markdown** e/o **XML** sono ideali perché:

- **Leggibile**: facile da scansionare per gli esseri umani.
- **Analizzabile**: permette di estrarre informazioni in modo semplice tramite programmazione.
- **Familiare**: probabilmente visto molto spesso durante l'addestramento del modello.

Una buona formattazione non solo aiuta il modello a comprendere il prompt, ma facilita anche agli sviluppatori l'iterazione e la manutenzione dell'applicazione.

> **Per noi**: Markdown con `#`, `##`, `-`, elenchi. Niente box ASCII (`═══`, `╔══╗`) — quelli sono rumore.

---

## 5. Esempio di richiesta (Few-Shot)

L'utilizzo di esempi è una tecnica che consiste nel fornire alcuni **esempi di attività** per migliorare la comprensione, la precisione e soprattutto il **formato di output** del modello.

```
# Esempi
Input: Hello, how are you?
Output: {"language_iso": "en"}
```

> **Per noi**: nel prompt attuale ci sono 0 esempi few-shot reali. Dobbiamo aggiungere 1-2 esempi di bolletta completa (input pool → output JSON).

---

## 6. Output strutturati

Il sistema include una modalità integrata per l'output JSON, oltre alla possibilità di utilizzare **output strutturati personalizzati**.

**Importante**: anche con `response_format: {"type": "json_object"}`, è essenziale istruire esplicitamente il modello nel prompt a generare un output in formato JSON e specificare il formato desiderato.

Gli output con **struttura personalizzata** (JSON Schema) sono più affidabili e sono consigliati ove possibile. Con schema rigido il modello è FORZATO a rispettare i campi e i tipi.

Quando usi lo schema, Mistral antepone automaticamente al system prompt:
`"Il tuo output deve essere un'istanza di un oggetto JSON che segue questo schema: {json_schema}"`

Tuttavia, si consiglia di aggiungere ulteriori spiegazioni e di perfezionare il prompt di sistema per chiarire meglio lo schema e il comportamento previsti.

> **Per noi**: noi usiamo `response_format: {"type": "json_object"}`. **DA VERIFICARE**: se si può passare JSON Schema rigido via REST API per eliminare errori di formato.

---

## 7. Cosa evitare

### Evitare parole soggettive e ambigue
- Evitare aggettivi quantitativi ambigui: "troppo lungo", "troppo corto", "molti", "pochi", ecc.
  - Fornire invece misure oggettive.
- Evitare parole vaghe come "cose", "roba", "scrivi un rapporto interessante", "miglioralo", ecc.
  - Specificare invece esattamente cosa si intende.

### Evitare le contraddizioni
Man mano che il prompt di sistema si allunga, potrebbero comparire lievi contraddizioni. Usare un albero decisionale:

```markdown
## Come aggiornare i record del database
Segui questi passaggi:
- Se i dati non includono nuove informazioni:
    - Ignora questi dati.
- Altrimenti, se i dati non sono correlati a nessun record esistente:
    - Crea un nuovo record.
- Altrimenti, se i dati contraddicono direttamente il record esistente:
    - Elimina il record esistente e creane uno nuovo.
- Altrimenti:
    - Aggiorna il record esistente.
```

### Non far contare/calcolare al modello
- Da evitare: "Se il record è troppo lungo, dividilo in più record."
- Fornire invece i numeri come input già calcolati.

### Non generare troppi token
I modelli sono più veloci nell'ingerire i token che nel generarli. Se si utilizzano output strutturati, chiedere al modello di **generare solo ciò che è strettamente necessario**.

### Preferire scale verbali
Se si ha bisogno che il modello valuti qualcosa, usare una scala verbale:
```
Valuta queste opzioni usando questa scala:
- Molto basso: se l'opzione è altamente irrilevante
- Basso: se l'opzione non è abbastanza buona
- Neutro: se l'opzione non è particolarmente interessante
- Buono: se l'opzione vale la pena considerare
- Molto buono: per opzioni altamente rilevanti
```

> **Per noi**:
> - Nel prompt attuale: "segnali negativi", "buona forma", "equilibrate" → vanno sostituiti con valori precisi.
> - Il prompt dice "fino a 3 bollette" e poi "3-5 bollette" → contraddizione.
> - Chiediamo di calcolare punteggi RH/RA/C che Python già calcola → inutile.
> - Il campo "reasoning" costa token e tempo → ridurlo o eliminarlo.
> - Invece di MN=0.72 e SCORE=12, dare etichette tipo "Eccellente", "Buona", "Discreta", "Sufficiente", "Minima".

---

## 8. Parametro N (completamenti multipli)

N rappresenta il numero di completamenti da restituire per ogni richiesta. Ogni completamento sarà una risposta univoca generata dal modello.

- I token di input vengono fatturati una sola volta, indipendentemente dal numero di completamenti richiesti.
- `mistral-large-2512` NON supporta il completamento N.

> **Per noi**: **DA VERIFICARE** se `mistral-medium-2508` supporta il parametro `n`. Possibile uso: generare 3 proposte per fascia e far scegliere a Python la migliore.

---

## 9. Temperatura

La temperatura controlla la diversità dell'output:
- **Bassa (0-0.2)**: deterministico. Per compiti che richiedono risposte coerenti e accurate (matematica, classificazione, ragionamento).
- **Alta (0.7-1.0)**: creativo. Per testi diversi e originali (brainstorming, scrittura).

Anche con `temperature=0`, possono verificarsi lievi variazioni dovute a differenze hardware ed errori di arrotondamento.

> **Per noi**: il compito è analitico (combinare selezioni rispettando vincoli), non creativo. Serve temperatura BASSA (0.1-0.3). Noi attualmente usiamo 1.0 — troppo alta.

---

## 10. Top P

Top P limita i token considerati in base a una soglia di probabilità. Aiuta a concentrarsi sui token più probabili, migliorando la qualità dell'output.

- Top P viene applicato DOPO la temperatura.
- È difficile trovare il giusto equilibrio tra Temperature e Top P: fissare un valore e regolare l'altro.
- Top P evita di prendere in considerazione token molto improbabili, mantenendo la qualità e la coerenza dell'output.

> **Per noi**: combinazione ideale = temperatura bassa (0.2) + top_p medio (0.5-0.7). Preciso ma non sempre identico. Da testare.

---

## 11. Penalità di presenza e frequenza

- **Penalità di presenza** (default 0, range -2 a 2): penalità una tantum applicata a tutti i token usati almeno una volta. Incoraggia varietà.
- **Penalità di frequenza** (default 0, range -2 a 2): penalità proporzionale alla frequenza di comparsa di un token. Evita ripetizioni.

Confronto dai test Mistral:
| | Nessuna penalità | Presenza (2) | Frequenza (2) |
|---|---|---|---|
| Risultato | Output coerente ma strutture ripetitive | Più diversificato, meno ripetizioni | Diversificato ma troppo aggressivo sui token lunghi |

Le penalità sono un parametro sensibile che può avere un impatto significativo, sia in positivo che in negativo.

> **Per noi**: potrebbe aiutare contro le ripetizioni di selezioni. Però con output JSON, penalità alte rischiano di rompere la struttura. Se si usa, tenere valori bassi (0.3-0.5). Opzione secondaria, non priorità.
