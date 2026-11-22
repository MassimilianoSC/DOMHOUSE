# Misure del lungo periodo con dispositivi veri

*Memoria storica, 22 novembre 2026 (risposta 1226 = a, voce 55 di `cose-da-fare.md`). Elenco di che cosa si misura
nel tempo, con la soglia «va bene / non va bene». Si misura prima su `lab-01` (con gli Shelly sempre accesi, da
chiedere a Youssouf) per avere i valori normali, poi nel mese di prove del primo appartamento. Le misure entrano nel
resoconto del lunedì. **Le soglie sono proposte da tarare con i primi dati**: dopo due settimane su `lab-01` si
correggono e si scrive qui il valore deciso.*

## 1. Dispositivi

| N. | Misura | Da dove | Va bene (proposta) | Non va bene |
|---|---|---|---|---|
| 1 | **Scollegamenti** per dispositivo al giorno | `last_seen` e decisioni «Dispositivo offline» del motore | al massimo 1 al giorno, e nessuno oltre i 15 minuti dell'avviso | più di 3 al giorno, o uno oltre 15 minuti senza un motivo noto (corrente staccata) |
| 2 | **Tempo di ritorno** dopo uno scollegamento | `last_seen` prima e dopo | entro 2 minuti | oltre 10 minuti |
| 3 | **Ritorno dopo un'interruzione di corrente** (prova a mano una volta a settimana su `lab-01`) | Panoramica, Stato dei dispositivi | tutti in linea entro 5 minuti, relè «come prima» | uno che non torna da solo |
| 4 | **Batteria dei sensori** Bluetooth | `battery_percent` | calo regolare; durata stimata dalla pendenza almeno 12 mesi | calo più veloce di 10 punti al mese, o salti |
| 5 | **Orologio del ponte** rispetto all'ora del server | messaggi del ponte (prova al banco 3) | scarto sotto 1 minuto | scarto oltre 5 minuti (limite R1 di `limiti-noti.md`) |
| 6 | **Forza del segnale** (`rssi`) di Shelly e sensori | quando il campo sarà nel contratto (strumento B) | stabile, sopra la soglia del collaudo | cali sotto la soglia |
| 7 | **Firmware**: resta quello fissato | Stato dei dispositivi, censimento di Youssouf | tutti alla versione fissata (oggi 2.2.0) | un aggiornamento non voluto |

## 2. Comandi e regole

| N. | Misura | Da dove | Va bene (proposta) | Non va bene |
|---|---|---|---|---|
| 8 | **Comandi falliti** o scaduti | esiti dei comandi nel motore («Il dispositivo non ha risposto») | sotto l'1 % dei comandi | oltre il 5 %, o due di fila sullo stesso dispositivo |
| 9 | **Avvisi falsi**: avvisi che a controllo risultano senza motivo | Decisioni, notifiche, controllo a mano | nessuno nella settimana | più di uno nella settimana |
| 10 | **Regole che non scattano** quando dovrebbero (prova a mano: finestra aperta, check-out simulato) | Decisioni | scattano tutte | una che non scatta |

## 3. Motore, VM e server

| N. | Misura | Da dove | Va bene (proposta) | Non va bene |
|---|---|---|---|---|
| 11 | **Memoria del motore** | `docker stats` sulla VM, allarmi di A7 | stabile settimana su settimana | crescita continua oltre il 10 % a settimana |
| 12 | **Dimensione dei dati del motore** (`engine.db`) | VM, sola lettura | crescita costante e prevedibile | sopra 500 MB (allarme del passo 2) o crescita che accelera |
| 13 | **Riavvii del motore** | registro della VM, resoconto del lunedì | nessuno non voluto | uno non voluto |
| 14 | **Memoria e disco della VM** | metriche di Google Cloud, allarmi di A7 | memoria libera sopra 500 MB, disco sotto il 70 % | allarme di A7 o disco oltre l'80 % |
| 15 | **Errori del server** (5xx) e rifiuti per troppe richieste (429) | log di Cloud Run | nessun 5xx senza motivo noto | 5xx ripetuti |
| 16 | **Accessi rifiutati** dei dispositivi | pagina «Accessi rifiutati» (A5) | nessuno, salvo prove volute | tentativi da un dispositivo che dovrebbe funzionare |

## 4. Come si legge

1. **Ogni lunedì** il resoconto riporta le 16 misure della settimana, confrontate con la settimana prima.
2. **Una misura «non va bene»** si guarda subito: se è un difetto si corregge (D-198), se è un limite si scrive in
   `limiti-noti.md`.
3. **Dopo due settimane su `lab-01`** le soglie si correggono con i valori veri.
4. **A fine mese di prove** l'esito entra nella guida, parte 1 («Come è stato controllato DOMHOUSE»), e nel manuale di
   manutenzione (voce 51).
