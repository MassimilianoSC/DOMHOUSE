# Proposta: A3, credenziali dei dispositivi, parte del server e dell'agente

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta con le risposte del committente** (scritta il 17 novembre 2026; risposte 1170–1177 del 19 novembre nel §9). Nessun codice | o1 | `docs/proposta-a3-sito.md` (o2, `f607187`, `4cb6bab`); `docs/progetto-strumento-a-base.md` §2.1, §2.2, §2.3, §2.5, §3, §3.2, §4, §6, §8.1, §8.3, §9 (D-233); il codice di A1 (`bff/agent.py`, `scripts/agent/`) | revisione di sicurezza del 19 novembre e la sua seconda lettura (N1–N5): correzioni scritte qui (§12); le misure delle prove `a3_` sul broker (con il via); conferma della memoria storica; poi il codice. **A3 prima di A2** (risposta 10: R8 entra qui) |

**Cosa copre:** le chiamate del server per «Registra», «Rigenera», «Revoca», «Riprova» e l'elenco; i dati in Firestore; gli stati e come cambiano con gli esiti dell'agente; errori, permessi, blocco, registro attività; cosa fa l'agente sulla VM (`aggiorna_broker`); le risposte tecniche alle domande di o2; la stima.

**Cosa non copre:** il modulo del catalogo (A4), gli accessi rifiutati (A5), l'eliminazione (A6). **La pagina locale degli Shelly** (§8.3 del progetto) **non entra in A3** (risposta 6): si fa dopo, a parte, con la sua revisione e le verifiche con Youssouf; il §7 resta come appunto per quel pezzo.

**Termini:** nelle risposte che il sito mostra valgono quelli della guida («sistema domotico», «Registro attività», «ID richiesta»); nei nomi tecnici restano quelli del progetto (impronta, broker, ordine).

## 1. In breve

1. La password nasce **sul server**, si mostra **una volta** nella risposta di «Registra» o «Rigenera», e non si salva da nessuna parte: in Firestore va solo la sua **impronta** (`hash_password` di `broker_accounts.py`, formato `$7$` di Mosquitto).
2. Ogni cambio manda all'agente un ordine **`aggiorna_broker`** con l'**elenco completo** delle impronte dell'appartamento e una `seq` nuova, presi nella stessa transazione Firestore che fa il cambio.
3. L'esito dell'ordine conferma **tutti** i cambi fatti fino a quella `seq` (§4.2): così due operazioni ravvicinate su dispositivi diversi non si confondono.
4. Le rotte sono del solo server, descritte **solo** in `bff/API.md` come quelle dell'agente; il contratto `contract/openapi.yaml` (motore) non cambia (risposta 5).

## 2. Le chiamate

Stile delle rotte di oggi, `X-Correlation-Id` come le altre. Due prefissi, con le stesse chiamate (risposta 1):

