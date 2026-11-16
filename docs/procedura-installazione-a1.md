# Installazione di A1: il ricevitore di ordini dello strumento A (staging)

| Stato | Preparata | Codice | Chi lancia | Comandi |
|---|---|---|---|---|
| **Pronta, da rileggere.** Nessun passo provato sul vero | o1, 16 novembre 2026 | `ee59625` (codice di A1 dopo quattro letture di sicurezza) | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | 15 blocchi (I0–I14) |

**Cosa si installa** (progetto `docs/progetto-strumento-a-base.md` §1, §3, §4, §6):

| Dove | Che cosa |
|---|---|
| Google Cloud | code `domhouse-staging-ordini`, `-risultati`, `-scarti`; tre sottoscrizioni; l'account di push `domhouse-push-staging@`; i permessi su ogni risorsa; due allarmi (`scripts/agent-gcp.sh`) |
| Firestore (staging) | la scadenza a 90 giorni delle operazioni (`agent_ops`) |
| Server dello staging | cinque variabili `AGENT_*`: senza, l'agente è spento (503) |
| VM | l'utente `domhouse-agent`, il lettore e l'esecutore come servizi systemd (`scripts/agent-vm.sh`) |
| Sito dello staging | il pulsante «Prova l'agente» di o2, nella pagina della piattaforma |

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.**
2. **Se un'uscita non torna, fermati.** In particolare: se un controllo di `agent-gcp.sh` si ferma, non si allarga nessun elenco a mano. Si decide con il committente.
3. Ogni passo che scrive ha accanto il ritorno indietro. Il ritorno completo è in I14.
4. Solo lo **staging**: sulla VM condivisa la produzione non manda ordini (§5.4).

**Quando:** dopo il passo 2 del piano (correzioni sulla VM, `docs/procedura-difetti-vm.md`). Il giorno lo decide il committente.

## I0. Prerequisiti (sola lettura)

**I0.1 Sul PC: il codice è quello delle letture di sicurezza, e l'API Cloud Asset.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git log --oneline -1 ee59625 && git diff --quiet ee59625 HEAD -- scripts/agent scripts/agent-vm.sh scripts/agent-gcp.sh bff/agent.py bff/routes/agent.py && echo "agente uguale a ee59625"; gcloud services list --enabled --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --filter="config.name=cloudasset.googleapis.com" --format="value(config.name)"
```

- **Atteso:**
  1. la riga del commit `ee59625` e «agente uguale a ee59625». Se manca la seconda riga, fermati: qualcuno ha cambiato i file dell'agente dopo le letture;
  2. `cloudasset.googleapis.com` se l'API è già attiva; **nessuna riga** se manca: allora c'è I1.

**I0.2 Sulla VM: E-31 attiva** (i container non raggiungono i metadati: rilievo R8 della revisione).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo nft list table inet domhouse_metadata > /dev/null && echo "tabella domhouse_metadata presente"; for c in engine-dev engine-lab-01; do echo "$c:"; sudo docker exec "$c" python -c "import urllib.request as u; print(u.urlopen(u.Request(\"http://169.254.169.254/computeMetadata/v1/instance/zone\", headers={\"Metadata-Flavor\": \"Google\"}), timeout=3).read().decode())" 2>&1 | tail -1; done; sudo journalctl -t domhouse-check --since "-2h" --no-pager | grep -E " metadata (blocked|OPEN)" | tail -1'
```

| Riga | Atteso |
|---|---|
| tabella | «tabella domhouse_metadata presente» |
| `engine-dev:` ed `engine-lab-01:` | un errore di tempo scaduto (`timed out`): i container non raggiungono i metadati |
| controllo orario | «metadata blocked» |

- **«metadata OPEN», oppure la zona `projects/444239063209/zones/…` letta da un container:** fermati. E-31 non è attiva, e l'agente non si installa (§3.2).

## I1. API Cloud Asset (scrive su Google Cloud; solo se I0.1 non l'ha trovata)

Serve ai controlli di `agent-gcp.sh` (R3): chi può pubblicare sulla coda degli ordini e chi può impersonare il server.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud services enable cloudasset.googleapis.com --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** «Operation … finished successfully». Poi di nuovo I0.1: ora deve uscire `cloudasset.googleapis.com`.
- **Ritorno indietro:** `gcloud services disable cloudasset.googleapis.com --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com`. Non costa niente tenerla.

