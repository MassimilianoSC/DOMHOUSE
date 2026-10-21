# Checklist di collaudo — DOMHOUSE

Per i collaboratori che collaudano l'app. Si usa insieme a `docs/guida-utente.md`.
*Versione del 16 ottobre 2026, ambiente di prova: https://domotica-poc-511707.web.app*

## Come si usa
- Ogni riga è una prova: segui i passi e confronta con il risultato atteso.
- In «Esito» scrivi **OK** oppure **KO**. Per ogni KO compila una segnalazione come spiegato nella guida, sezione 8.
- Servono tre account invitati da un amministratore: uno **Amministratore**, uno **Operatore**, uno **Sola lettura**.
- Dispositivi da provare (criterio del committente): **Chrome su Android**, **Safari su iPhone**, **Chrome o Edge su
  computer**. Le prove segnate 📱 vanno ripetute su tutti e tre.
- Gli appartamenti sono simulati e ripartono da zero a ogni aggiornamento dell'app: è normale.

---

## A. Accesso e account

| N. | Ruolo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| A1 📱 | Amministratore | Invita un tuo indirizzo nuovo da Amministrazione > Utenti. | Avviso «Invito inviato a …»; l'email arriva (controlla anche lo spam) con «Apri l'app». | |
| A2 📱 | Invitato | Dall'email, se l'indirizzo è Google, «Accedi con Google». | Entri nell'app. In Amministrazione > Utenti l'etichetta «in attesa del primo accesso» sparisce. | |
| A3 | Invitato senza Google | Dall'email usa «Scegli la password», poi accedi con email e password. | Entri nell'app. | |
| A4 | Qualsiasi | Accedi con una password sbagliata. | «Accesso non riuscito: controlla email e password». | |
| A5 | Account non invitato | Accedi con Google con un account mai invitato. | Una sola riga: «Non hai i permessi per accedere. Chiedi un invito.»; resti sulla pagina di accesso. | |
| A6 | Qualsiasi | «Password dimenticata?» con la tua email, poi con un'email inesistente. | In entrambi i casi lo stesso messaggio di conferma; l'email arriva solo all'indirizzo vero, in italiano. | |
| A7 | Utente con password | Impostazioni > Cambia password con password attuale sbagliata, poi giusta. | Prima «Password attuale non corretta», poi «Password cambiata». | |
| A8 | Utente con password | Impostazioni > Cambia email verso un altro tuo indirizzo. | «Link inviato a …»; il cambio avviene solo dopo aver aperto il link. | |
| A9 | Utente Google | Apri Impostazioni. | Al posto di password ed email: «…si gestiscono dal tuo account Google». | |
| A10 | Qualsiasi | Cambia il nome visualizzato e salva. | «Nome aggiornato»; il nome nuovo compare in Amministrazione > Utenti. | |
| A11 | Qualsiasi, su due dispositivi | Entra su due dispositivi, poi su uno «Esci da tutti i dispositivi». | Torni all'accesso su quel dispositivo; sull'altro, entro un minuto, l'app chiede di accedere di nuovo. | |
| A12 | Operatore di prova | «Elimina il mio account» e conferma. | «Account eliminato»; per rientrare serve un nuovo invito. | |
| A13 | Unico amministratore | «Elimina il mio account». | L'eliminazione è rifiutata con un messaggio che chiede di nominare un altro amministratore. | |
| A14 | Qualsiasi | Impostazioni > Notifiche. | C'è «Attiva su questo dispositivo» (le notifiche sono attive anche nell'ambiente di prova); nessuna scritta «Modalità sviluppo» né «FCM». | |
| A15 📱 | Amministratore | Guarda il titolo della scheda del browser e la pagina di accesso; poi invita un tuo indirizzo nuovo. | Ovunque compare il nome **DOMHOUSE**; l'email d'invito ha l'oggetto «Invito a DOMHOUSE». | |

## B. Installazione 📱

