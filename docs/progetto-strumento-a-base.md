# Progetto: base dello strumento A (creazione dell'appartamento dall'app)

| Stato | Scritto da | Decisioni | Prossimo passo |
|---|---|---|---|
| **Progetto, nessun codice. Seconda stesura**, con le correzioni della revisione di sicurezza (`DOMOTICA/revisione-progetto-a/REVISIONE-SICUREZZA.md`, 25 punti) | o1, 15 novembre 2026 | 1123 = a: un segreto per dispositivo; coda Pub/Sub. 1125 = a: prova della condizione sul nome. Opzione 1 del documento interno (§14) | rilettura delle sezioni cambiate da parte del revisore; prova 1125; poi il codice |

**Cosa copre:** l'agente sulla VM, la creazione e l'eliminazione del «posto» di un appartamento, le credenziali dei dispositivi, la capienza.

**Cosa non copre:** il modulo del catalogo, che aspetta il formato di Youssouf. Qui c'è solo l'operazione che lo applica.

**Il confine di fondo, detto subito:** sulla VM l'agente è **root**. Lo si limita con un elenco chiuso di operazioni, un lettore della coda senza privilegi e controlli doppi, non con un container (§1, §3).

## 1. I pezzi

1. **Il server dell'app** (staging e, dopo la seconda VM, produzione): decide, crea i segreti, manda gli ordini, tiene lo stato in Firestore.
2. **Pub/Sub, per ambiente:** una coda «ordini» con schema e dimensione massima; una coda «risultati»; una coda «scarti».
3. **Sulla VM, due servizi systemd** (non container: un container con il socket di Docker sarebbe root lo stesso):
   - **il lettore**, utente senza privilegi `domhouse-agent`: preleva gli ordini con il token della VM, controlla schema, ambiente, età e sequenza, scrive il giornale e pubblica i risultati;
   - **l'esecutore**, root, minimo: ascolta solo su un socket UNIX locale leggibile dal lettore. Accetta solo le 7 operazioni del §3, con argomenti già controllati, e li ricontrolla. Lancia `/opt/domhouse/engine-vm.sh` e `/opt/domhouse/broker-vm.sh` (di root, non scrivibili da altri) con `execve` e una lista di argomenti, mai `sh -c`, con l'ambiente pulito (`env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin`), mai `bash -x`.
4. **Secret Manager:** per ogni appartamento la chiave del motore e il conto del connector; **un segreto per dispositivo**.

## 2. Nomi e ambienti

### 2.1 Id

| Cosa | Regola | Esempio |
|---|---|---|
| Appartamento di **produzione** | **generato dal server**, mai scelto dal cliente: `a-` più 8 caratteri casuali `[a-z0-9]`. Il nome visibile resta libero | `a-k3f9x2qm` |
| Appartamento di **staging** | `lab-…` o `test-…`, poi `^[a-z0-9][a-z0-9-]{2,63}$`; scelto dal gestore della piattaforma | `lab-02` |
| `dev` | esiste, resta com'è (D-118); **escluso da ogni ordine** salvo `stato` e `capienza` | — |
| Dispositivo | `^[a-z0-9][a-z0-9-]{0,63}$` (gli id Shelly lo sono già) | `shellyplugmg3-9070695cb0d0` |

**Nessun id contiene `_`**, che diventa il separatore. Agente, server e `engine-vm.sh` usano le stesse regole: niente maiuscole.

**Vietato finché esiste un segreto della forma vecchia:** un id di appartamento che finisce con `-devices`. Oggi c'è solo `langbrain-shelly-lab-01-devices`, da migrare (§9).

### 2.2 Segreti

| Segreto | Nome |
|---|---|
| Chiave del motore | `langbrain-api-key-<apt>` (nome di oggi: lo usa il server per chiamare il motore) |
| Conto del connector | `langbrain-shelly-<apt>` |
| Dispositivo | `langbrain-shelly-<apt>_<device>` |

Dalla forma nuova nessuna collisione è possibile: `_` non può stare negli id.

**Ogni segreto si crea con parametri fissi, scritti nel codice e provati:**

