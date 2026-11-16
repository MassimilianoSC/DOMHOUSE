# Correzioni sulla VM: E-31 (metadati), prova del rinnovo, E-32 (backup), E-33 (broker), E-34 (uscite), limiti di risorse

| Stato | Preparata | Quando | Chi lancia | Durata | Comandi |
|---|---|---|---|---|---|
| **Pronta, da rileggere** | o1, 15 novembre 2026, sul codice di `8fe12b9` | **dopo la fine delle prove con Youssouf**; il giorno lo decide il committente (decisioni 1127 e 1128) | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | circa 1 ora | 18 blocchi (V0–V16, più V10b per E-34) |

**Cosa si corregge** (registro, §6):

| Difetto | Che cosa | Commit |
|---|---|---|
| E-31 | ogni container della VM raggiunge il server dei metadati, quindi il token di `langbrain-vm@` | prove `c94207a`, correzione `8fe12b9` |
| E-32 | il backup notturno, da root, segue i link in `/data/<apt>` | prove `b4342d0`, correzione `06df55c` |
| E-33 | un segreto illeggibile ferma il `sync` del broker per tutti gli appartamenti | prove `cda144b`, correzione `beeba84` |
| E-34 | il controllo orario delle uscite segna «failed» quando il server dello staging dorme (114 volte su 131) | prove e correzione `69f2eea` (16 novembre) |
| Limiti (1128) | nessun tetto di memoria, processore e processi sui motori; journald senza limite; nessun allarme sullo spazio dei dati | `8fe12b9` |

**Regole:**

1. Ogni prova rossa si guarda **prima** della correzione.
2. Ogni passo che scrive ha accanto il ritorno indietro.
3. Nessun motore e nessun broker si riavvia: i tetti si mettono con `docker update` sui container che girano.
4. **Se un'uscita non torna, fermati e incolla il testo alla memoria storica.**

**Attenzione alla prossima pubblicazione:** `publish-all.sh` copia sulla VM il nuovo `engine-vm.sh` e il nuovo `compose.yaml`, reinstalla i timer e ricrea `dev`. Quindi `dev` prenderebbe il tetto di 120 MB e il servizio del blocco verrebbe abilitato (vale dal prossimo avvio della VM). Meglio lanciare questa procedura **prima** della prossima pubblicazione.

## V0. Controlli prima (sola lettura)

**V0.1 Sul PC: i file da portare sono quelli dei commit della correzione.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git log --oneline -1 69f2eea && git diff --quiet 69f2eea HEAD -- scripts/engine-vm.sh scripts/broker-vm.sh scripts/broker_accounts.py engine/compose.yaml engine/broker/compose.yaml scripts/monitoring && echo "file uguali a 69f2eea"
```

- **Atteso:** la riga del commit `69f2eea` e «file uguali a 69f2eea». Se manca la seconda riga, fermati: qualcuno ha cambiato quei file dopo.
- `69f2eea` è `8fe12b9` più E-34, che cambia solo `scripts/engine-vm.sh` (il controllo delle uscite) e `scripts/monitoring/rodaggio.py` (che gira sul PC, non sulla VM).

**V0.2 Sulla VM: strumenti, consumo dei container e la prova rossa di E-31.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='python3 -c "import sys; print(\"python\", sys.version.split()[0])"; command -v setpriv nft timeout; sudo docker stats --no-stream --format "{{.Name}} {{.MemUsage}}"; sudo nft list tables; ip -6 addr show scope global | grep -c inet6; for c in engine-dev engine-lab-01; do echo "$c:"; sudo docker exec "$c" python -c "import urllib.request as u; print(u.urlopen(u.Request(\"http://169.254.169.254/computeMetadata/v1/instance/zone\", headers={\"Metadata-Flavor\": \"Google\"}), timeout=3).read().decode())" 2>&1 | tail -1; done'
```

| Riga | Atteso |
|---|---|
| python | 3.11 o più nuovo (serve a E-32) |
| `command -v` | tre percorsi: `setpriv`, `nft`, `timeout` |
| `docker stats` | `engine-dev` e `engine-lab-01` sotto i 100 MiB ciascuno; `domhouse-broker` con il suo limite di 512 MiB. **Se un motore supera i 100 MiB, fermati**: il tetto di 120 MB va alzato prima |
| `nft list tables` | c'è `table inet domhouse_broker`; **non** c'è `domhouse_metadata` |
| numero dopo | `0` se la VM non ha IPv6 (la regola IPv6 resta innocua) |
| `engine-dev:` ed `engine-lab-01:` | **`projects/444239063209/zones/europe-west8-a`: è la prova ROSSA di E-31**, i container raggiungono i metadati. Si chiede solo la zona, mai il token |