| N. | Dispositivo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| B1 | Computer, Chrome o Edge | In fondo alla barra laterale «Installa l'app». | Si apre la finestra di installazione; dopo l'installazione l'app si apre in una finestra sua. | |
| B2 | Android, Chrome | Impostazioni > «Installa l'app» > «Installa». | L'icona compare nella schermata Home e l'app si apre a schermo intero. | |
| B3 | iPhone, Safari | Impostazioni > «Installa l'app». | Compaiono le istruzioni «Condividi > Aggiungi alla schermata Home»; seguendole l'app si installa. | |
| B4 | App installata | Apri Impostazioni dall'app installata. | «App installata su questo dispositivo». | |
| B5 📱 | Telefono | Apri un appartamento e tocca il pulsante con le tre righe in alto a sinistra; scegli «Consumi»; riapri il menu e chiudilo toccando fuori, poi con la X. | Il menu si apre da sinistra con il logo, tutte le pagine dell'appartamento e, in fondo, nome, ruolo ed «Esci»; la pagina aperta è evidenziata; scegliendo una pagina il menu si chiude; non c'è più una barra in basso. | |
| B6 | iPhone | Guarda la parte alta e il fondo delle pagine. | La testata non finisce sotto la tacca dello schermo e il fondo delle pagine non resta sotto la barretta per tornare alla Home. | |

## C. Ruoli

| N. | Ruolo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| C1 | Sola lettura | Apri un appartamento e prova a cambiare modalità o a comandare un dispositivo. | Pulsanti disattivati, «Il tuo ruolo consente solo la lettura». Niente Amministrazione e Simulatore nel menu. | |
| C2 | Operatore | Cambia modalità e comanda un dispositivo. | Le azioni funzionano. Niente Amministrazione e Simulatore. | |
| C3 | Amministratore | Cambia il ruolo dell'utente di prova da Operatore a Sola lettura; l'utente esce e rientra. | «Ruolo aggiornato»; al nuovo accesso l'utente ha solo la lettura. | |
| C4 | Amministratore | Rimuovi un utente di prova con il cestino. | «Utente rimosso»; quell'utente non riesce più a entrare. | |
| C5 | Amministratore | Invita un tuo secondo indirizzo come «Sola lettura» spuntando un solo appartamento (il «proprietario»). | Nel modulo la scelta compare per Sola lettura e Operatore, non per Amministratore; nell'elenco la sintesi mostra il nome dell'appartamento. | |
| C6 📱 | Proprietario | Entra. | Nell'elenco c'è solo il suo appartamento; in Impostazioni > Profilo la riga «Appartamenti» ne riporta il nome; nessuna voce Amministrazione o Simulatore. | |
| C7 | Proprietario | Scrivi a mano l'indirizzo di un altro appartamento (copialo dall'account amministratore). | «Appartamento non disponibile» con «Torna agli appartamenti»; nessun dato dell'altro appartamento. | |
| C8 | Amministratore + proprietario | Con il proprietario sulla pagina del suo appartamento, l'amministratore gli toglie quell'appartamento. | Entro 30 secondi il proprietario vede «Appartamento non disponibile». | |
| C9 | Amministratore | Togli tutte le caselle al proprietario e salva. | L'app chiede conferma; dopo, il proprietario legge «Nessun appartamento assegnato al tuo account». | |
| C10 | Proprietario, notifiche attive | Dal Simulatore (amministratore) genera un'approvazione su un appartamento NON del proprietario. | Il proprietario non riceve nessuna notifica. | |
| C11 | Amministratore | Promuovi il proprietario ad Amministratore. | La scelta degli appartamenti sparisce; ora vede tutti gli appartamenti. | |

## D. Appartamento

