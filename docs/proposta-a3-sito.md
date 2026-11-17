# Proposta: A3, credenziali dei dispositivi, parte del sito

| Stato | Scritto da | Basato su | Prossimo passo |
|---|---|---|---|
| **Proposta, nessun codice** (17 novembre 2026, 11:09) | o2 | `docs/progetto-strumento-a-base.md` §2.2, §2.3, §2.5, §8.1, §8.3, §8.4 (D-233); registro, pacchetto A3; documento interno dell'Autonomia, §14 e decisione 4 del §11; `docs/motore-vm.md`, impostazioni MQTT dello Shelly | rilettura della memoria storica; o1 fissa le chiamate del server (§6); risposte alle domande (§8); poi il codice |

**Termini:** quelli di `docs/guida-utente.md` (riletta il 17 novembre): «sistema domotico», «gestore della piattaforma», «accesso di assistenza», «Registro attività», «ID richiesta», «in linea». Nei testi per chi usa l'app non compaiono «catalogo», «broker» né «impronta».

**Cosa copre:** le schermate di «Registra», «Rigenera» e «Revoca», la password mostrata una volta sola, gli stati, gli errori, cosa serve dal server.

**Cosa non copre:**

- il modulo del catalogo (A4; nella guida «elenco dei dispositivi»): lì «Registra» partirà dal salvataggio, con le stesse chiamate;
- gli accessi rifiutati (A5): stanno nella pagina «Stato dei dispositivi»;
- la guida: i testi per la guida li mando alla memoria storica quando il codice è fatto.

## 1. Dove stanno

1. **Una pagina nuova dell'appartamento: «Credenziali dei dispositivi»**, indirizzo `/a/<apt>/credenziali`.
   - Elenca i dispositivi **registrati** (da Firestore, attraverso il server), non quelli del motore: un dispositivo si registra prima di essere nel catalogo e prima di collegarsi.
   - Nel menu dell'appartamento, accanto a «Stato dei dispositivi», visibile solo a chi ha il permesso (§1.4).
2. **Collegamenti dalle altre pagine:**
   - in «Stato dei dispositivi», sulla riga di un dispositivo registrato, la voce «Credenziali» porta alla sua riga;
   - con A4, nel modulo del catalogo, la riga di ogni Shelly ha lo stesso menu (dati di collegamento, «Rigenera», «Revoca»).
3. **Perché una pagina a sé e non dentro «Stato dei dispositivi»:** quella pagina mostra il motore, e un dispositivo appena registrato non c'è ancora. Tenerle separate evita righe «fantasma» nella diagnosi.
4. **Chi la vede:** un permesso nuovo, `devices.credentials`, nel punto unico dei permessi (`src/auth/permissions.ts`).
   - Proposta: l'amministratore dell'organizzazione, come «Stato dei dispositivi».
   - Nello staging: da decidere (domanda 1).
5. **Telefono (390 px):** la pagina funziona, ma il lavoro vero si fa in sede, su un PC. Sul telefono le colonne diventano schede e i valori da copiare vanno uno sotto l'altro.

## 2. Le schermate

### 2.1 L'elenco

| Colonna | Contenuto |
|---|---|
| Dispositivo | il nome, se il motore lo conosce; sotto, il codice (`shellyplugmg3-9070695cb0d0`) |
| Stato | un'etichetta colorata (§3) |
| Ultima modifica | data e ora, e chi l'ha fatta |
| Azioni | menu: «Dati di collegamento», «Rigenera», «Revoca» (o «Registra di nuovo» se revocato) |

- **In alto:** il pulsante «Registra un dispositivo».
- **Elenco vuoto:** «Nessun dispositivo registrato. Registra ogni Shelly prima di montarlo: ti diamo la password da copiare nella sua pagina.»
- **Mentre un'operazione è in corso** la pagina si rilegge da sola ogni 4 secondi, per al massimo 20 minuti (come «Prova l'agente»).

### 2.2 «Registra un dispositivo»

Una finestra con un solo campo.

1. **Campo:** «Codice del dispositivo», esempio nel segnaposto `shellyplugmg3-9070695cb0d0`.
2. **Controllo mentre si scrive**, con la regola del progetto (§2.1): `^[a-z0-9][a-z0-9-]{0,63}$`.
   - Messaggio: «Solo lettere minuscole, cifre e trattini, fino a 64 caratteri.»
   - Le maiuscole **non** si convertono da sole: il codice deve essere quello letto sul dispositivo (domanda 6).
3. **Pulsante:** «Registra». Poi si apre la finestra della password (§2.3).

### 2.3 La finestra della password (una volta sola)

È il punto delicato: la password esiste solo qui.

**Titolo:** «Password di {nome o codice}»