- replica `user-managed` solo in `europe-west8`;
- nessun `expireTime`, nessun `topics`, nessuna chiave CMEK;
- etichette `domhouse-env`, `domhouse-apt`, `domhouse-op`;
- **ritardo di distruzione di 7 giorni** (`version_destroy_ttl`). Una versione «distrutta» diventa subito disattivata e illeggibile, e per 7 giorni si può ancora riattivare dopo un incidente. Da verificare con la prova 1125.

**Un segreto che esiste già** si riusa solo se due condizioni valgono entrambe:

1. il Firestore di quell'ambiente registra di averlo creato lui (op_id);
2. i metadati (`secrets.get`, senza leggere il valore) coincidono: replica, nessun `expireTime`, `topics` o CMEK, etichette.

Altrimenti: errore, allarme, nessuna versione aggiunta.

### 2.3 Condizioni IAM (testo esatto; numero del progetto 444239063209)

`resource.name` di un segreto è `projects/444239063209/secrets/<nome>`, e quello di una versione ha in più `/versions/N`. La forma con il numero è **da confermare con la prova 1125**, che prova anche quella con l'identificativo.

**Staging:**

```
resource.name.startsWith("projects/444239063209/secrets/langbrain-shelly-lab-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-shelly-test-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-lab-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-test-")
```

**Produzione:**

```
resource.name.startsWith("projects/444239063209/secrets/langbrain-shelly-a-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-a-")
```

**Prefissi positivi per tutti e due gli ambienti**, con il trattino. Nessuno dei due copre `dev`, `devon-01`, `labrador` o un id maiuscolo.

**Alla prova 1125 vanno aggiunti questi casi negativi**, con un segreto vuoto ciascuno:

- `langbrain-shelly-labrador`;
- `langbrain-shelly-devon-01`;
- `langbrain-shelly-LAB-01`;
- `langbrain-shelly-dev_01`.

### 2.4 La prova di carico

Oggi crea appartamenti `carico-NN` con segreti leggibili dallo staging (`scripts/load/ambiente.py`).

- Si rinominano in `test-carico-NN`, nello staging.
- Prima si cancellano i segreti `langbrain-api-key-carico-*` rimasti.
- Le sue porte passano a **8170–8199** (§5.3).

## 3. L'elenco chiuso delle operazioni

Ogni ordine porta questi campi, con uno schema Pub/Sub e una dimensione massima di 128 KB:

- `op_id`;
- `operazione`;
- `apartment_id`;
- `seq`: numero di sequenza per appartamento, deciso dal server in una transazione Firestore;
- parametri;
- `ambiente`;
- `richiesto_da`: solo l'uid, mai l'email.

**Controlli comuni a ogni operazione con un appartamento:**

1. l'id segue la regola del §2.1;
2. il prefisso è quello dell'ambiente della **sottoscrizione**. Il campo `ambiente` deve coincidere: se no, rifiuto e allarme;
3. il file delle impostazioni sulla VM dice lo stesso ambiente (`ENV=staging|prod`, scritto da `crea_motore`, di root);
4. `seq` è più alto dell'ultimo applicato per quell'appartamento (salvato in un file di root);
5. `dev` è escluso.

| Operazione | Parametri | Cosa fa | Controlli in più |
|---|---|---|---|
| `capienza` | — | `MemAvailable` e numero dei motori, per ambiente | — |
| `crea_motore` | `apartment_id`, porta | installa il motore (catalogo vuoto, `CONNECTOR=shelly`, `ENV`), poi `add-apartment` sul broker | **porta:** intero `^[1-9][0-9]{3,4}$` nella fascia dell'ambiente, assente da ogni `/opt/domhouse/*.settings` dei due ambienti e da `ss -ltn`. **Immagine:** non è un parametro: quella approvata nella configurazione dell'agente, per digest. **Capienza:** §7. Se l'appartamento esiste già con gli stessi parametri: riuscito, senza rifare niente; con parametri diversi: rifiuto |
| `aggiorna_motore` | `apartment_id` | porta il motore all'immagine approvata (`engine-vm.sh update`) | stessi controlli dell'immagine |
| `aggiorna_broker` | `apartment_id`, elenco dei dispositivi | scrive `/etc/domhouse/_broker/devices/<apt>` (di root) e lancia il `sync` | ogni id con la regola del §2.1; al massimo 200 dispositivi |
| `applica_catalogo` | `apartment_id`, catalogo, versione | §3.1 | versione più alta dell'ultima applicata |
| `stato` | `apartment_id` | `/health` del motore e immagine in uso | ammesso anche per `dev` |
| `togli_motore` | `apartment_id` | §8.2 | ripetibile: «già tolto» vale come riuscito |

