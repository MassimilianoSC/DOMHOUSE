# Tappa A: le verifiche di laboratorio sulla Plug di Y e il cambio della sua password

| Stato | Comandi | Preparata | Chi lancia |
|---|---|---|---|
| Verifiche 1 e 2 **superate** (12 novembre 2026). Restano la verifica 3 e il cambio della password | o1, 11 e 13 novembre 2026 (motore-vm.md, G2, passo B5) | memoria storica | il committente, con Y vicino alla presa |

- **Dispositivo:** `lab-01.shellyplugmg3-9070695cb0d0` (utente del broker); id nativo `shellyplugmg3-9070695cb0d0`.
- **Tutti i comandi si lanciano in Git Bash.** Ognuno apre la VM attraverso il tunnel di Google.
- **Nessuna password compare a video**, tranne nella soluzione di riserva in fondo, che si usa solo se il committente la sceglie.
  - La VM legge da sola le password che servono.
  - Mentre il comando gira, per 5–15 secondi, la password del connector sta nella riga di comando di `mosquitto_sub`/`mosquitto_pub` dentro il container. La può leggere con `ps` chiunque sia collegato alla VM in quel momento; oggi ti colleghi solo tu.
  - In R2, per qualche secondo, la VM tiene anche la **password nuova della presa**, nel messaggio passato al container.
- **Incolla alla memoria storica l'uscita di ogni passo:** l'esito va nel registro. **Unica eccezione: l'uscita della soluzione di riserva non va mai incollata.**
- **Ordine:**
  1. verifica 3, poi il cambio della password (sezione 4);
  2. tutto **prima** di installare il motore `lab-01` (tappa B). Con il motore acceso, l'ascolto di R2 e R4 potrebbe prendere una risposta del connector: per questo i due comandi tengono solo la risposta con il loro numero (901, 902).
  3. La verifica 3 si può fare anche con il motore acceso: il connector non legge i topic di controllo.

## 1. La presa si è collegata? (sola lettura) — superata il 12 novembre

Si ripete solo se serve, per esempio dopo il cambio della password.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker logs --since 30m domhouse-broker 2>&1 | grep "New client connected" | grep "lab-01.shellyplugmg3-9070695cb0d0"'
```

- **Atteso:** una riga «New client connected from … as lab-01.shellyplugmg3-9070695cb0d0 (p4, c?, k…)». Vuol dire che **il certificato funziona**.
- **Se non esce niente:** la presa non si è collegata negli ultimi 30 minuti. Riprova con `--since 2h` al posto di `--since 30m`.

## 2. Lo stato «online» è conservato? (sola lettura) — superata il 12 novembre

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); PW=$(curl -sf -H "Authorization: Bearer $T" https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW; sudo --preserve-env=PW docker exec -e PW domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-verifica -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/online -C 1 -W 5 -v"; echo "uscita $?"; unset PW T'
```

- **«lab-01/shellyplugmg3-9070695cb0d0/online true» e poi «uscita 0»:** lo stato è conservato.
- **Dopo 5 secondi «uscita 27», senza righe:** lo stato non è conservato. Anche questo è un esito da registrare.
- **«uscita 5» o «not authorised»:** c'è un problema di utente o di permessi. Fermati e incolla il testo.

## 3. La presa ignora i comandi «di controllo»? (manda un messaggio di prova)

**Che cosa fa Y prima:** stacca dalla presa ciò che non può spegnersi. Se il controllo fosse attivo, la presa **cambierebbe stato** (da accesa a spenta o il contrario).