| N. | Ruolo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| D1 📱 | Qualsiasi | Apri l'elenco Appartamenti. | Schede con nome, stato, occupazione, kWh di oggi. | |
| D2 | Operatore | Panoramica: cambia modalità in eco. | Rotellina, poi «eco» selezionata. | |
| D3b | Operatore | «Forza per…» 2 ore, poi in Programmazione «Nuova azione»: modalità eco tra 2 minuti. | Allo scadere dei 2 minuti la modalità NON cambia; nelle Decisioni compare «rimandata per la forzatura, si esegue alla sua fine»; con «Annulla forzatura» l'azione si esegue e la modalità passa a eco. | |
| D3c | Operatore (su un dimostrativo) | Dal Simulatore apri una finestra; poi «Forza per…» 30 minuti. | Finestra di conferma «Finestra aperta» con il testo «Finestra aperta in Soggiorno: durante la forzatura il clima resta acceso.» (con il nome della stanza) e i pulsanti «Annulla» e «Forza comunque»; con «Forza comunque» la forzatura parte e il clima resta acceso. Aprendo una finestra dal Simulatore a forzatura attiva: in Decisioni una riga «Finestra: regola sospesa», attore la regola della finestra, frase con il nome della finestra e l'ora di fine forzatura; mai un codice inglese. | |
| D3 | Operatore | «Forza per…» 30 minuti, poi «Annulla forzatura». | «Forzatura … attiva fino alle …», poi la forzatura sparisce. | |
| D4 | Operatore | Accendi e spegni un interruttore; alza la temperatura con +. | Sotto il dispositivo «in corso» e poi «eseguito». | |
| D4b | Operatore | Sulla caldaia: «Attiva», poi «Disattiva». | Stato «Riscaldamento abilitato» e poi «Riscaldamento disabilitato»; con un misuratore collegato sopra 30 W compare «sta scaldando ora». Il clima resta «Acceso / Spento», «Accendi / Spegni». | |
| D5 | Operatore | Menu ⋮ > «Rinomina o sposta», cambia il nome. | «Dispositivo aggiornato» e il nome nuovo. | |
| D6 | Operatore | Approvazioni: approva una richiesta con una nota (generala dal Simulatore, prova F3). | «Azione approvata»; in «Tutte» compare «approvata da …» con la nota. | |
| D7 | Qualsiasi | Decisioni: filtra per autore, poi «Carica altri». | L'elenco si filtra e si allunga. | |
| D7b | Qualsiasi | Decisioni: cerca una parola presente solo in decisioni vecchie. | Il primo blocco dice fin dove è arrivato; «Cerca più indietro» la trova. | |
| D7c | Qualsiasi | Copia un ID richiesta da un messaggio d'errore o da una decisione e incollalo nella ricerca. | Compare quella decisione con «Ricerca per ID richiesta in tutto lo storico». | |
| D7d | Qualsiasi | Periodo «Ultimi 7 giorni». | L'elenco mostra solo l'ultima settimana. | |
| D7e 📱 | Qualsiasi, telefono in 4G | Una ricerca per parola. | Un blocco si chiude in pochi secondi; annota il tempo. | |
| D8 | Qualsiasi | Consumi: Oggi, 7 giorni, 30 giorni. | Totale e grafico per ogni periodo, oppure «Nessun dato nel periodo». | |
| D9 | Operatore | Programmazione: «Nuova azione» fra 10 minuti, poi «Sposta», poi «Annulla azione». | «Azione programmata», «Orario aggiornato», «Azione annullata». | |
| D10 | Operatore | Regole: cambia un valore fuori dai limiti, poi uno valido e salva. | Prima l'errore sotto il campo, poi «Regole aggiornate». | |
| D11 | Operatore | Assistente: «Spegni il clima del soggiorno». | Una risposta, oppure la richiesta di approvazione con «Vai alle approvazioni». | |

## E. Amministrazione

| N. | Ruolo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| E0 | Amministratore (non gestore) | Pagina Appartamenti. | Nessun pulsante «+ Appartamento»; c'è la nota «Per un nuovo appartamento scrivi all'assistenza HQE.». | |
| E1 | Amministratore | Amministrazione > Appartamenti. | Niente «Nuovo appartamento» e niente cestino; c'è la nota che i nuovi appartamenti li aggiunge HQE; collegamento e codice Italianway in sola lettura. | |
| E2 | Amministratore | «Verifica connessione» su un appartamento creato da HQE. | Bollino verde «Connessione OK». | |
| E2b | Amministratore | «Modifica» su un appartamento: cambia il nome e salva. | Il nome nuovo compare nell'elenco; nel modulo non ci sono campi per il collegamento. | |
| E3 | Amministratore | Funzioni: disattiva Consumi per l'organizzazione. | «Funzioni aggiornate»; la voce Consumi sparisce dal menu dell'appartamento. Riattivala. | |
| E4 | Amministratore | Funzioni: controlla le etichette di tutte le funzioni, nel riquadro dell'organizzazione e in quelli dei singoli appartamenti. | Ogni interruttore ha un nome in italiano; nessun testo come «nav.devices» o «nav.commands». | |
| E5 | Amministratore | Utenti: «Reinvia» su un invito in attesa. | «Invito inviato a …» e una nuova email. | |
| E6 | Amministratore | Prenotazioni ricevute: apri la scheda. | In cima «Ultime 24 ore: …»; poi l'elenco con una frase per riga e l'esito verde o rosso, oppure «Nessuna prenotazione ricevuta». «Dettagli tecnici» apre i dati per l'assistenza. | |
| E7 | Amministratore, più un utente di prova con l'app aperta su un appartamento | Abbassa il ruolo dell'utente (per esempio da Amministratore a Sola lettura) e togligli tutti gli appartamenti. | Entro un minuto all'utente l'app chiede di accedere di nuovo; rientrando non vede l'appartamento. | |
| E8 | Amministratore | Apri «Modifica» su un appartamento. | Il codice Italianway si vede ma non si può cambiare. | |