**L'immagine, in ogni caso**, deve seguire la regola ancorata:

`^europe-west8-docker\.pkg\.dev/domotica-poc-511707/domotica/engine(:[0-9a-f]{7,40}|@sha256:[0-9a-f]{64})$`

- La controllano sia l'agente sia `engine-vm.sh`: difesa doppia.
- `registry_login` rifiuta ogni host diverso da `europe-west8-docker.pkg.dev`.
- `update` non usa più l'immagine dentro `sed "s#…#…#"`.
- Lo staging può scegliere fra le immagini del registro, la produzione solo quella approvata.

### 3.1 Applicare un catalogo

1. **Dimensione massima: 64 KB**, controllata prima di leggere.
2. **Controllo in un container usa e getta** dell'immagine del motore, con il lettore del motore. Opzioni: `--network none --read-only --user 10001 --cap-drop ALL --security-opt no-new-privileges --memory 128m --pids-limit 64`, tempo massimo 30 s.
   - Mai letto da root sull'host: un YAML costruito apposta («billion laughs») consuma solo quel container.
3. **Il catalogo vive fuori dalla cartella del motore:**
   - in `/etc/domhouse/<apt>.catalog.yaml`, di root, permessi 644;
   - montato in sola lettura nel container e indicato con `CATALOG_PATH`, che il motore supporta già.
   - La copia di prima (`.catalog.yaml.prima`) e la versione applicata stanno accanto, sempre di root.
   - Così un motore compromesso non può mettere link simbolici dove scrive l'agente.
4. Scrittura atomica, riavvio con `key`. Se il motore non torna sano, si rimette la copia e si riavvia.

## 4. Permessi

### 4.1 Server

| Ruolo | Permessi esatti | Condizione |
|---|---|---|
| «creazione» | `secretmanager.secrets.create` | il §2.3 del suo ambiente, **se la prova 1125 riesce**. Se fallisce: nessuna condizione per la produzione, che però non riusa mai un segreto non suo (§2.2); **nessuna creazione per lo staging**, i cui segreti di prova li prepariamo noi |
| «versioni» | `secretmanager.versions.add`, `secretmanager.versions.list`, `secretmanager.versions.destroy`, `secretmanager.secrets.get` | il §2.3 del suo ambiente |
| lettura delle chiavi dei motori | `secretmanager.secretAccessor` | solo `langbrain-api-key-…` del suo ambiente |
| ordini | `pubsub.publisher` | solo la sua coda «ordini» |

**Mai** al server: `versions.access` sulle password, `versions.enable`, `secrets.update`, `secrets.delete`, `secrets.setIamPolicy`, `secrets.getIamPolicy`.

- I segreti rimasti vuoti dopo un'eliminazione li cancella dopo 30 giorni un nostro controllo periodico.
- Il controllo periodico cerca anche gli orfani: segreti `langbrain-*` senza appartamento o dispositivo nei due Firestore portano a un allarme.

**Registri di accesso ai dati di Secret Manager** attivi, con allarmi su:

- raffiche di `DestroySecretVersion`;
- ogni accesso negato a un server su `langbrain-shelly-*`.

### 4.2 Risultati verso il server (consegna «push»)

Un account di push diverso per ogni ambiente. Il server controlla:

1. firma Google;
2. `aud` uguale all'indirizzo esatto della rotta di **quell'**ambiente;
3. `email` uguale all'account di push di quell'ambiente, ed `email_verified`.

