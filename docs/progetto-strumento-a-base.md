# Progetto: base dello strumento A (creazione dell'appartamento dall'app)

| Stato | Scritto da | Decisioni | Prossimo passo |
|---|---|---|---|
| **Progetto, nessun codice.** Da far leggere al revisore di sicurezza prima di scrivere codice | o1, 15 novembre 2026 | 1123 = a: un segreto per dispositivo; coda Pub/Sub al posto di una porta sulla VM. Opzione 1 del documento interno (§14) | la prova della condizione sul nome (sezione 3.1) e la revisione |

**Cosa copre:** il ricevitore di ordini sulla VM, la creazione e l'eliminazione del «posto» di un appartamento, le credenziali dei dispositivi, la capienza.

**Cosa non copre ancora:** il modulo del catalogo. Si aggiunge quando Youssouf avrà fissato il formato e accettato il catalogo vuoto. Qui c'è solo l'operazione che lo applica.

## 1. I pezzi

1. **Il server dell'app**, di produzione e di staging: decide, crea i segreti, manda gli ordini, tiene lo stato in Firestore.
2. **Due code Pub/Sub per ambiente:** «ordini» (dal server alla VM) e «risultati» (dalla VM al server).
3. **L'agente sulla VM:** un container che preleva gli ordini con l'identità della VM, esegue solo le operazioni della sezione 2 e pubblica il risultato.
   - Riusa gli script di oggi (`engine-vm.sh`, `broker-vm.sh`, `broker_accounts.py`).
   - Non apre porte e non riceve collegamenti.
4. **Secret Manager:** un segreto per la chiave del motore, uno per il conto del connector, **uno per ogni dispositivo**.

Il motore e il broker non cambiano. Unica eccezione: il catalogo vuoto, che è lavoro di Youssouf.

## 2. L'elenco chiuso delle operazioni dell'agente

Ogni ordine ha: `op_id` (univoco), `operazione`, `apartment_id`, parametri, ambiente, chi l'ha chiesto, ora. L'agente rifiuta tutto ciò che non è in questa tabella e ogni parametro fuori dalle regole.

| Operazione | Parametri | Cosa fa | Controlli |
|---|---|---|---|
| `capienza` | nessuno | restituisce `MemAvailable` della VM e il numero dei motori | — |
| `crea_motore` | `apartment_id`, porta, immagine | `engine-vm.sh install <apt> <porta> <immagine> shelly`: impostazioni, file della chiave (letta dalla VM), motore con il catalogo vuoto, controllo ogni 5 minuti e backup; poi `broker-vm.sh add-apartment <apt>` | id con la regola di oggi (`[A-Za-z0-9][A-Za-z0-9_-]{0,63}`) e il prefisso del suo ambiente (sezione 4); porta libera e dentro la fascia dell'ambiente; immagine solo del nostro Artifact Registry, `engine:<commit>`; capienza (sezione 6) |
| `aggiorna_broker` | `apartment_id` | `broker-vm.sh sync`: rilegge i segreti dei dispositivi e ricarica utenti e permessi | appartamento esistente sulla VM |
| `applica_catalogo` | `apartment_id`, catalogo, versione | controlla il catalogo con il lettore del motore; tiene la copia di prima; lo scrive in `/data/<apt>/catalog.yaml`; riavvia il motore (`key`); se non torna sano, rimette la copia e riavvia | dimensione massima; nessuna chiave sconosciuta (lo fa già il lettore); la versione deve essere più nuova di quella applicata |
| `stato` | `apartment_id` | `/health` del motore e immagine in uso | — |
| `togli_motore` | `apartment_id` | ferma e toglie il motore; copia `engine.db` in `/data/_deleted/<apt>-<data>.db` (tenuta 30 giorni, poi cancellata da un timer); toglie impostazioni e file della chiave; `broker-vm.sh remove-apartment` | appartamento esistente; mai `dev` né i motori di un altro ambiente |