## F. Simulatore (solo amministratore, su un appartamento «Dimostrativo»)

| N. | Passi | Risultato atteso | Esito |
|---|---|---|---|
| F0 | Guarda l'elenco Appartamenti e il menu di un appartamento dimostrativo. | Etichetta viola «Dimostrativo» accanto al nome; nel menu c'è «Simulatore» (per un operatore o un lettore no). | |
| F1 | Apri una finestra con l'interruttore, poi chiudila. | «Finestra aperta», «Finestra chiusa»; la Panoramica si aggiorna. | |
| F2 | Metti offline un dispositivo. | «Dispositivo offline»; in Panoramica il dispositivo ha i comandi disattivati e compare l'avviso. | |
| F3 | «Richiedi un'approvazione». | «Approvazione generata»; la richiesta compare in Approvazioni. | |
| F4 | Invia un evento di prenotazione con check-in fra un'ora. | «Evento prenotazione inoltrato» e le azioni programmate; reinviando lo stesso evento, «Evento già elaborato». | |
| F5 | Metti un dispositivo offline e cambia la modalità; poi in fondo al Simulatore «Ripristina…»: leggi la conferma, prima «Annulla», poi di nuovo e «Ripristina». | Con «Annulla» non cambia nulla; con «Ripristina» compare «Stato iniziale ripristinato», il dispositivo torna online e la modalità iniziale; nel Registro attività la voce del ripristino. | |
| F6 | Con l'appartamento aperto anche su un secondo dispositivo, ripeti il ripristino dal primo. | Sul secondo la Panoramica si aggiorna da sola entro pochi secondi. | |

## G. Dopo ogni pubblicazione

| N. | Ruolo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| G1 📱 | Qualsiasi | Tieni una scheda dell'app aperta da prima della pubblicazione, senza aprire Consumi né Amministrazione. Dopo la pubblicazione apri Consumi, poi Amministrazione (se sei amministratore). | La pagina si ricarica da sola una volta e si apre; nessuna schermata bianca. | |
| G2 📱 | Qualsiasi | Apri per la prima volta in una scheda una pagina diversa da Appartamenti e Panoramica (per esempio Consumi). | Per un istante compare lo scheletro di caricamento, poi la pagina; il menu resta fermo. | |
| G3 | Amministratore | Apri una dopo l'altra: Panoramica, Approvazioni, Decisioni, Consumi, Programmazione, Regole, Assistente, Simulatore, Amministrazione, Impostazioni. | Ogni pagina si apre; alla prima apertura si vede per un attimo lo scheletro di caricamento, poi la pagina. Nessuna schermata bianca. | |

## H. Notifiche sul telefono

Servono due account: A riceve, B fa scattare gli eventi dal Simulatore. Preferenze attive in Impostazioni > Notifiche.