Un risultato vale solo se si riferisce a un `op_id` in attesa, con stesso ambiente, appartamento e operazione, e porta lo stato da «inviato» o «in corso». Il motivo è un **codice di un elenco chiuso**, che il server traduce in parole.

### 4.3 VM (`langbrain-vm@`)

| Permesso | Su cosa |
|---|---|
| `pubsub.subscriber` | la sottoscrizione «ordini» dello **staging**. Quella della produzione **non esiste sulla VM condivisa** (§5.4) |
| `pubsub.publisher` | la coda «risultati» dello staging |
| `secretmanager.secretAccessor` | con condizione sul nome: i prefissi del §2.3 più quelli di oggi (`dev`, `lab-01`) |
| quelli di oggi | Artifact Registry Reader, Logs Writer, Monitoring Metric Writer, «Creatore di token» su `domhouse-dns-lab@` (per lego) |

**Il token della VM non deve essere raggiungibile dai container** (vale già oggi, §9):

- una regola nella catena `DOCKER-USER` scarta il traffico dalle reti di Docker verso `169.254.169.254`, rimessa a ogni avvio da un servizio systemd come `domhouse-broker-limit`;
- lego, che oggi usa l'identità della VM dalla rete bridge, passa a `--network host`;
- `check-all` verifica da un container di prova che i metadati non rispondano.

Il lettore e l'esecutore girano sull'host: per loro il token c'è.

**Raggio del token, accettato fino alla seconda VM:** chi è root sulla VM legge tutti i segreti dei prefissi e può far sparire gli ordini dello staging. Root sulla VM resta il confine; per questo §3.1 e §8.2 non leggono mai da root file che il motore può cambiare.

## 5. Separazione fra prova e produzione

1. **Code separate per ambiente.** L'agente sa l'ambiente dalla sottoscrizione.
2. **Prefissi positivi** (§2) per segreti e appartamenti, più `ENV` nel file delle impostazioni.
3. **Fasce di porte** (decisione da confermare prima del codice):
   - produzione 8101–8149;
   - staging creato dall'app 8150–8159;
   - `lab-01` resta su 8169;
   - prova di carico 8170–8199;
   - `INSTANCE_ALLOWED` dello staging diventa `8100,8150-8199`.
4. **La produzione non manda ordini alla VM condivisa:** la sottoscrizione degli ordini della produzione non si crea su `langbrain-dev`, e il server di produzione non ha `publisher`. La regola «seconda VM prima del primo appartamento vero» la impone la tecnica.
5. **Nello staging creano ed eliminano appartamenti solo i gestori della piattaforma**, non gli amministratori dei clienti: Firebase Authentication è condiviso.
6. **Numero massimo di motori dello staging nell'agente:** 4, `dev` e `lab-01` compresi, indipendente dalla capienza.
7. **Seconda VM:** un account di servizio per VM, ciascuno con la lettura dei soli segreti del suo ambiente; un broker per VM; la regola dei prefissi resta come seconda difesa.
8. **Rischio accettato per iscritto fino alla seconda VM:** lo staging può disturbare (blocco unico, memoria) i motori di produzione già esistenti. Oggi non ce ne sono (D-134).

## 6. Se un ordine fallisce a metà

1. **Un solo esecutore per tutta la VM**, un ordine alla volta, con priorità alla produzione quando ci sarà. Il blocco di `engine-vm.sh` è già unico per la VM; `broker-vm.sh` prende lo stesso blocco.
2. **Giornale sulla VM:** «ricevuto» e «in corso» si scrivono **prima** di eseguire. Un doppione di un ordine in corso o finito si ignora, e si ripubblica l'esito registrato.
3. **Conferma subito, risultato sulla seconda coda:** il lettore conferma l'ordine appena l'ha scritto nel giornale. Il tempo di conferma di Pub/Sub non conta più.
4. **Sequenza:** `seq` per appartamento (§3); chiave d'ordine di Pub/Sub = `apartment_id`, come aiuto e non come garanzia.
5. **Età dell'ordine** da `publish_time` di Pub/Sub, che chi pubblica non può falsificare.
   - Oltre 15 minuti: scartato, con un risultato «scartato» e una riga nel registro di sistema.
   - Allarme se succede in produzione.