**Non ci sono:** comandi liberi, lettura di segreti restituita al server, modifica di immagini o script. Nessun parametro finisce in una riga di shell senza il controllo della tabella.

**Fatto dal server, senza agente:**

1. creare i segreti dell'appartamento (chiave del motore e conto del connector, con valori casuali che nessuno vede);
2. creare il segreto di un dispositivo, generarne la password e **mostrarla una volta**;
3. «Rigenera»: versione nuova e distruzione della vecchia (sezione 3);
4. distruggere i segreti all'eliminazione.

## 3. Permessi

### 3.1 Il server (produzione `domotica-bff@`, staging `domotica-bff-staging@`)

| Permesso | Ruolo | Su cosa |
|---|---|---|
| Creare segreti | ruolo su misura con `secretmanager.secrets.create` | **da provare:** condizione sul nome (`resource.name.startsWith(...)`). La creazione si controlla sul progetto, e la documentazione non dice se la condizione la limita. Se non funziona: creazione senza condizione, ma senza lettura (alternativa (a) della risposta del 15 novembre) |
| Aggiungere, elencare e distruggere versioni; eliminare un segreto | ruolo su misura con `versions.add`, `versions.list`, `versions.destroy`, `secrets.delete`, **senza** `versions.access` | condizione sul nome: `langbrain-shelly-<apt>-dev-…`, `langbrain-shelly-<apt>`, `langbrain-api-key-<apt>`, con i prefissi del suo ambiente |
| Leggere la chiave del motore | `secretmanager.secretAccessor` | solo `langbrain-api-key-…` del suo ambiente, con condizione sul nome (oggi è un permesso per ogni singolo segreto) |
| Mandare ordini | `pubsub.publisher` | solo la coda «ordini» del suo ambiente |
| Ricevere risultati | consegna «push» sulla sua rotta, autenticata con un token di Google di un account dedicato | coda «risultati» del suo ambiente |

**Il server non legge mai le password dei dispositivi né quella del connector.**

### 3.2 La VM (`langbrain-vm@`)

| Permesso | Ruolo | Su cosa |
|---|---|---|
| Prelevare ordini | `pubsub.subscriber` | le due sottoscrizioni «ordini» (produzione e staging) |
| Pubblicare risultati | `pubsub.publisher` | le due code «risultati» |
| Leggere i segreti | `secretmanager.secretAccessor` | `langbrain-shelly-…` e `langbrain-api-key-…`, con condizione sul nome a livello di progetto. Così il server non deve dare permessi segreto per segreto (niente `setIamPolicy` al server) |

**La VM non crea né scrive segreti.**

## 4. Separazione fra prova e produzione (sulla stessa VM, finché non c'è la seconda)

1. **Code separate:** `domhouse-ordini-prod` e `domhouse-ordini-staging`, e così i risultati. L'agente sa da quale ambiente viene un ordine dalla sottoscrizione da cui lo preleva, non da un campo del messaggio.
2. **Prefissi degli id:** lo staging può ordinare solo motori `dev`, `lab-…` e `test-…`; la produzione tutti gli altri, mai quelli. L'agente lo controlla in un punto solo.
3. **Fasce di porte:**
   - staging solo dentro `INSTANCE_ALLOWED` (oggi 8100 e 8150–8169);
   - produzione 8101–8149.
   - La prova di carico usa 8150–8189: va spostata, oppure la fascia dello staging ristretta, da decidere prima del codice.
4. **Segreti:** le condizioni sul nome della sezione 3 limitano ogni server ai prefissi del suo ambiente.
5. **Seconda VM:** prima che il cliente crei dall'app il primo appartamento vero in produzione, oppure all'allarme di capienza. Allora la regola dei prefissi si toglie.

## 5. Se un ordine fallisce a metà

