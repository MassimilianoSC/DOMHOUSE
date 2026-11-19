# E-38 sulla VM: l'indirizzo del broker non va più a nessun altro

| Stato | Preparata | Codice | Chi lancia | Comandi |
|---|---|---|---|---|
| **Pronta, da rileggere.** Nessun passo provato sul vero | o1, 19 novembre 2026 | `63ef157` | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | E0–E5 |

**Il difetto** (19 novembre, P11 del passo 3):

- al riavvio della VM, Docker ha avviato `engine-lab-01` prima del broker;
- gli ha dato `172.30.83.2` sulla rete interna `domhouse-broker-internal`: è l'indirizzo fisso del broker;
- il broker non è partito («Address already in use»): porta 8883 muta, `lab-01` senza dispositivi.

**La correzione** (`63ef157`):

| File | Che cosa |
|---|---|
| `engine/broker/compose.yaml` | la rete interna prende `ip_range: 172.30.83.128/25`: gli indirizzi dinamici (motori, prova oraria dei metadati) solo da `.128` in su. Il `.2` del broker resta fuori dal range |
| `scripts/broker-vm.sh` | `network` (e `install`) rifà la rete interna quando il range è diverso: broker fermo, motori staccati, rete tolta, broker ricreato sul `.2`, motori ricollegati |

`engine-vm.sh` e `mosquitto.conf` non cambiano.

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.**
2. **Se un'uscita non torna, fermati.**
3. E3 ed E5 **mai fra le 22:15 e le 23:15 UTC** (backup notturno alle 22:30, copia del disco alle 23:00).
4. Ogni `gcloud compute ssh` finisce con `< /dev/null`. Un «Segmentation fault» **dopo** l'uscita attesa è innocuo (plink, sul PC): conta il testo.

**Fermo:**

| Passo | Cosa si ferma | Quanto |
|---|---|---|
| E3 | broker e connector di `lab-01` (Plug e Shelly si ricollegano da soli). `dev` no | circa 1 minuto |
| E5 | il riavvio della VM: tutti i motori, anche `dev` (produzione) | 2–4 minuti |

## E0. Sul PC: i file sono quelli di `63ef157` (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git log --oneline -1 63ef157 && git diff --quiet 63ef157 HEAD -- scripts/broker-vm.sh engine/broker/compose.yaml && echo "file uguali a 63ef157"
```

- **Atteso:** la riga del commit, poi «file uguali a 63ef157». Senza la seconda riga, fermati.

## E1. Copia dei due file sulla VM (scrive solo nella cartella di chi si collega)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='mkdir -p ~/e38/broker' < /dev/null
gcloud compute scp scripts/broker-vm.sh langbrain-dev:e38/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp engine/broker/compose.yaml langbrain-dev:e38/broker/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** due file copiati al 100 %.

## E2. Installare i due file (scrive sulla VM; nessun container si riavvia)

Tiene una copia dei file di prima in `/opt/domhouse/prima-e38` (**solo la prima volta**) e toglie i ritorni a capo di Windows.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-e38; if ! sudo test -e $B/broker-compose.yaml; then sudo mkdir -p $B; sudo cp -p /opt/domhouse/broker-vm.sh $B/; sudo cp -p /opt/domhouse/_broker/compose.yaml $B/broker-compose.yaml; echo "copia di prima fatta"; else echo "copia di prima già presente: non la tocco"; fi; cd ~/e38; sed -i "s/\r*$//" broker-vm.sh broker/compose.yaml; sudo install -m 755 broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 broker/compose.yaml /opt/domhouse/_broker/compose.yaml; sha256sum /opt/domhouse/broker-vm.sh /opt/domhouse/_broker/compose.yaml' < /dev/null
```

- **Atteso:** «copia di prima fatta» (o «già presente» a un rilancio), poi due impronte che **cominciano** così:

| File | Impronta, primi 16 caratteri |
|---|---|
| `/opt/domhouse/broker-vm.sh` | `1236e60ff0259d0a` |
| `/opt/domhouse/_broker/compose.yaml` | `9bea49e3e1520000` |

- **Un'impronta diversa:** fermati.
- Il broker gira ancora com'era: la correzione vale da E3.
- **Ritorno indietro:** in fondo, «Ritorno indietro».

## E3. La rete interna con il range (scrive sulla VM; broker e `lab-01` fermi circa 1 minuto)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; sudo bash /opt/domhouse/broker-vm.sh network; sudo docker network inspect -f "{{range .IPAM.Config}}{{.Subnet}} {{.IPRange}}{{end}}" domhouse-broker-internal; sudo docker network inspect -f "{{range .Containers}}{{.Name}} {{.IPv4Address}} {{end}}" domhouse-broker-internal' < /dev/null
```

- **Atteso:**
  1. «rete domhouse-broker_default: già su 172.30.84.0/24»;
  2. «rete domhouse-broker-internal: «172.30.83.0/24» -> «172.30.83.0/24 172.30.83.128/25» (E-38); il broker si ferma un momento»;
  3. «motori sulla rete: engine-lab-01»;
  4. «engine-lab-01: di nuovo sulla rete interna»;
  5. «broker sano: healthy, porta TLS 8883 risponde»;
  6. `172.30.83.0/24 172.30.83.128/25`;
  7. `domhouse-broker 172.30.83.2/24` e `engine-lab-01 172.30.83.N/24` con **N da 128 in su** (l'ordine delle due voci può cambiare).
- **«rimessi com'erano»** (un container di pochi secondi, la prova oraria dei metadati, era sulla rete in quell'istante): **rilancia E3 una volta.**
- **Si ferma in un altro punto:** rilancia E3 una volta, poi E3.1. Se in E3.1 `engine-lab-01` non è sulla rete, ricollegalo e incolla:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker network connect domhouse-broker-internal engine-lab-01; sudo docker network inspect -f "{{range .Containers}}{{.Name}} {{.IPv4Address}} {{end}}" domhouse-broker-internal' < /dev/null
```

