# Proposta: A2, il posto dell'appartamento dall'app

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta, nessun codice** (17 novembre 2026) | o1 | `docs/progetto-strumento-a-base.md` §2.1, §2.2, §2.3, §3 (`crea_motore`), §4, §5, §6, §7; registro, pacchetto A2 e D-232; documento interno dell'Autonomia, §2 passo 4; il codice di A1 e la PR #17 (catalogo vuoto, `ce31e08`) | rilettura della memoria storica; risposte alle domande del §9; revisione di sicurezza; schermate di o2; poi il codice |

**Cosa copre:** creare dall'app il «posto» di un appartamento: id, porta libera, i due segreti, il motore con l'elenco dei dispositivi vuoto, l'account del connector sul broker, il collegamento del motore all'appartamento. Le rotte del server, l'ordine `crea_motore` passo per passo con il ritorno indietro, stati ed errori, cosa mostra il sito.

**Cosa non copre:** l'elenco dei dispositivi (A4), le credenziali dei dispositivi (A3), l'eliminazione (A6), la capienza come allarme (A7), la seconda VM (A10).

**Vincoli di oggi, da rispettare:**

1. **Solo nello staging fino alla seconda VM** (progetto §5.4): la produzione non manda ordini alla VM condivisa. In produzione la rotta risponde 503 finché A10 non c'è.
2. **Chi crea:** oggi solo il gestore della piattaforma (D-64, D-77). D-232 è una proposta per il cliente: finché non la accetta, resta così. Il permesso sta in un punto solo, così cambia con una riga (domanda 1).
3. **Codice dell'agente fermo** finché A1 non è installato sulla VM (I0.1 controlla `ee59625`); `engine-vm.sh` e `broker-vm.sh` fermi fino alla fine della finestra del passo 3 (D-213). Questo è solo un documento.

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
- Se D-232 passa, le stesse rotte anche sotto `/app/admin/apartments/…` per l'amministratore dell'organizzazione, con il numero massimo del §8 (domanda 2).
- Tutte con `X-Correlation-Id`; descritte in `bff/API.md`. Il contratto del motore non cambia.

### 2.1 `creazione`

| Campo | Tipo | Note |
|---|---|---|
| `stato` | `in_preparazione` · `pronto` · `non_creato` · `annullato` | §6 |
| `passo` | `riserva` · `segreti` · `capienza` · `motore` · `collegamento` | l'ultimo raggiunto: il sito lo mostra come avanzamento |
| `version` | intero | per il blocco, come in A3 |
| `porta` | intero | quella riservata |
| `op` | `{op_id, stato, messaggio}` o null | l'ultimo ordine all'agente; `op_id` è l'«ID richiesta» |
| `updated_at`, `updated_by` | | nome visibile, mai l'email |

## 3. Id, porta, segreti

### 3.1 L'id

