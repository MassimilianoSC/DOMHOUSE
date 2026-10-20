# Suite di conformità al contratto

Verifica che un'istanza implementi `contract/openapi.yaml` (1.0.4). Due livelli:

1. **Forma** — Schemathesis genera richieste da ogni operazione del contratto e controlla che
   le risposte rispettino schemi e codici dichiarati.
2. **Comportamento** — `test_scenari.py`: i 16 scenari `C01–C16` di `x-conformita`, uno per test.

Uno scenario che richiede una feature assente da `GET /version.features` viene **saltato**,
non fallisce: la suite si esegue dalla settimana 1 con `features: []`. Gli stati simulati
(offline, finestra aperta, approvazione) si creano con `POST /_test/state`; se l'istanza non è
in modalità simulata, lo scenario viene saltato.

## Installazione

```bash
pip install -r contract/conformance/requirements.txt
```

## Contro un'istanza reale

```bash
# comportamento
pytest contract/conformance --base-url http://10.0.0.10:8101/api/v1 --api-key "$LB_API_KEY"

# forma (solo le operazioni attive; quelle a 501 sono comunque dichiarate)
schemathesis run contract/openapi.yaml --base-url http://10.0.0.10:8101/api/v1 \
  -H "X-API-Key: $LB_API_KEY" -H "X-Actor: conformance@hqe.it" \
  -H "X-Correlation-Id: 2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10" --checks all

# C14 parte 503: istanza avviata con DOMOTICA_TEST_CONNECTOR_DOWN=1
pytest contract/conformance -m connector_down --base-url http://10.0.0.10:8101/api/v1 --api-key "$LB_API_KEY"
```

## Contro il mock Prism (verifica della suite stessa)

```bash
npx @stoplight/prism-cli mock contract/openapi.yaml -p 4010
pytest contract/conformance --base-url http://127.0.0.1:4010 --mock
```

Il mock non ha stato: gli scenari che lo richiedono vengono saltati con il motivo. Gli altri
verificano che la suite mandi richieste conformi e legga risposte conformi.

## Nel CI del nodo domotica

A ogni push: avvio dell'istanza di sviluppo con `DOMOTICA_SIMULATED=1`, esecuzione della suite,
una feature entra in `features` solo quando i suoi scenari passano. Un fallimento che dura più
di due giorni si discute lo stesso giorno (nota di consegna, §5).

| Tappa | Scenari |
| --- | --- |
| Scheletro (sett. 1) | C13, C14, C15 |
| M1 (sett. 2) | C01, C02, C03, C07 |
| M2 (sett. 3) | C04, C05, C06, C10, C11 |
| M3 (sett. 4) | C08, C09 |
| M4 (sett. 5) | C12, C16 |

## Due regole del contratto che la suite rispetta (e che l'istanza deve rispettare)

- **Stream senza `Last-Event-ID` = solo eventi nuovi.** Per vedere ciò che un'azione ha prodotto, la suite legge prima il
  cursore (`client.cursore()`, cioè l'ultimo `id` rigiocando il buffer con `Last-Event-ID: 0`) e poi si ricollega con
  `Last-Event-ID = cursore`. Un'istanza che non rigioca il buffer con `Last-Event-ID` fa fallire C01, C07, C10 e C12.
- **Una sola approvazione pendente per istanza** (contratto 1.0.1): un nuovo trigger con un'approvazione già pendente va
  in coda senza evento. C12 chiude prima le approvazioni pendenti lasciate da esecuzioni precedenti, ripetendo finché la
  coda è vuota, poi provoca la propria.

## Contro il mock integrato nel BFF (quello usato dall'app)

```bash
INSTANCE_API_KEY_FALLBACK=test-key DOMOTICA_SIMULATED=1 python -m bff.mock_instance --port 8100
pytest contract/conformance --base-url http://127.0.0.1:8100/dev/api/v1 --api-key test-key
# C14 (connector fermo): riavviare il mock con DOMOTICA_TEST_CONNECTOR_DOWN=1 e aggiungere -m connector_down
```

Esito atteso: 16 passati (+1 con `-m connector_down`). È lo stesso comando della CI (`.github/workflows/conformita.yml`):
se il mock smette di rispettare il contratto, l'app sta usando qualcosa che il motore reale non avrà.
