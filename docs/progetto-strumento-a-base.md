# Progetto: base dello strumento A (creazione dell'appartamento dall'app)

| Stato | Scritto da | Decisioni | Prossimo passo |
|---|---|---|---|
| **Progetto, nessun codice. Terza stesura (16 novembre):** le password dei dispositivi si conservano solo come **impronta** (D-233). La seconda stesura (15 novembre) aveva le correzioni della revisione di sicurezza (`DOMOTICA/revisione-progetto-a/REVISIONE-SICUREZZA.md`, 25 punti) | o1, 15–16 novembre 2026 | D-230 (1123 = a): coda Pub/Sub; **il segreto per dispositivo è una strada scartata** (registro §7.1). D-233 (1133 = a): impronte. 1125 = a: prova della condizione sul nome. Opzione 1 del documento interno (§14) | rilettura della memoria storica; poi una revisione di sicurezza delle parti cambiate (§10.3); prova 1125; poi il codice |

**Cosa copre:** l'agente sulla VM, la creazione e l'eliminazione del «posto» di un appartamento, le credenziali dei dispositivi (registrazione, «Rigenera», «Revoca»), la capienza.

**Cosa non copre:** il modulo del catalogo, che aspetta il formato di Youssouf. Qui c'è solo l'operazione che lo applica.

**Il confine di fondo, detto subito:** sulla VM l'agente è **root**. Lo si limita con un elenco chiuso di operazioni, un lettore della coda senza privilegi e controlli doppi, non con un container (§1, §3).

## 1. I pezzi

1. **Il server dell'app** (staging e, dopo la seconda VM, produzione): decide, crea i due segreti di ogni appartamento, genera le password dei dispositivi e ne tiene solo l'impronta, manda gli ordini, tiene lo stato in Firestore.
2. **Pub/Sub, per ambiente:** una coda «ordini» con schema e dimensione massima; una coda «risultati»; una coda «scarti».
3. **Sulla VM, due servizi systemd** (non container: un container con il socket di Docker sarebbe root lo stesso):
   - **il lettore**, utente senza privilegi `domhouse-agent`: preleva gli ordini con il token della VM, controlla schema, ambiente, età e sequenza, scrive il giornale e pubblica i risultati;
   - **l'esecutore**, root, minimo: ascolta solo su un socket UNIX locale. Accetta solo le 7 operazioni del §3, con argomenti già controllati, e li ricontrolla. Lancia `/opt/domhouse/engine-vm.sh` e `/opt/domhouse/broker-vm.sh` (di root, non scrivibili da altri) con `execve` e una lista di argomenti, mai `sh -c`, con l'ambiente pulito (`env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin`), mai `bash -x`.
   - **Il confine fra i due.** Il lettore è il pezzo esposto (legge JSON da Pub/Sub e ha il token): se è compromesso, l'esecutore è l'unica difesa.
     1. Il socket sta in `/run/domhouse-agent`: cartella di root, gruppo `domhouse-agent`, permessi 750; socket 660.
     2. L'esecutore controlla `SO_PEERCRED` e accetta solo l'uid del lettore.
     3. L'esecutore **ripete** tutti questi controlli, senza fidarsi del lettore: id (§2.1); prefisso contro ambiente; `ENV` del file delle impostazioni; `dev` escluso; porta e fascia; immagine; dimensioni (ordine, catalogo, elenco dei dispositivi); numero massimo dei motori dello staging; `seq`.
     4. L'esecutore ha l'ambiente ammesso nella **propria** configurazione di root: sulla VM condivisa rifiuta qualunque ordine con ambiente `prod`, qualunque cosa dica il lettore.
   - **Il blocco lo prende una volta sola l'esecutore**, per tutta l'operazione. Lancia gli script passando il descrittore già bloccato e la variabile `DOMHOUSE_LOCK_HELD=1`, l'unica ammessa nell'ambiente pulito oltre a `PATH`: gli script allora non lo riprendono. Lanciati a mano, gli script lo prendono come oggi. `broker-vm.sh check` (dentro `check-all`, ogni 5 minuti) non lo prende mai: lo prendono solo i comandi che cambiano qualcosa. Così `crea_motore` (`install` più `add-apartment`) e `togli_motore` (che finisce con `remove-apartment`) non si fermano su sé stessi.
4. **Secret Manager:** per ogni appartamento **solo due segreti**, la chiave del motore e il conto del connector. Il server ha bisogno della chiave in chiaro per chiamare il motore; il motore ha bisogno della password del connector.
5. **Le password dei dispositivi non si conservano da nessuna parte (D-233).** Restano solo le loro impronte: in Firestore (la fonte) e nel file dei dispositivi dell'appartamento sulla VM, che il broker legge (§2.5).

## 2. Nomi e ambienti

### 2.1 Id

| Cosa | Regola | Esempio |
|---|---|---|
| Appartamento di **produzione** | **generato dal server**, mai scelto dal cliente: `a-` più 8 caratteri casuali `[a-z0-9]`. Il nome visibile resta libero | `a-k3f9x2qm` |
| Appartamento di **staging** | `lab-…` o `test-…`, poi `^[a-z0-9][a-z0-9-]{2,63}$`; scelto dal gestore della piattaforma | `lab-02` |
| `dev` | esiste, resta com'è (D-118); **escluso da ogni ordine** salvo `stato` e `capienza` | — |
| Dispositivo | `^[a-z0-9][a-z0-9-]{0,63}$` (gli id Shelly lo sono già) | `shellyplugmg3-9070695cb0d0` |