1. **Ogni operazione è ripetibile senza danni**: `install`, `sync`, `remove-apartment` lo sono già. `applica_catalogo` lo è grazie alla versione.
2. **Registro sulla VM:** l'agente scrive `op_id` ed esito in un registro locale prima di confermare l'ordine. Un ordine arrivato due volte (Pub/Sub consegna «almeno una volta») restituisce l'esito già registrato, senza rifare niente.
3. **Un'operazione alla volta per appartamento**, con il blocco che `engine-vm.sh` usa già.
4. **Ordini vecchi:** l'agente scarta un ordine più vecchio di 15 minuti. Così un ordine rimasto in coda per un guasto non parte giorni dopo.
5. **Stato in Firestore** per ogni operazione: inviato, in corso, riuscito, fallito, con il motivo in parole semplici.
6. **La creazione dell'appartamento è una sequenza di passi ripetibili:**
   1. prenotare id e porta;
   2. creare i segreti (se ci sono già, si va avanti);
   3. `crea_motore`;
   4. «Verifica connessione».

   L'app mostra l'ultimo passo riuscito e il pulsante **«Riprova»**, che rifà i passi mancanti con un ordine nuovo. Niente ripresa automatica (taglio deciso).
7. **Coda degli scarti:** dopo 5 tentativi falliti l'ordine va in una coda a parte, con un allarme email. Lo guardiamo noi.

## 6. Capienza

1. Prima di `crea_motore` il server chiede `capienza`, e l'agente controlla di nuovo prima di installare.
2. **Rifiuto** se `MemAvailable` meno 150 MB (il motore nuovo, stima) è sotto 400 MB.
3. **Allarme** con `MemAvailable` sotto 500 MB per 10 minuti. Il controllo ogni 5 minuti scrive oggi la percentuale usata: va aggiunto il valore in MB.
4. Un secondo limite sul numero dei motori, impostabile, per sicurezza.
5. Tutte e tre le cifre sono **stime**: vanno misurate con il primo appartamento vero. Oggi 1205 MB disponibili con `dev`, `lab-01` e il broker.

## 7. Eliminazione (proposta del committente per il cliente)

1. **Chi:** l'amministratore dell'organizzazione del cliente, entro un massimo fissato dal gestore della piattaforma (per esempio un numero di eliminazioni ogni 30 giorni). Il server lo controlla.
2. **Prima «Disattiva»**, cioè l'interruttore «Attivo» spento: l'appartamento resta, il motore gira, nessuno lo usa. L'eliminazione è possibile solo dopo un periodo fissato.
3. **Conferma** scrivendo il nome dell'appartamento, con il testo:
   - **si perde subito:** la configurazione, il motore, le credenziali dei dispositivi;
   - **resta:** prenotazioni e riepiloghi per 12 mesi, il registro amministrativo per 24, lo storico del motore per 30 giorni nella copia di sicurezza.
4. **Cosa succede:**
   1. `togli_motore`, con la copia di `engine.db` di 30 giorni;
   2. il server distrugge versioni e segreti dell'appartamento;
   3. l'eliminazione di oggi in Firestore (`remove_apartment`): l'id resta riservato;
   4. una riga nel registro amministrativo.
5. **Recupero entro 30 giorni:** procedura scritta, lanciata da noi, dalla copia in `/data/_deleted/` oppure da uno snapshot del disco.

## 8. Domande per il revisore di sicurezza

1. L'agente con poteri da amministratore sulla VM condivisa: l'elenco chiuso e i controlli della sezione 2 bastano?
2. La creazione di segreti, se la condizione sul nome non funziona: l'alternativa senza condizione e senza lettura è accettabile?
3. La separazione con code e prefissi fino alla seconda VM: è sufficiente per il periodo di prova?
4. La password del dispositivo mostrata una volta, generata dal server senza poterla rileggere: ci sono punti in cui potrebbe restare (registri, risposte in cache)?
5. La coda degli scarti e gli ordini scartati perché vecchi: possono nascondere un attacco o un guasto?