**V0.3 Sulla VM: la prova rossa di E-34 (sola lettura).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo journalctl -t domhouse-check --since "-12h" --no-pager | grep " egress " | tail -6'
```

- **Atteso:** le righe orarie delle uscite. **La prova ROSSA di E-34:** almeno una «egress failed server=000 registry=401 acme=200», cioè il server dello staging che dormiva, con il registro e Let's Encrypt raggiunti.
- Se sono tutte «egress ok», va bene lo stesso: lo staging era sveglio. Annota quante sono.

## V1. Copiare i file sulla VM (scrive solo nella cartella di chi si collega)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="mkdir -p ~/difetti-vm/broker"
gcloud compute scp scripts/engine-vm.sh scripts/broker-vm.sh scripts/broker_accounts.py engine/compose.yaml langbrain-dev:difetti-vm/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp engine/broker/compose.yaml langbrain-dev:difetti-vm/broker/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** cinque file copiati, tutti al 100 %.

## V2. Installare gli script e i compose nuovi (scrive sulla VM; nessun container si riavvia)

Toglie anche i ritorni a capo di Windows, come fa `broker-vm.sh install`. Tiene una copia dei file di prima per tornare indietro.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-difetti-vm; sudo mkdir -p $B; sudo cp -p /opt/domhouse/engine-vm.sh /opt/domhouse/broker-vm.sh /opt/domhouse/broker_accounts.py /opt/domhouse/compose.yaml $B/; sudo cp -p /opt/domhouse/_broker/compose.yaml $B/broker-compose.yaml; cd ~/difetti-vm; sed -i "s/\r*$//" engine-vm.sh broker-vm.sh broker_accounts.py compose.yaml broker/compose.yaml; sudo install -m 755 engine-vm.sh /opt/domhouse/engine-vm.sh; sudo install -m 755 broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 broker_accounts.py /opt/domhouse/broker_accounts.py; sudo install -m 644 compose.yaml /opt/domhouse/compose.yaml; sudo install -m 644 broker/compose.yaml /opt/domhouse/_broker/compose.yaml; sha256sum /opt/domhouse/engine-vm.sh /opt/domhouse/broker-vm.sh /opt/domhouse/broker_accounts.py /opt/domhouse/compose.yaml /opt/domhouse/_broker/compose.yaml; ls $B'
```

- **Atteso:** cinque impronte e l'elenco della copia in `/opt/domhouse/prima-difetti-vm`.
- I compose nuovi valgono alla **prossima** ricreazione dei container; adesso non si riavvia niente.
- **Ritorno indietro di tutta la procedura:** rimettere i file di `/opt/domhouse/prima-difetti-vm` al loro posto, con gli stessi `install`, e i ritorni dei singoli passi.

## E-31: i metadati chiusi ai container

### V3. Timer e servizio del blocco, limite di journald (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh timers && systemctl is-enabled domhouse-metadata-block.service && cat /etc/systemd/journald.conf.d/domhouse.conf'
```

- **Atteso:** i timer di sempre, poi `enabled`, poi `[Journal]` e `SystemMaxUse=500M`.
- journald si riavvia (pochi millisecondi). Il blocco non è ancora attivo: lo mette V4.

### V4. Il blocco (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh metadata-block && sudo systemctl start domhouse-metadata-block.service && sudo nft list table inet domhouse_metadata'
```

- **Atteso:** «metadati chiusi ai container: …», poi la tabella con le due regole `drop` verso `169.254.169.254` e `fd20:ce::254`.

**Ritorno indietro di E-31:**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemctl disable domhouse-metadata-block.service; sudo rm -f /opt/domhouse/metadata.nft; sudo nft delete table inet domhouse_metadata; sudo nft list tables'
```

### V5. La prova diventa verde (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='for c in engine-dev engine-lab-01; do echo "$c:"; sudo docker exec "$c" python -c "import urllib.request as u; print(u.urlopen(u.Request(\"http://169.254.169.254/computeMetadata/v1/instance/zone\", headers={\"Metadata-Flavor\": \"Google\"}), timeout=3).read().decode())" 2>&1 | tail -1; done; echo "host:"; curl -s -m 3 -H "Metadata-Flavor: Google" http://169.254.169.254/computeMetadata/v1/instance/zone; echo; for p in 8100 8169; do curl -s -m 5 http://10.198.0.2:$p/api/v1/health | python3 -c "import json,sys; h=json.load(sys.stdin); print(h[\"apartment_id\"], h[\"status\"], h[\"connector\"][\"status\"])"; done; sudo rm -f /opt/domhouse/.metadata-checked; sudo bash /opt/domhouse/engine-vm.sh check-all | grep -E "metadata|data "'
```

