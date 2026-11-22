# Sicurezza in appartamento: analisi dei rischi

*Memoria storica, 22 novembre 2026 (risposta 1223 = a, voce 52 di `cose-da-fare.md`). Documento interno. Domanda: un
ospite, dentro l'appartamento e sulla stessa rete Wi-Fi, che cosa può fare ai dispositivi, per curiosità o per
dispetto? Dopo questa analisi, la prova al banco con Youssouf (sezione 4) dice che cosa passa davvero. Quello che
passa diventa un difetto da correggere (D-198) o una regola della guida del kit (voce 23).*

## 1. Da dove può agire l'ospite

| N. | Strada | Esempio |
|---|---|---|
| 1 | **Rete Wi-Fi dell'appartamento** | apre nel browser la pagina di uno Shelly, manda un comando diretto, cambia le impostazioni |
| 2 | **Bluetooth** | finge un sensore: una finestra «chiusa» quando è aperta, una temperatura falsa |
| 3 | **Con le mani** | stacca una presa o il ponte, preme il tasto di uno Shelly, lo riporta alle impostazioni di fabbrica, sposta un sensore |
| 4 | **Internet** | niente di diverso da chiunque altro: è l'«attacco da fuori», già esaminato il 22 novembre |

## 2. Rischi e difese di oggi

| N. | Rischio | Danno possibile | Difesa di oggi | Stato |
|---|---|---|---|---|
| 1 | Aprire la pagina dello Shelly dalla rete Wi-Fi | cambiare server, Wi-Fi, comportamento dopo un blackout; comandare i relè | **password della pagina locale** attiva sui tre Shelly del banco (19 novembre); nella guida del kit diventa un passo obbligatorio | da provare al banco (prova 1) |
| 2 | Mandare comandi diretti allo Shelly (chiamate RPC sulla rete locale) | accendere o spegnere caldaia e prese saltando l'app | la stessa password protegge anche le chiamate dirette | da provare (prova 2) |
| 3 | Usare Matter o le chiamate Bluetooth dello Shelly | comandarlo da un'app di casa | **Matter e chiamate Bluetooth spenti** sui tre del banco | da provare (prova 3) |
| 4 | Scoprire quali dispositivi ci sono (nomi sulla rete) | sapere che c'è uno Shelly e dove | nessuna; il danno è solo un'informazione | accettato, da scrivere in `limiti-noti.md` se la prova lo conferma |
| 5 | Fingere un sensore Bluetooth | finestra finta chiusa → caldaia accesa con la finestra aperta; temperatura falsa → riscaldamento sbagliato | **nessuna oggi:** la cifratura dei sensori è decisa solo se automatica (documento 1, passo 8) | **rischio aperto**, da provare (prova 4) |
| 6 | Staccare una presa o il ponte | dispositivi o sensori offline | avviso «Dispositivo offline» dopo 15 minuti; antigelo del motore | coperto; da misurare il tempo (prova 5) |
| 7 | Riportare uno Shelly alle impostazioni di fabbrica | lo Shelly perde il collegamento; relè fermo | avviso offline; l'accesso al server richiede la password del dispositivo, che non si legge dallo Shelly | coperto; da provare (prova 6) |
| 8 | Premere il tasto di uno Shelly | accendere o spegnere a mano | il motore vede il cambio e riprende il comando con le regole | da provare (prova 7) |
| 9 | Usare la password di un dispositivo per fingere un altro dispositivo | dati falsi a nome di un altro | ogni dispositivo scrive solo sul suo canale (`996e530`); la password non si legge dalla pagina dello Shelly (`MQTT.GetConfig` non la mostra) | da verificare che sia attivo sulla VM (voce 33) |
| 10 | Cambiare nello Shelly il server a cui si collega | il dispositivo smette di parlare con noi | richiede la password della pagina locale (rischio 1); poi avviso offline | coperto dalla 1 |

## 3. Che cosa riduce di più il rischio

1. **Una rete Wi-Fi solo per i dispositivi**, separata da quella degli ospiti (domanda 19.6 al cliente): toglie quasi
   del tutto i rischi 1, 2, 4 e 10.
2. **La password della pagina locale su ogni Shelly**, sempre (guida del kit, voce 23); con lo strumento A diventa
   generata e conservata dall'app (documento 2, riga 27).
3. **Il rischio 5 (sensore finto)** è il più serio, perché può portare alla caldaia accesa con la finestra aperta:
   dopo la prova, decidere se attivare la cifratura dei sensori Bluetooth anche se non automatica, oppure scrivere il
   limite e una regola prudente nel motore.

## 4. Prova al banco con Youssouf (da un portatile sul Wi-Fi del banco)

| N. | Prova | Va bene se |
|---|---|---|
| 1 | Aprire nel browser l'indirizzo di ogni Shelly | chiede la password; senza password non si vede niente |
| 2 | Mandare una chiamata diretta senza password (stato, accensione di un relè) | risposta «non autorizzato», relè fermo |
| 3 | Cercare lo Shelly con un'app Matter e via Bluetooth | non risponde |
| 4 | Trasmettere da un telefono un messaggio Bluetooth che imita un sensore della finestra | **il motore non lo accetta**; se lo accetta, rischio 5 confermato |
| 5 | Staccare la presa che fa da ponte | i sensori risultano offline e l'avviso arriva dopo i minuti previsti |
| 6 | Riportare uno Shelly alle impostazioni di fabbrica | avviso offline; dopo, il dispositivo non si ricollega da solo con i nostri dati |
| 7 | Premere il tasto di uno Shelly mentre una regola lo vuole spento | il motore lo vede e lo riporta allo stato della regola (o lo registra come comando a mano) |
| 8 | Con le credenziali di un dispositivo, scrivere sul canale di un altro | il broker rifiuta |

**Esito della prova:** si scrive in questo file, sezione 5, e in `cose-da-fare.md`; ogni «non va bene» è un difetto
(D-198) o una regola della guida del kit.

## 5. Esito della prova

*Da scrivere dopo la prova al banco.*