## I2. I pezzi Google Cloud, a secco (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
DRY_RUN=1 CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/agent-gcp.sh staging
```

- **Atteso:**
  1. «server: https://domotica-bff-staging-444239063209.europe-west8.run.app»;
  2. «controlli superati (prima)» e «persona ammessa (PERSONE_AMMESSE): m.scardovellicrac@gmail.com»;
  3. righe «(prova a secco) … lo creerei» per code, account, sottoscrizioni, permessi e allarmi;
  4. «controlli superati (dopo)».
- **Da verificare alla prima esecuzione** (i controlli sono stati scritti su una forma dell'uscita di `gcloud asset analyze-iam-policy` ricavata dalla documentazione, non su quella vera):
  - la forma dell'uscita: `mainAnalysis.analysisResults[].iamBinding.members` e `mainAnalysis.fullyExplored`. Se lo script si ferma con «analisi … non completa» o «non vede il server» **prima** di aver creato qualcosa, incolla l'uscita: o1 guarda la forma vera;
  - **account di Google che l'analisi può riportare:** l'agente di servizio di Cloud Run (`service-444239063209@serverless-robot-prod.iam.gserviceaccount.com`), quello di Cloud Build (`444239063209@cloudbuild.gserviceaccount.com`, `service-444239063209@gcp-sa-cloudbuild.iam.gserviceaccount.com`), il Compute predefinito (`444239063209-compute@developer.gserviceaccount.com`). Se lo script si ferma per uno di loro, **ci si ferma** e si decide con il committente: togliergli il permesso, oppure ammetterlo per iscritto. Nessun elenco aperto.

## I3. I pezzi Google Cloud (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/agent-gcp.sh staging
```

- **Atteso:**
  1. «controlli superati (prima)»;
  2. «coda … creato» per le tre code, «account domhouse-push-staging: creato», le tre sottoscrizioni «creato», sei righe di permessi, due allarmi «creata»;
  3. «controlli superati (dopo)»;
  4. il riepilogo finale con le variabili per il server e per la VM.
- **Da verificare alla prima esecuzione: il ritardo dell'analisi.** I permessi appena dati possono comparire nell'analisi di Cloud Asset solo dopo qualche minuto. Se il controllo «dopo» si ferma con «non vede il server fra chi pubblica»:
  - aspetta 10 minuti e rilancia lo stesso comando;
  - lo script trova tutto già fatto («esiste già») e rifà i due controlli. Non cambia niente.
  - Se si ferma ancora, incolla l'uscita.
- **Ritorno indietro:** I14.3.

## I4. La scadenza delle operazioni in Firestore (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud firestore fields ttls update expire_at --collection-group=agent_ops --enable-ttl --database=staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** l'operazione avviata e poi «ttlConfig: state: CREATING» o `ACTIVE`. Controllo: `gcloud firestore fields ttls list --database=staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com` mostra `agent_ops` con `expire_at`.
- **Ritorno indietro:** lo stesso comando con `--disable-ttl`. Non toglie niente: le operazioni restano finché non si ricancellano.

## I5. Le variabili del server dello staging (o1, commit; poi la pubblicazione del committente)

**I5.1 o1 aggiunge le variabili a `bff/cloudrun.staging.yaml`** (commit [o1], niente push; la memoria storica lo registra). Valori, come li vedrà il servizio dopo la pubblicazione:

| Variabile | Valore |
|---|---|
| `AGENT_AMBIENTE` | `staging` |
| `AGENT_ORDERS_TOPIC` | `projects/domotica-poc-511707/topics/domhouse-staging-ordini` |
| `AGENT_PUSH_AUDIENCE` | `https://domotica-bff-staging-444239063209.europe-west8.run.app/internal/agent/risultati` |
| `AGENT_PUSH_EMAIL` | `domhouse-push-staging@domotica-poc-511707.iam.gserviceaccount.com` |
| `AGENT_PUSH_SUBSCRIPTION` | `projects/domotica-poc-511707/subscriptions/domhouse-staging-risultati-push` |

- La produzione (`bff/cloudrun.yaml`) **non** le riceve: lì l'agente resta spento (§5.4).
- Il pulsante «Prova l'agente» di o2 deve essere nello stesso lotto: la memoria storica controlla che il commit del lotto lo contenga.

**I5.2 La pubblicazione del lotto** (procedura `docs/procedura-ambienti-separati.md`, M18: prima a secco, poi vera).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git log --oneline -1 && grep -c "name: AGENT_" bff/cloudrun.staging.yaml && DRY_RUN=1 bash scripts/publish-all.sh "$(git rev-parse --short HEAD)"
```

- **Atteso:** la riga del commit del lotto, poi `5` (le cinque variabili), poi la prova a secco come in M18.1.
- Poi la pubblicazione vera, come in M18.2: `bash scripts/publish-all.sh "$(git rev-parse --short HEAD)"`.

**I5.3 Controllo (sola lettura).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud run services describe domotica-bff-staging --region=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="yaml(spec.template.spec.containers[0].env)" | grep -A1 "name: AGENT_"
```