| Riga | Atteso |
|---|---|
| `engine-dev:` ed `engine-lab-01:` | un errore di tempo scaduto (`timed out`): **verde**, i container non raggiungono più i metadati |
| `host:` | `projects/444239063209/zones/europe-west8-a`: l'host li raggiunge ancora (servono agli script e a lego) |
| motori | `dev ok up` e `lab-01 … up` (`ok` oppure `degraded` se la Plug è spenta): i motori lavorano come prima |
| controllo | `metadata blocked`, e una riga `data <apt> mb=…` per appartamento |

## Prova del rinnovo del certificato, senza sostituirlo (decisione del committente)

### V6. Rimettere il permesso sul DNS

Il blocco D4 di `docs/procedura-permesso-dns.md`, così com'è. Poi aspetta 2 minuti: i permessi arrivano con un po' di ritardo.

### V7. Il rinnovo di prova (scrive sulla VM una cartella temporanea, poi la toglie)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh cert-test; sudo bash /opt/domhouse/broker-vm.sh check'
```

- **Atteso:** le righe di lego verso `acme-staging-v02`, poi «broker cert test ok (mqtt.dh-lab.eu, notAfter=…)», poi «broker ok cert_days=…», con gli stessi giorni di prima: il certificato servito non è cambiato.
- **«broker cert test failed»:** aspetta altri 3 minuti e rilancia una volta, perché il permesso può non essere ancora arrivato. Se fallisce ancora, incolla l'uscita. Il certificato servito resta comunque quello di prima.
- **Da verificare la prima volta:** lego sulla rete dell'host con l'impersonazione dopo il blocco, e il server di prova di Let's Encrypt.

### V8. Ritogliere il permesso

I blocchi D1 e poi D2 di `docs/procedura-permesso-dns.md`, così come sono.

## E-32 ed E-33

### V9. Backup senza link (scrive sulla VM le copie di oggi)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh backup dev; sudo bash /opt/domhouse/engine-vm.sh backup lab-01; sudo ls -la /data/_backup.tmp; sudo ls -ln /data/dev/backup /data/lab-01/backup | tail -4'
```

- **Atteso:**
  1. «backup dev: /data/dev/backup/engine-<oggi>.db (… byte, integrity_check ok)», e lo stesso per `lab-01`;
  2. `/data/_backup.tmp` vuota (solo `.` e `..`);
  3. le copie di oggi, di proprietà `10001`.
- **«backup refused»:** in una cartella c'è un link. Non succede con i motori di oggi: incolla l'uscita.
- **Ritorno indietro:** il `backup` del vecchio `engine-vm.sh`, in `/opt/domhouse/prima-difetti-vm`.

### V10. Il broker con il sync isolato (scrive sulla VM solo se qualcosa cambia; non deve cambiare niente)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh sync'
```

- **Atteso:** «lab-01: connector e 1 dispositivi» e «unchanged». Nessuna riga «kept»: i segreti di `lab-01` si leggono, e gli hash restano uguali.
  - Se prima è stata fatta la procedura dei due Shelly (`docs/procedura-lab01-due-shelly.md`), «connector e 3 dispositivi».
- La Plug resta collegata.

## E-34: le uscite della VM

### V10b. Il controllo delle uscite con lo staging che si sveglia (scrive sulla VM solo l'ora dell'ultimo controllo)

Il controllo delle uscite gira una volta all'ora. Qui si azzera l'ora dell'ultimo controllo, così parte subito.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='echo 0 | sudo tee /opt/domhouse/.egress-checked > /dev/null; sudo bash /opt/domhouse/engine-vm.sh check-all > /dev/null; sudo journalctl -t domhouse-check --since "-2min" --no-pager | grep " egress "'
```

- **Atteso:** una riga «egress ok server=… registry=401 acme=200», con il server in uno di due modi:
  - `server=waking`: lo staging dormiva, la connessione TLS è riuscita e la risposta non è arrivata in 10 s. **È la correzione di E-34**: prima questa riga era «failed server=000»;
  - `server=200`: lo staging era già sveglio.
