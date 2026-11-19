# Proposta: A2, il posto dell'appartamento dall'app

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta con le risposte del committente** (scritta il 17 novembre 2026; risposte 1161–1168 del 19 novembre nel §9). Nessun codice | o1 | `docs/progetto-strumento-a-base.md` §2.1, §2.2, §2.3, §3 (`crea_motore`), §4, §5, §6, §7; registro, pacchetto A2 e D-232; documento interno dell'Autonomia, §2 passo 4; il codice di A1 e la PR #17 (catalogo vuoto, `ce31e08`) | revisione di sicurezza del 19 novembre, seconda e terza lettura: **eseguibile** dopo N8, scritto qui (§5.2, §11); A3 prima (porta le firme e l'unità dell'esecutore); poi il codice |

**Cosa copre:** creare dall'app il «posto» di un appartamento: id, porta libera, i due segreti, il motore con l'elenco dei dispositivi vuoto, l'account del connector sul broker, il collegamento del motore all'appartamento. Le rotte del server, l'ordine `crea_motore` passo per passo con il ritorno indietro, stati ed errori, cosa mostra il sito.

**Cosa non copre:** l'elenco dei dispositivi (A4), le credenziali dei dispositivi (A3), l'eliminazione (A6), la capienza come allarme (A7), la seconda VM (A10).

**Vincoli di oggi, da rispettare:**

1. **Solo nello staging fino alla seconda VM** (progetto §5.4): la produzione non manda ordini alla VM condivisa. In produzione la rotta risponde 503 finché A10 non c'è.
2. **Chi crea:** solo il gestore della piattaforma (D-64, D-77; risposta 1 = a). Il permesso sta in un punto solo, così cambia con una riga. In futuro creerà L (Leonardo, Italianway), che con Scarantino è il cliente: il suo ruolo si decide con D-232.
3. **Codice:** A1 è installato sulla VM e la finestra del passo 3 è chiusa (19 novembre): i due vincoli di prima non valgono più. Il codice parte dopo la revisione di sicurezza, le schermate di o2 e la decisione su R8 (§4.3).

## 1. In breve

1. Il gestore della piattaforma preme «Nuovo appartamento» in un'organizzazione e scrive nome, fuso orario e id (nello staging `lab-…` o `test-…`).
2. Il server, in quest'ordine: riserva l'id e una porta libera, crea i due segreti, chiede `capienza` all'agente, poi manda `crea_motore`.
3. L'agente scrive il catalogo vuoto, installa il motore, aggiunge l'appartamento al broker, risponde.
4. Il server collega l'appartamento al motore (indirizzo interno e porta), controlla `/health`: «Pronto».
5. Da lì: A3 (registrare gli Shelly), A4 (elenco dei dispositivi).

## 2. Le rotte del server

| Chiamata | Corpo | Risposta | Chi |
|---|---|---|---|
| `POST /app/platform/tenants/{tenant_id}/apartments/nuovo` | `{apartment_id, name, timezone, italianway_id?}` | **202** `{apartment, creazione}` | gestore della piattaforma (oggi) |
| `GET /app/platform/tenants/{tenant_id}/apartments/{apt}/creazione` | — | 200 `{creazione}` | come sopra |
| `POST …/apartments/{apt}/creazione/riprova` | `{version}` | 202 `{creazione}` | come sopra |
| `POST …/apartments/{apt}/creazione/annulla` | `{version}` | 202 `{creazione}` | come sopra; vedi §5.3 |

- **Perché una rotta nuova** e non `POST /tenants/{tenant_id}/apartments` di oggi: quella collega un appartamento a un motore **già esistente** (`instance_url` e porta scritti a mano) e serve ancora per `dev`, `lab-01` e gli appartamenti dimostrativi. La nuova non riceve né indirizzo né porta: li decide il server.
- Se D-232 passa, le stesse rotte anche sotto `/app/admin/apartments/…` per l'amministratore dell'organizzazione, con un numero massimo di appartamenti (risposta 2: rimandato a D-232).
- Tutte con `X-Correlation-Id`; descritte in `bff/API.md`. Il contratto del motore non cambia.

### 2.1 `creazione`