6. **Rifiuto per regole o capienza:** non è un guasto. Si conferma subito con un risultato «rifiutato: codice». Solo un guasto dell'agente chiede un nuovo tentativo.
7. **Tentativi:** 5, con attesa fra 10 e 60 s, quindi tutti entro i 15 minuti. Poi la coda degli scarti, leggibile solo da noi, con conservazione 7 giorni e allarme.
8. **Tempo massimo nel server:** un'operazione «inviata» o «in corso» da più di 20 minuti diventa «fallita, Riprova». I risultati che arrivano dopo si ignorano.
9. **«Riprova»** manda un ordine nuovo, con una `seq` nuova, e rifà i passi mancanti. Le operazioni sono ripetibili: `crea_motore` con gli stessi parametri, `togli_motore` e `remove-apartment` con «già tolto» che vale come riuscito.
10. **Conteggio giornaliero** nel registro di sistema per ambiente (ricevuti, eseguiti, rifiutati, scartati, finiti negli scarti). Un confronto periodico fra le operazioni del server e il giornale della VM dà allarme sulle differenze.
11. **Registri:**
    - l'agente non restituisce mai l'uscita degli script: solo codici;
    - l'uscita completa resta nel giornale locale di root, conservato 14 giorni;
    - le righe dell'agente nel registro di sistema hanno solo op_id, operazione, appartamento, ambiente, esito, durata. Mai il catalogo, mai un'email.

## 7. Capienza

1. Prima di `crea_motore` il server chiede `capienza`; l'esecutore ricontrolla prima di installare.
2. **Rifiuto** se `MemAvailable` meno 150 MB (il motore nuovo, stima) è sotto 400 MB, oppure se lo staging è al suo massimo (§5.6).
3. **Allarme** con `MemAvailable` sotto 500 MB per 10 minuti: il controllo ogni 5 minuti scriverà anche il valore in MB.
4. **Ogni motore con un tetto di memoria e contenitore più chiuso**, in `engine/compose.yaml`: `mem_limit`, `cap_drop: [ALL]`, `no-new-privileges`, `read_only` con `tmpfs` per `/tmp`, `pids_limit`. Valori e funzionamento da provare: il motore scrive solo in `/data/<apt>` e in `/tmp`.
5. Le cifre sono **stime**, da misurare con il primo appartamento vero.

## 8. Credenziali dei dispositivi ed eliminazione

### 8.1 Registrare un dispositivo, «Rigenera»

