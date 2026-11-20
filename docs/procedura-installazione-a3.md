# Installazione di A3: le credenziali dei dispositivi (staging)

| Stato | Preparata | Codice | Chi lancia | Comandi |
|---|---|---|---|---|
| **Pronta, corretta dopo la revisione del codice** (19 novembre, «installabile dopo correzioni», tutte fatte). Nessun passo provato sul vero | o1, 19 novembre 2026 (notte, via 1184) | file della VM uguali a `f54a222`; server da `f54a222` più il commit del manifesto (Q3.1) | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | Q0–Q8 |

**Cosa si installa** (`docs/proposta-a3-server.md`):

| Dove | Che cosa |
|---|---|
| Google Cloud | due segreti nuovi, `domhouse-agent-ordini-staging` e `domhouse-agent-risultati-staging` (le chiavi delle firme), letti solo dal server dello staging; due allarmi nuovi (`scripts/agent-gcp.sh`) |
| VM | il codice nuovo dell'agente (firme, `aggiorna_broker`), l'unità dell'esecutore allargata, i due file delle chiavi, `broker-vm.sh` e `broker_accounts.py` nuovi, `auth/` a `root:1883` |
| Server dello staging | tre variabili nuove (due chiavi dai segreti, `DEVICE_BROKER_ADDRESS`) e il codice delle rotte |
| `lab-01` | la migrazione: le impronte di oggi nel file del broker e nell'app (risposta 1174) |

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.** Se un'uscita non torna, fermati.
2. Ogni passo che scrive ha accanto il ritorno indietro.
3. Solo lo **staging**. In produzione A3 non si apre prima della VM nuova e della pagina locale (risposta 1185).
4. Ogni `gcloud compute ssh` finisce con `< /dev/null`. Un «Segmentation fault» **dopo** l'uscita attesa è innocuo (plink, sul PC).
5. **Fra Q2 e Q3 l'agente rifiuta gli ordini del server vecchio** (non firmati): «Prova l'agente» risponde «firma non valida» finché Q3 non è finito. Non serve a nessuno in quei minuti.

**Quando:** dopo il push dei commit di A3 (fino al commit di questa procedura). Il giorno lo decide il committente.

## Q0. Prerequisiti (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git merge-base --is-ancestor f54a222 origin/main && git diff --quiet f54a222 HEAD -- scripts/agent scripts/agent-vm.sh scripts/broker-vm.sh scripts/broker_accounts.py && echo "file della VM uguali a f54a222, già su GitHub"
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash ~/agente/agent-vm.sh status | head -2; systemctl is-active domhouse-agent-esecutore domhouse-agent-lettore; sudo ls -ld /etc/domhouse/_broker/auth; sudo ls -l /etc/domhouse/_broker/auth' < /dev/null
```

- `agent-vm.sh` non è installato in `/opt/domhouse` (`install` copia solo `comune.py`, `lettore.py`, `esecutore.py`): lo status si chiama dalla copia di A1 in `~/agente`, come in I13.
- Q0 è stato fatto il 20 novembre su `f54a222`. Da `7952a68` cambiano solo `agent-vm.sh` e l'unità dell'esecutore (il gruppo del broker): li ricopia Q2.3a. A un rilancio di Q0 il confronto va fatto con `7952a68`.
- **Atteso:** «file della VM uguali a f54a222, già su GitHub»; i due servizi `active`; `auth/` di `1883 1883` con i quattro file `1883 1883` (`-rw-r-----`). Altrimenti fermati.

## Q1. Le due chiavi delle firme (scrive sulla VM e su Google Cloud)

**Q1.1 Le chiavi nascono sulla VM, da root** (revisione, punto 9). Nessuna compare a schermo.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; for n in ordini risultati; do f=/etc/domhouse/agent-$n.key; if sudo test -e $f; then echo "$f c era già: non la tocco"; else sudo sh -c "umask 077; python3 -c \"import secrets; print(secrets.token_hex(32))\" > $f"; echo "$f creata"; fi; done; sudo ls -l /etc/domhouse/agent-ordini.key /etc/domhouse/agent-risultati.key; sudo wc -c /etc/domhouse/agent-ordini.key /etc/domhouse/agent-risultati.key' < /dev/null
```