| Campo | Tipo | Note |
|---|---|---|
| `stato` | `in_preparazione` · `pronto` · `non_creato` · `annullamento_in_corso` · `annullato` | §6 |
| `passo` | `riserva` · `segreti` · `capienza` · `motore` · `collegamento` | l'ultimo raggiunto: il sito lo mostra come avanzamento |
| `version` | intero | per il blocco, come in A3 |
| `porta` | intero | quella riservata |
| `op` | `{op_id, stato, codice, messaggio}` o null | l'ultimo ordine all'agente; `op_id` è l'«ID richiesta»; `codice` quello del §6.3 (il sito ha i suoi testi per codice, `messaggio` è la riserva) |
| `fatti` | elenco fra `id`, `porta`, `segreti`, `motore`, `broker` | quello che esiste già: con `non_creato` il sito dice che cosa è rimasto a metà (risposta 7) |
| `updated_at`, `updated_by` | | nome visibile, mai l'email |

### 2.2 Cosa legge il sito (domande 19–26 di o2, 19 novembre; schermate in `docs/proposta-a2-sito.md`)

| N. | Richiesta di o2 | Risposta del server |
|---|---|---|
| 19 | il 429 con limite e ora | corpo `{error: "rate_limited", message, limite: 5, riprova_dal}` (`riprova_dal` ora UTC, ISO 8601) più l'intestazione `Retry-After` in secondi (§6.2) |
| 20 | il conto dell'ultima ora prima di aprire il modulo | in `GET /app/platform/tenants/{tenant_id}` (la scheda dell'organizzazione, da cui si apre il modulo) il campo `creazioni_ultima_ora: {usate, limite, libera_dal}`; `libera_dal` è null finché `usate < limite`. Nessuna rotta nuova |
| 21 | «Riprova» e «Annulla» non contano | sì (§6.2) |
| 22 | i conteggi per organizzazione | in `GET /app/platform/tenants` ogni riga ha `appartamenti_non_creati` e `appartamenti_in_preparazione` (0 se nessuno) |
| 23 | `creazione` in ogni appartamento | in `GET /app/platform/tenants/{tenant_id}/apartments` ogni appartamento ha `creazione` (§2.1, tutti i campi); `null` per gli appartamenti collegati a mano (`dev`, `lab-01`, i dimostrativi) |
| 24 | sapere prima del clic se la creazione c'è | in `GET /app/me`, nel blocco dell'ambiente, `creazione_disponibile`: `true` solo nello staging con l'agente configurato; `false` in produzione (fino ad A10) e senza agente. Il sito nasconde o disattiva «Nuovo appartamento»; il 503 resta come riserva |
| 25 | un appartamento non «Pronto» non compare nelle pagine dell'organizzazione | **sì, lo esclude il server**, in un punto solo: l'elenco degli appartamenti dell'organizzazione (`GET /app/apartments`, `GET /app/admin/apartments`, il selettore) non lo contiene, e ogni rotta per appartamento dell'organizzazione (dettaglio, proxy verso il motore, stream, riepiloghi, energia, permessi degli utenti) risponde 404 come per un id che non c'è. Lo vedono solo le rotte della piattaforma. Vale per `in_preparazione` e `non_creato`; un appartamento `pronto` e poi disattivato (D-201) resta com'è oggi |
| 26 | i testi per codice | li tiene il sito, per `op.codice` (§6.3); il `messaggio` del server resta come riserva |

## 3. Id, porta, segreti

### 3.1 L'id

