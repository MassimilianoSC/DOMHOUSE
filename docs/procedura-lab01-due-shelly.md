# Lab-01: lo Shelly 1 Gen4 e l'EM Mini Gen4 sul nostro broker

| Stato | Preparata | Decisione | Chi lancia |
|---|---|---|---|
| **Da fare.** Nessun passo provato su questi due modelli. Riletta dalla memoria storica il 17 novembre (versione del segreto ancora 3; §5 aggiornato: catalogo già nel motore) | o1, 16 novembre 2026 | risposta 1138 = a | il committente, con Youssouf che guida dalla pagina locale degli Shelly |

**Dispositivi** (catalogo di Youssouf, `per-youssouf/RISPOSTE-Y/lab-01.yaml`):

| Id nativo | Modello | Nel catalogo | Utente del broker |
|---|---|---|---|
| `shellyemminig4-acebe6e42d6c` | Shelly EM Mini Gen4 | `dev-misura-lab` | `lab-01.shellyemminig4-acebe6e42d6c` |
| `shelly1g4-98a3166d8d80` | Shelly 1 Gen4 | `dev-caldaia-lab`, ponte dei tre sensori BLU | `lab-01.shelly1g4-98a3166d8d80` |

**Tutti i comandi si lanciano in Git Bash**, dalla cartella `app`.

## Prima di cominciare

1. **Ordine:** passi 1 e 2 una volta sola; poi l'EM Mini (passo 3) e, **solo dopo che il passo 3 è finito**, lo Shelly 1 (passo 4). Un dispositivo alla volta.
2. **Lo Shelly 1 oggi è collegato al vecchio broker del banco di Youssouf.**
   - Dal passo 4.2 lascia quel broker: i tre sensori BLU passano con lui sul nostro.
   - **Youssouf conferma prima** che al banco non gli serve più sul vecchio broker.
3. **Come il committente arriva alla pagina locale:** gli Shelly sono dietro il router dedicato di Youssouf, quindi la pagina locale si apre solo da quella rete. **Da chiarire con Youssouf prima del passo 3:**
   - il committente è sulla stessa rete (sul posto, o con un collegamento che Youssouf gli dà): la password resta solo sul suo schermo;
   - oppure la scrive Youssouf, dettata o vista: la password passa da un'altra persona, come l'11 novembre per la Plug. È comunque **provvisoria**: la cambiano i passi 3.4 e 4.4.
   - Se la pagina locale è protetta da una password (come quella della Plug, verifica 3 della tappa A), la conosce Youssouf.
4. **La rete:** la Plug, dietro lo stesso router, arriva già a `mqtt.dh-lab.eu:8883`. **Da verificare** che i due Shelly siano sulla stessa rete della Plug (stesso Wi-Fi del router dedicato).
5. **Nessuna password in chat:** l'uscita dei passi 3.1 e 4.1 non si incolla mai, né alla memoria storica né altrove.
6. **Cosa non è provato su questi due modelli** (scritto «da verificare» nei passi):
   - `MQTT.SetConfig` arrivato via MQTT (R2): provato solo sulla Plug M Gen3;
   - il ricollegamento da solo con la password nuova dopo la ricarica del broker (R3): visto solo sulla Plug;
   - per l'EM Mini, che il riavvio non tolga corrente alla linea misurata.


## 1. Gli utenti dei due Shelly sul broker

### 1.1 Versione attuale del segreto dei dispositivi (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions list langbrain-shelly-lab-01-devices --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** in cima la versione `3`, `enabled` (quella del cambio della password della Plug, 16 novembre).
- **Se in cima non c'è la 3:** fermati e avvisa la memoria storica.

### 1.2 Gli utenti dei due Shelly (scrive su Secret Manager)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh add-device lab-01 shellyemminig4-acebe6e42d6c
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh add-device lab-01 shelly1g4-98a3166d8d80
```

- **Atteso:** due volte «nuova versione di langbrain-shelly-lab-01-devices scritta». Nessuna password a video.
- Lo script suggerisce «Ora, sulla VM: … sync»: è il passo 2.
- **«add-device non fatto: niente è cambiato»:** il dispositivo c'è già. Fermati e incolla il testo.
- **Controllo:** di nuovo il comando 1.1. In cima la versione `5`.

## 2. Il broker conosce i due utenti (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh sync'
```

