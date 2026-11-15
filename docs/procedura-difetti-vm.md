# Correzioni sulla VM: E-31 (metadati), prova del rinnovo, E-32 (backup), E-33 (broker), limiti di risorse

| Stato | Preparata | Quando | Chi lancia | Durata | Comandi |
|---|---|---|---|---|---|
| **Pronta, da rileggere** | o1, 15 novembre 2026, sul codice di `8fe12b9` | **dopo la fine delle prove con Youssouf**; il giorno lo decide il committente (decisioni 1127 e 1128) | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | circa 1 ora | 17 blocchi (V0–V16) |

**Cosa si corregge** (registro, §6):

| Difetto | Che cosa | Commit |
|---|---|---|
| E-31 | ogni container della VM raggiunge il server dei metadati, quindi il token di `langbrain-vm@` | prove `c94207a`, correzione `8fe12b9` |
| E-32 | il backup notturno, da root, segue i link in `/data/<apt>` | prove `b4342d0`, correzione `06df55c` |
| E-33 | un segreto illeggibile ferma il `sync` del broker per tutti gli appartamenti | prove `cda144b`, correzione `beeba84` |
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
git log --oneline -1 8fe12b9 && git diff --quiet 8fe12b9 HEAD -- scripts/engine-vm.sh scripts/broker-vm.sh scripts/broker_accounts.py engine/compose.yaml engine/broker/compose.yaml scripts/monitoring && echo "file uguali a 8fe12b9"
```

- **Atteso:** la riga del commit `8fe12b9` e «file uguali a 8fe12b9». Se manca la seconda riga, fermati: qualcuno ha cambiato quei file dopo.

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
- La Plug resta collegata.

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

## Da incollare alla memoria storica

Le uscite di V0.2 (prova rossa), V5 (prova verde), V7, V9, V10, V11, V13 e V15.