- **Staging:** scelto dal gestore, `^(lab|test)-[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, al massimo 64 caratteri (la stessa regola dell'agente, `STAGING_ID_RE`). Mai `dev`, mai un id usato prima (`reserve_apartment_id` di oggi, D-67), mai uno che finisce con `-devices` (progetto §2.1).
- **Produzione** (dopo A10): generato dal server, `a-` più 8 caratteri casuali `[a-z0-9]`; il nome visibile resta libero (risposta 4 = a).

### 3.2 La porta libera

1. Fasce (progetto §5.3): staging **8150–8159**, produzione 8101–8149.
2. Il server sceglie la porta più bassa della fascia che non è in nessun appartamento del **suo** Firestore e non è riservata da una creazione in corso, e la **riserva in modo atomico** (lo stesso meccanismo di `claim_link` di oggi, chiave `10.198.0.2:<porta>`).
3. L'agente ricontrolla sulla VM, prima di installare: la porta è nella fascia dell'ambiente, assente da ogni `/opt/domhouse/*.settings` e da `ss -ltn`. Se è occupata (per esempio da qualcosa installato a mano): rifiuto `porta_occupata`.
4. Con `porta_occupata` il server segna quella porta come «occupata sulla VM» e, a «Riprova», prende la successiva.
5. Fascia piena: **409 `no_free_port`** prima di creare qualsiasi cosa.
6. `INSTANCE_ALLOWED` dello staging copre già 8150–8199 (progetto §5.3): il server può raggiungere il motore nuovo.

### 3.3 I due segreti

| Segreto | Cosa contiene | Chi lo crea | Chi lo legge |
|---|---|---|---|
| `langbrain-api-key-<apt>` | la chiave del motore: `secrets.token_urlsafe(32)` | il server | il server (per chiamare il motore) e la VM (`write_key`) |
| `langbrain-shelly-<apt>` | la password del connector sul broker: `secrets.token_urlsafe(24)` | il server | **solo** la VM: il server può aggiungere la versione ma non leggerla (condizione «lettura» del progetto §2.3). Il server però la **genera**: «non la legge» vuol dire che dopo la creazione non la può più riavere, non che non l'abbia mai vista (revisione, punto 13) |

- **Parametri fissi** (progetto §2.2): replica `user-managed` in `europe-west8`; nessun `expireTime`, `topics`, CMEK; etichette `domhouse-env`, `domhouse-apt`, `domhouse-op`; ritardo di distruzione 7 giorni.
- **Prima** di creare: l'intenzione in Firestore (op_id e nome). Un segreto che esiste già si riusa solo se quel Firestore l'ha creato (stesso op_id) **e** i metadati coincidono; altrimenti 409 `secret_conflict` e allarme, nessuna versione aggiunta.
- Le password generate non passano per i log, né per l'ordine, né per Firestore: vanno solo in `versions.add`.
- **Permessi del server** (progetto §4.1): i ruoli «creazione» e «versioni» con le condizioni del §2.3, e la lettura delle sole chiavi dei motori. **I segreti fatti a mano di `lab-01` restano fuori** (revisione, punto 13): il prefisso `langbrain-shelly-lab-` copre anche `langbrain-shelly-lab-01` e `langbrain-shelly-lab-01-devices`, e `langbrain-api-key-lab-` copre `langbrain-api-key-lab-01`. Le condizioni «creazione» e «versioni» li escludono per nome esatto, nelle due forme (`…/secrets/NOME` e `…/secrets/NOME/`, per le versioni), così il server non può mai cambiare una password di `lab-01`. La prova 1125 è riuscita il 16 novembre; i ruoli veri si danno con i comandi del committente nella procedura di A2 (§7).

## 4. L'ordine `crea_motore`, passo per passo

### 4.1 Nel server

1. **Controlli:** permesso; id (§3.1); nome (1–80 caratteri); fuso orario; codice Italianway libero, se c'è; agente configurato (503 `agent_not_configured`); limite di frequenza (§6.2, `rate_limited`).
2. **Riserva** in una transazione: id (`reserve_apartment_id`), porta (§3.2), documento dell'appartamento con `creazione.stato` `in_preparazione`, `enabled: false`, nessun `instance_url`; nella stessa transazione l'ora della creazione nel conto dell'organizzazione (§6.2).
3. **Segreti** (§3.3). Un errore qui: `non_creato` con il passo `segreti`; «Riprova» riparte da qui.
4. **Capienza:** ordine `capienza`; se `MemAvailable − 150 MB < 400 MB` o lo staging ha già 4 motori: `non_creato`, codice `capienza_insufficiente` o `staging_pieno` (progetto §7, §5.6). Nessun motore installato.
5. **`crea_motore`** `{porta}` con la `seq` nuova dell'appartamento.
6. **Al risultato riuscito:** `instance_url` = `http://10.198.0.2`, `port` = la porta, `enabled: true`; poi la stessa verifica di oggi («Verifica connessione», `instances.verify`: chiama `/health` e `/version` del motore). Riuscita: `pronto`, riga nel registro attività.
7. **20 minuti** senza esito: `non_creato`, «Riprova» (progetto §6.8).

### 4.2 Nell'agente (esecutore), sotto il blocco della VM

| Passo | Cosa | Se fallisce | Ritorno indietro del passo |
|---|---|---|---|
| 0 | la firma dell'ordine (proposta A3, §6.3); controlli comuni (id, ambiente della sottoscrizione e di `ENV`, `seq`, `dev` escluso) e di `crea_motore`: porta nella fascia, libera; immagine **non** dall'ordine ma quella approvata, **solo per digest** (`@sha256:`), dal file di root riletto a ogni ordine (§4.3); capienza ricontrollata; `/data/<apt>` assente, vuota **oppure con il segno di creazione di questo appartamento** (revisione, punto 14; seconda lettura, N6: così «Riprova» dopo un passo 3 interrotto non si blocca), altrimenti rifiuto `dati_presenti` | rifiuto con il suo codice; niente scritto | — |
| 1 | se l'appartamento c'è già **e ha il segno di creazione dell'agente** (`/var/lib/domhouse-executor/creati/<apt>`, root) **con gli stessi parametri** (porta, immagine, `ENV`): riuscito senza rifare niente; senza il segno (per esempio `lab-01`) o con parametri diversi: rifiuto `gia_esiste_diverso` | — | — |
| 1b | il segno di creazione, **prima** di scrivere qualsiasi altra cosa (revisione, punto 8): da qui `togli_motore` può togliere quello che questo ordine crea | `errore_interno` | il segno si toglie per ultimo |
| 2 | **prima** il catalogo vuoto, `rooms: []` e `devices: []`, in `/etc/domhouse/<apt>.catalog.yaml` (root, 644): se mancasse, al `compose up` Docker creerebbe una cartella al suo posto | `errore_interno` | il file si toglie |
| 3 | `engine-vm.sh install --da-agente <apt> <porta> <immagine> shelly <ENV> <CATALOG_PATH>`: impostazioni, cartella dei dati, `write_key` (chiave del motore e conto del connector dai due segreti), `compose up`, attesa di `/health` 200. **`ENV` e `CATALOG_PATH` come argomenti**: l'esecutore pulisce l'ambiente lasciando solo `PATH`, una variabile non arriverebbe (revisione, punto 14). `--da-agente` non tocca systemd né l'Ops Agent (punto 4: timer e configurazione dei log restano dell'installazione a mano) | `segreto_illeggibile` (permessi appena dati, ritardo di IAM), `motore_non_sano` | `compose down`, via impostazioni, file della chiave e la cartella dei dati **di questo appartamento con il segno di creazione**: il motore crea il suo database all'avvio, quindi non è vuota (punto 14), ma è nata con questo ordine |
| 4 | `broker-vm.sh add-apartment <apt>`: l'account del connector `<apt>.connector` dal segreto, nessun dispositivo (arrivano con A3) | `broker_fallito` | `remove-apartment` |
| 5 | risultato riuscito con `{porta, immagine}` | — | — |

- **L'unità dell'esecutore** (revisione, punto 4), in più di quello che apre A3: `ReadWritePaths=/opt/domhouse /etc/domhouse /data`, `CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE`: `CAP_CHOWN` per dare la cartella dei dati all'utente 10001; **`CAP_DAC_OVERRIDE` dichiarata** (seconda lettura, N3) perché `/data/<apt>` è `10001` 750 e il ritorno indietro del passo 3 e `togli_motore` la devono svuotare da root. L'alternativa del revisore, cancellare come 10001 con `setpriv`, chiederebbe `CAP_SETUID` e `CAP_SETGID`, che permettono di diventare chiunque: peggio. Le scritture restano chiuse da `ProtectSystem=strict` e dai soli `ReadWritePaths`. **Da verificare** sulla VM con `systemd-run` e le stesse impostazioni, e la porta libera letta da `/proc/net/tcp` e `/proc/net/tcp6` invece di `ss` (così niente `AF_NETLINK`; da verificare sulla VM che basti). Provata sulla VM con `systemd-run` e le stesse impostazioni prima dell'installazione.
- **Ripetibile:** ogni passo controlla se è già fatto. «Riprova» manda un ordine nuovo (`seq` nuova) che completa i passi mancanti; un ordine identico già finito ripubblica il suo esito (giornale di A1).
- **Il motore con il catalogo vuoto** parte e risponde `/health` 200 con 0 dispositivi: PR #17 (`ce31e08`), provato dal revisore della memoria storica e nelle prove del connector. Il catalogo vero arriva con A4 (`applica_catalogo`, che riavvia il motore).
- **Sul broker:** il connector del motore nuovo si collega alla porta interna `172.30.83.2:1883` (rete interna del broker, `compose.broker.yaml`), come `lab-01`.

### 4.3 Cosa cambia nel codice dell'agente e degli script (dopo i due vincoli in testa)

- `crea_motore` eseguito (oggi `non_disponibile`), con i codici del §4.2;
- `engine-vm.sh` (progetto §9.2): `ENV` nelle impostazioni (`dev` e `lab-01` aggiornati una volta, a mano), catalogo in `/etc/domhouse` montato in sola lettura, regola dell'immagine e `registry_login` ancorati, porte normalizzate;
- `broker-vm.sh`: lo stesso blocco della VM, `add-apartment` e `remove-apartment` ripetibili;
- **l'immagine approvata, solo per digest** (revisione, punto 6): oggi `comune.IMAGE_RE` accetta anche un'etichetta (`engine:<commit>`) e `publish-all.sh` installa per etichetta, che chi scrive sul registro può spostare. Quindi:
  1. un file di root `/etc/domhouse/agent-immagine-<ambiente>` con una riga `…/engine@sha256:<64>`, **riletto a ogni ordine** (oggi `agent.conf` si legge solo all'avvio);
  2. `crea_motore` e `aggiorna_motore` accettano solo `@sha256:`: lo controllano l'agente **e** `engine-vm.sh`;
  3. `publish-all.sh` (risposta 5 = a) scrive il file con il digest letto dal registro dopo la spinta, e lo rilegge per controllo;
  4. un comando del committente rende immutabili le etichette del repository `domotica`. **Da verificare** che un rilancio di `publish-all.sh` sullo stesso commit (stesso digest sulla stessa etichetta) passi;
- **le firme nei due sensi e l'unità dell'esecutore** arrivano con A3 (proposta A3, §6.1 e §6.3), che va prima; se l'ordine cambiasse, entrano qui.

## 5. Ritorno indietro di tutta la creazione

### 5.1 Se si ferma a metà

Lo stato è `non_creato` con il passo raggiunto e `fatti` (§2.1). **Id e porta restano riservati finché qualcuno non preme «Riprova» o «Annulla»: nessun annullamento automatico** (risposta 7 = a). Condizione del committente: per chi guarda dev'essere chiaro che la creazione è rimasta a metà (§8). Due strade, sempre con la conferma del gestore:

1. **«Riprova»:** completa i passi mancanti (§4.2 ripetibile).
2. **«Annulla»:** toglie quello che c'è, in ordine inverso.

### 5.2 «Annulla», in ordine

1. Il server, in una transazione con `version`: stato **`annullamento_in_corso`** (revisione, punto 7), poi l'ordine `togli_motore`. In quello stato «Riprova» e un secondo «Annulla» rispondono 409 `invalid_state`.
2. L'agente (progetto §8.2), **solo se c'è il segno di creazione** (§4.2, passo 1b; revisione, punto 8; altrimenti rifiuto `non_creato_da_agente`, e così `lab-01` e `dev` non si toccano mai fino ad A6): `compose down`, impostazioni, chiave, catalogo, cartella dei dati, `remove-apartment`, per ultimo il segno; «già tolto» vale come riuscito. La `seq` dell'appartamento resta (lapide, progetto §6.4).
3. **Solo nel ricevitore, dopo `togli_motore` riuscito:** distruzione con ritardo delle versioni dei due segreti (7 giorni per riattivarle), poi l'appartamento esce da Firestore; l'id resta usato (D-67), la porta si libera.
4. `togli_motore` rifiutato o fallito, **o 20 minuti senza esito** (N7): di nuovo `non_creato`, con «Annulla» possibile; segreti e porta restano. Un esito riuscito che arriva dopo i 20 minuti chiude lo stesso l'annullamento (segreti, Firestore), perché il motore è già stato tolto, **ma solo se dopo quel `togli_motore` non è partito nessun altro ordine per l'appartamento** (terza lettura, N8: altrimenti un «Riprova» fatto nel frattempo avrebbe già lanciato un `crea_motore` nuovo, e chiudere distruggerebbe segreti e documento del motore che gira). In quel caso l'esito si ignora, con una riga nel log (`agent result ignored`, motivo `ordine_successivo`).

### 5.3 «Annulla» e A6

`togli_motore` è lo stesso pezzo dell'eliminazione (A6). In A2 «Annulla» vale **solo** per una creazione che non è mai arrivata a `pronto` (niente storico, niente dispositivi); l'eliminazione di un appartamento vero resta di A6, con «Disattiva», la conferma con il nome e il resto di D-232 (risposta 6 = a).

## 6. Stati ed errori

### 6.1 Stati della creazione

| Stato | Etichetta proposta | Quando | Azioni |
|---|---|---|---|
| `in_preparazione` | «In preparazione» | dalla riserva al collegamento | — (il sito rilegge ogni 4 s, al massimo 20 minuti) |
| `pronto` | «Pronto» | motore sano e collegato | quelle di un appartamento normale |
| `non_creato` | «Creazione rimasta a metà» | un passo rifiutato o fallito, o 20 minuti senza esito | «Riprova», «Annulla»; id e porta restano riservati fino a una delle due (risposta 7) |
| `annullamento_in_corso` | «Annullamento in corso» | da «Annulla» all'esito di `togli_motore`, **al massimo 20 minuti** (seconda lettura, N7): senza esito torna `non_creato`, calcolato alla lettura come in A3 | — (il sito rilegge ogni 4 s); «Riprova» e «Annulla» 409 `invalid_state` |
| `annullato` | — | dopo `togli_motore` riuscito | l'appartamento non c'è più |

### 6.2 Errori della chiamata

| HTTP | `error` | Quando | Testo |
|---|---|---|---|
| 403 | `forbidden` | senza permesso (D-64, D-77) | come oggi |
| 422 | `invalid_apartment_id` | id fuori regola, `dev`, `-devices` | «Id non valido: nello staging lab-… o test-…, lettere minuscole, cifre e trattini.» |
| 422 | `invalid_name`, `invalid_timezone` | | come oggi |
| 409 | `already_exists` | id usato, ora o prima (D-67) | «Identificativo non disponibile» (come oggi) |
| 409 | `external_id_in_use` | codice Italianway già usato | come oggi |
| 409 | `no_free_port` | fascia piena | «Non c'è più posto per un motore nuovo in questo ambiente.» |
| 409 | `version_changed` | blocco (Riprova, Annulla) | «Qualcuno ha appena cambiato questa creazione: ricarica.» |
| 409 | `invalid_state` | Riprova o Annulla fuori da `non_creato` (anche durante `annullamento_in_corso`) | «Con lo stato di adesso questa azione non si può fare.» |
| 409 | `secret_conflict` | un segreto con quel nome c'è e non è nostro | «C'è già un segreto con questo nome: serve un controllo (ID richiesta).» Con allarme |
| 429 | `rate_limited` | 5 creazioni avviate negli ultimi 60 minuti nell'organizzazione (risposta 9 = a, vedi sotto) | «Si possono creare al massimo 5 appartamenti l'ora per organizzazione. Il prossimo si può creare dalle HH:MM.» |
| 503 | `agent_not_configured` | agente non configurato, o produzione prima di A10 | come oggi |
| 502 | `agent_publish_failed` | ordine non inviato | come oggi, con `op_id` |

**Il limite di frequenza** (risposta 9 = a, con la condizione del committente):

- conta ogni `POST …/nuovo` accettato (202), riuscito o no, negli ultimi 60 minuti; «Riprova» e «Annulla» non contano;
- il conto sta in Firestore, per organizzazione, aggiornato nella transazione della riserva (§4.1): vale con più istanze del server;
- la risposta 429 porta `limite` (5) e `riprova_dal` (ora UTC, ISO 8601: la creazione più vecchia delle cinque più 60 minuti) e l'intestazione `Retry-After` in secondi; il sito mostra l'ora locale; lo stesso conto è leggibile prima, in `creazioni_ultima_ora` (§2.2);
- il modulo dice il limite prima di «Crea» (§8).

### 6.3 Esiti dell'agente (codici, tradotti dal server)

| Codice | Testo per il sito |
|---|---|
| `capienza_insufficiente` | «La VM non ha memoria per un motore in più.» |
| `staging_pieno` | «Lo staging ha già il numero massimo di motori.» |
| `porta_occupata` | «La porta scelta è occupata sulla VM: «Riprova» ne prende un'altra.» |
| `porta_fuori_fascia`, `immagine_non_approvata`, `gia_esiste_diverso`, `dati_presenti`, `non_creato_da_agente`, `firma_non_valida` | «Richiesta rifiutata dal sistema: serve un controllo (ID richiesta).» |
| `segreto_illeggibile` | «I permessi sui segreti non sono ancora attivi: riprova fra qualche minuto.» |
| `motore_non_sano` | «Il motore non è partito: «Riprova», e se succede ancora serve un controllo.» |
| `broker_fallito` | «Il broker non ha accettato l'appartamento: «Riprova».» |

### 6.4 Registro attività

- `apartment_created` (c'è già) quando la creazione arriva a `pronto`, con chi l'ha avviata.
- Due azioni nuove: `apartment_creation_retried`, `apartment_creation_cancelled`.
- Mai segreti, chiavi o password.

## 7. Cosa serve fuori dal codice (comandi del committente, in una procedura)

1. I ruoli del server su Secret Manager con le condizioni del progetto §2.3 (staging), più la lettura delle sole chiavi dei motori.
2. Il permesso della VM sui due prefissi (progetto §4.3). **Controllato in sola lettura il 19 novembre: non c'è.** Nessun ruolo di Secret Manager a livello di progetto; `langbrain-vm@` legge solo i quattro segreti di oggi, uno per uno (`langbrain-api-key-dev`, `langbrain-api-key-lab-01`, `langbrain-shelly-lab-01`, `langbrain-shelly-lab-01-devices`). Senza il permesso, il motore nuovo si fermerebbe al passo 3 con `segreto_illeggibile`. Serve un comando del committente: `secretAccessor` a `langbrain-vm@` a livello di progetto, con la condizione sui quattro prefissi dello staging (`langbrain-api-key-lab-`, `langbrain-api-key-test-`, `langbrain-shelly-lab-`, `langbrain-shelly-test-`, scritti con il numero del progetto, §2.3 del progetto). Anche `domotica-bff-staging@` non ha ancora i ruoli «creazione», «versioni» e «lettura»: atteso, è il punto 1.
3. L'immagine approvata nella configurazione dell'agente sulla VM.
4. `ENV=staging` nelle impostazioni di `lab-01` (e `dev`), a mano, una volta.

## 8. Cosa mostra il sito (in breve; le schermate le fa o2)

1. **Dove:** pagina della piattaforma, nell'organizzazione, «Appartamenti» → pulsante «Nuovo appartamento» accanto a quello di oggi («Collega un motore esistente», da rinominare).
2. **Il modulo:** id (solo nello staging, con il controllo mentre si scrive), nome, fuso orario, codice Italianway facoltativo (risposta 8); una riga con il limite: «Al massimo 5 appartamenti nuovi l'ora per organizzazione».
3. **Dopo «Crea»:** la riga dell'appartamento con «In preparazione» e i passi (riserva, segreti, capienza, motore, collegamento), riletta ogni 4 secondi per al massimo 20 minuti, come «Prova l'agente».
4. **«Creazione rimasta a metà»:** il messaggio del §6.3; che cosa esiste già (`fatti`: id e porta riservati, segreti, motore, broker) e che resta così finché non si sceglie; l'«ID richiesta» da copiare; «Riprova» e «Annulla» (con conferma).
5. **Limite superato (429):** il messaggio con il perché e l'ora da cui si può rifare (`riprova_dal`, in ora locale). Prima del clic, il conto di `creazioni_ultima_ora` (§2.2).
6. **«Pronto»:** l'appartamento come gli altri; un invito a registrare gli Shelly (A3) e a scrivere l'elenco dei dispositivi (A4).
7. Se D-232 passa: lo stesso nell'area dell'amministratore, con il contatore «N di M appartamenti».

## 9. Risposte del committente (19 novembre, registro 1161–1168)

| N. | Registro | Domanda | Risposta | Dove nel documento |
|---|---|---|---|---|
| 1 | 1161 | Chi crea | **a:** per ora solo il gestore della piattaforma, permesso in un punto solo. In futuro L (Leonardo), con il ruolo deciso da D-232 | vincolo 2 |
| 2 | — | Numero massimo per organizzazione | **rimandata a D-232** (serve solo se crea l'amministratore) | §2 |
| 3 | 1162 | Produzione | **a:** solo staging fino alla seconda VM (A10), in produzione 503. Non esistono ancora appartamenti veri | vincolo 1 |
| 4 | 1163 | Id in produzione | **a:** `a-` più 8 caratteri casuali | §3.1 |
| 5 | 1164 | Immagine approvata | **a:** la aggiorna `publish-all.sh` da solo quando installa il motore nuovo | §4.3 |
| 6 | 1165 | «Annulla» | **a:** solo prima di «Pronto»; l'eliminazione vera resta di A6 | §5.3 |
| 7 | 1166 | Creazione non riuscita | **a:** id e porta riservati finché «Riprova» o «Annulla», nessun annullamento automatico. **Condizione:** per l'utente dev'essere chiaro che la creazione è rimasta a metà | §2.1 `fatti`, §5.1, §6.1, §8 |
| 8 | 1167 | Codice Italianway | **a:** nel modulo, facoltativo. Confermata dopo la domanda del committente su Italianway (19 novembre: non cambia A2) | §8 |
| 9 | 1168 | Limite di frequenza | **a:** 5 l'ora per organizzazione. **Condizione:** il limite detto nel modulo; al superamento un messaggio semplice con il perché e l'ora da cui si può rifare, che il server restituisce | §6.2, §8 |

## 10. Stima in ore di A2

**Le ore valgono solo come grandezza relativa fra i pezzi** (19 novembre): misurate sul lavoro fatto, le stime di o1 sono state da 7 a 15 volte più alte del tempo reale (`stime/confronto-stime-reali.md`, fuori dal repository). Non sono una previsione da dare al committente.

Ore di lavoro, prove comprese, senza le attese.

| Pezzo | Chi | Cosa | Ore |
|---|---|---|---|
| Server: segreti | o1 | creazione con parametri fissi, intenzione in Firestore, riuso solo se nostro, distruzione con ritardo per «Annulla», prove con un Secret Manager finto | 5–7 |
| Server: creazione | o1 | rotte, stati, porta libera atomica, flusso capienza → `crea_motore` → collegamento e verifica, «Riprova», «Annulla», errori, registro, `bff/API.md`; `fatti` e il limite di frequenza con `riprova_dal` (risposte 7 e 9); i campi per il sito del §2.2 e l'esclusione degli appartamenti non pronti dalle rotte dell'organizzazione (domanda 25 di o2) | 9–12 |
| Server: prove | o1 | prove delle rotte, delle corse sulla porta, dei 20 minuti, dei passi ripresi | 4–6 |
| Agente: `crea_motore` | o1 | esecutore, passi ripetibili, codici, catalogo vuoto, segno di creazione, cartella dei dati controllata, argomenti al posto dell'ambiente, ritorno indietro del passo 3, unità allargata e prova sulla VM, prove | 8–11 |
| `engine-vm.sh` e `broker-vm.sh` | o1 | progetto §9.2 e §9.3 (ENV, catalogo in `/etc`, immagine solo per digest, blocco, `add-apartment` ripetibile), `install --da-agente`, prove | 6–8 |
| `togli_motore` per «Annulla» | o1 | il pezzo che A6 riusa, solo con il segno; `annullamento_in_corso` con i 20 minuti, segreti e Firestore solo dopo l'esito | 4–7 |
| `publish-all.sh` | o1 | il digest approvato scritto sulla VM quando si installa il motore nuovo (risposta 5), con il controllo dopo la scrittura e le prove; comando per le etichette immutabili | 2–3 |
| Procedura e permessi | o1 | ruoli di Secret Manager con le condizioni (segreti di `lab-01` esclusi per nome), permesso condizionato della VM (§7), immagine approvata, `ENV` a `lab-01`, installazione | 4–6 |
| Sito | o2 | modulo, riga con i passi, rilettura, «Riprova» e «Annulla» | 6–9 |
| **Totale** | | | **48–69** |
| Firme e unità di base dell'esecutore, se A3 non va prima | o1 | proposta A3, §6.1 e §6.3 | +10–14 |

**Probabile:** circa **40–51 ore** (o1 circa 34–42, o2 6–9), dopo le correzioni della revisione di sicurezza (§11), con A3 fatto prima. Come per A3, la voce che può crescere è la revisione di sicurezza: A2 è il primo pacchetto in cui il server crea segreti e l'agente installa motori.

## 11. Correzioni dopo la revisione di sicurezza (19 novembre)

Revisione indipendente (`revisione-a2-a3/REVISIONE-SICUREZZA-A2-A3.md`, fuori dal repository): A2 «eseguibile dopo correzioni». Valutazione di o1 verificata sul codice: d'accordo su tutti i punti.

| Punto | Che cosa | Dove è corretto |
|---|---|---|
| 1 | ordini firmati dal server, risultati con l'impronta dell'ordine | proposta A3, §6.3 (A3 va prima); qui il passo 0 del §4.2 verifica la firma |
| 4, N3 | l'unità dell'esecutore: cosa apre A2 in più di A3 (`CAP_DAC_OVERRIDE` dichiarata per `/data/<apt>`); `install --da-agente` che non tocca systemd né l'Ops Agent | §4.2 |
| 6 | immagine approvata solo per digest, file di root riletto a ogni ordine, controllo anche in `engine-vm.sh`, etichette immutabili | §4.3 |
| 7, N7, N8 | `annullamento_in_corso` che blocca «Riprova», al massimo 20 minuti; segreti e Firestore solo dopo `togli_motore` riuscito, e un esito in ritardo solo se nessun ordine è partito dopo | §5.2, §6.1 |
| 8 | segno di creazione dell'agente; `togli_motore` e «c'è già» solo con il segno: mai `lab-01` né `dev` fino ad A6 | §4.2 (passi 1 e 1b), §5.2 |
| 13 | i segreti fatti a mano di `lab-01` esclusi per nome dalle condizioni; «solo la VM» precisato | §3.3 |
| 14, N6 | `/data/<apt>` controllata al passo 0 (assente, vuota o con il segno di creazione); il ritorno indietro toglie la cartella creata da questo ordine; `ENV` e `CATALOG_PATH` come argomenti | §4.2 |

I punti 2, 3, 5, 9–12, 15, 16 e N1, N2, N4, N5 sono di A3 (proposta A3, §12).
