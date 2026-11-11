# Tappa A: le tre verifiche di laboratorio sulla Plug di Y

| Stato | Comandi | Preparata | Chi lancia |
|---|---|---|---|
| **Pronta** | o1, 11 novembre 2026 (motore-vm.md, G2, passo B5) | memoria storica | il committente, dopo che Y ha configurato e riavviato la presa |

- **Dispositivo:** `lab-01.shellyplugmg3-9070695cb0d0`.
- **Tutti i comandi si lanciano in Git Bash.** Ognuno apre la VM attraverso il tunnel di Google.
- **Nessuna password compare a video.** La password del connector la legge la VM da sola.
- **Incolla alla memoria storica l'uscita di ogni verifica:** l'esito va nel registro.

## 1. La presa si è collegata? (sola lettura)

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker logs --since 30m domhouse-broker 2>&1 | grep "New client connected" | grep "lab-01.shellyplugmg3-9070695cb0d0"'
```

- **Atteso:** una riga «New client connected from … as lab-01.shellyplugmg3-9070695cb0d0 (p4, c?, k…)». Vuol dire che **il certificato funziona**.
- **Se non esce niente:** la presa non si è collegata negli ultimi 30 minuti. Riprova con `--since 2h` al posto di `--since 30m`.

## 2. Lo stato «online» è conservato? (sola lettura)

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); PW=$(curl -sf -H "Authorization: Bearer $T" https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW; sudo --preserve-env=PW docker exec -e PW domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-verifica -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/online -C 1 -W 5 -v"; echo "uscita $?"; unset PW T'
```

- **«lab-01/shellyplugmg3-9070695cb0d0/online true» e poi «uscita 0»:** lo stato è conservato.
- **Dopo 5 secondi «uscita 27», senza righe:** lo stato non è conservato. Anche questo è un esito da registrare.
- **«uscita 5» o «not authorised»:** c'è un problema di utente o di permessi. Fermati e incolla il testo.

## 3. La presa ignora i comandi «di controllo»? (manda un messaggio di prova)

**Prima di lanciarla:** se il controllo fosse attivo, la presa **cambierebbe stato** (da accesa a spenta o il contrario). Y non deve avere attaccato niente che non possa spegnersi.

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); PW=$(curl -sf -H "Authorization: Bearer $T" https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW; sudo --preserve-env=PW docker exec -e PW domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-ascolto -u lab-01.connector -P \"\$PW\" -t \"lab-01/shellyplugmg3-9070695cb0d0/#\" -v -W 10 & sleep 2; mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-prova -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/command/switch:0 -m toggle; mosquitto_pub -h 172.30.83.2 -p 1883 -i lab-01.connector-prova -u lab-01.connector -P \"\$PW\" -t lab-01/shellyplugmg3-9070695cb0d0/command -m status_update; sleep 9"; unset PW T'
```

- **Atteso:**
  - compaiono solo i due comandi mandati da noi, «…/command/switch:0 toggle» e «…/command status_update», e forse «online true»;
  - nessuna risposta della presa;
  - la presa non cambia stato (Y lo vede dalla luce).
- **Se invece compaiono messaggi su «…/status/…»**, oppure una NotifyStatus con «output» cambiato, oppure la presa cambia stato: la presa non rispetta l'impostazione. È un esito da registrare. Se la presa ha cambiato stato, Y la rimette com'era.
- **Da verificare:** i nomi dei topic di controllo vengono dalla documentazione Shelly Gen2+. Se Y ne conosce altri per la Plug M Gen3, o1 aggiunge un comando.