| N. | Dispositivo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| H1 | Android, Chrome (meglio con l'app installata) | A: Impostazioni > Notifiche > «Attiva su questo dispositivo», poi Consenti. | «Notifiche attive su questo dispositivo». | |
| H2 | Android | Telefono bloccato, app chiusa. B: Simulatore > «Richiedi un'approvazione». | Arriva UNA notifica «<appartamento>: approvazione richiesta»; toccandola si apre Approvazioni di quell'appartamento. | |
| H3 | Android | App aperta su un'altra pagina, stesso evento. | Un solo avviso in alto con «Apri», nessun doppione. | |
| H4 | Android | B: Simulatore, mettere offline un dispositivo e aspettare i minuti della regola. | Notifica «<appartamento>: dispositivo offline»; il tocco apre la Panoramica. Se il dispositivo torna online prima, nessuna notifica. | |
| H5 | Android | Spegnere la preferenza «Dispositivi e istanza offline», ripetere H4. | Nessuna notifica. | |
| H5b | Android | Su un dimostrativo senza forzatura attiva. B, Simulatore › Evento prenotazione: (1) «Check-out effettivo», ID `bk-77812` (libera l'appartamento: finché c'è un ospite il motore non rimette a vuoto); (2) «Prenotazione creata», ID `bk-prova-d121`, check-in fra 30 minuti, check-out domani, 2 ospiti; (3) «Prenotazione annullata», stesso ID e stesse date. Alla fine «Ripristina lo stato iniziale». | Dopo (2), entro un secondo: modalità Comfort, pre-arrivo eseguito in Programmazione. Dopo (3), entro due secondi: modalità Vuoto; nelle Decisioni «Prenotazione bk-prova-d121 annullata dopo il pre-arrivo: appartamento rimesso a vuoto»; ad A la notifica «<appartamento>: prenotazione annullata, appartamento rimesso a vuoto», il tocco apre le Decisioni. | |
| H5c | Android | Spegnere la preferenza «Prenotazioni» (in Impostazioni > Notifiche risulta attiva dall'inizio), ripetere H5b. | Nessuna notifica; la decisione c'è comunque. | |
| H6 | Android | «Disattiva», poi un nuovo evento. | «Notifiche disattivate su questo dispositivo»; nessuna notifica. | |
| H7 | Android | Riattivare, ricaricare l'app, ripetere H2 e H3. | Funzionano ancora. | |
| H8 | iPhone, Safari, senza installare | Impostazioni > Notifiche. | Testo «Su iPhone e iPad le notifiche arrivano solo all'app installata…» e nessun pulsante. | |
| H9 | iPhone, app installata (iOS 16.4 o più recente) | Aprire dall'icona, attivare, poi ripetere H2-H7 con l'app chiusa e il telefono bloccato. | Come su Android. | |
| H10 | iPhone | Impostazioni di iOS > Notifiche > spegnerle per l'app, poi riaprire l'app. | La scheda segnala che le notifiche sono state tolte. | |
| H11 | Computer, Chrome o Edge | Attivare; con la scheda chiusa e il browser aperto, un evento; poi clic sulla notifica. | Notifica di sistema; il clic porta in primo piano l'app o la apre. | |
| H12 | Computer | Bloccare le notifiche dal lucchetto della barra degli indirizzi. | La scheda lo segnala. | |
| H13 | Qualsiasi | Istanza giù dal Simulatore. | UNA sola notifica «istanza non raggiungibile» finché non torna su. | |
| H15 | Telefono con notifiche attive per l'utente A | A preme «Esci»; poi da B, Simulatore > «Richiedi un'approvazione». | A non riceve nulla. | |
| H16 | Stesso telefono | Entra B. | In Impostazioni > Notifiche le notifiche risultano da attivare; nessuna notifica di A arriva a B. | |
| H16b | Stesso telefono | B esce; rientra A. | Compare «Notifiche riattivate su questo dispositivo, come prima della tua uscita.»; da un amministratore, Simulatore > «Richiedi un'approvazione»: la notifica arriva ad A. | |
| H16c | Telefono con notifiche attive per A | A le spegne da Impostazioni > Notifiche, esce e rientra. | Le notifiche restano spente. | |
| H17 | Stessa scheda del browser | A guarda la sua lista appartamenti, preme «Esci»; entra B di un'altra organizzazione. | La lista di A non compare nemmeno per un attimo. | |
| H18 | Telefono con notifiche attive | Chiudi l'app, metti il telefono in modalità aereo, riapri l'app, poi togli la modalità aereo. | In Impostazioni > Notifiche risulta ancora «Notifiche attive su questo dispositivo»; le notifiche continuano ad arrivare. | |
| H19 | Telefono con notifiche attive per l'utente A, più un computer | Sul computer A preme «Esci da tutti i dispositivi». Sul telefono, quando l'app chiede di accedere, entra B di un'altra organizzazione. Poi, da un amministratore di A, Simulatore > «Richiedi un'approvazione». | B non riceve nessuna notifica di A. | |
| H14 | Qualsiasi | Dopo una nuova pubblicazione. | Le notifiche arrivano ancora e l'app si apre anche senza rete dopo il primo caricamento. | |

## I. Organizzazioni e appartamenti della piattaforma

Servono un account **gestore della piattaforma** e un **amministratore** normale.

| N. | Ruolo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| I1 | Amministratore normale | Guarda il menu; poi scrivi a mano l'indirizzo `/organizzazioni`. | Nessuna voce «Organizzazioni»; l'indirizzo dà «Pagina non trovata». | |
| I2 | Gestore | Organizzazioni > «Nuova organizzazione» con un nome e un'email reale. | Arriva l'invito; l'organizzazione compare con «in attesa del primo accesso» e «Reinvia invito». | |
| I3 | Gestore | Crea di nuovo un'organizzazione con lo stesso nome, anche con maiuscole diverse. | Messaggio di nome già usato. | |
| I4 | Nuovo amministratore | Entra dall'email di invito. | L'organizzazione risulta «attiva» e «Reinvia invito» sparisce. | |
| I5 | Gestore | Aggiungi un secondo gestore, poi prova a toglierli entrambi; poi togli il ruolo a te stesso con un altro gestore presente. | L'ultimo gestore non si toglie; togliendoti il ruolo la voce «Organizzazioni» sparisce. | |
| I0 | Gestore che è anche amministratore | Pagina Appartamenti > «+ Appartamento»; poi guarda le schede della pagina Organizzazioni. | Si apre Organizzazioni con gli appartamenti della tua organizzazione; la prima scheda si chiama «Elenco organizzazioni». | |
| I6 | Gestore | In un'organizzazione: «Appartamenti» > «Nuovo appartamento» (in staging `mock://builtin`), poi «Verifica connessione». | Compare con «Ultima verifica: mai eseguita», poi «riuscita il …». | |
| I7 | Gestore | «Modifica collegamento»; poi «Elimina» con conferma. | La modifica mostra solo indirizzo e porta; dopo l'eliminazione l'amministratore dell'organizzazione non lo vede più. | |
| I8 | Gestore | Crea un appartamento con un identificativo già usato in un'altra organizzazione. | «Identificativo non disponibile». | |
| I9 | Gestore | Prova ad aprire una pagina interna di un appartamento di un'altra organizzazione (Panoramica, Consumi). | Non è possibile: nessun dato di dispositivi, consumi o decisioni. | |
| I10 | Amministratore, in produzione | Amministrazione > Appartamenti. | Niente «Nuovo appartamento», niente cestino; collegamento in sola lettura con la nota; «Verifica connessione» funziona e mostra l'esito. | |
| I11 | Gestore | In un'organizzazione, «Nuovo appartamento» con un codice Italianway di prova; poi l'amministratore di quell'organizzazione apre l'appartamento. | Il gestore inserisce e modifica il codice; l'amministratore lo vede ma non lo cambia. | |
| I12 | Gestore | In un'altra organizzazione crea un appartamento con lo stesso codice Italianway. | Il codice è rifiutato perché già in uso. | |
| I13 | Gestore | «Nuova organizzazione» indicando come amministratore l'email di un gestore della piattaforma. | L'invito è rifiutato con un messaggio che non dice perché; nessuna organizzazione creata. | |
| I14 | Gestore | In un'organizzazione, «Nuovo appartamento» con `mock://builtin`. | La casella «Istanza simulata (appartamento dimostrativo)» è accesa e non si toglie; l'appartamento compare «Dimostrativo». | |

## J. Registro, sospensione, assistenza, privacy

Servono un **gestore della piattaforma** (che sia anche amministratore di un'organizzazione) e un **amministratore**
normale di prova con un **operatore**.

| N. | Ruolo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| J1 | Gestore che è anche amministratore | Guarda il fondo della barra laterale; poi Amministrazione > Appartamenti. | Due righe: «Amministratore · …» e «Gestore della piattaforma»; nessuna nota «scrivi all'assistenza». | |
| J2 | Amministratore | Cambia il ruolo di un utente, poi apri Amministrazione > Registro attività. | La voce in cima dice chi ha cambiato il ruolo di chi, da quale ruolo a quale, con la data. | |
| J3 | Gestore | Organizzazioni > Registro attività, scegli l'organizzazione di J2. | La stessa azione compare con i soli ruoli («Un amministratore ha cambiato il ruolo di un utente…»), senza nomi né email. | |
| J4 | Gestore | Elenco organizzazioni > «Sospendi» su un'organizzazione di prova (con un utente collegato), con un motivo. | L'organizzazione ha l'etichetta «Sospesa»; l'utente collegato esce con «La tua organizzazione è sospesa…» e non riesce a rientrare. | |
| J5 | Gestore | «Riattiva» sulla stessa organizzazione. | L'utente rientra normalmente; nel Registro attività ci sono sospensione (con il motivo) e riattivazione. | |
| J6 | Gestore | Elenco organizzazioni > «Accesso di assistenza» su un'organizzazione di prova: 1 ora, un motivo; poi «Entra come assistenza». | Barra in alto «Stai lavorando come assistenza in … con i permessi di un operatore.»; si vedono gli appartamenti di quell'organizzazione; Amministrazione non c'è. | |
| J7 | Amministratore dell'organizzazione di J6 | Apri l'app. | In cima l'avviso «L'assistenza HQE (…) ha accesso alla tua organizzazione fino al …», con il motivo, «Chiudi accesso» e la X. | |
| J8 | Amministratore | «Chiudi accesso» e conferma. | «Accesso di assistenza chiuso»; entro un minuto il gestore torna alla sua area con «L'accesso di assistenza a … è finito». Nel Registro attività apertura e chiusura con il nome della persona di HQE. | |
| J9 | Gestore | Apri un nuovo accesso e premi «Termina». | Si torna alla propria area; i dati dell'organizzazione assistita non compaiono più nemmeno tornando indietro. | |
| J10 | Operatore di prova | Impostazioni > «Elimina il mio account» (leggi la conferma) e conferma. | La conferma spiega cosa si cancella e cosa resta; nelle decisioni e nel Registro attività quella persona compare come «utente rimosso». | |
| J11 | Utente «Sola lettura» | Apri l'Assistente di un appartamento. | Non si possono fare domande e non compaiono quelle dei colleghi. | |
| J12 | Amministratore | Prenotazioni ricevute > «Dettagli tecnici» di una riga (se ce ne sono). | Ci sono «Codice Italianway» e «Ospiti»; nel corpo grezzo nessun nome, email o telefono degli ospiti. | |

## K. Rendiconti dei consumi in Excel

| N. | Ruolo | Passi | Risultato atteso | Esito |
|---|---|---|---|---|
| K1 | Amministratore | Amministrazione > Appartamenti > «Prezzo dell'energia»: scrivi 0,25 e «Salva». | «Prezzo dell'energia salvato»; ogni appartamento dice «0,25 €/kWh (dell'organizzazione)». | |
| K2 | Amministratore | «Modifica» su un appartamento: prezzo 0,3 e salva; poi svuota il campo e salva. | Prima «0,3 €/kWh (solo per questo appartamento)», poi di nuovo quello dell'organizzazione. Nel Registro attività i tre cambi. | |
| K3 | Amministratore | Scrivi 12 come prezzo. | «Scrivi un numero da 0 a 10 con al massimo 4 decimali, per esempio 0,25.» | |
| K4 📱 | Qualsiasi (anche Sola lettura) | Consumi > «Rendiconto in Excel»: scegli il mese in corso e «Scarica Excel». | Si scarica `consumi-<appartamento>-<mese>.xlsx`; aperto in Excel ha i fogli Riepilogo, Giornaliero, Orario, Dispositivi e l'importo in euro. | |
| K5 | Qualsiasi | Consumi, periodo «Soggiorno», «Excel del soggiorno» (serve un soggiorno, anche dal Simulatore). | Il file copre dall'arrivo alla partenza; nessun nome, email o telefono di ospiti. | |
