# Proposta: A3, credenziali dei dispositivi, parte del server e dell'agente

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta con le risposte del committente** (scritta il 17 novembre 2026; risposte 1170–1177 del 19 novembre nel §9). Nessun codice | o1 | `docs/proposta-a3-sito.md` (o2, `f607187`, `4cb6bab`); `docs/progetto-strumento-a-base.md` §2.1, §2.2, §2.3, §2.5, §3, §3.2, §4, §6, §8.1, §8.3, §9 (D-233); il codice di A1 (`bff/agent.py`, `scripts/agent/`) | i punti di o2 chiusi (§11); revisione di sicurezza indipendente, insieme ad A2; poi il codice. **A3 prima di A2** (risposta 10: R8 entra qui), da confermare dopo la revisione |

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

Calcolarlo alla lettura vuol dire che il limite dei 20 minuti (progetto §6.8) non ha bisogno di un timer.

### 4.2 Un esito conferma tutto fino alla sua `seq`

Quando arriva un risultato **riuscito** di `aggiorna_broker` con `seq` S per l'appartamento:

- ogni dispositivo con `pending_seq ≤ S` esce dall'attesa: `registra` e `rigenera` → `pronto`; `revoca` → `revocato`;
- perché l'ordine S portava l'elenco completo letto **dopo** tutti i cambi con `seq` più bassa.

Quando arriva un risultato **non riuscito** con `seq` S: cambiano solo i dispositivi con `pending_seq = S`, che si leggono `non_applicato`. Se poi riesce un ordine con `seq` più alta, li conferma (regola sopra).

Un risultato con `seq` più bassa di uno già riuscito non cambia niente (l'agente lo rifiuta comunque, §6.4 del progetto).

### 4.3 Azioni ammesse per stato

| Stato | Rigenera | Revoca | Riprova | Registra |
|---|---|---|---|---|
| `in_attesa` | sì (password persa prima della conferma) | sì | 409 `invalid_state` | 409 `already_registered` |
| `pronto` | sì | sì | 409 `invalid_state` | 409 `already_registered` |
| `cambio_in_corso` | 409 `operation_in_progress` | **sì** (domanda 3 di o2, §8) | 409 `operation_in_progress` | 409 `already_registered` |
| `revoca_in_corso` | 409 `operation_in_progress` | 409 `operation_in_progress` | 409 `operation_in_progress` | 409 `operation_in_progress` |
| `revocato` | 409 `invalid_state` | 409 `invalid_state` | 409 `invalid_state` | sì: «Registra di nuovo», password nuova |
| `non_applicato` | sì | sì | sì | 409 `already_registered` |

**La regola dei due codici:** `operation_in_progress` quando l'azione è bloccata da un ordine in volo (aspettando, diventerà possibile); `invalid_state` quando lo stato non la ammette proprio (il sito ricarica l'elenco). Ogni casella ha il suo codice: nessun «no» senza codice (§11, punto 6).

## 5. Le azioni, passo per passo

### 5.1 «Registra»

1. Controlli: permesso (§8.1), id del dispositivo (422 `invalid_device_id`, **senza** convertire le maiuscole: domanda 6 di o2), limite di frequenza (§8.3), agente configurato (503 `agent_not_configured`), indirizzo del broker configurato (503 `broker_address_missing`), al massimo 200 dispositivi non revocati (409 `too_many_devices`). Tutti **prima** di generare la password.
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
3. Al risultato riuscito il broker ha tolto l'utente. **Da verificare** (progetto §8.1): che la ricarica di Mosquitto faccia cadere anche il collegamento **già aperto** di un utente tolto. Per «Rigenera» è provato il 16 novembre; per un utente tolto si prova sul broker in container (`tests/broker_container_test.py`, **con il via del committente**). Se non cade, l'agente dopo il `sync` riavvia il broker quando un utente è stato tolto (§6.2).

### 5.5 «Riprova»

Una transazione con `version` e una `seq` nuova che rilegge l'elenco completo; nessuna password nuova. Ammessa solo in `non_applicato`.

### 5.6 Rete caduta durante «Registra» o «Rigenera» (domanda 4 di o2)

- Il server non conserva la password nemmeno per pochi secondi: rifare la stessa chiamata dà 409 (`already_registered` o `version_changed`), e il sito dice di usare «Rigenera». È la strada del progetto (§8.1); la propongo anche io.

## 6. L'agente sulla VM per A3

### 6.1 `aggiorna_broker` (l'esecutore)

Oggi l'elenco chiuso lo accetta già nei controlli (`scripts/agent/comune.py`: al massimo 200, id con la regola, impronte nel formato `$7$`, mai una password) ma risponde «non_disponibile». In A3 l'esecutore lo **esegue**:

1. sotto il blocco della VM, scrive in modo atomico `/etc/domhouse/_broker/devices/<apt>` (root, 600): una riga `<device_id> <impronta>` per dispositivo dell'elenco;
2. lancia il `sync` del broker per quell'appartamento (isolato, E-33);
3. esiti, con codici di un elenco chiuso:

| Esito | Codice | Quando |
|---|---|---|
| riuscito | — | file scritto e `sync` concluso; `dati`: `{dispositivi: N}` |
| rifiutato | `appartamento_sconosciuto` | il broker non ha l'appartamento (`add-apartment` non fatto: arriva con A2) |
| rifiutato | i codici dei controlli di oggi | `troppi_dispositivi`, `id_non_valido`, `impronta_non_valida`, `parametri_non_validi` |
| fallito | `sync_fallito` | il `sync` ha tenuto le righe di prima per quell'appartamento («kept») o non è riuscito |
| fallito | `errore_interno` | come oggi |