**Nessun id contiene `_` né `.`**. Agente, server e `engine-vm.sh` usano le stesse regole: niente maiuscole. Il punto separa appartamento e dispositivo nel nome utente del broker (`<apt>.<device>`); il trattino basso resta escluso anche se, con D-233, non c'è più un segreto per dispositivo da separare.

**Vietato finché esiste un segreto della forma vecchia:** un id di appartamento che finisce con `-devices`. Oggi c'è solo `langbrain-shelly-lab-01-devices`, da migrare (§9).

### 2.2 Segreti

| Segreto | Nome | Chi lo legge |
|---|---|---|
| Chiave del motore | `langbrain-api-key-<apt>` (nome di oggi: lo usa il server per chiamare il motore) | il server e la VM |
| Conto del connector | `langbrain-shelly-<apt>` | solo la VM (lo scrive nel file della chiave del motore) |

**Nessun segreto per i dispositivi** (D-233): le loro password non si conservano (§2.5). Il segreto vecchio `langbrain-shelly-lab-01-devices` resta solo per `lab-01`, finché non si migra (§9.7).

**Ogni segreto si crea con parametri fissi, scritti nel codice e provati:**

- replica `user-managed` solo in `europe-west8`;
- nessun `expireTime`, nessun `topics`, nessuna chiave CMEK;
- etichette `domhouse-env`, `domhouse-apt`, `domhouse-op`;
- **ritardo di distruzione di 7 giorni** (`version_destroy_ttl`). Una versione «distrutta» diventa subito disattivata e illeggibile, e per 7 giorni si può ancora riattivare dopo un incidente. Da verificare con la prova 1125.

**Prima di creare un segreto** il server scrive in Firestore l'intenzione (op_id e nome). Se cade fra la creazione e la scrittura dell'esito, il segreto non risulta «suo»: con gli id casuali se ne genera un altro, e il controllo degli orfani trova quello rimasto.

**Un segreto che esiste già** si riusa solo se due condizioni valgono entrambe:

1. il Firestore di quell'ambiente registra di averlo creato lui (op_id);
2. i metadati (`secrets.get`, senza leggere il valore) coincidono: replica, nessun `expireTime`, `topics` o CMEK, etichette.

Altrimenti: errore, allarme, nessuna versione aggiunta.

### 2.3 Condizioni IAM (testo esatto; numero del progetto 444239063209)

`resource.name` di un segreto è `projects/444239063209/secrets/<nome>`, e quello di una versione ha in più `/versions/N`. La forma con il numero è **da confermare con la prova 1125**, che prova anche quella con l'identificativo.

**Due condizioni per ambiente, mai una sola:** la condizione «versioni» copre i due segreti dell'appartamento (chiave del motore e conto del connector); la condizione «lettura» copre **solo** le chiavi dei motori. Così il server non legge mai la password del connector. Le password dei dispositivi non sono in Secret Manager.

**Staging, «versioni»** (ruoli «creazione» e «versioni»):

```
resource.name.startsWith("projects/444239063209/secrets/langbrain-shelly-lab-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-shelly-test-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-lab-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-test-")
```

**Staging, «lettura»** (`secretAccessor`):

```
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-lab-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-test-")
```

**Produzione, «versioni»:**

```
resource.name.startsWith("projects/444239063209/secrets/langbrain-shelly-a-") ||
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-a-")
```

**Produzione, «lettura»:**

```
resource.name.startsWith("projects/444239063209/secrets/langbrain-api-key-a-")
```

Le chiavi di `dev` e `lab-01` restano lette con i permessi segreto per segreto di oggi.

**Prefissi positivi per tutti e due gli ambienti**, con il trattino. Nessuno dei due copre `dev`, `devon-01`, `labrador` o un id maiuscolo.

**Alla prova 1125 vanno aggiunti questi casi negativi**, con un segreto vuoto ciascuno:

- `langbrain-shelly-labrador`;
- `langbrain-shelly-devon-01`;
- `langbrain-shelly-LAB-01`;
- `langbrain-shelly-dev_01`;
- e un caso di lettura: un account con la sola condizione «lettura» non legge un segreto `langbrain-shelly-test-…`.

### 2.4 La prova di carico

Oggi crea appartamenti `carico-NN` con segreti leggibili dallo staging (`scripts/load/ambiente.py`).

- Si rinominano in `test-carico-NN`, nello staging.
- Prima si cancellano i segreti `langbrain-api-key-carico-*` rimasti.
- Le sue porte passano a **8170–8199** (§5.3).

### 2.5 Le password dei dispositivi: solo l'impronta (D-233)

**Perché basta.** Mosquitto conserva e confronta solo impronte. Oggi `broker_accounts.py` legge la password in chiaro solo per calcolarne l'impronta (`$7$`, PBKDF2-SHA512, 1000 iterazioni, sale di 12 byte, il formato di Mosquitto). La stessa funzione, `hash_password`, la può usare il server.