- **Atteso:** «lab-01: connector e 3 dispositivi», «changed», «utenti e permessi ricaricati».
- **La Plug resta collegata:** la sua password non cambia, quindi la ricarica non la stacca (oggi la ricarica ha staccato solo l'utente cambiato). Controllo:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker logs --since 3m domhouse-broker 2>&1 | grep -E "Reloading|lab-01\."'
```

- **Atteso:** «Reloading config.» e **nessuna** riga «disconnected» della Plug (`lab-01.shellyplugmg3-9070695cb0d0`).
- **Se la Plug risulta scollegata:** è un esito da registrare; di solito si ricollega da sola in pochi secondi (stessa password).

## 3. EM Mini Gen4 (`shellyemminig4-acebe6e42d6c`), il misuratore

### 3.1 La password provvisoria, sul solo schermo del committente

**Non incollare l'uscita di questo comando in chat, né alla memoria storica né altrove.** Dopo l'uso chiudi la finestra del terminale.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions access latest --secret=langbrain-shelly-lab-01-devices --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com | .venv/Scripts/python.exe -c "import json,sys; print(json.load(sys.stdin)['shellyemminig4-acebe6e42d6c'])"
```

- Mostra **solo** la password di questo Shelly.
- È una lettura del valore di un segreto, come la riserva della tappa A: si fa per scelta del committente (risposta 1138).
- La password è **provvisoria**: al passo 3.4 la VM la cambia, e quella letta qui non vale più.

### 3.2 La configurazione MQTT dalla pagina locale dello Shelly

**Chi:** il committente scrive, Youssouf guida (vedi «Prima di cominciare», punto 3).

| Impostazione (nome di `MQTT.SetConfig`) | Valore |
|---|---|
| `enable` | acceso |
| `server` | `mqtt.dh-lab.eu:8883` |
| `ssl_ca` | `ca.pem`: TLS **con** verifica, con le CA predefinite. Come sulla Plug; mai «senza verifica» |
| `client_id` | `lab-01.shellyemminig4-acebe6e42d6c` |
| `user` | `lab-01.shellyemminig4-acebe6e42d6c` |
| `pass` | la password del passo 3.1 |
| `topic_prefix` | `lab-01/shellyemminig4-acebe6e42d6c` (prefisso dei topic, come la Plug: `lab-01/<id>`) |
| `rpc_ntf` | acceso |
| `status_ntf` | spento |
| `enable_rpc` | acceso |
| `enable_control` | **spento** |

- Poi **Salva** e **riavvia** lo Shelly: la configurazione MQTT vale solo dopo il riavvio.
- Non ha relè: il riavvio non toglie corrente alla linea che misura (da verificare: Y guarda la spia della ciabatta).
- I nomi dei campi nella pagina web non sono quelli della tabella: Youssouf li conosce, sono gli stessi che ha usato per la Plug l'11 novembre.

### 3.3 Verifica 1: lo Shelly si è collegato? (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker logs --since 30m domhouse-broker 2>&1 | grep -E "lab-01\.shellyemminig4-acebe6e42d6c"'
```

- **Atteso:** «New client connected from … as lab-01.shellyemminig4-acebe6e42d6c (p4, c…, k…)». Vuol dire che **il certificato e la password funzionano**.
- **«… not authorised»** o **«disconnected: not authorised»**: la password non è quella giusta. Ripeti 3.1 e 3.2.
- **Nessuna riga:** lo Shelly non è arrivato al broker. Youssouf controlla nella pagina locale lo stato MQTT (collegato o no, e l'errore). Riprova dopo un minuto.

### 3.4 Cambio della password a distanza (R0–R4 della tappa A)

**Regola fino alla fine di 3.4:** nessun altro `sync` e nessun altro `add-device` o `rotate-device` per `lab-01`.

**R0. Versione attuale (sola lettura).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions list langbrain-shelly-lab-01-devices --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** in cima la versione `5`. Se no, fermati.

**R1. Password nuova nel segreto (scrive su Secret Manager).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh rotate-device lab-01 shellyemminig4-acebe6e42d6c
```

- **Atteso:** «nuova versione di langbrain-shelly-lab-01-devices scritta». **Non** fare ora il `sync` suggerito: è R3.

**R2. La VM manda la password nuova allo Shelly (scrive nello Shelly).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); S=https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets; PW=$(curl -sf -H "Authorization: Bearer $T" $S/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); MSG=$(curl -sf -H "Authorization: Bearer $T" $S/langbrain-shelly-lab-01-devices/versions/latest:access | python3 -c "import base64,json,sys; d=json.loads(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"])); print(json.dumps(dict(id=901,src=\"lab-01/shellyemminig4-acebe6e42d6c/connector\",method=\"MQTT.SetConfig\",params=dict(config={\"pass\":d[\"shellyemminig4-acebe6e42d6c\"]}))))"); [ -n "$PW" ] && [ -n "$MSG" ] || { echo "segreti non letti da Secret Manager"; exit 1; }; export PW MSG; sudo --preserve-env=PW,MSG docker exec -e PW -e MSG domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-rotazione-ascolto -u lab-01.connector -P \"\$PW\" -t lab-01/shellyemminig4-acebe6e42d6c/connector/rpc -C 5 -W 10 | grep -m1 id.:901 & L=\$!; sleep 2; printf %s \"\$MSG\" | mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-rotazione -u lab-01.connector -P \"\$PW\" -t lab-01/shellyemminig4-acebe6e42d6c/rpc -s; wait \$L"; echo "uscita $?"; unset PW MSG T'
```

- **Atteso:** una riga con `"id":901` e `"result":{"restart_required":true}`, poi «uscita 0».
- **Da verificare:** che il EM Mini Gen4 accetti `MQTT.SetConfig` arrivato via MQTT. Oggi è provato solo sulla Plug M Gen3.
- **Subito dopo «uscita 0», R3.**
- **«uscita 1» senza righe:** lo Shelly non ha risposto in 10 secondi. Non fare R3; ripeti 3.3.
- **Una riga con `"error"`:** lo Shelly ha rifiutato. Non fare R3; incolla il testo.

**R3. Il broker accetta la password nuova (scrive sulla VM).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh sync'
```

- **Atteso:** «lab-01: connector e 3 dispositivi», «changed», «utenti e permessi ricaricati».
- **Atteso, come sulla Plug il 16 novembre:** la ricarica stacca lo Shelly la cui password è cambiata, e lo Shelly si ricollega da solo in pochi secondi con la password nuova. **Da verificare** sul EM Mini Gen4: lo mostra R4.

**R4. Riavvio e controllo (scrive nello Shelly).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); S=https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets; PW=$(curl -sf -H "Authorization: Bearer $T" $S/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); MSG=$(python3 -c "import json; print(json.dumps(dict(id=902,src=\"lab-01/shellyemminig4-acebe6e42d6c/connector\",method=\"Shelly.Reboot\")))"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW MSG; sudo --preserve-env=PW,MSG docker exec -e PW -e MSG domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-riavvio-ascolto -u lab-01.connector -P \"\$PW\" -t lab-01/shellyemminig4-acebe6e42d6c/connector/rpc -C 5 -W 10 | grep -m1 id.:902 & L=\$!; sleep 2; printf %s \"\$MSG\" | mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-riavvio -u lab-01.connector -P \"\$PW\" -t lab-01/shellyemminig4-acebe6e42d6c/rpc -s; wait \$L"; echo "uscita $?"; unset PW MSG T; echo "attesa di 60 secondi per il riavvio"; sleep 60; sudo docker logs --since 2m domhouse-broker 2>&1 | grep "shellyemminig4-acebe6e42d6c"'
```

- **Atteso:**
  1. la risposta `{"id":902,…}`, poi «uscita 0»;
  2. dopo 60 secondi lo Shelly che si scollega e poi «New client connected … as lab-01.shellyemminig4-acebe6e42d6c».
- **Riuscito:** lo Shelly è collegato con la password nuova; quella letta al passo 3.1 non vale più.
- **«not authorised»** con il nome dello Shelly: non ha la password nuova. Fermati e incolla il testo. Riserva: rifare 3.1 e 3.2 con la password nuova (si rilegge con lo stesso comando di 3.1), poi di nuovo R1–R4.
- Non ha relè: il riavvio non toglie corrente alla linea che misura (da verificare: Y guarda la spia della ciabatta).

## 4. Shelly 1 Gen4 (`shelly1g4-98a3166d8d80`), il relè (ponte dei tre sensori BLU)

### 4.1 La password provvisoria, sul solo schermo del committente

**Non incollare l'uscita di questo comando in chat, né alla memoria storica né altrove.** Dopo l'uso chiudi la finestra del terminale.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions access latest --secret=langbrain-shelly-lab-01-devices --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com | .venv/Scripts/python.exe -c "import json,sys; print(json.load(sys.stdin)['shelly1g4-98a3166d8d80'])"
```

- Mostra **solo** la password di questo Shelly.
- È una lettura del valore di un segreto, come la riserva della tappa A: si fa per scelta del committente (risposta 1138).
- La password è **provvisoria**: al passo 4.4 la VM la cambia, e quella letta qui non vale più.

### 4.2 La configurazione MQTT dalla pagina locale dello Shelly

**Chi:** il committente scrive, Youssouf guida (vedi «Prima di cominciare», punto 3).

| Impostazione (nome di `MQTT.SetConfig`) | Valore |
|---|---|
| `enable` | acceso |
| `server` | `mqtt.dh-lab.eu:8883` |
| `ssl_ca` | `ca.pem`: TLS **con** verifica, con le CA predefinite. Come sulla Plug; mai «senza verifica» |
| `client_id` | `lab-01.shelly1g4-98a3166d8d80` |
| `user` | `lab-01.shelly1g4-98a3166d8d80` |
| `pass` | la password del passo 4.1 |
| `topic_prefix` | `lab-01/shelly1g4-98a3166d8d80` (prefisso dei topic, come la Plug: `lab-01/<id>`) |
| `rpc_ntf` | acceso |
| `status_ntf` | spento |
| `enable_rpc` | acceso |
| `enable_control` | **spento** |

- Poi **Salva** e **riavvia** lo Shelly: la configurazione MQTT vale solo dopo il riavvio.
- Il riavvio può far scattare il relè: a valle c'è solo la ciabatta con la spia, si può spegnere liberamente.
- I nomi dei campi nella pagina web non sono quelli della tabella: Youssouf li conosce, sono gli stessi che ha usato per la Plug l'11 novembre.

### 4.3 Verifica 1: lo Shelly si è collegato? (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker logs --since 30m domhouse-broker 2>&1 | grep -E "lab-01\.shelly1g4-98a3166d8d80"'
```

- **Atteso:** «New client connected from … as lab-01.shelly1g4-98a3166d8d80 (p4, c…, k…)». Vuol dire che **il certificato e la password funzionano**.
- **«… not authorised»** o **«disconnected: not authorised»**: la password non è quella giusta. Ripeti 4.1 e 4.2.
- **Nessuna riga:** lo Shelly non è arrivato al broker. Youssouf controlla nella pagina locale lo stato MQTT (collegato o no, e l'errore). Riprova dopo un minuto.

### 4.4 Cambio della password a distanza (R0–R4 della tappa A)

**Regola fino alla fine di 4.4:** nessun altro `sync` e nessun altro `add-device` o `rotate-device` per `lab-01`.

**R0. Versione attuale (sola lettura).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions list langbrain-shelly-lab-01-devices --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** in cima la versione `6`. Se no, fermati.

**R1. Password nuova nel segreto (scrive su Secret Manager).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh rotate-device lab-01 shelly1g4-98a3166d8d80
```

- **Atteso:** «nuova versione di langbrain-shelly-lab-01-devices scritta». **Non** fare ora il `sync` suggerito: è R3.

**R2. La VM manda la password nuova allo Shelly (scrive nello Shelly).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); S=https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets; PW=$(curl -sf -H "Authorization: Bearer $T" $S/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); MSG=$(curl -sf -H "Authorization: Bearer $T" $S/langbrain-shelly-lab-01-devices/versions/latest:access | python3 -c "import base64,json,sys; d=json.loads(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"])); print(json.dumps(dict(id=901,src=\"lab-01/shelly1g4-98a3166d8d80/connector\",method=\"MQTT.SetConfig\",params=dict(config={\"pass\":d[\"shelly1g4-98a3166d8d80\"]}))))"); [ -n "$PW" ] && [ -n "$MSG" ] || { echo "segreti non letti da Secret Manager"; exit 1; }; export PW MSG; sudo --preserve-env=PW,MSG docker exec -e PW -e MSG domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-rotazione-ascolto -u lab-01.connector -P \"\$PW\" -t lab-01/shelly1g4-98a3166d8d80/connector/rpc -C 5 -W 10 | grep -m1 id.:901 & L=\$!; sleep 2; printf %s \"\$MSG\" | mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-rotazione -u lab-01.connector -P \"\$PW\" -t lab-01/shelly1g4-98a3166d8d80/rpc -s; wait \$L"; echo "uscita $?"; unset PW MSG T'
```

- **Atteso:** una riga con `"id":901` e `"result":{"restart_required":true}`, poi «uscita 0».
- **Da verificare:** che il Shelly 1 Gen4 accetti `MQTT.SetConfig` arrivato via MQTT. Oggi è provato solo sulla Plug M Gen3.
- **Subito dopo «uscita 0», R3.**
- **«uscita 1» senza righe:** lo Shelly non ha risposto in 10 secondi. Non fare R3; ripeti 4.3.
- **Una riga con `"error"`:** lo Shelly ha rifiutato. Non fare R3; incolla il testo.

**R3. Il broker accetta la password nuova (scrive sulla VM).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh sync'
```

- **Atteso:** «lab-01: connector e 3 dispositivi», «changed», «utenti e permessi ricaricati».
- **Atteso, come sulla Plug il 16 novembre:** la ricarica stacca lo Shelly la cui password è cambiata, e lo Shelly si ricollega da solo in pochi secondi con la password nuova. **Da verificare** sul Shelly 1 Gen4: lo mostra R4.

**R4. Riavvio e controllo (scrive nello Shelly).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); S=https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets; PW=$(curl -sf -H "Authorization: Bearer $T" $S/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); MSG=$(python3 -c "import json; print(json.dumps(dict(id=902,src=\"lab-01/shelly1g4-98a3166d8d80/connector\",method=\"Shelly.Reboot\")))"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW MSG; sudo --preserve-env=PW,MSG docker exec -e PW -e MSG domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-riavvio-ascolto -u lab-01.connector -P \"\$PW\" -t lab-01/shelly1g4-98a3166d8d80/connector/rpc -C 5 -W 10 | grep -m1 id.:902 & L=\$!; sleep 2; printf %s \"\$MSG\" | mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-riavvio -u lab-01.connector -P \"\$PW\" -t lab-01/shelly1g4-98a3166d8d80/rpc -s; wait \$L"; echo "uscita $?"; unset PW MSG T; echo "attesa di 60 secondi per il riavvio"; sleep 60; sudo docker logs --since 2m domhouse-broker 2>&1 | grep "shelly1g4-98a3166d8d80"'
```

- **Atteso:**
  1. la risposta `{"id":902,…}`, poi «uscita 0»;
  2. dopo 60 secondi lo Shelly che si scollega e poi «New client connected … as lab-01.shelly1g4-98a3166d8d80».
- **Riuscito:** lo Shelly è collegato con la password nuova; quella letta al passo 4.1 non vale più.
- **«not authorised»** con il nome dello Shelly: non ha la password nuova. Fermati e incolla il testo. Riserva: rifare 4.1 e 4.2 con la password nuova (si rilegge con lo stesso comando di 4.1), poi di nuovo R1–R4.
- Il riavvio può far scattare il relè: a valle c'è solo la ciabatta con la spia, si può spegnere liberamente.

## 5. Dopo

- **Alla memoria storica:** l'uscita di ogni passo, tranne quella di 3.1 e 4.1, mai.
- **Il catalogo nel motore `lab-01` c'è già** (aggiornamento della memoria storica, 17 novembre): caricato con C2 di `docs/procedura-difetti-vm.md` (sei dispositivi) e motore aggiornato a `engine:d368f0d`. Quindi, appena ciascuno Shelly si collega, **il motore lo vede subito**: nell'app di staging EM Mini, Shelly 1 («caldaia») e i tre sensori BLU passano da «non in linea» a «in linea». Controllo dopo il passo 4: pagina dei dispositivi di `lab-01`, sei dispositivi in linea, temperatura e batteria dei sensori.
- **Lo Shelly 1 è la «caldaia» del motore:** appena collegato, il termostato del motore può comandare il relè da solo secondo la temperatura del sensore H&T e la modalità dell'appartamento. A valle c'è solo la ciabatta con la spia: è atteso.
- **Dopo questa procedura, non prima** (risposte 1153 e 1154 del 17 novembre): Youssouf applica le tre impostazioni approvate (`initial_state` «restore_last», Matter spento, chiamate via Bluetooth spente) e poi prova il firmware 2.x, un dispositivo alla volta.
- **Se il motore `lab-01` è acceso** durante R2 e R4: due righe «mqtt rpc answer dropped» nel suo log sono attese, come nella tappa A.