4. Il server traduce i codici in italiano (`MESSAGES` di `bff/agent.py`).

### 6.2 Il broker

- `broker_accounts.py` (§9.4 del progetto): i dispositivi di un appartamento dal file delle impronte, prese così come sono; il conto del connector da Secret Manager come oggi. Senza file resta il segreto vecchio `-devices` (solo `lab-01`).
- `broker-vm.sh`: la cartella `devices/` (root, 700), `remove-apartment` toglie anche il file.
- Se la prova del §5.4 dice che un utente tolto resta collegato: dopo il `sync`, se l'elenco nuovo ha **tolto** qualcuno, `broker-vm.sh restart` (tutti si ricollegano: pochi secondi).

### 6.3 Condizione di sicurezza: i risultati firmati (R8) prima di A3

Con A1 un risultato falso cambia solo un «stato». Con A3 un risultato falso «riuscito» di una **revoca** farebbe vedere «Revocato» mentre il dispositivo rubato si collega ancora. Quindi **R8 (progetto §3.2) entra in A3, prima di qualunque ordine che scrive** (risposta 10). Conseguenza: A3 prima di A2, da confermare dopo la revisione di sicurezza.

1. l'esecutore firma i risultati con HMAC-SHA256 (chiave di root `/etc/domhouse/agent-hmac.key`, 600; il lettore non la legge);
2. la firma copre op_id, ambiente, appartamento, operazione, seq, esito, codice e dati;
3. il server legge la stessa chiave da un segreto nuovo (`domhouse-agent-hmac-staging`) e scarta un risultato senza firma valida;
4. servono: il segreto, il permesso di lettura del server su quel solo segreto, l'installazione della chiave sulla VM. Comandi del committente, in una procedura.

### 6.4 `lab-01` prima del primo «Registra»

Oggi i dispositivi di `lab-01` stanno nel segreto vecchio `langbrain-shelly-lab-01-devices`, non in Firestore. Il primo `aggiorna_broker` di `lab-01` scriverebbe un file con i soli dispositivi registrati dall'app, e la Plug (e gli Shelly della sessione delle 14:00) **perderebbero l'utente**. Quindi, prima di usare A3 su `lab-01`:

- **deciso (risposta 7): la migrazione prima di A3.** La VM calcola le impronte dalle password di oggi (§9.7 del progetto) e le scrive nel file; uno script le copia in Firestore come dispositivi «pronti» (le impronte, **mai** le password), così l'elenco dell'app e il file coincidono;
- con una procedura propria e il ritorno indietro: il file nuovo si toglie e il broker torna a leggere il segreto `-devices`, che resta com'è fino alla fine della migrazione; i documenti in Firestore si tolgono con lo stesso script;
- fatto quando: `broker-vm.sh status` con gli stessi utenti di prima, i dispositivi di `lab-01` in linea, e l'elenco dell'app uguale al file.

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

- Per organizzazione: **30 azioni l'ora** fra «Registra», «Rigenera», «Revoca», «Riprova» (ognuna fa un `sync` e una ricarica del broker). Stessi contatori di oggi (`take_mail_quota`, nome da generalizzare).
- Per appartamento: al massimo **un ordine `aggiorna_broker` in volo ogni 5 secondi**; le azioni ravvicinate si accodano nella `seq` e l'ultimo ordine porta tutto. Proposta semplice: nessuna coda, si accetta lo stesso; l'ordine più recente conferma i precedenti (§4.2).
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
| Server: esiti | o1 | conferma per `seq` (§4.2) nel ricevitore dei risultati di A1 | 2–3 |
| Server: prove | o1 | prove delle rotte, degli stati, delle corse fra azioni, dei 20 minuti, della password mai salvata | 5–7 |
| Agente: `aggiorna_broker` | o1 | esecutore, file atomico, `sync`, codici, prove | 3–4 |
| Broker | o1 | `broker_accounts.py` dal file, `broker-vm.sh` (cartella, `remove-apartment`), prove; la prova della revoca sul broker in container (con il via) | 3–5 |
| R8 firma dei risultati | o1 | esecutore, lettore, server, segreto, `agent-gcp.sh`, prove | 5–7 |
| `lab-01` | o1 | migrazione delle impronte (VM e Firestore), lo script e il suo ritorno indietro, procedura | 3–4 |
| Installazione | o1 | procedura di A3 (segreto, chiave, file sulla VM, variabile del server), correzioni dopo la revisione di sicurezza | 4–6 |
| Sito | o2 | pagina, finestre, stati, errori, rilettura ogni 4 s, permesso, prove (proposta di o2) | 10–14 |
| **Totale** | | | **45–64** |
| Pagina locale (§7): **fuori da A3** (risposta 6), pezzo a parte | o1, o2 | due operazioni dell'agente, due rotte, chiusura dopo 24 ore, finestra nel sito | (6–9, a parte) |

**Probabile:** circa **37–47 ore** in tutto (circa 27–33 di o1 e 10–14 di o2). Le stime per pezzo tendono a essere larghe: quella del clima a infrarossi (risposta 1141) è scesa da 15–22 a 8–11 ore dopo la rilettura. La voce che può crescere è un'altra: la revisione di sicurezza di A3, che tocca password e revoche, e le sue correzioni (per A1 le letture sono state quattro).

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