| Passo | Dove | Cosa succede |
|---|---|---|
| 1. Nasce la password | **il server**, quando il cliente registra uno Shelly o preme «Rigenera» | `secrets.token_urlsafe(24)`: 32 caratteri, 192 bit casuali. **Sempre generata dal sistema, mai scelta da una persona**: con una password umana l'impronta si potrebbe invertire per tentativi |
| 2. Si calcola l'impronta | il server | `hash_password`, la stessa funzione di `broker_accounts.py`. Una prova automatica controlla che l'impronta del server la accetti il broker vero (`tests/broker_container_test.py`) |
| 3. Si salva l'impronta | Firestore, documento del dispositivo, in una transazione | impronta, versione, op_id, stato («in attesa del broker»). **Mai la password** |
| 4. Il cliente la vede una volta | la risposta di quella sola chiamata; nell'app una finestra con «Copia» | poi sparisce; §8.1 |
| 5. L'impronta arriva al broker | ordine `aggiorna_broker` (§3) con l'elenco completo dei dispositivi dell'appartamento e le loro impronte | l'agente la scrive nel file dei dispositivi, poi il `sync`. Un'impronta nel messaggio non è un segreto: senza la password non serve a entrare |
| 6. Il broker la carica | `sync` isolato per appartamento (E-33): il conto del connector da Secret Manager, i dispositivi dal file delle impronte | ricarica con SIGHUP |

**Il file dei dispositivi** sta in `/etc/domhouse/_broker/devices/<apt>`: di root, permessi 600, una riga `<device> <impronta>` per dispositivo. Lo scrive solo l'esecutore, in modo atomico.

**Se la VM si perde:** il file torna dallo snapshot del disco, oppure il server rimanda le impronte che ha in Firestore con un `aggiorna_broker`.

**Rischi:**

1. chi può scrivere Firestore come il server (un server compromesso) può mettere l'impronta di una password che conosce e fingersi quel dispositivo. Era lo stesso con `versions.add` sul segreto per dispositivo: **rischio pari**;
2. le impronte in Firestore sono leggibili da più persone dei segreti (console). Con password casuali di 192 bit non si invertono. PBKDF2 con 1000 iterazioni è debole solo per password umane, che il sistema non ammette;
3. la password resta **dentro lo Shelly**, che la usa per collegarsi. **Da verificare con Youssouf** (domanda 8 del messaggio del 16 novembre): se la pagina web locale dello Shelly la mostra o la lascia leggere a chi sta sulla stessa rete Wi-Fi, per esempio gli ospiti. Se sì, va protetta la pagina locale (password dello Shelly): è un punto della «sicurezza in appartamento», non di questo progetto;
4. **pubblicare nella coda degli ordini equivale a poter creare un utente del broker.** `aggiorna_broker` porta le impronte: chi mette lì l'impronta di una password che conosce si collega come quel dispositivo. Oggi nella coda «ordini» di un ambiente può pubblicare solo il server di quell'ambiente (§4.1), quindi il rischio è pari a «server compromesso». **Condizione da non allargare mai:** nessun altro account, persona o servizio riceve `pubsub.publisher` sulle code «ordini». Si controlla in ogni revisione dei permessi IAM, con il comando di sola lettura che elenca chi ha quel ruolo sulle due code.

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
| `crea_motore` | `apartment_id`, porta | scrive **prima** il catalogo vuoto in `/etc/domhouse/<apt>.catalog.yaml` (se mancasse, al `compose up` Docker creerebbe al suo posto una cartella), poi installa il motore (`CONNECTOR=shelly`, `ENV`), poi `add-apartment` sul broker | **porta:** intero `^[1-9][0-9]{3,4}$`; per lo staging **solo 8150–8159**; assente da ogni `/opt/domhouse/*.settings` dei due ambienti e da `ss -ltn` (i motori della prova di carico, creati dallo script, si vedono solo con `ss`: le fasce sono separate). **Immagine:** non è un parametro, né per la produzione né per lo staging: quella approvata nella configurazione dell'agente, per digest. **Capienza:** §7. Se l'appartamento esiste già con gli stessi parametri: riuscito, senza rifare niente; con parametri diversi: rifiuto |
| `aggiorna_motore` | `apartment_id` | porta il motore all'immagine approvata (`engine-vm.sh update`) | stessi controlli dell'immagine |
| `aggiorna_broker` | `apartment_id`, **elenco completo** dei dispositivi dell'appartamento, ciascuno con la sua **impronta** (D-233) | sostituisce, in modo atomico, `/etc/domhouse/_broker/devices/<apt>` (di root, 600) e lancia il `sync`. Un dispositivo che non è nell'elenco perde il suo utente: è così che funzionano «Rigenera» e «Revoca» (§8.1) | ogni id con la regola del §2.1; ogni impronta nel formato di Mosquitto, controllato con l'espressione `^\$7\$[0-9]{3,6}\$[A-Za-z0-9+/]{16}\$[A-Za-z0-9+/]{86}==$`; al massimo 200 dispositivi; **mai** una password in chiaro (un campo che non è un'impronta valida fa rifiutare l'ordine intero) |
| `applica_catalogo` | `apartment_id`, catalogo, versione | §3.1 | versione più alta dell'ultima applicata |
| `stato` | `apartment_id` | `/health` del motore e immagine in uso | ammesso anche per `dev` |
| `togli_motore` | `apartment_id` | §8.2 | ripetibile: «già tolto» vale come riuscito |

