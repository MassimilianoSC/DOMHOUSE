# Prove a mano in staging dopo la pubblicazione del 13 novembre

**Per chi:** il committente, guidato in chat dalla memoria storica, un passo alla volta.
**Dove:** il sito di staging, su un **appartamento dimostrativo** con il Simulatore. Nessun dispositivo vero (D-134).
**Quando:** dopo la pubblicazione del lotto del 13 novembre.
**Fonte dei testi:** o2, lettura del codice su `1996198`. I testi segnati «da verificare a schermo» non sono ancora
stati visti.

> **Da sapere prima di cominciare**
>
> - **In staging un minuto è un minuto vero.**
> - **I dispositivi del dimostrativo:** «Climatizzatore soggiorno» (16–30 °C), «Caldaia» (7–23 °C), «Finestra
>   camera», «Sensore soggiorno», «Presa stufetta camera», «Misuratore clima».
> - **Prima di ogni prova:** Simulatore → «Ripristina lo stato iniziale» → «Ripristina…» → «Ripristina».
> - **Usa il dimostrativo occupato:** in quello «vuoto» clima e caldaia sono spenti.
> - **Le regole cambiate si perdono** quando lo staging si spegne per inattività: va bene per provare.

## Prova 1 — Configurare un appartamento con le Regole

1. Apri l'appartamento → menu → **«Regole»**.
2. Controlla che ci siano **otto schede**, in quest'ordine, con questi valori iniziali:

| N. | Regola | Campi (limiti) e valore iniziale |
|---|---|---|
| 1 | «Finestra aperta spegne il clima» | Minuti 1–30: **5** |
| 2 | «Limiti del setpoint», gruppo «Inverno (riscaldamento)» | Minimo 7–20: **16**; Massimo 20–28: **24**; Temperatura in eco 10–22: **18**; Temperatura in comfort 16–26: **21** |
| 2 | «Limiti del setpoint», gruppo «Estate (raffrescamento)» | Minimo 16–28: **18**; Massimo 22–30: **28**; Raffrescamento in comfort 22–28: **25** |
| 3 | «Antigelo a casa vuota» | Temperatura 5–12: **8** |
| 4 | «Antimuffa a casa vuota» | Umidità 50–80: **65** |
| 5 | «Pre-arrivo» | Ore prima del check-in 0–6: **2** |
| 6 | «Risparmio al check-out» | Minuti dopo il check-out 0–180: **30**; Minuti di presenza 5–180: **30** |
| 7 | «Pausa minima del compressore» | «Non modificabile», **3** minuti |
| 8 | «Avviso dispositivo offline» | Minuti 5–120: **15** |

3. Leggi la descrizione di «Limiti del setpoint». Deve cominciare con «Limita la temperatura che si può impostare
   dall'app e dall'assistente…» e dire «non vale per il telecomando del climatizzatore né per l'antigelo».
4. Leggi la descrizione di «Avviso dispositivo offline». Deve dire «L'avviso «sistema domotico non raggiungibile» non
   dipende da questa regola: arriva sempre dopo 15 minuti.»
5. **Prova un errore:** in Inverno metti **Massimo = 20**.
   - **Atteso:** in rosso «La temperatura comfort non può superare il massimo invernale»; «Salva le modifiche»
     disattivato.
6. Rimetti **Massimo = 24**: l'errore sparisce.
7. **Prova un salvataggio:** in «Finestra aperta spegne il clima» metti **Minuti = 1** (serve per la prova 3).
   - **Atteso:** in basso la barra «1 regola modificata» con «Annulla le modifiche» e «Salva le modifiche».
8. Premi **«Salva le modifiche»**.
   - **Atteso:** «Regole aggiornate».

**Altri errori, se vuoi provarli** (poi riporta i valori iniziali):

| Cosa scrivi | Messaggio atteso |
|---|---|
| Inverno Minimo 19 | «La temperatura eco non può essere sotto il minimo invernale» |
| Eco 22 | «La temperatura eco non può superare quella comfort» |
| Estate Minimo 24 e Massimo 23 | «Il minimo estivo non può superare il massimo estivo» |
| Estate Minimo 26 | «La temperatura di raffrescamento deve stare fra il minimo e il massimo estivi» |
| Comfort 25 e Inverno Massimo 26 | «La temperatura di raffrescamento deve essere più alta di quella comfort» |

## Prova 2 — Il climatizzatore in Panoramica

1. Panoramica → scheda **«Climatizzatore soggiorno»**, riga «Temperatura», sotto c'è «da … a … °C».
2. Cambia **«Modo»** e controlla l'intervallo. Il cambio parte subito come comando; l'intervallo nuovo compare in
   pochi secondi (intanto lo stepper è disattivato).

| Modo | Atteso |
|---|---|
| caldo | «da 16 a 24 °C» |
| freddo | «da 18 a 28 °C» |
| deumidifica | «da 18 a 28 °C» |
| ventilazione | «da 16 a 30 °C» (solo i limiti del dispositivo) |