- **Da verificare** (nessuna prova possibile sul PC): Docker accetta il `.2` fisso fuori dal range. Se `compose up` lo rifiuta, il broker resta fermo: subito il ritorno indietro, poi `sudo bash /opt/domhouse/broker-vm.sh network`.

**E3.1 Controllo, dopo un minuto (sola lettura).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker network inspect -f "{{range .Containers}}{{.Name}} {{.IPv4Address}} {{end}}" domhouse-broker-internal; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "scartati|connessioni|^broker"; for p in 8100 8169; do curl -s -m 5 http://10.198.0.2:$p/api/v1/health | python3 -c "import json,sys; h=json.load(sys.stdin); print(h[\"apartment_id\"], h[\"status\"], h[\"connector\"][\"status\"])"; done; true' < /dev/null
```

- **Atteso:**
  1. broker sul `.2`, `engine-lab-01` da `.128` in su;
  2. «connessioni sulla porta TLS: N» con **N ≥ 1** (se 0, aspetta un altro minuto e rilancia);
  3. «broker ok cert_days=…»;
  4. `dev ok … up` e `lab-01 ok … up`.
- Nell'app di staging, `lab-01`: i dispositivi in linea.

## E4. Prova: un container nuovo prende un indirizzo da `.128` in su (sola lettura; un container di pochi secondi)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='IMG=$(sudo docker inspect -f "{{.Config.Image}}" engine-lab-01); sudo docker run --rm --network domhouse-broker-internal --entrypoint python "$IMG" -c "import socket; print(socket.gethostbyname(socket.gethostname()))"' < /dev/null
```

- **Atteso:** una riga `172.30.83.N` con **N da 128 in su**. Il container si toglie da solo.

## E5. La prova vera: il riavvio della VM (scrive sulla VM; tutti i motori fermi 2–4 minuti)

Solo con il via del committente: ferma anche `dev`, cioè la produzione.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemctl reboot' < /dev/null
```

- **Atteso:** il collegamento si chiude, a volte con un errore di gcloud: è normale. **Aspetta 3 minuti.**

**E5.1 Dopo il riavvio (sola lettura).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='uptime; sudo docker ps --format "{{.Names}} {{.Status}}"; sudo docker network inspect -f "{{range .Containers}}{{.Name}} {{.IPv4Address}} {{end}}" domhouse-broker-internal; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "connessioni|^broker"; for p in 8100 8169; do curl -s -m 5 http://10.198.0.2:$p/api/v1/health | python3 -c "import json,sys; h=json.load(sys.stdin); print(h[\"apartment_id\"], h[\"status\"], h[\"connector\"][\"status\"])"; done; true' < /dev/null
```

- **Atteso:**
  1. `uptime` di pochi minuti;
  2. `domhouse-broker Up …` (non «Exited»), i due motori `Up`;
  3. broker sul `.2`, `engine-lab-01` da `.128` in su, **qualunque sia stato l'ordine di partenza**;
  4. «broker ok …» e «connessioni sulla porta TLS: N» con N ≥ 1 (se 0, un altro minuto);
  5. `dev ok … up` e `lab-01 ok … up`.
- **Broker «Exited»:** incolla anche `sudo docker logs --tail 20 domhouse-broker`. Il ripristino di oggi (stop di `lab-01`, start del broker, start di `lab-01`) si prepara con la memoria storica.

## Ritorno indietro

Rimette i due file di prima. La rete interna **resta con il range**: limita solo gli indirizzi dinamici e non dà fastidio al broker di prima.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-e38; sudo install -m 755 $B/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 $B/broker-compose.yaml /opt/domhouse/_broker/compose.yaml; sudo docker inspect domhouse-broker > /dev/null 2>&1 || sudo docker compose --env-file /opt/domhouse/_broker/broker.settings -f /opt/domhouse/_broker/compose.yaml up -d; sudo docker ps --format "{{.Names}} {{.Status}}"' < /dev/null
```

- **Atteso:** i container `Up`, con il broker.
- **Da verificare:** il compose di prima non dice il range. Se `compose up` segnala che la rete esistente è diversa da quella attesa, incolla l'uscita: si decide con la memoria storica.

## Da incollare alla memoria storica

Le uscite di tutti i blocchi. Al registro: E-38 chiuso quando E5.1 torna come atteso.