- **«egress failed server=000»** con il registro e Let's Encrypt raggiunti: il server non si raggiunge nemmeno con TLS (DNS o rete). È un esito vero, da incollare.
- Il controllo dura al massimo circa 30 secondi (tre prove da 10 s).
- **Ritorno indietro:** il vecchio `engine-vm.sh` di `/opt/domhouse/prima-difetti-vm` (V2). L'ora azzerata non va rimessa: al prossimo giro il controllo la riscrive.

## Limiti di risorse (decisione 1128)

### V11. Tetti sui container che girano (scrive sulla VM; nessun riavvio)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh limits dev && sudo bash /opt/domhouse/engine-vm.sh limits lab-01 && sudo docker update --cpus 1.0 --pids-limit 256 domhouse-broker && for c in engine-dev engine-lab-01 domhouse-broker; do sudo docker inspect -f "{{.Name}} mem={{.HostConfig.Memory}} cpu={{.HostConfig.NanoCpus}} pids={{.HostConfig.PidsLimit}}" $c; done; sudo docker stats --no-stream --format "{{.Name}} {{.MemUsage}}"'
```

- **Atteso:**
  1. «engine-dev: memoria 120m, cpus 1.0, processi 128», lo stesso per `engine-lab-01`;
  2. `/engine-dev mem=125829120 cpu=1000000000 pids=128`, lo stesso per `engine-lab-01`;
  3. `/domhouse-broker mem=536870912 cpu=1000000000 pids=256`;
  4. i consumi, sotto i tetti.
- **Se un motore viene ucciso** perché supera il tetto, Docker lo riavvia da solo. Si alza il suo tetto con una riga `ENGINE_MEM_LIMIT=160m` in `/opt/domhouse/<apt>.settings`, poi di nuovo `limits <apt>`.
- **Ritorno indietro:** `sudo docker update --memory 0 --memory-swap -1 --cpus 0 --pids-limit -1 engine-dev` (lo stesso per `engine-lab-01`), e `--cpus 0 --pids-limit -1` per il broker. **Da verificare**: se Docker rifiuta `--memory 0` su un container già limitato, si toglie il tetto alla prossima ricreazione, con il `compose.yaml` di prima.

### V12. Spazio dei dati e registri (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='journalctl --disk-usage; sudo journalctl -t domhouse-check --since "-10min" --no-pager | grep -E "data |metadata"'
```

- **Atteso:** journald sotto i 500 MB; le righe `data dev mb=…`, `data lab-01 mb=…` e `metadata blocked` di V5.

## Allarmi

### V13. Le quattro politiche nuove (scrive su Google Cloud)

**Prima di lanciarlo, l'esito del controllo D3** di `docs/procedura-permesso-dns.md`, fatto almeno un giorno dopo D1. Se dice «broker cert renew failed», l'allarme nuovo «rinnovo non riuscito» scatterebbe ogni giorno: fermati e avvisa la memoria storica, si decide prima di crearlo.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com DRY_RUN=1 GCP_PROJECT_ID=domotica-poc-511707 scripts/monitoring/engine-alerts.sh
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 scripts/monitoring/engine-alerts.sh
```

- **Atteso:**
  - prova a secco: «la creerei da» per le quattro nuove;
  - davvero: «creata» per «Motori: metadati raggiungibili dai container», «Motori: rinnovo del certificato del broker non riuscito», «Motori: broker, un appartamento non aggiornato», «Motori: dati di un appartamento oltre 500 MB»; «esiste già» per le altre otto.

### V14. Controllo delle politiche (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud alpha monitoring policies list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(displayName,enabled)" | grep "Motori:"
```

- **Atteso:** dodici righe «Motori: …» con `True`.

## Fine

### V15. Il controllo completo, e la Plug (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh check-all; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "^appartamenti|^utenti|^broker ok|connessioni"; sudo docker logs --since 30m domhouse-broker 2>&1 | grep -c "lab-01.shellyplugmg3-9070695cb0d0"'
```

- **Atteso:**
  - «engine ok dev», «engine ok lab-01», «domhouse-check: 2 motori, 0 muti», `vm mem_used_pct=…`, «broker ok cert_days=…»;
  - nessuna riga `kept`, `refused`, `OPEN`;
  - broker con 1 appartamento e i suoi utenti;
  - la Plug, se è accesa, ancora nel registro del broker.

### V16. Pulizia della cartella di lavoro (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='rm -rf ~/difetti-vm; ls ~ | head'
```

- `/opt/domhouse/prima-difetti-vm` resta: è il ritorno indietro. Si toglie dopo una settimana senza problemi.