3. **Riportato dentro:** in «caldo» premi «−» fino a **16**, poi Modo → **freddo**.
   - **Atteso:** la temperatura diventa **18**. Nelle Decisioni, nel comando, la nota «setpoint 16 °C riportato a
     18 °C (limiti 18–28)» (da verificare a schermo).
4. **Caldaia:** l'intervallo è «da 16 a 23 °C», perché la caldaia del dimostrativo arriva al massimo a 23.

## Prova 3 — Finestra aperta e forzatura

Serve la regola della finestra a **1 minuto** (prova 1, passo 7).

1. Simulatore → sezione «Finestre» → interruttore **«Finestra camera · chiusa»**.
   - **Atteso:** «Finestra aperta»; la riga diventa «· aperta».
2. Aspetta **1 minuto**.
   - **Atteso nelle Decisioni:** «Spegnimento» per climatizzatore e caldaia, attore la regola «Finestra aperta spegne
     il clima».
3. Panoramica → **«Forza per…» → «30 min»**.
   - **Atteso:** la finestra «Finestra aperta» con «Finestra aperta in Camera: durante la forzatura la finestra non
     spegne clima e caldaia; se li aveva già spenti, ripartono quando la forzatura finisce e la finestra è chiusa.»
4. Premi **«Forza comunque»**.
   - **Atteso:** «Forzatura … attiva fino alle …»; nelle Decisioni «Forzatura».
5. Simulatore → **chiudi** «Finestra camera».
   - **Atteso:** clima e caldaia **restano spenti**: vince la forzatura.
6. Panoramica → **«Annulla forzatura»**.
   - **Atteso:** nelle Decisioni «Forzatura annullata».
7. Aspetta **circa un minuto**.
   - **Atteso:** nelle Decisioni «Finestra chiusa: riacceso»; clima e caldaia di nuovo accesi.
   - **Questa è la riparazione di oggi:** prima restavano spenti fino al cambio di modalità successivo.

## Prova 4 — Un'azione «casa vuota» fissata a mano con ospiti in casa

1. Simulatore → **«Evento prenotazione»**:
   - Tipo evento «Prenotazione creata»;
   - ID prenotazione **PROVA-S10**;
   - Check-in: **oggi, un'ora fa**; Check-out: **domani**; Ospiti **2**;
   - «Invia evento».
   - **Atteso:** «Evento prenotazione inoltrato».
2. Programmazione → **«Nuova azione»**:
   - Quando: **fra 3 minuti**;
   - Cosa fare: «Cambia modalità»; Modalità: **«casa vuota»**;
   - «Salva».
   - **Atteso:** «Azione programmata».
3. Aspetta l'ora scelta.
   - **Atteso:** la modalità **non** cambia.
4. Apri **Approvazioni → «In attesa»**.
   - **Atteso:** «Passare alla modalità casa vuota con ospiti in casa», con il motivo «Azione programmata a mano per
     le … del …: alla sua ora c'è una prenotazione in corso, gli ospiti potrebbero essere in casa» e «Alla scadenza
     verrà respinta».
5. Premi **«Respingi»**.
   - **Atteso:** la casa resta com'è.

## Prova 5 — Disattivare e riattivare un appartamento

1. Amministrazione → scheda **«Appartamenti»** → riga del dimostrativo → interruttore **«Attivo»**, spegnilo.
   - **Atteso:** la finestra del browser «Disattivare «…»? Gli automatismi continuano; notifiche, riepiloghi,
     prenotazioni ed export Excel si fermano finché non lo riattivi.»
2. Premi **«Annulla»**: non cambia niente.
3. Rifai il passo 1 e premi **«OK»**.
   - **Atteso:** «Appartamento salvato», etichetta «disattivato».
4. **Riaccendi** l'interruttore.
   - **Atteso:** nessuna domanda, «Appartamento salvato».

## Prova 6 — Chi ha sola lettura (facoltativa)

Serve un utente di prova con ruolo «Sola lettura».

1. Amministrazione → «Utenti» → **«Invita un utente»**:
   - un'email che leggi tu, per esempio un alias della tua Gmail con «+sola» prima della «@»;
   - Ruolo **«Sola lettura»**; appartamenti visibili: i dimostrativi;
   - «Invita».
2. Entra con quell'utente, in una **finestra anonima**.
3. Apri Impostazioni → riquadro «Notifiche».
   - **Atteso:** **manca** «Approvazioni richieste»; ci sono «Dispositivi e sistema domotico offline», «Prenotazioni»
     e «Riepilogo».

## Cosa non si può provare in staging

| Cosa | Perché | Dove si prova |
|---|---|---|
| L'avviso giallo «“Limiti del setpoint” da correggere» | Compare solo con regole salvate incoerenti prima del 13 novembre | Coperto dalle prove automatiche |
| Il climatizzatore spento col telecomando | Serve uno split vero con il suo misuratore | Tappa B e pilota |
| «Sistema domotico non raggiungibile» dopo 15 minuti | Il Simulatore non ferma il motore | Coperto dalle prove automatiche |
| Le notifiche sul telefono | In staging possono non essere attive | Pilota |