**Un'ottava operazione, solo per l'opzione 2 (non fa parte dell'opzione 1):** `cambia_password`, per il cambio automatico al primo collegamento.

- La password nuova la genera **l'agente sulla VM**, la scrive nello Shelly con `MQTT.SetConfig` (come R2 della tappa A), aggiorna il file delle impronte, fa il `sync` e riavvia lo Shelly (come R3 ed R4).
- Al server restituisce **solo l'impronta**: la password non lascia mai la VM.
- **Da verificare con Youssouf** e con la sezione 4 della tappa A di oggi: che ogni modello ammesso accetti `MQTT.SetConfig` arrivato via MQTT, e che una password di 32 caratteri vada bene a tutti (per la Plug M Gen3 va bene: è quella di oggi).

**L'immagine, in ogni caso**, deve seguire la regola ancorata:

`^europe-west8-docker\.pkg\.dev/domotica-poc-511707/domotica/engine(:[0-9a-f]{7,40}|@sha256:[0-9a-f]{64})$`

- La controllano sia l'agente sia `engine-vm.sh`: difesa doppia.
- `registry_login` rifiuta ogni host diverso da `europe-west8-docker.pkg.dev`.
- `update` non usa più l'immagine dentro `sed "s#…#…#"`.
- Lo staging e la produzione usano tutti e due l'immagine della configurazione dell'agente. L'immagine di prova si cambia nella configurazione, di root: meno superficie.

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
| «creazione» | `secretmanager.secrets.create` | il §2.3 del suo ambiente, **se la prova 1125 riesce**. Se fallisce: nessuna condizione per la produzione, che però non riusa mai un segreto non suo (§2.2); **nessuna creazione per lo staging**, i cui segreti di prova li prepariamo noi. Con D-233 si creano solo due segreti per appartamento, una volta, alla creazione |
| «versioni» | `secretmanager.versions.add`, `secretmanager.versions.list`, `secretmanager.versions.destroy`, `secretmanager.secrets.get` | il §2.3 del suo ambiente. Servono solo alla creazione dell'appartamento (prima versione) e alla sua eliminazione (distruzione con ritardo): **non** a «Rigenera» né a «Revoca» |
| lettura delle chiavi dei motori | `secretmanager.secretAccessor` | solo `langbrain-api-key-…` del suo ambiente |
| impronte dei dispositivi | i permessi di Firestore che il server ha già | il documento del dispositivo, nel database del suo ambiente. Nessuno dei client legge Firestore (regole di produzione di oggi) |
| ordini | `pubsub.publisher` | solo la sua coda «ordini» |

**Mai** al server: `versions.access` sulle password, `versions.enable`, `secrets.update`, `secrets.delete`, `secrets.setIamPolicy`, `secrets.getIamPolicy`.

- **Nessun account di servizio riceve `secrets.delete`.**
- I segreti rimasti vuoti dopo un'eliminazione, e gli orfani, li cancella **uno script che il committente lancia una volta al mese con il suo account** (D-116). Lo script elenca i segreti `langbrain-*` senza appartamento o dispositivo nei due Firestore, oppure vuoti da oltre 30 giorni, li mostra e chiede conferma prima di cancellare.
- Lo stesso elenco, in sola lettura, gira anche nel controllo periodico e dà un allarme se trova orfani.

**Registri di accesso ai dati di Secret Manager** attivi, con allarmi su:

- raffiche di `DestroySecretVersion`;
- ogni accesso negato a un server su `langbrain-shelly-*`.

**Registro delle impronte:** ogni impronta scritta, sostituita o tolta in Firestore lascia una riga nel registro amministrativo (chi, quale dispositivo, «generata», «rigenerata», «revocata»), mai l'impronta stessa né la password.

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
| `secretmanager.secretAccessor` | con condizione sul nome: i prefissi del §2.3 (chiave del motore e conto del connector) più quelli di oggi (`dev`, `lab-01`, compreso `langbrain-shelly-lab-01-devices` fino alla migrazione). Nessun permesso nuovo con D-233: le impronte arrivano negli ordini |
| quelli di oggi | Artifact Registry Reader, Logs Writer, Monitoring Metric Writer, «Creatore di token» su `domhouse-dns-lab@` (per lego) |

**Il token della VM non deve essere raggiungibile dai container.** È un difetto di oggi (E-31), da correggere per conto suo, prima dello strumento A, con la prova rossa scritta prima (§9.1):

1. **Una tabella nftables propria**, `inet domhouse_metadata`, aggancio `forward`, priorità -10, come quella del limite del broker. Scarta per **destinazione** `169.254.169.254` tutto il traffico inoltrato, cioè quello di **tutte** le reti di Docker: `docker0`, i ponti `br-…` dei progetti Compose dei motori, la rete interna del broker. Se la VM ha IPv6, una seconda regola per l'indirizzo IPv6 dei metadati (da verificare sulla VM). Il traffico dei processi dell'host (lettore, esecutore, Ops Agent, script) non passa dall'inoltro e non viene toccato.
2. **Caricata prima di Docker:** un servizio systemd con `Before=docker.service`, così a ogni avvio o riavvio di Docker non resta nessuna finestra. Docker non la tocca, perché non è la sua catena.
3. **Rimessa da sola:** se la tabella manca, il controllo ogni 5 minuti la rimette e scrive una riga, come fa già per il limite del broker («broker limit restored»).
4. **Provata una volta all'ora**, come `egress`: un container usa e getta sulla rete Compose di un motore (`--network domhouse-<apt>_default`), con l'immagine approvata del motore, prova a leggere la sola zona con un tempo massimo di 3 s. Se risponde, la riga è «metadata OPEN», con allarme email.
5. **lego** passa a `--network host`, restando con utente 1883, sola lettura e `cap_drop ALL`. Subito dopo si prova `broker-vm.sh cert-renew force`: lego deve ancora farsi dare il token.
6. In sola lettura si guarda il registro di controllo IAM per usi di `domhouse-dns-lab@` non fatti da lego. I token durano un'ora: se non risulta niente, non serve cambiare chiavi.

Il lettore e l'esecutore girano sull'host: per loro il token c'è.

**Raggio del token, accettato fino alla seconda VM:** chi è root sulla VM legge tutti i segreti dei prefissi e può far sparire gli ordini dello staging. Root sulla VM resta il confine; per questo §3.1 e §8.2 non leggono mai da root file che il motore può cambiare.

## 5. Separazione fra prova e produzione

1. **Code separate per ambiente.** L'agente sa l'ambiente dalla sottoscrizione.
2. **Prefissi positivi** (§2) per segreti e appartamenti, più `ENV` nel file delle impostazioni.
3. **Fasce di porte** (accettate dal revisore il 15 novembre):
   - produzione 8101–8149;
   - staging creato dall'app 8150–8159: l'agente ammette **solo** queste per un `crea_motore` dello staging;
   - `lab-01` resta su 8169;
   - prova di carico 8170–8199, creata dal suo script;
   - `INSTANCE_ALLOWED` dello staging diventa `10.198.0.2:8100,10.198.0.2:8150-8199`, nella forma che il server legge. È più largo della fascia dell'agente perché il server deve raggiungere anche `lab-01` e la prova di carico; non comprende nessuna porta della produzione.
4. **La produzione non manda ordini alla VM condivisa:** la sottoscrizione degli ordini della produzione non si crea su `langbrain-dev`, e il server di produzione non ha `publisher`. La regola «seconda VM prima del primo appartamento vero» la impone la tecnica.
5. **Nello staging creano ed eliminano appartamenti solo i gestori della piattaforma**, non gli amministratori dei clienti: Firebase Authentication è condiviso.
6. **Numero massimo di motori dello staging nell'agente:** 4, `dev` e `lab-01` compresi (accettato). Il numero da solo non protegge la memoria: **la somma dei tetti di memoria dei motori dello staging resta sotto circa 500 MB** (per esempio `mem_limit` 128 MB, se la misura lo permette). In più il rifiuto per capienza conta anche quella somma, non solo `MemAvailable`. La prova di carico resta fuori dal limite: si fa di notte, con la sua procedura.
7. **Seconda VM:** un account di servizio per VM, ciascuno con la lettura dei soli segreti del suo ambiente; un broker per VM; la regola dei prefissi resta come seconda difesa.
8. **Rischio accettato per iscritto fino alla seconda VM:** lo staging può disturbare (blocco unico, memoria) i motori di produzione già esistenti. Oggi non ce ne sono (D-134).

## 6. Se un ordine fallisce a metà

1. **Un solo esecutore per tutta la VM**, un ordine alla volta, con priorità alla produzione quando ci sarà. Il blocco di `engine-vm.sh` è già unico per la VM; `broker-vm.sh` prende lo stesso blocco.
2. **Giornale sulla VM:** «ricevuto» e «in corso» si scrivono **prima** di eseguire. Un doppione di un ordine in corso o finito si ignora, e si ripubblica l'esito registrato.
   - **Dopo un riavvio della VM** l'ordine già confermato non torna da Pub/Sub. All'avvio il lettore pubblica «fallito: interrotto» per ogni voce del giornale non chiusa e non la riesegue: c'è «Riprova».
3. **Conferma subito, risultato sulla seconda coda:** il lettore conferma l'ordine appena l'ha scritto nel giornale. Il tempo di conferma di Pub/Sub non conta più.
4. **Sequenza:** `seq` per appartamento (§3); chiave d'ordine di Pub/Sub = `apartment_id`, come aiuto e non come garanzia.
   - Il file di root con l'ultima `seq` applicata **resta per sempre**, anche dopo `togli_motore`, come una lapide: pochi byte. Così un `crea_motore` vecchio, con una `seq` più bassa e ancora entro i 15 minuti, non ricrea un appartamento appena eliminato.
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

### 8.1 Registrare un dispositivo, «Rigenera», «Revoca» (D-233)

**Comune a tutte e tre:**

- un **blocco per dispositivo** in Firestore (transazione): due «Rigenera» insieme non si scavalcano, perché la seconda trova la versione cambiata e si ferma;
- l'ordine `aggiorna_broker` porta **sempre l'elenco completo** delle impronte dell'appartamento, preso da Firestore dentro la transazione, con una `seq` nuova: un ordine vecchio non può rimettere un'impronta tolta (§6.4).

**Registrare uno Shelly** (nel modulo del catalogo, alla riga del dispositivo):

1. il server genera la password e ne salva l'impronta (§2.5), stato «in attesa del broker»;
2. la mostra **una volta** nell'app, con i valori da copiare nella pagina dello Shelly (§14 del documento interno);
3. manda `aggiorna_broker`; al risultato riuscito lo stato diventa «pronto»: da lì lo Shelly può collegarsi.

**«Rigenera»** (una password persa prima di copiarla, o da cambiare):

1. stesso percorso: password nuova, impronta nuova al posto della vecchia, mostrata una volta;
2. **stato «cambio in corso»** finché non arriva il risultato riuscito di `aggiorna_broker`. Fino ad allora la password vecchia vale ancora sul broker, e l'app non dice «cambiata». Allarme se non arriva;
3. lo Shelly va riconfigurato con la password nuova, sul posto o in sede.

**«Revoca»** (un dispositivo perso, rubato, o tolto dall'impianto):

1. il server toglie l'impronta da Firestore (lo stato resta, «revocato», per il registro) e manda `aggiorna_broker` senza quel dispositivo;
2. **stato «revoca in corso»** finché non arriva il risultato riuscito; poi «revocato»;
3. per rimettere lo stesso Shelly serve una registrazione nuova, con una password nuova.

**Da verificare (nostro, sul broker vero, prima del codice):** se una ricarica di Mosquitto con un utente tolto o con un'impronta cambiata **fa cadere** il collegamento già aperto da quell'utente.

- Se non lo fa cadere, un dispositivo revocato, o chi usa una password trapelata, resta collegato fino al prossimo ricollegamento.
- In quel caso «Revoca» e «Rigenera» devono anche chiudere quel collegamento: un riavvio del broker (fa ricollegare tutti), oppure il plugin di sicurezza dinamica di Mosquitto, da valutare.
- Si prova in `tests/broker_container_test.py`.

**Dove la password non deve restare:**

- mai nei registri, né nell'ordine Pub/Sub, né in Firestore, né in una risposta salvata per i tentativi: una seconda chiamata dice «già generata, usa Rigenera»;
- nel sito solo in memoria nel componente, `autocomplete="off"`, mai nell'URL, in `localStorage` o nella cache delle query;
- nella guida, l'avvertenza sugli appunti sincronizzati.

**Il `sync` del broker è isolato per appartamento** (E-33, fatto il 15 novembre): se il segreto del connector di un appartamento non si legge, o il suo file delle impronte è malformato, si tengono le sue righe di prima (o le si toglie, se è in eliminazione), si aggiornano gli altri, e una riga d'allarme dice quale. La VM non elenca segreti: i dispositivi li legge dal file delle impronte.

**Limiti di frequenza** per organizzazione su registrazioni, «Rigenera», «Revoca» ed eliminazioni: ognuno fa un `sync` e una ricarica del broker.

### 8.2 Eliminazione

1. **Chi:** l'amministratore dell'organizzazione del cliente, entro un massimo fissato dal gestore della piattaforma. Nello staging solo il gestore (§5.5).
2. **Prima «Disattiva»** per un periodo fissato. Email al gestore e agli altri amministratori dell'organizzazione a «Disattiva» e a «Elimina».
3. **Conferma** scrivendo il nome, con il testo:
   - **si perde subito:** la configurazione, il motore, le credenziali dei dispositivi. Dopo un recupero ogni Shelly va riconfigurato sul posto con password nuove;
   - **resta:** prenotazioni e riepiloghi per 12 mesi, registro amministrativo per 24, lo storico del motore per il tempo della scelta qui sotto.
   - Va scritto anche nell'informativa sulla privacy: compito della memoria storica.

**Scelta per il committente: quanto resta recuperabile lo storico di un appartamento eliminato.** Gli snapshot fatti **prima** dell'eliminazione contengono comunque `engine.db` e restano 30 giorni.

| Scelta | Durata reale | Cosa comporta |
|---|---|---|
| **c. Nessuna copia: recupero solo dagli snapshot** (consiglio del revisore, e mio) | 30 giorni | meno codice (niente `/data/_deleted`, niente timer, niente copia come utente 10001), meno copie di dati personali; il recupero è più pesante (disco dallo snapshot), ma è un caso raro dopo «Disattiva», la conferma con il nome e gli avvisi |
| a. Copia sul disco di avvio | fino a 60 giorni | accettabile solo se dichiarata nel testo di conferma e nell'informativa, con lo scopo |
| b. Copia su un disco a parte senza snapshot | circa 30 giorni | sconsigliata: un disco in più da gestire per nessun guadagno reale |

I passi 5.1 e 6 qui sotto valgono solo con la scelta (a).
4. **Ordine imposto dal server**, con «Riprova» e lo stato dell'ultimo passo:
   1. `togli_motore` riuscito (toglie anche il file delle impronte dell'appartamento e i suoi utenti del broker);
   2. distruzione, con ritardo, delle versioni dei **due** segreti dell'appartamento (chiave del motore e conto del connector);
   3. eliminazione in Firestore (`remove_apartment`), comprese le impronte dei dispositivi: la porta si libera solo qui.
5. **`togli_motore`, tutto sotto il blocco**, ogni passo saltato senza errore se è già fatto:
   1. (solo con la scelta a) copia coerente del database **prima** di fermare il motore: backup in linea di SQLite e `PRAGMA integrity_check`, eseguiti **come utente 10001** (`setpriv --reuid=10001 --regid=10001 --clear-groups`), così anche `-wal` e `-shm`, che SQLite apre da solo, non seguono link verso file di root. L'utente 10001 non può scrivere in `/data/_deleted`: scrive la copia su stdout, e root la salva con `umask 077` in `/data/_deleted/<apt>-<data>.db` (cartella di root 700, file di root 600);
   2. `compose down`;
   3. tolto `/opt/domhouse/<apt>.settings` (il controllo ogni 5 minuti e l'avvio non lo vedono più);
   4. tolti `/etc/domhouse/<apt>.env`, `.settings.env`, `.catalog.yaml`;
   5. tolto `/data/<apt>`, backup compresi;
   6. `remove-apartment` sul broker e il suo file dei dispositivi.
   7. Il file della `seq` dell'appartamento **resta** (§6.4).
6. (solo con la scelta a) Un timer cancella i file di `/data/_deleted` con più di 30 giorni, compresi `-wal` e `-shm`, e scrive una riga per ogni file tolto.
7. **Recupero:** dagli snapshot, entro 30 giorni (scelta c), oppure anche dalla copia (scelta a). Procedura scritta, lanciata da noi. I dispositivi vanno riconfigurati con password nuove.

## 9. Cosa cambia nel codice di oggi (dopo la fine delle prove con Youssouf)

1. **Subito, vale già oggi (E-31), per conto suo e prima dello strumento A:** la tabella dei metadati del §4.3, con la prova rossa scritta e committata per prima. Prima la richiesta della sola zona da dentro `engine-dev` ed `engine-lab-01` (oggi risponde) e la riga oraria del controllo (oggi «metadata OPEN»); poi la tabella; poi lego in `--network host` e `cert-renew force`. Insieme: il backup notturno che non segue link in `/data/<apt>` e il `sync` isolato per appartamento, che sono difetti di oggi anche loro.
2. `engine-vm.sh`:
   - regole degli id e dell'immagine;
   - `registry_login` ancorato;
   - `ENV` nelle impostazioni (`dev` e `lab-01` aggiornati una volta, a mano);
   - catalogo in `/etc/domhouse`;
   - comando `remove`;
   - `backup` senza seguire link;
   - porte normalizzate e confrontate.
3. `broker-vm.sh`: `remove-apartment` ripetibile; un blocco; file delle impronte dei dispositivi.
4. `broker_accounts.py` (D-233): i dispositivi dal file delle impronte, prese così come sono; il conto del connector da Secret Manager, come oggi. Il `sync` isolato per appartamento c'è già (E-33). Per un appartamento senza file delle impronte resta il segreto vecchio `-devices` (solo `lab-01`, fino alla migrazione).
5. `engine/compose.yaml`: tetto di memoria e contenitore più chiuso; catalogo in sola lettura.
6. `scripts/load`: appartamenti `test-carico-NN`, porte 8170–8199.
7. **Migrazione di `lab-01`** dal segreto `-devices` al file delle impronte, con la stessa password: la Plug non cade.
   - La VM calcola l'impronta dalla password che legge oggi e la scrive nel file; il `sync` dice «unchanged», perché l'impronta corrisponde.
   - Poi il segreto `-devices` si svuota e, dopo qualche giorno, si cancella.
   - Procedura scritta a parte, dopo il cambio di password della tappa A.

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

### 10.1 Seconda lettura del revisore (15 novembre, 11:11): «si può cominciare il codice»

| Punto | Esito |
|---|---|
| S1.1, condizione unica per lettura e versioni | corretto in §2.3 (due condizioni per ambiente; caso di lettura negativo nella prova 1125) |
| S1.2, intenzione prima della creazione | corretto in §2.2 |
| S1.3 e S2.3, confine fra lettore ed esecutore; catalogo prima del `compose up` | corretto in §1.3 (socket, `SO_PEERCRED`, controlli ripetuti, `prod` rifiutato sulla VM condivisa) e §3 `crea_motore` |
| S1.4 e S5, regola dei metadati | corretto in §4.3 e §9.1 (destinazione su tutte le reti di Docker, tabella propria prima di Docker, rimessa dal controllo, IPv6, prova oraria dalla rete Compose, `cert-renew force`, registro IAM) |
| S1.6 e S2.4, immagine dello staging | corretto in §3: nessun parametro immagine, nemmeno per lo staging |
| S1.10 e S2.2, ordini interrotti e sequenza dopo l'eliminazione | corretto in §6.2 e §6.4 |
| S1.13, chi cancella vuoti e orfani | corretto in §4.1 (script mensile del committente, nessun account di servizio con `secrets.delete`) |
| S1.15, `setpriv` e `/data/_deleted` | corretto in §8.2.5 |
| S2.1, il blocco che si ferma su sé stesso | corretto in §1.3 (blocco preso una volta dall'esecutore, `DOMHOUSE_LOCK_HELD`, `check` senza blocco) |
| S3.1, porte | accettate, scritte in §5.3 e §3 |
| S3.2, 4 motori di staging | accettato, con la somma dei tetti di memoria in §5.6 |
| S3.3, storico eliminato | scelta per il committente in §8.2.3; consiglio (c) |

### 10.2 I sette punti «corretti in parte»: stato finale

| N. | Stato | Motivo (dalla seconda lettura del revisore) |
|---|---|---|
| 1 | **chiuso** | mancavano le due condizioni separate, perché il `secretAccessor` del server non coprisse anche `langbrain-shelly-`: ora §2.3 ne ha due per ambiente, e la prova 1125 ha il caso di lettura negativo |
| 3 | **chiuso** | mancavano il confine fra lettore ed esecutore e il catalogo prima del `compose up`: ora §1.3 (socket, `SO_PEERCRED`, controlli ripetuti, `prod` rifiutato) e §3 `crea_motore` |
| 4 | **chiuso** | la regola dei metadati andava precisata in sei punti: ora §4.3 e §9.1. Il codice si prepara con la prova rossa per prima (E-31) |
| 6 | **chiuso** | c'era una contraddizione sull'immagine dello staging: scelta la proposta del revisore, nessun parametro immagine per nessun ambiente (§3) |
| 10 | **chiuso** | mancavano lo stallo del blocco, gli ordini interrotti da un riavvio e la `seq` dopo l'eliminazione: ora §1.3, §6.2 e §6.4 |
| 13 | **chiuso** | non era scritto chi cancella vuoti e orfani, e con quale identità: ora §4.1, con uno script mensile del committente e nessun account di servizio con `secrets.delete` |
| 15 | **chiuso** | `setpriv` contro `/data/_deleted` di root: ora §8.2.5 (copia su stdout, salvata da root). Con la scelta (c) del §8.2.3 la copia non serve affatto |

Nessun punto «accettato così»: tutti e sette sono corretti come chiedeva il revisore.

### 10.3 Terza stesura (16 novembre): impronte al posto del segreto per dispositivo (D-233)

**Cosa è cambiato**, da far rileggere a una revisione di sicurezza:

| Sezione | Prima (D-230) | Ora (D-233) |
|---|---|---|
| §1.4–1.5, §2.2 | un segreto per dispositivo | solo due segreti per appartamento; le password dei dispositivi non si conservano |
| §2.5 (nuova) | — | dove nasce la password, l'impronta, come arriva al broker, i rischi |
| §2.3 | condizioni anche per i segreti dei dispositivi | le stesse condizioni, che ora coprono solo chiave del motore e conto del connector |
| §3 `aggiorna_broker` | id dei dispositivi | id e impronte, con il controllo del formato; nessuna password nei messaggi |
| §3 `cambia_password` (nuova, solo opzione 2) | il cambio automatico passava da Secret Manager | lo fa l'agente; al server torna solo l'impronta |
| §4.1 | versioni dei segreti dei dispositivi aggiunte e distrutte a ogni «Rigenera» | versioni solo alla creazione e all'eliminazione dell'appartamento; impronte in Firestore, con il registro |
| §4.3 | — | nessun permesso nuovo alla VM |
| §8.1 | «Rigenera» con versioni e distruzione | registrazione, «Rigenera» e «Revoca» con le impronte in Firestore e l'elenco completo in ogni `aggiorna_broker` |
| §8.2 | distruzione dei segreti dei dispositivi | distruzione dei due segreti; le impronte si tolgono con l'appartamento |
| §9.4, §9.7 | segreti per dispositivo, migrazione verso di essi | file delle impronte, migrazione verso di esso |

**Punti della prima revisione che cambiano:**

- **13** (distruzione di massa): più piccola, perché ci sono due soli segreti per appartamento;
- **14** («Rigenera» in corsa): non si basa più sulle versioni di Secret Manager, ma sul blocco in Firestore e sull'elenco completo.

**Condizione da non allargare mai (rilettura della memoria storica, 1230f81):** con D-233 la coda «ordini» porta le impronte, quindi chi vi pubblica può creare un utente del broker (§2.5, rischio 4). Solo il server del suo ambiente pubblica in quella coda; nessun altro `pubsub.publisher`, mai. Va controllato in ogni revisione dei permessi IAM.

**Da verificare prima del codice:**

1. **nostro:** se la ricarica del broker fa cadere un collegamento il cui utente è stato tolto o cambiato (§8.1);
2. **con Youssouf:** la pagina locale dello Shelly e la password del broker (§2.5, rischio 3); `MQTT.SetConfig` via MQTT e password di 32 caratteri su tutti i modelli ammessi (§3, `cambia_password`, solo opzione 2).