**Avvertenza in evidenza, in alto:**

> La vedi solo ora. Copiala nella pagina dello Shelly prima di chiudere: dopo non si può più leggere, né qui né altrove. Se la perdi, usa «Rigenera».

**I valori da copiare**, ognuno con il suo «Copia» (dal §8 di `docs/motore-vm.md`; i valori li manda il server, il sito non ne scrive nessuno):

| Etichetta nel sito | Valore | Esempio nello staging |
|---|---|---|
| Server | indirizzo e porta del broker | `mqtt.dh-lab.eu:8883` |
| Certificato | sempre «certificato integrato (ca.pem)» | `ca.pem` |
| Client ID | uguale all'utente | `lab-01.shellyplugmg3-9070695cb0d0` |
| Utente | `<apt>.<dispositivo>` | `lab-01.shellyplugmg3-9070695cb0d0` |
| **Password** | 32 caratteri, in chiaro, carattere a larghezza fissa | — |
| Prefisso | `<apt>/<dispositivo>` | `lab-01/shellyplugmg3-9070695cb0d0` |
| Altre impostazioni | notifiche RPC sì; stato generico no; controllo no | — |

**Come si chiude:**

1. il pulsante «Chiudi» resta spento finché non si spunta «Ho copiato la password nello Shelly»;
2. il tasto Esc e il clic fuori dalla finestra **non** la chiudono;
3. chiusa la finestra, la password non è più nella pagina.

**Sotto i valori, una riga piccola:** «Se il tuo PC sincronizza gli appunti con altri dispositivi, dopo la copia svuotali.» (testo completo nella guida).

**Il PC senza internet:** per aprire la pagina locale, il PC spesso si collega alla rete Wi-Fi dello Shelly e perde internet. La finestra deve restare aperta e leggibile anche così: niente uscita automatica, niente ricarica della pagina (domanda 9).

### 2.4 «Dati di collegamento» (sempre visibili)

La stessa tabella del §2.3, **senza la password**. Al suo posto:

> Password: non si può più leggere. Se è persa o l'ha vista chi non doveva, usa «Rigenera».

Serve a chi riconfigura uno Shelly o controlla un valore: tutto tranne la password resta sempre leggibile (decisione 4 del documento interno, §11).

### 2.5 «Rigenera»: la conferma

**Titolo:** «Nuova password per {nome}?»

**Testo:**

> Creiamo una password nuova. Quella di adesso smette di valere appena il sistema domotico conferma il cambio: da quel momento lo Shelly si scollega, finché non ci copi la password nuova (sul posto o in sede).

**Pulsanti:** «Annulla» e «Crea la password nuova». Poi la finestra del §2.3.

### 2.6 «Revoca»: la conferma

**Titolo:** «Revocare {nome}?»

**Testo:**

> Il dispositivo non potrà più collegarsi al sistema domotico. Usalo se è stato perso, rubato o tolto dall'impianto. Per rimetterlo in uso serve una registrazione nuova, con una password nuova, dopo averlo riportato alle impostazioni di fabbrica.

**Pulsanti:** «Annulla» e «Revoca», rosso.

- Proposta: **niente codice da riscrivere** per confermare, perché si torna indietro con «Registra di nuovo». Chi preferisce la conferma scritta, come per l'eliminazione di un appartamento: domanda 5.

### 2.7 La pagina locale dello Shelly (solo se il §8.3 del progetto viene approvato)

1. **Per tutti:** nella riga del dispositivo, «Pagina locale: chiusa» oppure «aperta fino alle {ora}».
2. **Solo per il gestore della piattaforma:** «Apri la pagina locale».
   - Mostra una password **una volta**, con la stessa finestra del §2.3 (solo utente `admin` e password).
   - Testo: «La pagina locale resta aperta al massimo 24 ore. Quando hai finito, premi «Chiudi la pagina locale»: la password che hai visto smette di valere.»
3. **«Chiudi la pagina locale»**, accanto, finché è aperta.

Questa parte aspetta la revisione di sicurezza del §8.3 (domanda 10).

## 3. Gli stati