- **Atteso:** due «creata» (a un rilancio «c era già»); i due file `-rw------- root root`, **65** byte ciascuno (64 cifre e l'a capo).
- **Ritorno indietro:** `sudo rm -f /etc/domhouse/agent-ordini.key /etc/domhouse/agent-risultati.key` (solo prima di Q1.3).

**Q1.2 I due segreti, vuoti** (parametri fissi del progetto §2.2).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for n in ordini risultati; do gcloud secrets create "domhouse-agent-$n-staging" --replication-policy=user-managed --locations=europe-west8 --labels=domhouse-env=staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com; done
```

- **Atteso:** due «Created secret».
- **Ritorno indietro:** `gcloud secrets delete domhouse-agent-ordini-staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet`, e lo stesso per `domhouse-agent-risultati-staging`.

**Q1.3 Il valore dalla VM al segreto**, passando solo dalla memoria del PC (una variabile, mai stampata).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for n in ordini risultati; do K="$(gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo cat /etc/domhouse/agent-$n.key" < /dev/null 2>/dev/null | tr -d '\r\n')"; if [ "${#K}" -eq 64 ]; then printf '%s' "$K" | gcloud secrets versions add "domhouse-agent-$n-staging" --data-file=- --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com; else echo "chiave $n non letta (lunghezza ${#K}): fermati"; fi; unset K; done
```

- **Atteso:** due «Created version [1]». «chiave … non letta»: fermati e incolla.
- **Da verificare:** il «Segmentation fault» di plink, se compare, va sullo schermo e non nella variabile (è scritto su stderr); il controllo della lunghezza ferma comunque un valore sbagliato.

**Q1.4 Chi legge i due segreti: solo il server dello staging.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for n in ordini risultati; do gcloud secrets add-iam-policy-binding "domhouse-agent-$n-staging" --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(bindings)"; done
for n in ordini risultati; do echo "== $n"; gcloud secrets get-iam-policy "domhouse-agent-$n-staging" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --flatten="bindings[].members" --format="table[no-heading](bindings.role,bindings.members)"; done
```

- **Atteso:** per ciascuno **una sola** riga, `roles/secretmanager.secretAccessor serviceAccount:domotica-bff-staging@…`. Nessun `langbrain-vm@`: la VM ha le chiavi nei suoi file e non deve poterle leggere da Secret Manager (vincolo della revisione, punto 9).
- **E a livello di progetto** (revisione del codice, punto 8), sola lettura:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects get-iam-policy domotica-poc-511707 --account=m.scardovellicrac@gmail.com --flatten="bindings[].members" --filter="bindings.role~secretmanager" --format="table[no-heading](bindings.role,bindings.members,bindings.condition.title)"
```

- **Atteso:** nessuna riga con `langbrain-vm@` senza condizione. Il 19 novembre non c'era nessun ruolo di Secret Manager a livello di progetto; dopo A2 ci sarà quello condizionato sui prefissi `langbrain-…`, che non copre `domhouse-agent-…`.
- **Ritorno indietro:** `gcloud secrets remove-iam-policy-binding` con gli stessi argomenti.

## Q2. La VM: codice dell'agente e del broker (scrive sulla VM; il broker non si riavvia)

**Q2.1 I file sulla VM** (nella cartella di chi si collega).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='mkdir -p ~/a3/agent' < /dev/null
gcloud compute scp scripts/agent-vm.sh scripts/broker-vm.sh scripts/broker_accounts.py langbrain-dev:a3/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp scripts/agent/comune.py scripts/agent/lettore.py scripts/agent/esecutore.py scripts/agent/domhouse-agent-esecutore.service scripts/agent/domhouse-agent-lettore.service langbrain-dev:a3/agent/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd ~/a3 && sed -i "s/\r*$//" agent-vm.sh broker-vm.sh broker_accounts.py agent/*.py agent/*.service && sha256sum agent-vm.sh broker-vm.sh broker_accounts.py agent/* | cut -c1-16,65-' < /dev/null
```

- **Atteso:** otto file copiati, poi otto impronte. La memoria storica le confronta con quelle di `f54a222` (calcolate sul PC senza i ritorni a capo). Una diversa: fermati.

**Q2.2 Broker: `auth/` a `root:1883`, la cartella `devices/`, il codice nuovo** (N9). Copia di prima in `/opt/domhouse/prima-a3`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-a3; if ! sudo test -e $B/broker-vm.sh; then sudo mkdir -p $B; sudo cp -p /opt/domhouse/broker-vm.sh /opt/domhouse/broker_accounts.py $B/; echo "copia di prima fatta"; fi; sudo install -m 755 ~/a3/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 ~/a3/broker_accounts.py /opt/domhouse/broker_accounts.py; sudo chown root:1883 /etc/domhouse/_broker/auth; sudo chmod 750 /etc/domhouse/_broker/auth; sudo sh -c "umask 077; mkdir -p /etc/domhouse/_broker/devices"; sudo ls -ld /etc/domhouse/_broker/auth /etc/domhouse/_broker/devices; sudo bash /opt/domhouse/broker-vm.sh sync | tail -3' < /dev/null
```

- **Atteso:** `drwxr-x--- root 1883 … auth`, `drwx------ root root … devices`; dal sync «lab-01: connector e N dispositivi» (N come oggi) e **«unchanged»**: `lab-01` legge ancora il suo segreto vecchio, niente cambia.
- **Ritorno indietro:** `sudo install -m 755 /opt/domhouse/prima-a3/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 /opt/domhouse/prima-a3/broker_accounts.py /opt/domhouse/broker_accounts.py; sudo chown 1883:1883 /etc/domhouse/_broker/auth`.

**Q2.3 Il gruppo del broker, poi la prova dell'unità allargata, prima di installarla** (N9).

Il 20 novembre la prima prova si è fermata: con `SupplementaryGroups=1883` systemd non avvia niente (stato 216, EXIT_GROUP), perché sull'host **nessun gruppo ha il gid 1883** (è solo l'utente del contenitore di Mosquitto). Correzione `7952a68`: un gruppo di sistema `domhouse-broker` con gid 1883, e l'unità lo nomina (`SupplementaryGroups=domhouse-broker`). Da `7952a68` lo crea anche `agent-vm.sh install`, che si ferma se il gid 1883 è già di un altro gruppo.

**Q2.3a I tre file cambiati da ricopiare** (`agent-vm.sh` e l'unità dell'esecutore da `7952a68`, `esecutore.py` da `6af9f5c`: il sync con `DOCKER_CONFIG`, difetto trovato da Q2.3c il 20 novembre; gli altri cinque di Q2.1 restano).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute scp scripts/agent-vm.sh langbrain-dev:a3/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp scripts/agent/domhouse-agent-esecutore.service scripts/agent/esecutore.py langbrain-dev:a3/agent/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd ~/a3 && sed -i "s/\r*$//" agent-vm.sh agent/domhouse-agent-esecutore.service agent/esecutore.py && sha256sum agent-vm.sh agent/domhouse-agent-esecutore.service agent/esecutore.py | cut -c1-16,65-; grep -n "^SupplementaryGroups" agent/domhouse-agent-esecutore.service; grep -c "DOCKER_CONFIG" agent/esecutore.py' < /dev/null
```

- **Atteso:** tre impronte che cominciano così: `agent-vm.sh` `b013386278381469`, `agent/domhouse-agent-esecutore.service` `dc24e3330fe99266`, `agent/esecutore.py` `c60dff3fdd600f86`; poi `SupplementaryGroups=domhouse-broker` e **4** (le righe con `DOCKER_CONFIG` in `esecutore.py`).

**Q2.3b Il gruppo** (scrive sulla VM: un gruppo di sistema, nessun utente dentro).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='n="$(getent group domhouse-broker || true)"; g="$(getent group 1883 || true)"; if [ -n "$n" ]; then echo "esiste: $n"; elif [ -n "$g" ]; then echo "FERMATI: il gid 1883 è già del gruppo: $g"; else sudo groupadd --system --gid 1883 domhouse-broker && echo "creato"; fi; getent group domhouse-broker; sudo ls -ln /etc/domhouse/_broker/auth | head -3' < /dev/null
```

- **Atteso:** «creato» (a un rilancio «esiste: domhouse-broker:x:1883:»), poi `domhouse-broker:x:1883:`; i file di `auth/` restano `1883 1883`.
- **«FERMATI»:** il gid 1883 è di un altro gruppo; non si tocca niente, si decide con o1.
- **Ritorno indietro:** `sudo groupdel domhouse-broker` (solo prima di Q2.4, o dopo il ritorno indietro di Q2.4).

**Q2.3c La prova dell'unità** (sola lettura, salvo un file di prova in `auth/` tolto subito).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='P="-p User=root -p Group=domhouse-agent -p SupplementaryGroups=domhouse-broker -p NoNewPrivileges=yes -p ProtectSystem=strict -p ProtectHome=yes -p PrivateTmp=yes -p ReadWritePaths=/etc/domhouse/_broker -p CapabilityBoundingSet=CAP_CHOWN -p RestrictAddressFamilies=AF_UNIX -p RestrictAddressFamilies=AF_INET -p MemoryMax=128M -p UMask=0077"; sudo systemd-run --quiet --pipe --wait $P /bin/sh -c "id; head -c 0 /etc/domhouse/_broker/auth/devices.passwd && echo lettura-ok; f=/etc/domhouse/_broker/auth/.prova-a3; touch \$f && chown 1883:1883 \$f && echo scrittura-ok; rm -f \$f"; sudo systemd-run --quiet --pipe --wait -E PATH=/usr/sbin:/usr/bin:/sbin:/bin -E DOCKER_CONFIG=/var/lib/domhouse-executor/docker $P /bin/bash /opt/domhouse/broker-vm.sh sync | tail -1' < /dev/null
```

- **Atteso:** `uid=0(root) gid=…(domhouse-agent) groups=…(domhouse-agent),1883(domhouse-broker)`; «lettura-ok»; «scrittura-ok»; dal sync «unchanged».
- **Da verificare** (non provabile sul PC; revisione del codice, «da verificare» 1), tutto in questo blocco:
  1. `SupplementaryGroups=domhouse-broker` accettato e visibile in `id`;
  2. lettura di un file 640 di `auth/` dal gruppo 1883, scrittura e `chown` a 1883;
  3. il `sync` sotto le stesse restrizioni e con lo stesso ambiente che gli dà l'esecutore (`PATH` e `DOCKER_CONFIG=/var/lib/domhouse-executor/docker`: `ProtectHome` nasconde `/root/.docker`, 20 novembre): token della VM (rete `AF_INET`, dal server dei metadati, senza gcloud) e `docker` (socket `AF_UNIX`), con `MemoryMax=128M` e `UMask=0077` come nell'unità (`write_files` mette comunque 640).
- Un «Permission denied», un errore del sync o un processo fermato per memoria: **fermati** e incolla; non si installa l'unità (si decide con o1 cosa aprire).

**Q2.4 L'agente nuovo** (come I7 di A1: rilanciare `install` aggiorna codice e unità e riavvia).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo AMBIENTE=staging SOTTOSCRIZIONE=projects/domotica-poc-511707/subscriptions/domhouse-staging-ordini-vm RISULTATI=projects/domotica-poc-511707/topics/domhouse-staging-risultati bash ~/a3/agent-vm.sh install; sudo bash ~/a3/agent-vm.sh status | head -2; grep -E "^(ReadWritePaths|CapabilityBoundingSet|SupplementaryGroups)" /etc/systemd/system/domhouse-agent-esecutore.service' < /dev/null
```

- **Atteso:** «== Gruppo domhouse-broker (gid 1883)» e «esiste già» (da Q2.3b), «agente installato: ambiente staging»; i due servizi `active`; le tre righe dell'unità, con `SupplementaryGroups=domhouse-broker`.
- **Ritorno indietro:** lo stesso comando dalla copia di A1 (`~/agente`, I6 di A1), poi `sudo systemctl restart domhouse-agent-esecutore domhouse-agent-lettore`. **Dopo Q3** l'agente di A1 rifiuta gli ordini firmati del server nuovo (`campo_non_valido`): tornare ad A1 sulla VM vuol dire tornare **anche** al server di prima (ritorno indietro di Q3.2), e viceversa (revisione del codice, punto 6).

## Q3. Il server dello staging (o1 committa, il committente spinge e pubblica)

**Q3.1 Il manifesto** (o1, un commit; **dopo** Q1: senza i segreti la pubblicazione fallirebbe). In `bff/cloudrun.staging.yaml`, dopo `AGENT_PUSH_SUBSCRIPTION`:

```yaml
            - name: AGENT_ORDINI_KEY
              valueFrom:
                secretKeyRef:
                  name: domhouse-agent-ordini-staging
                  key: latest
            - name: AGENT_RISULTATI_KEY
              valueFrom:
                secretKeyRef:
                  name: domhouse-agent-risultati-staging
                  key: latest
            - name: DEVICE_BROKER_ADDRESS
              value: mqtt.dh-lab.eu:8883
```

e i tre nomi in `ONLY_STAGING` di `tests/cloudrun_manifests_test.py`. Poi il push del committente.

**Q3.2 La pubblicazione dello staging: server E sito** (non come I5.2 di A1: con A1 il sito non cambiava, con A3 sì).

- Senza il sito dello staging le pagine di A3 di o2 (Credenziali dei dispositivi, l'accesso da Organizzazioni) non ci sarebbero: Q5 andrebbe, Q6.3 e Q7 no. Quindi `TARGET=staging` **senza** `SKIP_HOSTING`: `publish.sh` pubblica anche il sito, su `STAGING_SITE` (`domhouse-staging`, da `scripts/publish-settings.conf`).
- Il sito dello staging prende **tutte** le modifiche del sito da `f4c6a20` (l'ultima pubblicazione del sito) a HEAD, non solo A3.
- La produzione non si tocca.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git merge-base --is-ancestor HEAD origin/main && git log --oneline -1 && git show HEAD:bff/cloudrun.staging.yaml | grep -c -E "name: (AGENT_ORDINI_KEY|AGENT_RISULTATI_KEY|DEVICE_BROKER_ADDRESS)" && while IFS='=' read -r k v; do v="${v%$'\r'}"; case "$k" in ''|'#'*) ;; *) export "$k=$v" ;; esac; done < scripts/publish-settings.conf && TARGET=staging bash scripts/publish.sh "$(git rev-parse --short HEAD)"
```

- **Atteso:** la riga del commit, **3**, poi la pubblicazione dello staging riuscita, con la revisione nuova al 100 %, e la riga «PWA: https://domhouse-staging.web.app» (non «non pubblicata (SKIP_HOSTING)»).
- **Dopo:** nell'app dello staging **ricarica la pagina** (P-92: una scheda aperta tiene il sito di prima).
- **Ritorno indietro:** `gcloud run services update-traffic domotica-bff-staging --to-revisions=<la revisione di prima>=100 --region=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com`; la revisione di prima la dice l'uscita di `publish.sh` (e la memoria storica la scrive qui prima di Q3.2).

## Q4. I due allarmi nuovi (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
DRY_RUN=1 CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/agent-gcp.sh staging
```

- **Atteso:** i controlli di A1 come allora, e negli allarmi due «esiste già» e due «(prova a secco) … la creerei»: «Agente: allarme dal server dello staging» e «Agente: ordini non letti da oltre 20 minuti (staging)». Poi lo stesso comando **senza** `DRY_RUN=1`: due «creata».
- **Ritorno indietro:** gli allarmi si tolgono dalla console di Monitoring (Avvisi → criteri).

## Q5. «Prova l'agente» con le firme (scrive: un ordine «stato»)

Nell'app dello staging, pagina della piattaforma → «Prova l'agente» su `lab-01`.

- **Atteso:** esito **riuscito**, come in I10 di A1. Ora l'ordine è firmato dal server, verificato dall'esecutore, e il risultato è firmato.
- **«firma non valida»** o «in attesa» oltre un minuto: incolla le ultime righe di `sudo journalctl -u domhouse-agent-lettore -u domhouse-agent-esecutore -n 30 --no-pager`.

## Q6. La migrazione di `lab-01` (scrive sulla VM e nel database dello staging)

**Q6.1 Sulla VM: le impronte di oggi nel file del broker.** Nessuna password letta; il sync non cambia niente.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh devices-from-auth lab-01 | grep -vF "\$7\$"; sudo wc -l /etc/domhouse/_broker/devices/lab-01' < /dev/null
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo cat /etc/domhouse/_broker/devices/lab-01' < /dev/null > impronte-lab-01.txt; wc -l impronte-lab-01.txt
```

- **Atteso:** «== impronte di lab-01 …», poi dal sync **«unchanged»**; lo stesso numero di righe sulla VM e nel file `impronte-lab-01.txt` del PC (uno per dispositivo di `lab-01`). Le impronte non sono password, ma il file si cancella dopo Q6.2.
- **Ritorno indietro:** `sudo rm -f /etc/domhouse/_broker/devices/lab-01 && sudo bash /opt/domhouse/broker-vm.sh sync` (`lab-01` torna al suo segreto vecchio).

**Q6.2 Nell'app: i dispositivi «pronti».** Prima a secco, poi con `--applica`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
.venv/Scripts/python.exe scripts/migra_credenziali.py --progetto domotica-poc-511707 --database staging --appartamento lab-01 --file impronte-lab-01.txt
.venv/Scripts/python.exe scripts/migra_credenziali.py --progetto domotica-poc-511707 --database staging --appartamento lab-01 --file impronte-lab-01.txt --applica && rm -f impronte-lab-01.txt
```

- **Atteso:** «N impronte nel file; N dispositivi da scrivere …», poi «… scritti» con gli stessi nomi.
- **Da verificare:** lo script scrive con le credenziali predefinite del PC (Application Default Credentials). Se risponde «permission denied», incolla: si sceglie con la memoria storica l'account giusto.
- **«credenziali del PC scadute o assenti» o «nessuna risposta da Firestore»** (codice 3; il 20 novembre la prova a secco sembrava bloccata: le credenziali del 19 erano scadute e la libreria riprovava all'infinito):
  1. `gcloud auth application-default login` (Git Bash, nella cartella `app`), con l'account del progetto;
  2. poi rifai la prova a secco.
  - Con `--applica` interrotto: la prova a secco dice cosa manca; rilanciare `--applica` scrive solo quelli (i documenti già scritti restano).
- **Ritorno indietro:** lo stesso comando con `--annulla --applica` al posto di `--file …`: toglie solo i documenti «migrato» (una «Rigenera» o una «Revoca» fatta dall'app toglie il segno «migrato» a quel documento, che quindi resta). **Solo dopo aver tolto il segno di Q6.3** (il suo ritorno indietro): altrimenti il primo `aggiorna_broker` di `lab-01` manderebbe al broker un elenco senza gli Shelly veri (revisione del codice, punto 5).

**Q6.3 Controllo nell'app**, poi il segno che apre `aggiorna_broker` su `lab-01`.

1. Nell'app dello staging, le credenziali di `lab-01` (pagina della piattaforma): i dispositivi di Q6.1, tutti «Pronto».
2. Solo se il punto 1 torna:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo install -d -m 700 /var/lib/domhouse-executor/migrati && sudo touch /var/lib/domhouse-executor/migrati/lab-01 && sudo ls -l /var/lib/domhouse-executor/migrati' < /dev/null
```

- **Atteso:** il file `lab-01` di root. Prima di questo, ogni azione su `lab-01` torna «non applicato» con «Le credenziali di questo appartamento non sono ancora passate all'app».
- **Ritorno indietro:** `sudo rm -f /var/lib/domhouse-executor/migrati/lab-01`.

## Q7. La prova vera: un dispositivo finto registrato e revocato (scrive: due ordini)

**Prima, sola lettura:** il broker della VM è la stessa immagine del banco della misura del 19 novembre (revisione del codice, «da verificare» 2).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker inspect -f "{{.Config.Image}}" domhouse-broker; sudo docker image inspect -f "{{join .RepoDigests \" \"}}" "$(sudo docker inspect -f "{{.Image}}" domhouse-broker)"' < /dev/null
```

- **Atteso:** fra i digest, `eclipse-mosquitto@sha256:75d6662dee52c947dc9dd9c29f1d8d7ffef78ddaf38001caa09755681e8bbc98` (quello di `tests/broker_container_test.py`). **Diverso:** fermati prima del punto 3: la misura non vale per quella versione, e la prova della revoca si fa con un client MQTT vero, preparato con o1.

Nell'app dello staging, credenziali di `lab-01`:

1. «Registra» il codice `prova-a3`: la finestra mostra la password **una volta**; dopo pochi secondi la riga dice «Pronto».
2. Sulla VM, sola lettura: `sudo grep -c "^lab-01.prova-a3:" /etc/domhouse/_broker/auth/devices.passwd` → **1**.
3. «Revoca» `prova-a3` (riscrivendo il codice): dopo pochi secondi «Revocato»; lo stesso `grep` → **0**.
4. Gli Shelly veri di `lab-01` restano collegati: «connessioni sulla porta TLS» come prima in `sudo bash /opt/domhouse/broker-vm.sh status`.

- **Una riga resta «non applicato»:** incolla le righe dell'esecutore (Q5). Una revoca non applicata manda anche la mail «Agente: allarme dal server dello staging».

## Q8. Dopo, con Youssouf (non in questa sessione)

1. «Rigenera» per ciascuno Shelly di `lab-01`, con la password nuova messa nello Shelly (revisione, punto 16): le password di prima sono state in un segreto leggibile.
2. Quando tutti sono «Pronto» con la password nuova: distruzione con ritardo del segreto `langbrain-shelly-lab-01-devices` (comando preparato allora dalla memoria storica).

## Da incollare alla memoria storica

Le uscite di tutti i blocchi, comprese le impronte di Q2.1 e l'esito di Q2.3.