## Dopo V16, a parte: il catalogo di Youssouf nel motore `lab-01` (risposta 1144)

**Non fa parte di V0–V16.** Si fa dopo V16, oppure un altro momento: lo decide il committente. Sono i passi 6.5 della tappa B, con il file unito in `main` (`4c5f427`).

**Prima di cominciare, da sapere:**

1. **Lo Shelly 1 e l'EM Mini risultano «non in linea»** finché non c'è la procedura `docs/procedura-lab01-due-shelly.md`. Senza di loro, anche i tre sensori BLU (che passano dallo Shelly 1) restano «non in linea». È atteso.
2. **L'immagine di `lab-01` è `engine:247fda0`.** Il catalogo con quel codice si carica (controllato da o1). Ma per i sensori BLU mancano le correzioni dell'orologio del ponte (#12 e #13, tappa B 6.4): finché l'immagine non si aggiorna, dopo un riavvio del ponte un sensore morto può sembrare vivo per qualche minuto.
3. **Quando lo Shelly 1 sarà collegato**, il motore regola la «Caldaia» con il sensore H&T: il relè può scattare da solo. Al banco a valle c'è solo la ciabatta con la spia.
4. **La Plug resta `dev-presa-lab`:** l'app tiene il suo nome di oggi e il suo storico.
5. **Ricreare il container** (comando `key`) applica il `compose.yaml` installato in V2, con i tetti di V11: è atteso.

### C1. Il catalogo sul PC (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git log --oneline -1 4c5f427 && .venv/Scripts/python.exe -c "from pathlib import Path; from engine.connector.shelly.catalog import load_catalog; from engine.connector.shelly.offline import load_thresholds; c = load_catalog(Path('engine/connector/shelly/cataloghi/lab-01.yaml'), load_thresholds()); print('catalogo valido:', [(d.device_id, d.shelly_id or d.blu.addr, d.device_type) for d in c.devices])"
```

- **Atteso:** la riga di `4c5f427`, poi `catalogo valido:` con sei dispositivi, il primo `('dev-presa-lab', 'shellyplugmg3-9070695cb0d0', 'plug')`.
- Se la Plug ha un altro `device_id`, fermati: l'app perderebbe lo storico.

### C2. Copia di sicurezza, file nuovo, motore ricreato (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute scp engine/connector/shelly/cataloghi/lab-01.yaml langbrain-dev:catalog-lab-01.yaml --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo cp -p /data/lab-01/catalog.yaml /data/lab-01/catalog.yaml.prima && sudo install -m 640 -o 10001 -g 10001 ~/catalog-lab-01.yaml /data/lab-01/catalog.yaml && sudo ls -ln /data/lab-01 && sudo bash /opt/domhouse/engine-vm.sh key lab-01'
```

- `key` riscrive il file della chiave e ricrea il container: il motore rilegge il catalogo.
- **Atteso:** `catalog.yaml` e `catalog.yaml.prima` nella cartella, poi `health 200: ok … connector up`.

### C3. Controllo (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker logs --since 5m engine-lab-01 2>&1 | grep -E "shelly connector started|engine started|link ignored|not supported|unknown shelly|blu sensor not paired" | cut -c1-220'
```

- **Atteso:**
  1. «shelly connector started» con `devices: 6` (o `"devices": 6`);
  2. «engine started» con 6 dispositivi;
  3. **nessuna** riga «link ignored» (il collegamento caldaia → sensore H&T è valido) né «not supported».
- «blu sensor not paired» compare solo quando lo Shelly 1 è collegato e un sensore non risulta abbinato al ponte: da incollare.
- Poi, nell'app di staging, la pagina dei dispositivi di `lab-01`: sei dispositivi, la Plug in linea, gli altri «non in linea» finché non c'è la procedura dei due Shelly.

### C4. Tornare al catalogo di prima (scrive sulla VM), solo se il motore non riparte o qualcosa non va

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo cp -p /data/lab-01/catalog.yaml.prima /data/lab-01/catalog.yaml && sudo bash /opt/domhouse/engine-vm.sh key lab-01'
```

- **Atteso:** `health 200: ok … connector up`, con la sola Plug.
- I dispositivi nuovi restano salvati nel motore ma non si aggiornano più. Lo storico della Plug non cambia.

## Da incollare alla memoria storica

Le uscite di V0.2 (prova rossa), V0.3 (prova rossa di E-34), V5 (prova verde), V7, V9, V10, V10b, V11, V13 e V15.
Se si fa anche il catalogo: C1, C2 e C3.