- `/app/apartments/{apt}/device-credentials`: l'amministratore dell'organizzazione (§8.1);
- `/app/platform/apartments/{apt}/device-credentials`: il gestore della piattaforma, **solo nello staging e solo** per gli appartamenti `lab-…` e `test-…` (come «Prova l'agente»). In produzione, o per un altro id, 404.

Sotto, `…` sta per uno dei due.

| Chiamata | Corpo | Risposta | Note |
|---|---|---|---|
| `GET …/device-credentials` | — | 200 `{items: [DeviceCredential]}` | ordinati per `device_id`; anche i revocati |
| `POST …/device-credentials` | `{device_id}` | **201** `{credential, password}` | «Registra»; anche «Registra di nuovo» di un revocato |
| `POST …/device-credentials/{device_id}/rigenera` | `{version}` | **200** `{credential, password}` | |
| `POST …/device-credentials/{device_id}/revoca` | `{version}` | **202** `{credential}` | |
| `POST …/device-credentials/{device_id}/riprova` | `{version}` | **202** `{credential}` | rimanda l'elenco completo; nessuna password nuova |

- **Tutte le risposte** di queste rotte hanno `Cache-Control: no-store`; quelle con `password` anche `Pragma: no-cache`.
- **I nomi delle rotte** in italiano (`rigenera`, `revoca`, `riprova`) come proposto da o2: sono le parole dei pulsanti. Se la memoria storica preferisce l'inglese delle altre rotte (`regenerate`, `revoke`, `retry`), si cambia solo qui.
- **Una password non passa mai** per una chiamata `GET`, per i log del server, per gli errori, né per l'ordine Pub/Sub.

### 2.1 `DeviceCredential`

Come al §6.2 di o2, con tre precisazioni.

| Campo | Tipo | Note |
|---|---|---|
| `device_id` | stringa | `^[a-z0-9][a-z0-9-]{0,63}$` |
| `name` | stringa o null | il nome che il motore dà al dispositivo, se lo conosce (§2.2) |
| `stato` | `in_attesa` · `pronto` · `cambio_in_corso` · `revoca_in_corso` · `revocato` · `non_applicato` | §4 |
| `version` | intero | per il blocco (§3); parte da 1, +1 a ogni azione |
| `updated_at` | data e ora ISO | l'ultima azione di una persona |
| `updated_by` | nome visibile o null | dal registro dei nomi (`actors`), mai l'email |
| `azione` | `registra` · `rigenera` · `revoca` o null | l'azione **in attesa di conferma**, null quando non ce n'è; «Riprova» non la cambia (§11, punto 1): così con `non_applicato` il sito sa sempre cosa non è stato applicato, revoca compresa |
| `engine_device_id` | stringa o null | **solo con A4**: il `device_id` del motore (`dev-presa-lab`) legato a questo id Shelly dal catalogo; prima di A4 sempre null (§11, punto 3) |
| `op` | `{op_id, stato, messaggio}` o null | l'ultimo ordine verso il broker; `messaggio` in italiano come in «Prova l'agente»; `op_id` è l'«ID richiesta» |
| `connection` | `{server, ssl_ca, client_id, user, topic_prefix}` | sempre presente, anche per un revocato; `server` è **null** quando `DEVICE_BROKER_ADDRESS` è vuota (§11, punto 5) |

**`connection`:** `server` viene da un'impostazione nuova del server per ambiente, `DEVICE_BROKER_ADDRESS` (staging `mqtt.dh-lab.eu:8883`; produzione vuota fino alla seconda VM). `ssl_ca` è sempre `ca.pem` (il certificato integrato dello Shelly). `client_id` e `user` sono `<apt>.<device_id>`, `topic_prefix` `<apt>/<device_id>`.

**Mai nelle risposte:** l'impronta, l'uid di chi ha fatto l'azione, l'email.

### 2.2 Il nome dal motore (solo con A4)

- Il `Device` del contratto ha `device_id` del motore, `label` e capacità, **non** l'id Shelly: il legame fra i due sta solo nel catalogo.
- **Fino ad A4:** `name` ed `engine_device_id` sono null. Il sito mostra il codice del dispositivo e non mette la voce «Credenziali» in «Stato dei dispositivi» (proposta di o2, §11 punto 3).
- **Con A4** il catalogo lo scrive l'app e il server lo conosce: per ogni id Shelly mette `engine_device_id` e il `label`. Il sito lega le due pagine con `engine_device_id`, senza leggere il catalogo.
- Le credenziali non dipendono mai dal motore: se il motore non risponde, l'elenco arriva lo stesso.

## 3. Il blocco (`version`)

1. Ogni azione legge il documento del dispositivo **in una transazione** Firestore e confronta la `version` mandata dal sito.
2. Se è diversa: **409 `version_changed`**, «Qualcuno ha appena cambiato questo dispositivo: ricarica l'elenco». Due «Rigenera» insieme: la seconda si ferma.
3. Nella stessa transazione:
   1. cambia impronta e stato del dispositivo, `version + 1`;
   2. legge **tutte** le impronte vive dell'appartamento;
   3. prende la `seq` nuova dell'appartamento (`agent_seq`, come in A1) e scrive l'operazione `AgentOp` «inviato» con quella `seq`;
   4. scrive nel dispositivo `pending_seq` = quella `seq`.
4. **Dopo** la transazione il server pubblica l'ordine (§6). Se la pubblicazione fallisce, l'operazione diventa «fallito, non_inviato» e lo stato si legge «non applicato» (§4): la password, se c'era, si restituisce lo stesso (§5.3).
5. «Registra» non ha `version`: la transazione rifiuta se il documento c'è già e non è revocato. Per un revocato («Registra di nuovo») la transazione lo riporta ad attivo con `version + 1`: di due «Registra di nuovo» insieme la prima passa, la seconda trova il documento non più revocato e riceve **409 `already_registered`** (§11, punto 7).

## 4. Gli stati

### 4.1 Cosa si salva e cosa si mostra

In Firestore il dispositivo ha `stato_salvato` (`attivo` o `revocato`), l'`azione` in attesa e `pending_seq`. Lo `stato` della risposta si **calcola** alla lettura dall'esito dell'operazione di quella `seq`:

| Azione in attesa | Operazione di `pending_seq` | `stato` mostrato |
|---|---|---|
| `registra` | inviata, entro 20 minuti | `in_attesa` |
| `rigenera` | inviata, entro 20 minuti | `cambio_in_corso` |
| `revoca` | inviata, entro 20 minuti | `revoca_in_corso` |
| qualsiasi | rifiutata, scartata, fallita, o inviata da oltre 20 minuti | `non_applicato` |
| nessuna | — | `pronto` (attivo) o `revocato` |

«Riprova» cambia solo `pending_seq` (l'ordine nuovo), non `azione`: mentre è in volo lo stato è quello dell'azione riprovata, e se fallisce di nuovo `non_applicato` dice ancora quale azione manca (§11, punti 1 e 2).

Calcolarlo alla lettura vuol dire che il limite dei 20 minuti (progetto §6.8) non ha bisogno di un timer **per lo stato**. L'allarme invece sì: §8.4 (revisione, punto 3).

### 4.2 Un esito conferma tutto fino alla sua `seq`

**Nessuna scrittura sui dispositivi** quando arriva un esito (revisione, punto 2: una scrittura «a ventaglio» fuori transazione si scavalca con una revoca che arriva nello stesso momento).

- Per appartamento, in `agent_seq/{apt}`, il campo `ultima_seq_riuscita`: il ricevitore lo aggiorna **in transazione** con il massimo fra il valore salvato e la `seq` dell'operazione riuscita, **solo per gli esiti riusciti di `aggiorna_broker`** (seconda lettura, N1): `stato`, `capienza`, `crea_motore` e `applica_catalogo` usano la stessa sequenza, e un «Prova l'agente» riuscito dopo una revoca fallita non deve farla sembrare applicata.
- La `seq` si prende dall'operazione **salvata** (`AgentOp`), mai dal risultato; `finish_agent_op` controlla anche che coincida.
- Alla lettura: un dispositivo con `pending_seq ≤ ultima_seq_riuscita` è confermato (`registra` e `rigenera` → `pronto`; `revoca` → `revocato`), perché l'ordine riuscito portava l'elenco completo letto **dopo** tutti i cambi con `seq` più bassa. Con `pending_seq` più alta, lo stato dipende dall'operazione di quella `seq` (§4.1).
- Un risultato con `seq` più bassa di uno già riuscito non cambia niente (e l'agente lo rifiuta comunque, §6.4 del progetto).

### 4.3 Azioni ammesse per stato

| Stato | Rigenera | Revoca | Riprova | Registra |
|---|---|---|---|---|
| `in_attesa` | sì (password persa prima della conferma) | sì | 409 `invalid_state` | 409 `already_registered` |
| `pronto` | sì | sì | 409 `invalid_state` | 409 `already_registered` |
| `cambio_in_corso` | 409 `operation_in_progress` | **sì** (domanda 3 di o2, §8) | 409 `operation_in_progress` | 409 `already_registered` |
| `revoca_in_corso` | 409 `operation_in_progress` | 409 `operation_in_progress` | 409 `operation_in_progress` | 409 `operation_in_progress` |
| `revocato` | 409 `invalid_state` | 409 `invalid_state` | 409 `invalid_state` | sì: «Registra di nuovo», password nuova |
| `non_applicato` con `azione` `registra` o `rigenera` | sì | sì | sì | 409 `already_registered` |
| `non_applicato` con `azione` `revoca` | 409 `invalid_state` | 409 `invalid_state` | **sì, solo questa** | 409 `already_registered` |

**Le regole valgono sullo stato calcolato** (§4.1), non su `stato_salvato`: durante `revoca_in_corso` quello salvato è già `revocato` (revisione, punto 10). Una revoca non applicata si chiude solo con «Riprova»: «Rigenera» riattiverebbe il dispositivo.

**La regola dei due codici:** `operation_in_progress` quando l'azione è bloccata da un ordine in volo (aspettando, diventerà possibile); `invalid_state` quando lo stato non la ammette proprio (il sito ricarica l'elenco). Ogni casella ha il suo codice: nessun «no» senza codice (§11, punto 6).

## 5. Le azioni, passo per passo

### 5.1 «Registra»

1. Controlli: permesso (§8.1), id del dispositivo (422 `invalid_device_id`, **senza** convertire le maiuscole: domanda 6 di o2; `connector` rifiutato, è l'utente del connector: revisione, punto 11, come `broker_accounts.RESERVED_DEVICE`, e lo stesso in `comune.py`), limite di frequenza (§8.3), agente configurato (503 `agent_not_configured`), indirizzo del broker configurato (503 `broker_address_missing`), al massimo 200 dispositivi non revocati (409 `too_many_devices`). Tutti **prima** di generare la password.
2. La password: `secrets.token_urlsafe(24)` (32 caratteri), l'impronta con `hash_password`.
3. La transazione del §3.
4. La pubblicazione dell'ordine.
5. **201** con `credential` e `password`.

### 5.2 «Rigenera»

Come «Registra» sul dispositivo che c'è: impronta nuova al posto della vecchia, `azione` `rigenera`. Fino al risultato riuscito vale la password vecchia sul broker (l'impronta vecchia è nell'ultimo elenco applicato). **200** con la password.

### 5.3 Se la pubblicazione fallisce dopo la transazione

- **«Registra» e «Rigenera»:** la risposta resta **201/200 con la password**, con `stato` `non_applicato` e `op.messaggio` «Ordine non inviato al sistema domotico: copia comunque la password, poi usa «Riprova»». La password non si perde: l'impronta è già salvata, manca solo l'ordine.
- **«Revoca» e «Riprova»:** **502 `agent_publish_failed`**, con `op_id` nel corpo («ID richiesta»); lo stato si legge `non_applicato`.

### 5.4 «Revoca»

1. Nella transazione: l'impronta si toglie dal documento (resta il documento, `stato_salvato` `revocato`, per l'elenco e il registro), `azione` `revoca`.
2. L'ordine porta l'elenco **senza** quel dispositivo.
3. Al risultato riuscito il broker ha tolto l'utente **e chiuso il suo collegamento già aperto** (revisione, punto 5). `mosquitto.conf` dice che la ricarica rilegge utenti e permessi «senza far cadere chi è collegato»; lo stesso vale per **«Rigenera»**: una password uscita resterebbe dentro sul collegamento aperto. Quindi l'esecutore, dopo il `sync`, **riavvia il broker** quando l'elenco nuovo toglie un utente o gli cambia l'impronta, e l'esito è «riuscito» solo dopo il riavvio e `wait_healthy` (§6.2).
4. Le prove sul broker vero, in container (`tests/broker_container_test.py`, `-k a3_ -s`, **solo con il via del committente**) **misurano senza presupporre**: il 16 novembre, dal vivo, il cambio della password della Plug con una ricarica aveva fatto cadere la Plug, contro quello che dice `mosquitto.conf`. Le prime due stampano una riga «MISURA A3 …» (dopo il solo `sync`: riceve, pubblica, resta collegato, si ricollega) per «Revoca» e per «Rigenera»; la terza controlla che dopo il riavvio la password vecchia sia fuori e misura in quanti secondi gli altri tornano. **Decide la misura:** se dopo il solo `sync` un collegamento aperto non riceve né pubblica più, per quel caso il riavvio si toglie.

### 5.5 «Riprova»

Una transazione con `version` e una `seq` nuova che rilegge l'elenco completo; nessuna password nuova. Ammessa solo in `non_applicato`.

### 5.6 Rete caduta durante «Registra» o «Rigenera» (domanda 4 di o2)

- Il server non conserva la password nemmeno per pochi secondi: rifare la stessa chiamata dà 409 (`already_registered` o `version_changed`), e il sito dice di usare «Rigenera». È la strada del progetto (§8.1); la propongo anche io.

## 6. L'agente sulla VM per A3

### 6.1 `aggiorna_broker` (l'esecutore)

Oggi l'elenco chiuso lo accetta già nei controlli (`scripts/agent/comune.py`: al massimo 200, id con la regola, impronte nel formato `$7$`, mai una password) ma risponde «non_disponibile». In A3 l'esecutore lo **esegue**, dopo aver verificato la firma dell'ordine (§6.3):

1. sotto il blocco della VM, scrive in modo atomico `/etc/domhouse/_broker/devices/<apt>` (root, 600): una riga `<device_id> <impronta>` per dispositivo dell'elenco;
2. lancia il `sync` del broker per quell'appartamento (isolato, E-33), poi il riavvio del broker se qualcuno è stato tolto o ha cambiato impronta (§5.4);
3. esiti, con codici di un elenco chiuso:

| Esito | Codice | Quando |
|---|---|---|
| riuscito | — | file scritto e `sync` concluso; `dati`: `{dispositivi: N}` |
| rifiutato | `appartamento_sconosciuto` | il broker non ha l'appartamento (`add-apartment` non fatto: arriva con A2) |
| rifiutato | i codici dei controlli di oggi | `troppi_dispositivi`, `id_non_valido`, `impronta_non_valida`, `parametri_non_validi` |
| fallito | `sync_fallito` | il `sync` ha tenuto le righe di prima per quell'appartamento («kept») o non è riuscito |
| fallito | `riavvio_fallito` | il broker non è tornato sano dopo il riavvio |
| rifiutato | `migrazione_non_fatta` | `lab-01` prima della migrazione (§6.4) |
| rifiutato | `firma_non_valida` | ordine senza la firma del server, o con una firma sbagliata (§6.3), con un allarme |
| fallito | `errore_interno` | come oggi |

4. Il server traduce i codici in italiano (`MESSAGES` di `bff/agent.py`).

**L'unità dell'esecutore** (revisione, punto 4): oggi `ProtectSystem=strict`, nessuna capacità, `AF_UNIX AF_INET`. A3 apre esattamente:

| Cosa | Perché |
|---|---|
| `ReadWritePaths=/etc/domhouse/_broker` | il file delle impronte e i file `auth/` scritti dal `sync` |
| `CapabilityBoundingSet=CAP_CHOWN` | oggi `auth/` è `1883:1883` 750 (`broker-vm.sh:566`): root senza `CAP_DAC_OVERRIDE` non ci legge né scrive, e `CAP_FOWNER` non aiuta (seconda lettura, N3). Quindi la cartella cambia: `auth/` **`root:1883` 750**, i file **`1883:root` 640**. Root scrive nella cartella da proprietario e legge i file dal gruppo (il `sync` rilegge le righe tenute, E-33); il broker (utente e gruppo 1883) attraversa la cartella dal gruppo e legge i file da proprietario. `CAP_CHOWN` serve solo per dare i file nuovi a 1883. Rispetto alla proposta del revisore (file `root:1883`): i file restano dell'utente del broker perché Mosquitto avvisa quando i file di utenti e permessi non sono suoi (**da verificare** con le prove sul broker in container). Il cambio di proprietario si fa una volta con `broker-vm.sh install` della versione di A3 |
| nessuna famiglia di indirizzi nuova | `sync` e `restart` passano dal socket di Docker (`AF_UNIX`) e da Secret Manager (`AF_INET`) |

Il `sync` gira con l'ambiente ripulito (solo `PATH`): quello che gli serve passa come argomento, mai per variabile d'ambiente. Prima dell'installazione si prova sulla VM con `systemd-run` e le stesse impostazioni, come I9 di A1.

### 6.2 Il broker

- `broker_accounts.py` (§9.4 del progetto): i dispositivi di un appartamento dal file delle impronte, prese così come sono; il conto del connector da Secret Manager come oggi. **Il ripiego sul segreto vecchio `-devices` vale solo per un elenco esplicito, `lab-01`** (revisione, punto 12); per ogni altro appartamento senza file: nessun dispositivo. Il file (anche vuoto) si crea prima di `add-apartment`.
- `broker-vm.sh`: la cartella `devices/` (root, 700), `remove-apartment` toglie anche il file.
- Dopo il `sync`, se l'elenco nuovo ha **tolto** qualcuno o gli ha **cambiato l'impronta**: `broker-vm.sh restart` (tutti si ricollegano: pochi secondi; i numeri veri dalla prova del §5.4), salvo che la misura dica che il solo `sync` basta. Nello staging è la scelta tecnica.
- **Vincolo aperto per la produzione** (seconda lettura, N4): il broker è uno solo per tutti gli appartamenti, e un amministratore può fare fino a 30 azioni l'ora (§8.3), cioè fino a 30 ondate di ricollegamento per tutti. **Prima della produzione si decide** fra: raccogliere i riavvii (al massimo uno ogni N minuti; le revoche in attesa restano «revoca in corso» fino al riavvio), oppure staccare il singolo client (il plugin di sicurezza dinamica di Mosquitto, un cambio più grande del broker). Da portare al committente con i numeri della prova.

### 6.3 Condizione di sicurezza: i risultati firmati (R8) prima di A3

Con A1 un risultato falso cambia solo un «stato». Con A3 un risultato falso «riuscito» di una **revoca** farebbe vedere «Revocato» mentre il dispositivo rubato si collega ancora. Quindi **R8 (progetto §3.2) entra in A3, prima di qualunque ordine che scrive** (risposta 10). Conseguenza: A3 prima di A2, da confermare dopo la revisione di sicurezza.

**Firmare i risultati non basta** (revisione, punto 1): un lettore compromesso può passare all'esecutore un ordine ben formato con lo stesso `op_id` e la stessa `seq` di una revoca vera ma con l'elenco che contiene ancora lo Shelly rubato, e l'esecutore lo firmerebbe «riuscito»; oppure una `seq = 2^31-1` che blocca la lapide per sempre. Quindi **firme nei due sensi**, con due chiavi diverse:

1. **Ordini firmati dal server:** HMAC-SHA256 con la chiave «ordini» (segreto `domhouse-agent-ordini-staging`); sulla VM la stessa chiave in un file di root (`/etc/domhouse/agent-ordini.key`, 600) letto dal solo esecutore. L'esecutore verifica la firma **prima di ogni altro controllo**; senza firma valida: rifiutato `firma_non_valida`, con un allarme. Precisazioni (seconda lettura, N5):
   - **cosa copre:** l'ordine intero in forma canonica, cioè tutti i campi dell'elenco chiuso `comune.FIELDS` (op_id, operazione, appartamento, seq, parametri, ambiente, chi l'ha chiesto) più un campo nuovo **`firmato_at`** (ora UTC del server);
   - **dove viaggia:** nel corpo JSON del messaggio Pub/Sub, campo nuovo `firma` (esadecimale), escluso dalla forma canonica; `firmato_at` e `firma` entrano nell'elenco chiuso dei campi; il lettore passa all'esecutore il corpo così com'è;
   - **l'orario:** l'esecutore controlla da solo, con il suo orologio, che `firmato_at` non sia più vecchio di 15 minuti né più avanti di 2 (orologi), invece di fidarsi del lettore;
   - **il cambio della chiave degli ordini:** è l'esecutore ad accettare le due chiavi, la vecchia e la nuova, finché il server non firma solo con la nuova.
2. **Risultati firmati dall'esecutore:** HMAC-SHA256 con la chiave «risultati» (`/etc/domhouse/agent-risultati.key`, segreto `domhouse-agent-risultati-staging`). La firma copre op_id, ambiente, appartamento, operazione, seq, esito, codice, dati **e lo SHA-256 dell'ordine eseguito**; il server lo confronta con quello dell'ordine che ha pubblicato, salvato in `AgentOp`.
3. **Il formato:** JSON canonico (chiavi ordinate, nessuno spazio, UTF-8); confronto con `hmac.compare_digest` (revisione, punto 9).
4. **I risultati scritti dal lettore** (`scaduto`, `interrotto`, i rifiuti dei controlli) non hanno la firma dell'esecutore: il server li accetta **solo se non sono «riuscito»**.
5. **Le chiavi:** generate da root sulla VM (`secrets.token_bytes(32)`), messe in Secret Manager con i comandi del committente; il server ha `secretAccessor` solo su quei due segreti. `langbrain-vm@` non deve mai poterle leggere: i nomi `domhouse-agent-…` non sono coperti dai prefissi `langbrain-` (vincolo scritto anche nella procedura). Procedura di cambio delle chiavi: chiave nuova accanto alla vecchia; per i **risultati** il server accetta le due per un'ora, per gli **ordini** l'esecutore (punto 1); poi la vecchia si toglie.
6. **Repliche:** un ordine firmato ripetuto lo fermano già la `seq` e la scadenza di 15 minuti.

### 6.4 `lab-01` prima del primo «Registra»

Oggi i dispositivi di `lab-01` stanno nel segreto vecchio `langbrain-shelly-lab-01-devices`, non in Firestore. Il primo `aggiorna_broker` di `lab-01` scriverebbe un file con i soli dispositivi registrati dall'app, e la Plug (e gli Shelly della sessione delle 14:00) **perderebbero l'utente**. Quindi, prima di usare A3 su `lab-01`:

- **deciso (risposta 7): la migrazione prima di A3.** La VM calcola le impronte dalle password di oggi (§9.7 del progetto) e le scrive nel file; uno script le copia in Firestore come dispositivi «pronti» (le impronte, **mai** le password), così l'elenco dell'app e il file coincidono;
- con una procedura propria e il ritorno indietro: il file nuovo si toglie e il broker torna a leggere il segreto `-devices`, che resta com'è fino alla fine della migrazione; i documenti in Firestore si tolgono con lo stesso script;
- fatto quando: `broker-vm.sh status` con gli stessi utenti di prima, i dispositivi di `lab-01` in linea, e l'elenco dell'app uguale al file. Solo allora un segno di root (`/var/lib/domhouse-executor/migrati/lab-01`) apre `aggiorna_broker` su `lab-01`; prima: rifiutato `migrazione_non_fatta` (revisione, punto 12);
- **dopo la migrazione** (revisione, punto 16): un «Rigenera» per ciascuno Shelly di `lab-01` (le password di prima sono state in un segreto leggibile), poi la distruzione con ritardo del segreto `langbrain-shelly-lab-01-devices`.

## 7. La pagina locale (§8.3 del progetto), solo se entra in A3

**Non in A3** (risposta 6): appunto per il pezzo a parte, che avrà la sua proposta e la sua revisione. Rotte (gestore della piattaforma soltanto):

| Chiamata | Risposta |
|---|---|
| `POST …/{device_id}/apri-pagina-locale` | 200 `{password, open_until}`: la password una volta; all'agente `apri_accesso_locale` con l'`ha1` |
| `POST …/{device_id}/chiudi-pagina-locale` | 202: all'agente `chiudi_accesso_locale` |

- Due operazioni nuove nell'elenco chiuso dell'agente, con le regole del §8.3 (l'`ha1` è un segreto: mai in Firestore, nei giornali, nei log; ordine che scade in 2 minuti).
- Dopo 24 ore il server manda da solo `chiudi_accesso_locale`: serve un lavoro periodico (oggi il server non ne ha uno per questo).
- Prima: la revisione di sicurezza del §8.3 e le tre verifiche con Youssouf.

## 8. Permessi, limiti, registro

### 8.1 Chi può

- **Proposta:** l'amministratore dell'organizzazione (`require_admin`), come «Stato dei dispositivi». Un gestore della piattaforma entrato con l'accesso di assistenza ha i diritti di un operatore, quindi **non** può: è voluto, la password di un dispositivo la vede chi ne risponde.
- **Nello staging** (risposta 1): anche il gestore della piattaforma, con il prefisso `/app/platform/…`, solo per `lab-…` e `test-…` (§2). Il permesso sta in un punto solo.
- Lo stesso permesso nel sito: `devices.credentials` per il ruolo `admin`.

### 8.2 Gli errori

| Codice HTTP | `error` | Quando | Testo del server |
|---|---|---|---|
| 422 | `invalid_device_id` | id fuori regola (maiuscole comprese) | «Il codice non è valido: solo lettere minuscole, cifre e trattini, fino a 64 caratteri.» |
| 422 | `invalid_version` | `version` mancante o non intera | «Richiesta non valida: ricarica la pagina.» |
| 404 | `not_found` | appartamento o dispositivo che non c'è | «Dispositivo non registrato.» |
| 409 | `already_registered` | «Registra» su un dispositivo non revocato | «Questo dispositivo ha già una password. Se è persa, usa «Rigenera».» |
| 409 | `version_changed` | `version` diversa da quella salvata | «Qualcuno ha appena cambiato questo dispositivo: ricarica l'elenco.» |
| 409 | `operation_in_progress` | azione non ammessa mentre un'altra è in corso (§4.3) | «C'è già un'operazione in corso su questo dispositivo: aspetta che finisca.» |
| 409 | `invalid_state` | azione non ammessa per lo stato (§4.3) | «Con lo stato di adesso questa azione non si può fare: ricarica l'elenco.» |
| 409 | `too_many_devices` | 200 non revocati | «Questo appartamento ha già 200 dispositivi registrati: è il massimo.» |
| 429 | `rate_limited` | §8.3 | «Troppe operazioni in poco tempo: riprova fra qualche minuto.» |
| 503 | `agent_not_configured` | agente non configurato (`AGENT_*`) | «L'agente sulla VM non è configurato in questo ambiente» (come oggi) |
| 503 | `broker_address_missing` | `DEVICE_BROKER_ADDRESS` vuota (oggi la produzione); controllato **prima** di generare la password | «Indirizzo del sistema domotico per i dispositivi non configurato in questo ambiente.» |
| 502 | `agent_publish_failed` | «Revoca» o «Riprova» non inviate (§5.3) | il messaggio di oggi, con `op_id` |
| 403 | `forbidden` | senza permesso | come oggi |

Rispetto a o2: `version_changed`, `invalid_state` e `broker_address_missing` in più, separati da `operation_in_progress` e `agent_not_configured`, perché il sito fa cose diverse (ricaricare l'elenco, aspettare, o dire che manca una configurazione).

### 8.3 Limiti di frequenza

- Per organizzazione: **30 azioni l'ora** fra «Registra», «Rigenera», «Revoca», «Riprova» (ognuna fa un `sync`, e una revoca o una password nuova anche un riavvio del broker). Un contatore **suo**, separato da quello delle email (revisione, punto 15), con la stessa transazione di `take_mail_quota`.
- Per appartamento: **nessun limite a parte e nessuna coda**: le azioni ravvicinate si accettano, ognuna con la sua `seq`, e l'ordine riuscito più recente conferma i precedenti (§4.2).
- Un kit da 10 Shelly in una volta resta sotto il limite.

### 8.4 Registro attività

Quattro azioni nuove in `AuditAction`, una riga per azione di una persona:

| Azione | Testo nel registro (proposta per il sito) |
|---|---|
| `device_credential_registered` | «Registrato il dispositivo {id}» |
| `device_credential_regenerated` | «Nuova password per il dispositivo {id}» |
| `device_credential_revoked` | «Revocato il dispositivo {id}» |
| `device_credential_retried` | «Rimandate le credenziali di {id} al sistema domotico» |

- Bersaglio: l'appartamento e l'id del dispositivo. **Mai** password né impronta.
- Gli esiti dell'agente non fanno righe nel registro attività: restano nell'operazione (`agent_ops`, 90 giorni) e nei log del server. **Unica eccezione (risposta 8):** una riga «di sistema» quando una **revoca** finisce `non_applicato`, perché è il caso che conta per la sicurezza: azione `device_credential_revoke_not_applied`, «Revoca del dispositivo {id} non applicata: il dispositivo può ancora collegarsi. Usa «Riprova».», attore «sistema».
- **Riga e allarme nascono senza che nessuno apra la pagina** (revisione, punto 3; lo staging ha `minScale 0`, quindi un giro periodico da solo non basta lì):
  1. **nel ricevitore:** un esito rifiutato, scartato o fallito di una revoca o di una «Rigenera» scrive subito la riga (una volta per `seq`) e un log `agent alarm codice=revoca_non_applicata`; la consegna push di Pub/Sub sveglia l'istanza. **Anche la rotta:** quando «Revoca» risponde 502 `agent_publish_failed` scrive la stessa riga e lo stesso log (seconda lettura, N2);
  2. **l'allarme email su quel log è nuovo** (N2: oggi `agente-allarme.json` guarda solo i log della VM, `gce_instance`): un terzo allarme di A1 in `scripts/agent/allarmi/`, criterio sui log di Cloud Run (`resource.type="cloud_run_revision"`, servizio `domotica-bff-staging`, messaggio `agent alarm`), installato da `agent-gcp.sh` come gli altri due;
  3. **nessun esito** (VM ferma, ordine perso): **un allarme nuovo** sull'età del messaggio più vecchio non letto della sottoscrizione degli ordini (`pubsub.googleapis.com/subscription/oldest_unacked_message_age` di `domhouse-staging-ordini-vm`, oltre 20 minuti). In A1 c'è solo «scarti non vuoti»: nel primo giro avevo scritto per sbaglio che c'era già;
  4. **di riserva**, nel giro orario che c'è già (`summary_job`; in produzione `minScale 1`): le revoche e le «Rigenera» non confermate da oltre 20 minuti, una riga per `seq` e lo stesso log.

### 8.5 Firestore

- Documento `apartments/{apt}/device_credentials/{device_id}`: `device_id`, `impronta` (assente se revocato), `stato_salvato`, `azione`, `pending_seq`, `op_id`, `version`, `updated_at`, `updated_by` (uid), `revoked_at`.
- Nessun indice nuovo (lettura della sola sottoraccolta). Conservazione: finché c'è l'appartamento; un revocato resta nell'elenco per tutto quel tempo (risposta 9).
- Nessun client legge Firestore (regole di oggi).

## 9. Risposte del committente (19 novembre)

| N. | Registro | Domanda | Risposta | Dove nel documento |
|---|---|---|---|---|
| 1 | 1170 | Chi usa la pagina nello staging | **a:** le stesse rotte anche sotto `/app/platform/apartments/{apt}/device-credentials` per il gestore della piattaforma, solo `lab-…` e `test-…` nello staging | §2, §8.1 |
| 2 | — | Registrare prima di A4 | **rimandata ad A4** (non tocca il server) | — |
| 3 | 1171 | Conferma di «Revoca» | **riscrivere il codice del dispositivo** (al server non cambia niente) | sito |
| 4 | — | Molti dispositivi insieme | **rimandata ad A4** | — |
| 5 | 1172 | Contratto | **a:** solo `bff/API.md` | §1 |
| 6 | 1173 | Pagina locale | **a:** NON in A3; dopo, a parte, con la sua revisione e le verifiche con Youssouf | in testa, §7 |
| 7 | 1174 | `lab-01` | **a:** migrazione prima di A3 (§9.7 del progetto più lo script che copia le impronte in Firestore come «pronti», mai password), con procedura e ritorno indietro | §6.4 |
| 8 | 1175 | Revoca non applicata nel registro | **a:** riga «di sistema» solo per una revoca non applicata | §8.4 |
| 9 | 1176 | I revocati nell'elenco | **a:** restano finché c'è l'appartamento | §8.5 |
| 10 | 1177 | R8 dentro A3 | **a:** R8 entra in A3, prima di qualunque ordine che scrive. Quindi A3 prima di A2 (da confermare dopo la revisione) | §6.3 |

Le domande 6, 9 e 11 di o2 (maiuscole, PC senza internet, etichette della pagina dello Shelly) non toccano il server: la 6 ha la risposta tecnica «il server rifiuta, non converte» (§5.1); la 9 e la 11 restano di o2.

## 10. Stima in ore di A3

Ore di lavoro, prove comprese, senza le attese (revisioni, via, finestre sulla VM). Prima la stima per pezzo, poi quella che ritengo probabile.

| Pezzo | Chi | Cosa | Ore |
|---|---|---|---|
| Server: dati | o1 | repository (memoria e Firestore), transazione con `seq` e operazione, calcolo dello stato | 4–6 |
| Server: rotte | o1 | cinque rotte sotto i due prefissi (risposta 1), permessi, errori, limiti, registro con la riga di sistema (risposta 8), `DEVICE_BROKER_ADDRESS`, nome dal motore, `bff/API.md` | 6–8 |
| Server: esiti | o1 | `ultima_seq_riuscita` in transazione solo da `aggiorna_broker`, `seq` dall'operazione salvata (§4.2); riga e log nel ricevitore, nella rotta su 502 e nel giro orario (§8.4) | 6–8 |
| Allarmi | o1 | due allarmi nuovi in `scripts/agent/allarmi/` (log di Cloud Run, età dei messaggi degli ordini), `agent-gcp.sh`, prove | 1–2 |
| Server: prove | o1 | prove delle rotte, degli stati, delle corse fra azioni, dei 20 minuti, della password mai salvata | 5–7 |
| Agente: `aggiorna_broker` | o1 | esecutore, file atomico, `sync`, riavvio, codici, segno di `lab-01`, unità allargata e prova sulla VM, prove | 6–8 |
| Broker | o1 | `broker_accounts.py` dal file con il ripiego solo per `lab-01`, `broker-vm.sh` (cartella, `remove-apartment`, `auth/` a `root:1883` e i file a `1883:root`), prove; le prove `a3_` sul broker in container (scritte; lanciate con il via) | 4–6 |
| R8 firme nei due sensi | o1 | ordini firmati dal server con `firmato_at` e verificati dall'esecutore (orario compreso, doppia chiave nel cambio), risultati firmati con l'impronta dell'ordine, JSON canonico, due segreti, `agent-gcp.sh`, prove | 8–12 |
| `lab-01` | o1 | migrazione delle impronte (VM e Firestore), lo script e il suo ritorno indietro, procedura | 3–4 |
| Installazione | o1 | procedura di A3 (segreto, chiave, file sulla VM, variabile del server), correzioni dopo la revisione di sicurezza | 4–6 |
| Sito | o2 | pagina, finestre, stati, errori, rilettura ogni 4 s, permesso, prove (proposta di o2) | 10–14 |
| **Totale** | | | **57–81** |
| Pagina locale (§7): **fuori da A3** (risposta 6), pezzo a parte | o1, o2 | due operazioni dell'agente, due rotte, chiusura dopo 24 ore, finestra nel sito | (6–9, a parte) |

**Probabile:** circa **48–59 ore** in tutto (circa 38–45 di o1 e 10–14 di o2), dopo le correzioni della revisione di sicurezza (§12). Le stime per pezzo tendono a essere larghe: quella del clima a infrarossi (risposta 1141) è scesa da 15–22 a 8–11 ore dopo la rilettura. La voce che può crescere è un'altra: la revisione di sicurezza di A3, che tocca password e revoche, e le sue correzioni (per A1 le letture sono state quattro).

## 11. Risposte ai punti di o2 (`docs/proposta-a3-sito.md` §9, `a0b2df1`)

| N. | Punto | Risposta | Dove è corretto |
|---|---|---|---|
| 1 | `azione` dopo «Riprova» | **o2 ha ragione.** `azione` è l'azione in attesa di conferma (`registra`, `rigenera`, `revoca`) e «Riprova» non la sovrascrive: un `non_applicato` dopo una riprova dice ancora se manca una revoca. `riprova` non è più un valore di `azione`; la riga del registro attività resta `device_credential_retried` | §2.1, §4.1 |
| 2 | coerenza fra azione e stato durante una riprova | Con il punto 1 lo stato in volo è quello dell'azione riprovata (`in_attesa`, `cambio_in_corso`, `revoca_in_corso`) e `azione` dice la stessa cosa | §4.1 |
| 3 | il nome del dispositivo | **o2 ha ragione:** `Device` non ha l'id Shelly. `name` null fino ad A4, nessuna voce «Credenziali» in «Stato dei dispositivi» fino ad allora; con A4 il server aggiunge `engine_device_id` e il `label` dal catalogo che conosce | §2.1, §2.2 |
| 4 | un solo 503 per due cause | **o2 ha ragione:** codice a parte `broker_address_missing`, con il testo proposto da o2 | §5.1, §8.2 |
| 5 | `connection.server` in produzione | Il `GET` non dà mai 503 per questo: `connection.server` è **null** e il sito scrive «non configurato» al posto del valore da copiare. «Registra» e «Rigenera» invece rispondono 503 `broker_address_missing` prima di generare la password | §2.1, §5.1 |
| 6 | i «no» senza codice | Ogni casella del §4.3 ha ora il suo codice: `operation_in_progress` se un ordine in volo blocca (si aspetta), `invalid_state` se lo stato non ammette l'azione (si ricarica) | §4.3 |
| 7 | due «Registra di nuovo» insieme | La transazione riporta il revocato ad attivo: la prima passa (201 con la password), la seconda riceve **409 `already_registered`** | §3 |

## 12. Correzioni dopo la revisione di sicurezza (19 novembre)

Revisione indipendente (`revisione-a2-a3/REVISIONE-SICUREZZA-A2-A3.md`, fuori dal repository): A3 «eseguibile dopo correzioni». Valutazione di o1 verificata sul codice: d'accordo su tutti i punti.

| Punto | Che cosa | Dove è corretto |
|---|---|---|
| 1 | ordini non firmati fra lettore ed esecutore: firme nei due sensi, l'impronta dell'ordine nella firma del risultato | §6.3 |
| 2, N1 | nessuna scrittura a ventaglio: `ultima_seq_riuscita` in transazione, solo dagli esiti riusciti di `aggiorna_broker`; `seq` dall'operazione salvata | §4.2 |
| 3, N2 | riga e allarme per una revoca non applicata anche senza nessuno sulla pagina: nel ricevitore e nella rotta su 502; due allarmi nuovi (log di Cloud Run, età dei messaggi degli ordini); il giro orario di riserva | §4.1, §8.4 |
| 4, N3 | l'unità dell'esecutore: l'elenco esatto di cosa si apre; `auth/` a `root:1883`, i file a `1883:root`, solo `CAP_CHOWN` | §6.1 |
| 5, N4 | il collegamento già aperto: riavvio del broker dopo una revoca **e** dopo una «Rigenera», salvo che la misura dica che basta il `sync`; tre prove sul broker in container che misurano senza presupporre; per la produzione un vincolo aperto (raccogliere i riavvii o staccare il singolo client) | §5.4, §6.2 |
| 9, N5 | R8 completo: JSON canonico, `compare_digest`, risultati del lettore mai «riuscito», chiavi mai leggibili dalla VM, cambio della chiave; cosa copre la firma degli ordini e dove viaggia, `firmato_at` controllato dall'esecutore, doppia chiave degli ordini nell'esecutore | §6.3 |
| 10 | regole sullo stato calcolato; una revoca non applicata solo con «Riprova» | §4.3 |
| 11 | `connector` rifiutato come id | §5.1 |
| 12 | ripiego su `-devices` solo per `lab-01`; file creato prima di `add-apartment`; `lab-01` rifiutato prima della migrazione | §6.1, §6.2, §6.4 |
| 13 | condizioni IAM: il segreto del connector di `lab-01` escluso per nome | proposta A2, §3.3 (i ruoli li usa A2) |
| 15 | limite di frequenza senza contraddizione, contatore suo | §8.3 |
| 16 | dopo la migrazione un «Rigenera» per ciascuno Shelly di `lab-01`, poi via il segreto `-devices` | §6.4 |

I punti 6, 7, 8 e 14 sono di A2 (proposta A2, §11).