| Stato (server) | Etichetta | Colore | Riga di spiegazione | Azioni |
|---|---|---|---|---|
| in attesa del broker | «In preparazione» | neutro | «Registrato: il sistema domotico lo sta abilitando.» | Dati di collegamento |
| pronto | «Pronto» | verde | «Può collegarsi.» | Dati, Rigenera, Revoca |
| cambio in corso | «Cambio password in corso» | giallo | «Finché il sistema non conferma, vale ancora la password vecchia.» | Dati, Revoca |
| revoca in corso | «Revoca in corso» | giallo | «Finché il sistema non conferma, il dispositivo può ancora collegarsi.» | — |
| revocato | «Revocato» | grigio | «Non può più collegarsi.» | Registra di nuovo |
| non applicato | «Non applicato» | rosso | il messaggio del server, con il pulsante «ID richiesta» da copiare (il codice dell'operazione) | Riprova, Revoca |

**Note:**

1. «Pronto» **non** vuol dire «in linea»: dice solo che il broker lo accetta. Se è in linea lo dice «Stato dei dispositivi». La riga lo ricorda con un collegamento.
2. «Non applicato» arriva quando l'ordine al broker è rifiutato, scartato, fallito, o senza risposta dopo 20 minuti (progetto §6.8).
3. «Riprova» **non** crea una password nuova: rimanda l'elenco delle impronte al broker.
4. Se «Revoca» si può premere anche durante un cambio in corso: domanda 3.

## 4. Gli errori

Il testo viene dal server quando c'è; altrimenti questi, in `it.json`. Codici provvisori, da fissare con o1.

| Quando | Codice provvisorio | Testo |
|---|---|---|
| codice del dispositivo non valido | 422 `invalid_device_id` | «Il codice non è valido: solo lettere minuscole, cifre e trattini, fino a 64 caratteri.» |
| dispositivo già registrato | 409 `already_registered` | «Questo dispositivo ha già una password. Se è persa, usa «Rigenera».» |
| un'altra operazione sullo stesso dispositivo | 409 `operation_in_progress` | «C'è già un'operazione in corso su questo dispositivo: aspetta che finisca.» |
| troppi dispositivi (200) | 409 `too_many_devices` | «Questo appartamento ha già 200 dispositivi registrati: è il massimo.» |
| troppe operazioni ravvicinate | 429 `rate_limited` | «Troppe operazioni in poco tempo: riprova fra qualche minuto.» |
| agente non installato | 503 `agent_not_configured` | «Agente non ancora installato in questo ambiente.» (già nel sito) |
| ordine non inviato | 502 `agent_publish_failed` | il messaggio del server, con il pulsante «ID richiesta» da copiare |
| senza permesso | 403 | il testo che il sito usa già |
| rete caduta durante «Registra» o «Rigenera» | — | «Non sappiamo se la password è stata creata. Ricarica l'elenco: se il dispositivo risulta registrato, usa «Rigenera».» |

L'ultimo caso è il più delicato: la password può essere nata sul server senza arrivare al sito. Domanda 4.

## 5. La password nel sito: cosa fa il codice

1. Vive **solo nello stato del componente** della finestra: mai nell'URL, in `localStorage`, `sessionStorage`, nella cache delle query o nei registri della console.
2. Il campo è in sola lettura, con `autocomplete="off"`: il browser non la propone e non la salva.
3. Chiusa la finestra o cambiata pagina, lo stato si azzera.
4. Gli errori che il sito mostra o scrive nella console non contengono mai il corpo della risposta.
5. **Prove previste** (vitest), prima del codice:
   - la password compare una volta, e sparisce dalla pagina dopo «Chiudi»;
   - Esc e clic fuori non chiudono; «Chiudi» è spento senza la spunta;
   - dopo la chiusura non è in `localStorage`, `sessionStorage`, nell'URL;
   - «Dati di collegamento» non la mostra mai;
   - ogni stato del §3 ha etichetta e azioni giuste;
   - la rilettura ogni 4 secondi si ferma all'esito e dopo 20 minuti.

## 6. Cosa serve dal server

Nomi provvisori, sullo stile delle rotte di oggi (`/app/apartments/{apt}/…`). Tutte con l'id di correlazione, come le altre.

### 6.1 Le chiamate

| Chiamata | Corpo | Risposta |
|---|---|---|
| `GET /app/apartments/{apt}/device-credentials` | — | elenco di `DeviceCredential` (§6.2) |
| `POST /app/apartments/{apt}/device-credentials` | `{device_id}` | 201 `{credential, password}` |
| `POST /app/apartments/{apt}/device-credentials/{device_id}/rigenera` | `{version}` | 200 `{credential, password}` |
| `POST /app/apartments/{apt}/device-credentials/{device_id}/revoca` | `{version}` | 202 `{credential}` |
| `POST /app/apartments/{apt}/device-credentials/{device_id}/riprova` | `{version}` | 202 `{credential}` |

- `version` è quella che il sito ha letto: se nel frattempo è cambiata, 409 `operation_in_progress` (il blocco per dispositivo del §8.1 del progetto).
- Le risposte con la password hanno `Cache-Control: no-store`.

### 6.2 I campi di `DeviceCredential`

| Campo | Tipo | Note |
|---|---|---|
| `device_id` | stringa | |
| `name` | stringa o null | il nome dal motore, se lo conosce |
| `stato` | `in_attesa` · `pronto` · `cambio_in_corso` · `revoca_in_corso` · `revocato` · `non_applicato` | §3 |
| `version` | intero | per il blocco |
| `updated_at` | data e ora | |
| `updated_by` | nome visibile | mai l'email |
| `op` | `{op_id, stato, messaggio}` o null | l'ultima operazione verso il broker, con il messaggio già in italiano, come in «Prova l'agente» |
| `connection` | `{server, ssl_ca, client_id, user, topic_prefix}` | i dati sempre visibili; il server li calcola (indirizzo del broker per ambiente) |
| `local_page` | `{open_until}` o null | solo con il §8.3 |

**Mai nelle risposte:** l'impronta. Al sito non serve, e così non finisce nel browser.

### 6.3 Altro

1. **Registro attività:** una riga per «Registra», «Rigenera», «Revoca», «Riprova», con i nomi delle azioni da fissare; il sito aggiunge i loro testi al «Registro attività».
2. **Il permesso** `devices.credentials`: o1 dice chi lo ha sul server, il sito lo mette in `permissions.ts` uguale.
3. **Nessun evento nello stream:** basta rileggere l'elenco mentre c'è un'operazione in corso.
4. **Con il §8.3:** `POST …/{device_id}/apri-pagina-locale` (risposta `{password, open_until}`) e `POST …/{device_id}/chiudi-pagina-locale`.
5. **Il contratto:** se queste rotte entrano in `contract/openapi.yaml` o restano del solo server, come quelle dell'agente (domanda 8).

## 7. Testi per la guida (da mandare alla memoria storica a codice fatto)

1. dove si registra un dispositivo, e perché prima del montaggio;
2. come si copiano i valori nella pagina dello Shelly, campo per campo;
3. la password si vede una volta sola; gli appunti sincronizzati;
4. quando usare «Rigenera» e quando «Revoca»;
5. la differenza fra «Pronto» e «in linea».

## 8. Domande aperte

1. **Chi usa la pagina nello staging?** Gli appartamenti `lab-…` e `test-…` li crea solo il gestore della piattaforma (progetto §5.5), che però oggi non vede l'uso di un'organizzazione (P-36). Proposta: nello staging la pagina è anche del gestore della piattaforma, con una voce in «Organizzazioni» accanto a «Prova l'agente». Va bene, o serve l'accesso di assistenza?
2. **Registrare prima di A4:** finché il modulo del catalogo non c'è, il codice si scrive a mano in «Registra un dispositivo» (§2.2). Con A4 la registrazione parte dal salvataggio del catalogo: questa finestra resta, o sparisce?
3. **«Revoca» durante un cambio in corso:** la propongo ammessa, perché un dispositivo rubato non deve aspettare. Il blocco del server lo permette, o deve rifiutare con `operation_in_progress`?
4. **Rete caduta durante «Registra» o «Rigenera»** (§4, ultima riga): il server ha salvato l'impronta, ma la password non è arrivata. Il progetto dice «una seconda chiamata dice «già generata, usa Rigenera»». Va bene così, o il server accetta di nuovo la stessa richiesta (stesso id di correlazione) entro pochi secondi, senza conservare la password? Io lascerei la strada del progetto, che è più semplice.
5. **Conferma di «Revoca»:** basta il pulsante rosso, o si riscrive il codice del dispositivo come per l'eliminazione?
6. **Codici con le maiuscole:** se qualcuno scrive `ShellyPlugMG3-…`, il sito rifiuta (proposta) o converte in minuscole? Gli id Shelly sono già minuscoli.
7. **Molti dispositivi insieme (A4):** un kit ha circa 10 Shelly. Al salvataggio del catalogo le password nascono tutte insieme: una finestra con l'elenco di tutte, una per riga con «Copia»? La stampa no: il foglio dell'elettricista non contiene password (decisione 4 del §11 del documento interno).
8. **Contratto:** le rotte entrano in `contract/openapi.yaml` (con i tipi generati nel sito) o restano descritte in `bff/API.md`, come quelle dell'agente?
9. **PC senza internet in sede** (§2.3): va provato che la finestra resti aperta e la sessione non scada mentre il PC è collegato alla rete Wi-Fi dello Shelly. È una prova mia, con il sito di sviluppo e la rete staccata: la faccio a codice fatto.
10. **Pagina locale (§2.7):** entra in A3 insieme, o dopo la revisione di sicurezza del §8.3, come pezzo a parte?
11. **Le etichette dei campi nella pagina dello Shelly:** il sito usa «Server», «Client ID», «Utente», «Password», «Prefisso». Per la guida servono i nomi esatti della pagina locale dei modelli ammessi, con una schermata: da chiedere a Youssouf (insieme alle schermate del pacchetto A9)?