- **Atteso:** le cinque variabili con i valori della tabella di I5.1.
- **Ritorno indietro:** I14.2.

## I6. I file dell'agente sulla VM (scrive solo nella cartella di chi si collega)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="mkdir -p ~/agente/agent"
gcloud compute scp scripts/agent-vm.sh langbrain-dev:agente/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp scripts/agent/comune.py scripts/agent/lettore.py scripts/agent/esecutore.py scripts/agent/domhouse-agent-esecutore.service scripts/agent/domhouse-agent-lettore.service langbrain-dev:agente/agent/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd ~/agente && sed -i "s/\r*$//" agent-vm.sh agent/*.py agent/*.service && sha256sum agent-vm.sh agent/*'
```

- **Atteso:** sei file copiati al 100 %, poi sei impronte. `sed` toglie i ritorni a capo di Windows, come V2 della procedura dei difetti.

## I7. L'installazione (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo AMBIENTE=staging SOTTOSCRIZIONE=projects/domotica-poc-511707/subscriptions/domhouse-staging-ordini-vm RISULTATI=projects/domotica-poc-511707/topics/domhouse-staging-risultati bash ~/agente/agent-vm.sh install'
```

- **Atteso:** «== Utente domhouse-agent» e «creato», «== Codice in /opt/domhouse/agent», «== Configurazione», «== Servizi», «agente installato: ambiente staging».
- **«configurazione non valida»** o **«niente installato»:** fermati e incolla. Non è stato scritto niente.
- **Ritorno indietro:** I14.1.

## I8. Lo stato dei due servizi (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash ~/agente/agent-vm.sh status; ls -ld /run/domhouse-agent /run/domhouse-agent/esecutore.sock /var/lib/domhouse-agent /var/lib/domhouse-executor'
```

- **Atteso:**
  1. `domhouse-agent-esecutore.service: active` e `domhouse-agent-lettore.service: active`;
  2. nelle ultime righe nessun «agent fault»;
  3. `/run/domhouse-agent` di `root domhouse-agent`, `drwxr-x---`; il socket `srw-rw----` di `root domhouse-agent`; le due cartelle di stato `drwx------`.
- **Un servizio `failed`:** incolla anche `sudo journalctl -u <servizio> -n 40 --no-pager`.

## I9. `docker inspect` senza capacità (R7, sola lettura)

L'esecutore gira con `ProtectSystem=strict` e nessuna capacità. Si prova che `docker inspect` funzioni lo stesso, con le stesse impostazioni del servizio.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemd-run --quiet --pipe --wait -p User=root -p Group=domhouse-agent -p NoNewPrivileges=yes -p ProtectSystem=strict -p ProtectHome=yes -p PrivateTmp=yes -p CapabilityBoundingSet= -p Environment=DOCKER_CONFIG=/var/lib/domhouse-executor/docker /usr/bin/docker inspect -f "{{.Config.Image}}" engine-lab-01'
```

- **Atteso:** una riga `europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:<tag>`.
- **«permission denied»** sul socket di Docker: fermati e incolla. L'esecutore risponderebbe a «stato» senza l'immagine. La correzione (una capacità precisa, oppure il gruppo `docker`) la decide la memoria storica con o1.

## I10. La prova con il pulsante (scrive: un ordine «stato»)

**Chi:** il committente, come gestore della piattaforma, nell'app dello staging.

1. Pagina della piattaforma → «Prova l'agente» su `lab-01`.
2. **Atteso, in pochi secondi:**
   - esito **riuscito**;
   - motore raggiungibile: `health` 200, connector `up`;
   - l'immagine `…engine:<tag>`, la stessa di I9.
3. Controllo sulla VM (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo journalctl -u domhouse-agent-lettore -u domhouse-agent-esecutore --since "-15min" --no-pager | grep "agent "'
```

- **Atteso:** «agent exec … operazione=stato apartment=lab-01 ambiente=staging esito=riuscito codice=ok» e «agent order … esito=riuscito codice=ok». Nessuna riga con un indirizzo email.
- **L'esito resta «in attesa» per più di un minuto:** incolla il blocco qui sopra e le righe del server: `gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="domotica-bff-staging" AND jsonPayload.msg:"agent"' --freshness=15m --limit=20 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(timestamp,jsonPayload.msg,jsonPayload.reason)"`.

## I11. Un ordine ripetuto lascia la sua traccia (scrive: due messaggi di prova)

**Perché:** «fatto quando» di A1 nel registro. Un ordine consegnato due volte si esegue una volta sola; la seconda copia ripubblica l'esito registrato. Si usa «capienza», che non ha appartamento né numero di sequenza, così non tocca le lapidi di `lab-01` e di `dev`. Il committente è l'unica persona ammessa a pubblicare (PERSONE_AMMESSE).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for n in 1 2; do gcloud pubsub topics publish domhouse-staging-ordini --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --message='{"op_id":"0f5c3c8e-2b1d-4c7a-9e3f-5a6b7c8d9e01","operazione":"capienza","apartment_id":null,"seq":null,"parametri":{},"ambiente":"staging","richiesto_da":"provaManuale1"}'; done
```

- **Atteso:** due righe `messageIds`.
- **Controllo**, dopo 30 secondi: il blocco di I10.3. **Atteso:** **una sola** «agent order op_id=0f5c3c8e-2b1d-4c7a-9e3f-5a6b7c8d9e01 operazione=capienza … esito=riuscito» (eseguito una volta).
- Il server riceve due volte il risultato e lo ignora (l'operazione non è sua): due righe «agent result ignored» con `sconosciuto` nel comando del server di I10.

## I12. Un ordine vecchio viene scartato con la sua traccia (scrive: ferma il lettore 16 minuti)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemctl stop domhouse-agent-lettore && systemctl is-active domhouse-agent-lettore || true'
gcloud pubsub topics publish domhouse-staging-ordini --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --message='{"op_id":"1a6d4d9f-3c2e-4d8b-8f40-6b7c8d9e0f12","operazione":"capienza","apartment_id":null,"seq":null,"parametri":{},"ambiente":"staging","richiesto_da":"provaManuale1"}'
```

- **Atteso:** «inactive», poi una riga `messageIds`.
- **Aspetta 16 minuti**, poi rimetti in moto il lettore:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemctl start domhouse-agent-lettore && sleep 20 && sudo journalctl -u domhouse-agent-lettore --since "-2min" --no-pager | grep "agent "'
```

- **Atteso:** «agent order op_id=1a6d4d9f-3c2e-4d8b-8f40-6b7c8d9e0f12 operazione=capienza … esito=scartato codice=scaduto».
- Durante i 16 minuti il pulsante risponde «in attesa»: non usarlo.

## I13. Fine (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash ~/agente/agent-vm.sh status | head -2; sudo bash /opt/domhouse/engine-vm.sh check-all | grep -E "engine|metadata"'
```

- **Atteso:** i due servizi `active`; «engine ok dev», «engine ok lab-01», «metadata blocked».
- La cartella `~/agente` resta: serve al ritorno indietro (I14.1). Si toglie dopo una settimana senza problemi.

## I14. Ritorno indietro

**I14.1 La VM** (scrive sulla VM): servizi fermati, codice e unità tolti. Restano i giornali e le lapidi.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash ~/agente/agent-vm.sh uninstall'
```

- **Atteso:** «agente tolto; restano i giornali e le lapidi …».

**I14.2 Il server.** o1 toglie le cinque variabili (un commit che annulla quello di I5.1), poi la pubblicazione del lotto come in I5.2. Senza le variabili il pulsante risponde «L'agente sulla VM non è configurato» (503).

**I14.3 Google Cloud** (scrive su Google Cloud). Solo se si decide di togliere tutto; prima I14.1 e I14.2.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for s in domhouse-staging-ordini-vm domhouse-staging-scarti-lettura domhouse-staging-risultati-push; do gcloud pubsub subscriptions delete "$s" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet; done
for t in domhouse-staging-ordini domhouse-staging-risultati domhouse-staging-scarti; do gcloud pubsub topics delete "$t" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet; done
gcloud iam service-accounts delete domhouse-push-staging@domotica-poc-511707.iam.gserviceaccount.com --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet
```

- **Atteso:** tre «Deleted subscription», tre «Deleted topic», «deleted service account».
- I due allarmi «Agente: …» si tolgono dalla console di Monitoring (Avvisi → criteri), oppure restano: senza le code non scattano.

## Da incollare alla memoria storica

Le uscite di tutti i blocchi, comprese quelle di I2 e I3 per intero: servono a verificare la forma vera dell'analisi dei permessi.