1. **Un blocco per dispositivo** in Firestore (transazione) per creazione, «Rigenera» e rimozione.
2. Il server genera la password, aggiunge la versione e la **mostra una volta**. Poi distrugge, con ritardo, **tutte le versioni attive tranne quella appena creata**, di cui conosce il numero dalla risposta di `versions.add`.
3. **Stato «revoca in corso»** finché non arriva il risultato riuscito di `aggiorna_broker`: fino ad allora la password vecchia vale ancora sul broker, e l'app non dice «revocata». Allarme se non arriva.
4. **Dove la password non deve restare:**
   - mai nei registri, nemmeno la richiesta a Secret Manager (un'eccezione si registra solo con la sua classe);
   - mai in Firestore né in una risposta salvata per i tentativi: una seconda chiamata dice «già generata, usa Rigenera»;
   - nel sito solo in memoria nel componente, `autocomplete="off"`, mai nell'URL, in `localStorage` o nella cache delle query;
   - nella guida, l'avvertenza sugli appunti sincronizzati.
5. **Il `sync` del broker è isolato per appartamento:** se i segreti di un appartamento non si leggono, si tengono le sue righe di prima (o le si toglie, se è in eliminazione), si aggiornano gli altri, e una riga d'allarme dice quale. La VM sa quali segreti leggere dal file dei dispositivi del §3: niente `secrets.list`.
6. **Limiti di frequenza** per organizzazione su creazioni, «Rigenera» ed eliminazioni.

### 8.2 Eliminazione

1. **Chi:** l'amministratore dell'organizzazione del cliente, entro un massimo fissato dal gestore della piattaforma. Nello staging solo il gestore (§5.5).
2. **Prima «Disattiva»** per un periodo fissato. Email al gestore e agli altri amministratori dell'organizzazione a «Disattiva» e a «Elimina».
3. **Conferma** scrivendo il nome, con il testo:
   - **si perde subito:** la configurazione, il motore, le credenziali dei dispositivi. Dopo un recupero ogni Shelly va riconfigurato sul posto con password nuove;
   - **resta:** prenotazioni e riepiloghi per 12 mesi, registro amministrativo per 24, lo storico del motore **fino a 60 giorni** (30 nella copia, e altri 30 negli snapshot del disco).
   - Va scritto anche nell'informativa sulla privacy: compito della memoria storica.
4. **Ordine imposto dal server**, con «Riprova» e lo stato dell'ultimo passo:
   1. `togli_motore` riuscito;
   2. distruzione, con ritardo, delle versioni dei segreti dell'appartamento;
   3. eliminazione in Firestore (`remove_apartment`): la porta si libera solo qui.
5. **`togli_motore`, tutto sotto il blocco**, ogni passo saltato senza errore se è già fatto:
   1. copia coerente del database **prima** di fermare il motore: backup in linea di SQLite e `PRAGMA integrity_check`, eseguiti come utente 10001 (`setpriv`) o aprendo i file senza seguire link. La copia va in `/data/_deleted/<apt>-<data>.db`: cartella di root 700, file di root 600;
   2. `compose down`;
   3. tolto `/opt/domhouse/<apt>.settings` (il controllo ogni 5 minuti e l'avvio non lo vedono più);
   4. tolti `/etc/domhouse/<apt>.env`, `.settings.env`, `.catalog.yaml`;
   5. tolto `/data/<apt>`, backup compresi;
   6. `remove-apartment` sul broker e il suo file dei dispositivi.
6. Un timer cancella i file di `/data/_deleted` con più di 30 giorni, compresi `-wal` e `-shm`, e scrive una riga per ogni file tolto.
7. **Recupero entro 30 giorni** dalla copia, oppure entro 60 dagli snapshot: procedura scritta, lanciata da noi. I dispositivi vanno riconfigurati con password nuove.

## 9. Cosa cambia nel codice di oggi (dopo le prove di lunedì 16)

1. **Subito, vale già oggi:** blocco dei metadati per i container, lego in `--network host`, controllo in `check-all`.
2. `engine-vm.sh`:
   - regole degli id e dell'immagine;
   - `registry_login` ancorato;
   - `ENV` nelle impostazioni (`dev` e `lab-01` aggiornati una volta, a mano);
   - catalogo in `/etc/domhouse`;
   - comando `remove`;
   - `backup` senza seguire link;
   - porte normalizzate e confrontate.
3. `broker-vm.sh`: `remove-apartment` ripetibile; un blocco; file dei dispositivi.
4. `broker_accounts.py`: segreti per dispositivo; `sync` isolato per appartamento.
5. `engine/compose.yaml`: tetto di memoria e contenitore più chiuso; catalogo in sola lettura.
6. `scripts/load`: appartamenti `test-carico-NN`, porte 8170–8199.
7. **Migrazione di `lab-01`** dal segreto `-devices` ai segreti per dispositivo, con la stessa password: la Plug non cade. Procedura scritta a parte.

## 10. Punti della revisione di sicurezza

| N. | Esito |
|---|---|
| 1 | corretto in §2.1, §2.2, §2.3 (id minuscoli senza `_`, separatore `_`, prefissi positivi, CEL esatto con il numero del progetto, casi negativi per la prova 1125) e §9.7 (migrazione di `lab-01`) |
| 2 | corretto in §2.2 (riuso solo se creato da quell'ambiente, metadati ed etichette), §2.1 (id di produzione generati), §2.4 (`carico-*`), §4.1 (orfani; staging senza creazione se la condizione non funziona) |
| 3 | corretto in §1.3 (agente dichiarato root, lettore senza privilegi ed esecutore minimo, `execve`, ambiente pulito), §3.1 (catalogo in `/etc/domhouse`, in sola lettura), §8.2.5 (database letto senza seguire link), §9.2 (`backup`) |
| 4 | corretto in §4.3 (regola `DOCKER-USER`, lego, controllo in `check-all`, raggio del token scritto) e §9.1; vale già oggi |
| 5 | corretto in §8.1.5 (`sync` isolato per appartamento, file dei dispositivi, niente `secrets.list`), §6.1 (blocco anche per `broker-vm.sh`), §8.1.3 (revoca considerata fatta solo dopo `aggiorna_broker`) |
| 6 | corretto in §3 (regola ancorata dell'immagine in agente ed `engine-vm.sh`, `registry_login`, niente `sed` con l'immagine, immagine approvata per la produzione) |
| 7 | corretto in §3 `crea_motore` (porta intera, confronto con tutti i motori e con `ss`), §5.3 (fasce), §8.2.4 (porta liberata dopo `togli_motore`) |
| 8 | corretto in §2.1 e §3, controlli comuni (regola degli id, `dev` escluso, ambiente controllato per ogni operazione, `ENV` sulla VM) |
| 9 | corretto in §3 e §6.9 (`crea_motore` uguale o rifiuto; «già tolto» = riuscito) e §8.2.5 (ordine di `togli_motore`) |
| 10 | corretto in §6.1–6.4 (un esecutore per la VM, «in corso» prima di eseguire, conferma subito e risultato a parte, `seq`, chiave d'ordine) |
| 11 | corretto in §6.5–6.8 e §6.10 (età da `publish_time`, rifiuti confermati subito, risultato «scartato», tempo massimo nel server, tentativi entro 15 minuti, scarti 7 giorni, conteggi e confronto) |
| 12 | corretto in §4.2 (firma, `aud`, `email`, account di push per ambiente, risultati solo per operazioni in attesa, codici chiusi) |
| 13 | corretto in §4.1 (elenco esatto, niente `secrets.delete` al server, orfani dopo 30 giorni, registri di accesso con allarmi) e §2.2 (ritardo di distruzione di 7 giorni, da verificare con la prova 1125) |
| 14 | corretto in §8.1.1–8.1.3 (blocco per dispositivo, distruzione di tutte le versioni tranne la nuova, «revoca in corso») |
| 15 | corretto in §8.2 (ordine dei passi, «Riprova», copia coerente senza link in cartella di root, timer dei 30 giorni, fino a 60 giorni con gli snapshot, recupero senza password, informativa) |
| 16 | corretto in §1.3 e §6.11 (solo codici, giornale locale, righe minime, solo uid, ambiente pulito, mai `-x`; l'agente non è in container, quindi l'Ops Agent non ne raccoglie l'uscita) |
| 17 | corretto in §3.1 (64 KB, controllo nel container usa e getta con le opzioni, versione fuori da `/data`) |
| 18 | corretto in §5.5, §5.6, §7.2, §7.4 (staging solo per i gestori, massimo 4 motori di staging, tetto di memoria) |
| 19 | accolto: §5.4 (nessuna sottoscrizione della produzione sulla VM condivisa) e §5.7 (account e broker per VM, prefissi tenuti) |
| 20 | accolto in §7.4 e §9.5, con i valori da provare |
| 21 | accolto in §2.2 (parametri fissi e provati) |
| 22 | accolto in §8.1.6 e §8.2.2 (limiti di frequenza, email a «Disattiva» ed «Elimina») |
| 23 | accolto in §3 (schema, 128 KB, ambiente uguale alla sottoscrizione) |
| 24 | accolto: settima operazione `aggiorna_motore` in §3 |
| 25 | accolto in §1.3 (script di `/opt/domhouse`, di root, mai copie dall'agente) |

**Domande che restano per la rilettura:**

1. le fasce di porte del §5.3;
2. il massimo di 4 motori di staging;
3. la conservazione fino a 60 giorni dello storico eliminato, o una copia fuori dal disco degli snapshot.