**Che cosa fa Y durante:** guarda la luce della presa per i 10 secondi del comando e dice se è cambiata.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); PW=$(curl -sf -H "Authorization: Bearer $T" https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW; sudo --preserve-env=PW docker exec -e PW domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-ascolto -u lab-01.connector -P \"\$PW\" -t \"lab-01/shellyplugmg3-9070695cb0d0/#\" -v -W 10 & sleep 2; mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-prova -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/command/switch:0 -m toggle; mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-prova -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/command -m status_update; sleep 9"; unset PW T'
```

| Che cosa compare | Che cosa vuol dire |
|---|---|
| i due comandi mandati da noi: «…/command/switch:0 toggle» e «…/command status_update» | normale: sono i nostri |
| «…/online true» | normale: è lo stato conservato (verifica 2) |
| «…/events/rpc» con una `NotifyStatus` che contiene solo `aenergy` o `apower` | normale: la presa manda i consumi circa una volta al minuto |
| **«…/status/…»**, oppure una `NotifyStatus` con **`output`** cambiato | la presa **non** rispetta `enable_control: false`: esito da registrare |
| Y vede la luce cambiare | come sopra; Y rimette la presa com'era |

- **Atteso:** solo righe delle prime tre file della tabella, e la presa che non cambia stato.
- **Da verificare:** i nomi dei topic di controllo vengono dalla documentazione Shelly Gen2+. Se Y ne conosce altri per la Plug M Gen3, o1 aggiunge un comando.

## 4. Cambio della password della presa (rotate-device)

**Perché:** la password di oggi è passata nella chat aziendale (risposta 1080). Quella nuova la scrive **la VM** nella presa con un comando MQTT (`MQTT.SetConfig`), mentre la presa è collegata. Nessuna persona la vede, nessuno la copia.

**Che cosa fa Y:** sta vicino alla presa. Al passo R4 la vede riavviarsi e dice se torna accesa entro 1–2 minuti. Non deve scrivere niente.

**Regola fino alla fine del passo R4:** nessun `broker-vm.sh sync` e nessun `broker-secrets.sh add-device` per `lab-01`, oltre a quelli scritti qui. Una `sync` prima di R2 lascerebbe fuori la presa.

| Passo | Dove | Scrive? | Che cosa fa |
|---|---|---|---|
| R0 | PC | no | controlla la versione attuale del segreto dei dispositivi |
| R1 | PC | Secret Manager | password nuova nel segreto (versione nuova) |
| R2 | VM | la presa | la VM manda la password nuova alla presa |
| R3 | VM | broker | il broker accetta la password nuova |
| R4 | VM | la presa | la VM fa riavviare la presa, che si ricollega con la password nuova |

### R0. Versione attuale (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions list langbrain-shelly-lab-01-devices --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** in cima la versione `2`, `enabled`. È quella con la Plug (registro, 11 novembre).
- **Se la versione in cima non è la 2:** fermati e avvisa la memoria storica.

### R1. Password nuova nel segreto (scrive su Secret Manager)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh rotate-device lab-01 shellyplugmg3-9070695cb0d0
```

- **Atteso:** «nuova versione di langbrain-shelly-lab-01-devices scritta», nessuna password a video.
- Lo script poi suggerisce «Ora, sulla VM: … sync»: **non** farlo adesso. Si fa al passo R3.
- **Controllo:** R0 di nuovo; in cima la versione `3`, `enabled`.

### R2. La VM manda la password nuova alla presa (scrive nella presa)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); S=https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets; PW=$(curl -sf -H "Authorization: Bearer $T" $S/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); MSG=$(curl -sf -H "Authorization: Bearer $T" $S/langbrain-shelly-lab-01-devices/versions/latest:access | python3 -c "import base64,json,sys; d=json.loads(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"])); print(json.dumps(dict(id=901,src=\"lab-01/shellyplugmg3-9070695cb0d0/connector\",method=\"MQTT.SetConfig\",params=dict(config={\"pass\":d[\"shellyplugmg3-9070695cb0d0\"]}))))"); [ -n "$PW" ] && [ -n "$MSG" ] || { echo "segreti non letti da Secret Manager"; exit 1; }; export PW MSG; sudo --preserve-env=PW,MSG docker exec -e PW -e MSG domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-rotazione-ascolto -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/connector/rpc -C 5 -W 10 | grep -m1 id.:901 & L=\$!; sleep 2; printf %s \"\$MSG\" | mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-rotazione -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/rpc -s; wait \$L"; echo "uscita $?"; unset PW MSG T'
```

- **Come passa la password:** la VM la legge dal segreto e la mette nel messaggio, che `mosquitto_pub` legge da stdin (`-s`), non dalla riga di comando. Il messaggio va alla presa attraverso il broker, poi in TLS. La risposta della presa non contiene la password.
- **Atteso:** una riga `{"id":901,"src":"shellyplugmg3-9070695cb0d0","dst":"lab-01/shellyplugmg3-9070695cb0d0/connector","result":{"restart_required":true}}`, poi «uscita 0».
- La presa tiene la password nuova, ma la usa solo dal prossimo riavvio. Fino ad allora resta collegata con quella vecchia.
- **Subito dopo «uscita 0», senza aspettare, R3 e poi R4.** Se la presa si ricollegasse da sola (per esempio per il Wi-Fi), userebbe già la password nuova, che il broker conosce solo dopo R3.
- **«uscita 1» senza righe:** la presa non ha risposto in 10 secondi, probabilmente è scollegata. Non fare R3. Controlla con la verifica 1 se è collegata, poi ripeti R2.
- Il comando tiene solo la risposta con `"id":901`: un'eventuale risposta a una chiamata del connector, se il motore fosse acceso, non conta.
- **Una riga con `"error"`:** la presa ha rifiutato. Non fare R3; incolla il testo alla memoria storica.
- **Da verificare la prima volta:** che la Plug M Gen3 accetti `MQTT.SetConfig` arrivato proprio via MQTT. La documentazione Shelly Gen2+ lo prevede, ma noi non l'abbiamo ancora provato.

### R3. Il broker accetta la password nuova (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh sync'
```

- **Atteso:** «lab-01: connector e 1 dispositivi», «changed», «utenti e permessi ricaricati».
- La ricarica non fa cadere chi è collegato: la presa resta collegata.
- **Subito dopo, R4.** Da adesso il broker conosce solo la password nuova: se la presa si ricollegasse prima del riavvio, con quella vecchia, sarebbe rifiutata.

### R4. Riavvio della presa e controllo (scrive nella presa)

**Y guarda la presa:** si spegne la luce per qualche secondo e torna.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); PW=$(curl -sf -H "Authorization: Bearer $T" https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); MSG=$(python3 -c "import json; print(json.dumps(dict(id=902,src=\"lab-01/shellyplugmg3-9070695cb0d0/connector\",method=\"Shelly.Reboot\")))"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW MSG; sudo --preserve-env=PW,MSG docker exec -e PW -e MSG domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-riavvio-ascolto -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/connector/rpc -C 5 -W 10 | grep -m1 id.:902 & L=\$!; sleep 2; printf %s \"\$MSG\" | mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-riavvio -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/rpc -s; wait \$L"; echo "uscita $?"; unset PW MSG T; echo "attesa di 60 secondi per il riavvio della presa"; sleep 60; sudo docker logs --since 2m domhouse-broker 2>&1 | grep "shellyplugmg3-9070695cb0d0"'
```

- **Atteso:**
  1. la risposta `{"id":902,…,"result":null}` o simile, poi «uscita 0»;
  2. dopo 60 secondi, nelle righe del broker, la presa che si scollega e poi «New client connected from … as lab-01.shellyplugmg3-9070695cb0d0 (p4, c1, k…)».
- **Riuscito:** la presa si è ricollegata **con la password nuova**, perché il broker ormai conosce solo quella. La password passata in chat non vale più.
- **«disconnected: not authorised»** con il nome della presa: la presa non ha la password nuova. Fermati e incolla il testo alla memoria storica. La soluzione di riserva è sotto.
- **«uscita 1» senza risposta:** il riavvio non è arrivato alla presa. Di solito vuol dire che la presa si è già ricollegata con la password vecchia ed è stata rifiutata, quindi non riceve più niente.
  - Y stacca la presa dalla corrente e la riattacca dopo 10 secondi: è un riavvio, e al riavvio la presa usa la password nuova.
  - Poi la verifica 1.
- **Nessuna riga «New client connected» dopo 60 secondi:** ripeti solo la verifica 1 dopo un minuto. Se ancora niente, Y guarda se la presa è accesa; se è accesa, la stacca e la riattacca come sopra.

### Soluzione di riserva (solo se R2 o R4 non riescono, e solo se il committente la sceglie)

Come l'11 novembre: il committente legge sul suo schermo la password della sola presa e Y la scrive nella pagina web della presa (MQTT → Password). Poi riavvio della presa e verifica 1.

**Non incollare l'uscita di questo comando in chat, né alla memoria storica né altrove.** Dopo l'uso chiudi la finestra del terminale.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions access latest --secret=langbrain-shelly-lab-01-devices --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com | .venv/Scripts/python.exe -c "import json,sys; print(json.load(sys.stdin)['shellyplugmg3-9070695cb0d0'])"
```

- Mostra **solo** la password della presa, non il resto del segreto.
- Se R3 non è ancora stato fatto, va fatto prima del riavvio della presa.
- Alla memoria storica scrivi solo «riserva usata, presa ricollegata» (o l'esito della verifica 1).
- È una lettura del valore di un segreto, fuori dalla regola D-116, che riguarda solo l'esistenza dei segreti: si fa solo per scelta esplicita del committente.
- Dopo una riserva riuscita la password è passata sotto gli occhi di qualcuno: appena possibile si rifanno R1–R4. Se va scritto come regola lo decide il committente.