- **Staging:** scelto dal gestore, `^(lab|test)-[a-z0-9]([a-z0-9-]*[a-z0-9])?$`, al massimo 64 caratteri (la stessa regola dell'agente, `STAGING_ID_RE`). Mai `dev`, mai un id usato prima (`reserve_apartment_id` di oggi, D-67), mai uno che finisce con `-devices` (progetto §2.1).
- **Produzione** (dopo A10): generato dal server, `a-` più 8 caratteri casuali `[a-z0-9]`; il nome visibile resta libero.

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
| `langbrain-shelly-<apt>` | la password del connector sul broker: `secrets.token_urlsafe(24)` | il server | **solo** la VM: il server può aggiungere la versione ma non leggerla (condizione «lettura» del progetto §2.3) |

- **Parametri fissi** (progetto §2.2): replica `user-managed` in `europe-west8`; nessun `expireTime`, `topics`, CMEK; etichette `domhouse-env`, `domhouse-apt`, `domhouse-op`; ritardo di distruzione 7 giorni.
- **Prima** di creare: l'intenzione in Firestore (op_id e nome). Un segreto che esiste già si riusa solo se quel Firestore l'ha creato (stesso op_id) **e** i metadati coincidono; altrimenti 409 `secret_conflict` e allarme, nessuna versione aggiunta.
- Le password generate non passano per i log, né per l'ordine, né per Firestore: vanno solo in `versions.add`.
- **Permessi del server** (progetto §4.1): i ruoli «creazione» e «versioni» con le condizioni del §2.3, e la lettura delle sole chiavi dei motori. La prova 1125 è riuscita il 16 novembre; i ruoli veri si danno con i comandi del committente nella procedura di A2 (§7).

## 4. L'ordine `crea_motore`, passo per passo

### 4.1 Nel server

1. **Controlli:** permesso; id (§3.1); nome (1–80 caratteri); fuso orario; codice Italianway libero, se c'è; agente configurato (503 `agent_not_configured`).
2. **Riserva** in una transazione: id (`reserve_apartment_id`), porta (§3.2), documento dell'appartamento con `creazione.stato` `in_preparazione`, `enabled: false`, nessun `instance_url`.
3. **Segreti** (§3.3). Un errore qui: `non_creato` con il passo `segreti`; «Riprova» riparte da qui.
4. **Capienza:** ordine `capienza`; se `MemAvailable − 150 MB < 400 MB` o lo staging ha già 4 motori: `non_creato`, codice `capienza_insufficiente` o `staging_pieno` (progetto §7, §5.6). Nessun motore installato.
5. **`crea_motore`** `{porta}` con la `seq` nuova dell'appartamento.
6. **Al risultato riuscito:** `instance_url` = `http://10.198.0.2`, `port` = la porta, `enabled: true`; poi la stessa verifica di oggi («Verifica connessione», `instances.verify`: chiama `/health` e `/version` del motore). Riuscita: `pronto`, riga nel registro attività.
7. **20 minuti** senza esito: `non_creato`, «Riprova» (progetto §6.8).

### 4.2 Nell'agente (esecutore), sotto il blocco della VM

| Passo | Cosa | Se fallisce | Ritorno indietro del passo |
|---|---|---|---|
| 0 | controlli comuni (id, ambiente della sottoscrizione e di `ENV`, `seq`, `dev` escluso) e di `crea_motore`: porta nella fascia, libera; immagine **non** dall'ordine ma quella approvata nella configurazione dell'agente, per digest, con la regola ancorata (progetto §3); capienza ricontrollata | rifiuto con il suo codice; niente scritto | — |
| 1 | se l'appartamento c'è già **con gli stessi parametri** (porta, immagine, `ENV`): riuscito senza rifare niente; con parametri diversi: rifiuto `gia_esiste_diverso` | — | — |
| 2 | **prima** il catalogo vuoto, `rooms: []` e `devices: []`, in `/etc/domhouse/<apt>.catalog.yaml` (root, 644): se mancasse, al `compose up` Docker creerebbe una cartella al suo posto | `errore_interno` | il file si toglie |
| 3 | `engine-vm.sh install <apt> <porta> <immagine> shelly` con `ENV` e `CATALOG_PATH`: impostazioni, cartella dei dati, `write_key` (chiave del motore e conto del connector dai due segreti), `compose up`, attesa di `/health` 200 | `segreto_illeggibile` (permessi appena dati, ritardo di IAM), `motore_non_sano` | `compose down`, via impostazioni, file della chiave e cartella dei dati **vuota** (un motore appena nato non ha storico) |
| 4 | `broker-vm.sh add-apartment <apt>`: l'account del connector `<apt>.connector` dal segreto, nessun dispositivo (arrivano con A3) | `broker_fallito` | `remove-apartment` |
| 5 | risultato riuscito con `{porta, immagine}` | — | — |

- **Ripetibile:** ogni passo controlla se è già fatto. «Riprova» manda un ordine nuovo (`seq` nuova) che completa i passi mancanti; un ordine identico già finito ripubblica il suo esito (giornale di A1).
- **Il motore con il catalogo vuoto** parte e risponde `/health` 200 con 0 dispositivi: PR #17 (`ce31e08`), provato dal revisore della memoria storica e nelle prove del connector. Il catalogo vero arriva con A4 (`applica_catalogo`, che riavvia il motore).
- **Sul broker:** il connector del motore nuovo si collega alla porta interna `172.30.83.2:1883` (rete interna del broker, `compose.broker.yaml`), come `lab-01`.

### 4.3 Cosa cambia nel codice dell'agente e degli script (dopo i due vincoli in testa)

- `crea_motore` eseguito (oggi `non_disponibile`), con i codici del §4.2;
- `engine-vm.sh` (progetto §9.2): `ENV` nelle impostazioni (`dev` e `lab-01` aggiornati una volta, a mano), catalogo in `/etc/domhouse` montato in sola lettura, regola dell'immagine e `registry_login` ancorati, porte normalizzate;
- `broker-vm.sh`: lo stesso blocco della VM, `add-apartment` e `remove-apartment` ripetibili;
- la configurazione dell'agente: l'**immagine approvata per ambiente** (digest), di root (domanda 5);
- **R8, i risultati firmati** (progetto §3.2): necessari prima di A2 se A3 non li ha già portati (proposta A3, §6.3).

## 5. Ritorno indietro di tutta la creazione

### 5.1 Se si ferma a metà

Lo stato è `non_creato` con il passo raggiunto. Due strade, sempre con la conferma del gestore:

1. **«Riprova»:** completa i passi mancanti (§4.2 ripetibile).
2. **«Annulla»:** toglie quello che c'è, in ordine inverso.

### 5.2 «Annulla», in ordine

1. `togli_motore` all'agente (progetto §8.2): `compose down`, impostazioni, chiave, catalogo, cartella dei dati, `remove-apartment`; «già tolto» vale come riuscito. La `seq` dell'appartamento resta (lapide, progetto §6.4).
2. Distruzione con ritardo delle versioni dei due segreti (7 giorni per riattivarle).
3. L'appartamento esce da Firestore; l'id resta usato (D-67), la porta si libera.

### 5.3 «Annulla» e A6

`togli_motore` è lo stesso pezzo dell'eliminazione (A6). Proposta: in A2 «Annulla» vale **solo** per una creazione che non è mai arrivata a `pronto` (niente storico, niente dispositivi); l'eliminazione di un appartamento vero resta di A6, con «Disattiva», la conferma con il nome e il resto di D-232. Domanda 6.

## 6. Stati ed errori

### 6.1 Stati della creazione

| Stato | Etichetta proposta | Quando | Azioni |
|---|---|---|---|
| `in_preparazione` | «In preparazione» | dalla riserva al collegamento | — (il sito rilegge ogni 4 s, al massimo 20 minuti) |
| `pronto` | «Pronto» | motore sano e collegato | quelle di un appartamento normale |
| `non_creato` | «Non creato» | un passo rifiutato o fallito, o 20 minuti senza esito | «Riprova», «Annulla» |
| `annullato` | — | dopo «Annulla» riuscito | l'appartamento non c'è più |

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
| 409 | `invalid_state` | Riprova o Annulla fuori da `non_creato` | «Con lo stato di adesso questa azione non si può fare.» |
| 409 | `secret_conflict` | un segreto con quel nome c'è e non è nostro | «C'è già un segreto con questo nome: serve un controllo (ID richiesta).» Con allarme |
| 429 | `rate_limited` | più di 5 creazioni l'ora per organizzazione | «Troppe operazioni in poco tempo.» |
| 503 | `agent_not_configured` | agente non configurato, o produzione prima di A10 | come oggi |
| 502 | `agent_publish_failed` | ordine non inviato | come oggi, con `op_id` |

### 6.3 Esiti dell'agente (codici, tradotti dal server)

| Codice | Testo per il sito |
|---|---|
| `capienza_insufficiente` | «La VM non ha memoria per un motore in più.» |
| `staging_pieno` | «Lo staging ha già il numero massimo di motori.» |
| `porta_occupata` | «La porta scelta è occupata sulla VM: «Riprova» ne prende un'altra.» |
| `porta_fuori_fascia`, `immagine_non_approvata`, `gia_esiste_diverso` | «Richiesta rifiutata dal sistema: serve un controllo (ID richiesta).» |
| `segreto_illeggibile` | «I permessi sui segreti non sono ancora attivi: riprova fra qualche minuto.» |
| `motore_non_sano` | «Il motore non è partito: «Riprova», e se succede ancora serve un controllo.» |
| `broker_fallito` | «Il broker non ha accettato l'appartamento: «Riprova».» |

### 6.4 Registro attività

- `apartment_created` (c'è già) quando la creazione arriva a `pronto`, con chi l'ha avviata.
- Due azioni nuove: `apartment_creation_retried`, `apartment_creation_cancelled`.
- Mai segreti, chiavi o password.

## 7. Cosa serve fuori dal codice (comandi del committente, in una procedura)

1. I ruoli del server su Secret Manager con le condizioni del progetto §2.3 (staging), più la lettura delle sole chiavi dei motori.
2. Il permesso della VM sui due prefissi (progetto §4.3): c'è già per la lettura? Da controllare in sola lettura prima della procedura.
3. L'immagine approvata nella configurazione dell'agente sulla VM.
4. `ENV=staging` nelle impostazioni di `lab-01` (e `dev`), a mano, una volta.

## 8. Cosa mostra il sito (in breve; le schermate le fa o2)

1. **Dove:** pagina della piattaforma, nell'organizzazione, «Appartamenti» → pulsante «Nuovo appartamento» accanto a quello di oggi («Collega un motore esistente», da rinominare).
2. **Il modulo:** id (solo nello staging, con il controllo mentre si scrive), nome, fuso orario, codice Italianway facoltativo.
3. **Dopo «Crea»:** la riga dell'appartamento con «In preparazione» e i passi (riserva, segreti, capienza, motore, collegamento), riletta ogni 4 secondi per al massimo 20 minuti, come «Prova l'agente».
4. **«Non creato»:** il messaggio del §6.3, l'«ID richiesta» da copiare, «Riprova» e «Annulla» (con conferma).
5. **«Pronto»:** l'appartamento come gli altri; un invito a registrare gli Shelly (A3) e a scrivere l'elenco dei dispositivi (A4).
6. Se D-232 passa: lo stesso nell'area dell'amministratore, con il contatore «N di M appartamenti».

## 9. Domande per il committente

1. **Chi crea (D-232).** Fino alla risposta del cliente solo il gestore della piattaforma (D-64, D-77). Se il cliente accetta D-232, l'amministratore dell'organizzazione può creare: confermi che A2 si costruisce con il permesso in un punto solo, per ora al gestore?
2. **Il numero massimo** di appartamenti per organizzazione (serve solo se crea l'amministratore): quanto, e chi lo cambia (il gestore, nella pagina dell'organizzazione)?
3. **Produzione:** A2 resta solo per lo staging fino alla seconda VM (A10). Confermi?
4. **Il nome dell'id in produzione:** `a-` più 8 caratteri casuali (progetto §2.1), invisibile al cliente. Va bene?
5. **L'immagine approvata del motore:** chi la cambia sulla VM dopo una pubblicazione (comando del committente, in `publish-all.sh` o a parte)? Senza, gli appartamenti nuovi partono con l'immagine di prima.
6. **«Annulla»** solo per una creazione mai arrivata a «Pronto» (§5.3), e l'eliminazione di un appartamento vero resta di A6?
7. **Una creazione non riuscita** tiene id e porta riservati finché qualcuno non preme «Riprova» o «Annulla» (proposta), o si annulla da sola dopo un tempo?
8. **Il codice Italianway** si mette alla creazione o dopo, quando l'appartamento è «Pronto»? (Proposta: alla creazione, facoltativo, come oggi.)
9. **Limite di frequenza:** 5 creazioni l'ora per organizzazione va bene?

## 10. Stima in ore di A2

Ore di lavoro, prove comprese, senza le attese.

| Pezzo | Chi | Cosa | Ore |
|---|---|---|---|
| Server: segreti | o1 | creazione con parametri fissi, intenzione in Firestore, riuso solo se nostro, distruzione con ritardo per «Annulla», prove con un Secret Manager finto | 5–7 |
| Server: creazione | o1 | rotte, stati, porta libera atomica, flusso capienza → `crea_motore` → collegamento e verifica, «Riprova», «Annulla», errori, registro, `bff/API.md` | 6–8 |
| Server: prove | o1 | prove delle rotte, delle corse sulla porta, dei 20 minuti, dei passi ripresi | 4–6 |
| Agente: `crea_motore` | o1 | esecutore, passi ripetibili, codici, catalogo vuoto, ritorno indietro del passo 3, prove | 5–7 |
| `engine-vm.sh` e `broker-vm.sh` | o1 | progetto §9.2 e §9.3 (ENV, catalogo in `/etc`, immagine ancorata, blocco, `add-apartment` ripetibile), prove | 5–7 |
| `togli_motore` per «Annulla» | o1 | il pezzo che A6 riusa | 3–4 |
| Procedura e permessi | o1 | ruoli di Secret Manager con le condizioni, immagine approvata, `ENV` a `lab-01`, installazione; correzioni dopo la revisione di sicurezza | 4–6 |
| Sito | o2 | modulo, riga con i passi, rilettura, «Riprova» e «Annulla» | 6–9 |
| **Totale** | | | **38–54** |
| R8, se non arriva con A3 | o1 | firma dei risultati (proposta A3, §6.3) | +5–7 |

**Probabile:** circa **30–40 ore** (o1 circa 24–31, o2 6–9). Come per A3, la voce che può crescere è la revisione di sicurezza: A2 è il primo pacchetto in cui il server crea segreti e l'agente installa motori.
