# Monitoraggio del BFF (P-4)

Un controllo di disponibilità chiama `/health` del BFF ogni minuto da 3 regioni; se fallisce da almeno 2 regioni per
5 minuti, la policy `alert-policy.json` manda un'email. Quando il BFF torna su arriva l'email di chiusura.

`alert-policy.json` è un modello: `__CHECK_ID__` e `__CHANNEL__` si sostituiscono al momento con i valori creati dai
comandi qui sotto (nessun valore reale nel repository). I comandi si lanciano da Git Bash, nella cartella `app`, con
`P` = progetto e `HOST` = indirizzo del BFF senza `https://` (vedi `CLAUDE.md`).

**Perché `/health` e non `/healthz`**: Cloud Run riserva i percorsi che finiscono in «z» e da fuori risponde 404
da solo, senza arrivare al BFF ([known issues, «Reserved URL paths»](https://cloud.google.com/run/docs/known-issues#reserved-url-paths));
`/healthz` serve solo alle sonde interne di Cloud Run. Il controllo va provato da fuori prima di fidarsene (E-12):
`setup.sh` lo fa da solo. Il nome del controllo resta `domotica-bff-healthz` per continuità.

**Attenzione, Git Bash**: un argomento come `--path=/health` viene convertito in un percorso Windows
(`/C:/Program Files/Git/health`) e il controllo chiamerebbe una pagina inesistente, cioè un falso allarme continuo.
Per questo i comandi con `--path=` cominciano con `MSYS2_ARG_CONV_EXCL='--path='`, che esclude solo quell'argomento
dalla conversione (`MSYS_NO_PATHCONV=1` invece rompe lo script `gcloud` stesso). Dopo la creazione, verificare che la
colonna PATH di `gcloud monitoring uptime list-configs --project="$P" --format="table(displayName,httpCheck.path)"`
mostri `/health`.

## Scritture non riuscite (P-57)

Alcune scritture del BFF sono «al meglio»: se non riescono, l'azione dell'utente resta valida e il BFF scrive solo un
avviso nel log. Sono la voce del registro delle azioni, i passi della cancellazione di un account (GDPR), l'accesso di
assistenza salvato dopo la sua voce, la voce di scadenza di un accesso e il controllo del limite sulle email di invito.
Da D-99 la stessa regola avvisa anche se in produzione un appartamento dimostrativo ha un codice Italianway (il webhook
ne rifiuta le prenotazioni e il BFF lo scrive a ogni avvio): il codice va tolto dalla piattaforma.
La regola `log-alert-policy.json` («BFF: scrittura non riuscita») manda un'email quando nei log del servizio
`domotica-bff` compare uno dei messaggi di `log-alert-messages.txt` (uno per riga; una prova controlla che il BFF li
scriva davvero). Al massimo un'email all'ora; l'avviso si chiude da solo dopo un giorno. `setup.sh` la crea, e se la
lista dei messaggi cambia la aggiorna. Dove guardare: Cloud Run > domotica-bff > Log, cercare il messaggio dell'avviso
e il campo `error`.

## Con un solo comando (consigliato)

```bash
GCP_PROJECT_ID=<progetto> EMAIL=<destinatario> scripts/monitoring/setup.sh            # crea o ripara
DRY_RUN=1 GCP_PROJECT_ID=<progetto> EMAIL=<destinatario> scripts/monitoring/setup.sh  # legge soltanto
```

Crea solo ciò che manca, corregge un percorso sbagliato e alla fine rilegge percorso del controllo, controllo guardato
dalla regola e destinatario: se qualcosa non torna si ferma con «FERMO». I comandi qui sotto fanno le stesse cose a mano.

## Creazione a mano (una volta)

```bash
P=<progetto>; HOST=<host del BFF>; EMAIL=<destinatario>

# 1. Canale email
gcloud beta monitoring channels create --project="$P" --type=email \
  --display-name="Avvisi BFF ($EMAIL)" --channel-labels=email_address="$EMAIL"

# 2. Controllo di disponibilità: /health deve rispondere 2xx con "status":"ok" (provarlo prima da fuori)
MSYS2_ARG_CONV_EXCL='--path=' gcloud monitoring uptime create domotica-bff-healthz --project="$P" \
  --resource-type=uptime-url --resource-labels=host="$HOST",project_id="$P" \
  --protocol=https --path=/health --period=1 --timeout=10 \
  --regions=europe,usa-oregon,asia-pacific \
  --matcher-content='"status":"ok"' --matcher-type=contains-string

# 3. Policy di avviso collegata al canale
CHECK_ID=$(gcloud monitoring uptime list-configs --project="$P" --filter='displayName="domotica-bff-healthz"' --format='value(name.basename())')
CHANNEL=$(gcloud beta monitoring channels list --project="$P" --filter="labels.email_address=\"$EMAIL\"" --format='value(name)' | head -1)
sed -e "s|__CHECK_ID__|$CHECK_ID|" -e "s|__CHANNEL__|$CHANNEL|" scripts/monitoring/alert-policy.json > /tmp/alert-policy.json
gcloud alpha monitoring policies create --project="$P" --policy-from-file=/tmp/alert-policy.json
```

## Prova dell'email senza fermare il server

Un secondo controllo, temporaneo, chiama un percorso che non esiste (`/health-prova-allarme` risponde 404 dal BFF), con una
copia della policy. Il BFF vero non viene toccato.

```bash
MSYS2_ARG_CONV_EXCL='--path=' gcloud monitoring uptime create prova-allarme --project="$P" \
  --resource-type=uptime-url --resource-labels=host="$HOST",project_id="$P" \
  --protocol=https --path=/health-prova-allarme --period=1 --timeout=10 \
  --regions=europe,usa-oregon,asia-pacific
TEST_ID=$(gcloud monitoring uptime list-configs --project="$P" --filter='displayName="prova-allarme"' --format='value(name.basename())')
sed -e "s|__CHECK_ID__|$TEST_ID|" -e "s|__CHANNEL__|$CHANNEL|" \
    -e 's|"displayName": "BFF non raggiungibile"|"displayName": "PROVA allarme (da cancellare)"|' \
    scripts/monitoring/alert-policy.json > /tmp/prova-allarme.json
gcloud alpha monitoring policies create --project="$P" --policy-from-file=/tmp/prova-allarme.json
# Entro 7-10 minuti arriva l'email "PROVA allarme (da cancellare)". Poi si cancella tutto:
gcloud alpha monitoring policies delete --project="$P" "$(gcloud alpha monitoring policies list --project="$P" --filter='displayName="PROVA allarme (da cancellare)"' --format='value(name)')"
gcloud monitoring uptime delete --project="$P" "$TEST_ID"
```
