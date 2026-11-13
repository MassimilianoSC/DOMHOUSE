# Revisione per scenari (P-90), 13 novembre 2026

Cinque agenti in sola lettura, uno per area. Ognuno è partito da situazioni reali e le ha seguite passo per passo nel
codice pubblicato `396b522`, con il motore simulato. Poi cinque verificatori indipendenti hanno ricontrollato ogni
rilievo. **Nessun rilievo è stato smentito.** Molti sono stati declassati di gravità.

- Rapporti completi, con file:riga e prove: `DOMOTICA/revisione-scenari-esiti/` (fuori dal repository; cinque
  rapporti e cinque verifiche).
- Esclusi: i difetti già noti di «Limiti del setpoint» (in riparazione, 1098 = b) e P-88 (check-out con movimento).
- **Riserva generale:** nel codice pubblicato il connettore Shelly gestisce solo la Plug M Gen3. I rilievi sulla
  caldaia (Shelly 1) e sugli split a infrarossi riguardano hardware che arriverà con la tappa B.

Gravità: quella data dal verificatore. Categoria: **P** progettazione, **L** logico, **T** testo.

## A. Gravi: riparare prima del primo appartamento vero

| N. | Rilievo | Cat. | Gravità | Riparazione proposta |
|---|---|---|---|---|
| S1 | **L'ospite spegne il clima col telecomando e il motore lo riaccende ogni 5 minuti** (in comfort, con il misuratore collegato). Contraddice «non va mai contro il comando di una persona». Di notte ci sarebbe un bip a ogni comando a infrarossi. Trovato da due agenti | P | alta | Uno spegnimento visto dal misuratore, senza un comando in corso, toglie lo split dalla regolazione fino al prossimo cambio di modalità, con una decisione. Va chiesto qualche minuto di watt bassi prima di crederlo spento (vedi S9) |
| S2 | **Forzatura dopo lo scatto della finestra: la caldaia resta disabilitata** fino al prossimo cambio di modalità; in eco non torna nemmeno il clima. Basta anche una forzatura che scade a finestra aperta. Il testo «durante la forzatura il clima resta acceso» (it.json:521) è falso | P+T | alta | Durante la forzatura rimandare il ripristino invece di cancellarlo (core.py:1081-1083); correggere il testo |
| S3 | **Un comando di modalità partito e poi fallito o scaduto non si ripete.** Dopo il passaggio a casa vuota il termostato resta a 21 °C con il relè acceso; dopo un pre-arrivo resta a 8 °C e l'ospite trova freddo. D16 copre solo il dispositivo già offline. La guida promette il contrario | P | alta | La caldaia prende sempre la temperatura della modalità (è un valore del motore); il comando al clima che fallisce va in attesa |
| S4 | **Il relè della caldaia resta nell'ultimo stato se la catena si interrompe** (VM, broker, motore, Wi-Fi della caldaia): o scalda per tutto il fermo, o a casa vuota l'antigelo non agisce. Nessuna sicurezza locale sugli Shelly | P | alta (hardware futuro) | Con Youssouf: spegnimento automatico sul relè (per esempio 30 minuti) e il motore che rinnova l'«acceso»; da provare in laboratorio. Come minimo, scriverlo in limiti-noti |
| S5 | **Proroga o late check-out arrivati dopo l'azione «check-out»: l'ospite resta in casa vuota**, senza notifica (D06 vale anche per il check-out) | P | media-alta | Limitare il `continue` di D06 al pre-arrivo; per il check-out riprogrammare, e se già eseguito rimettere il comfort con una decisione |
| S6 | **Contatto della finestra senza segnale, caduto mentre era aperto: caldaia e clima spenti finché non torna** (giorni con la batteria scarica). L'app intanto mostra «Stato non noto» o «Nessuna aperta» | P | media-alta | Nel calcolo della finestra aperta ignorare i contatti offline, o farli scadere dopo la soglia, con una decisione |
| S7 | **«Esci da tutti i dispositivi» non ferma le notifiche sugli altri telefoni**: su un telefono perso restano visibili appartamenti e approvazioni | P (privacy) | media-alta | Quando si revocano le sessioni, svuotare anche i token delle notifiche |

## B. Medi e bassi: nello stesso lotto se costano poco

| N. | Rilievo | Cat. | Gravità | Riparazione proposta |
|---|---|---|---|---|
| S8 | Due split sullo stesso misuratore (dual split): lo split spento risulta acceso, lo spegnimento finisce in «nessuna conferma» | P | media | Un misuratore collegato a più split viene ignorato (conferma «none»); «un misuratore per split» in connector-v2 §2.2. **Chiedere al cliente se ha dual split** |
| S9 | Split acceso ma fermo a temperatura raggiunta (meno di 15 W): creduto spento, un comando ogni 5 minuti mai confermato | P | media | Al collaudo misurare il consumo a riposo di ogni modello e regolare la soglia per appartamento (già possibile, D-131); scriverlo nella procedura del tecnico |
| S10 | Un'azione programmata a mano non si accorge di una prenotazione arrivata dopo: gli ospiti vanno in casa vuota senza avviso | P | media | All'ora dell'azione, con ospiti in casa, eco o casa vuota diventano un'approvazione (come F1) |
| S11 | Spegnere o riaccendere «Pre-arrivo» e «Risparmio al check-out» non tocca le azioni già programmate. Il testo «Ricalcolata a ogni modifica» è falso con la regola spenta | P+T | media | Le azioni delle prenotazioni non partono, e si annullano con una decisione, se la loro regola è spenta; alla riaccensione si riprogrammano |
| S12 | La richiesta «Spegnere … con l'appartamento vuoto» resta aperta dopo l'uscita da casa vuota e si esegue all'approvazione | P | bassa-media | Chiuderla all'uscita da casa vuota. Da fare insieme alla questione consumi durante le pulizie (P-88) |
| S13 | Assistente: un cambio di sola temperatura su un clima spento diventa «Spengo … con ospiti presenti?», mentre la pagina Approvazioni dice «a 24 °C» | L+T | media-bassa | Dire «spegnere» solo se l'apparecchio è acceso; nel prompt «per accendere includi "on": true» |
| S14 | Broker giù oltre 15 minuti: una notifica per ogni dispositivo più quella del sistema fermo, mentre la guida promette una sola notifica | L | media-bassa | Nell'attesa per dispositivo, uscire se il sistema è già segnalato fermo |
| S15 | «Consumi disponibili dal» non va mai avanti: dopo un ricollegamento a un altro motore il riepilogo segnala per 4 settimane falsi «Consumi alti» e l'Excel mostra zeri | L | media-bassa | Azzerare la data al ricollegamento |
| S16 | Chi ha sola lettura riceve «approvazione richiesta», anche di notte, e non può approvare | P | media-bassa | Escludere la sola lettura dalle notifiche di approvazione |
| S17 | «Avviso dispositivo offline» spenta a metà attesa avvisa lo stesso; riaccesa con un dispositivo già offline non avvisa mai | P | bassa | Ricontrollare la regola a fine attesa e riarmarla alla riaccensione, come per la finestra (D30) |
| S18 | Comando a mano sulla caldaia, poi sensore perso: relè sempre acceso, anche a casa vuota. Comportamento deciso (D-164), conseguenza non scritta | P | medio-bassa | Una notifica propria per l'episodio e una riga in limiti-noti; cambiare D-164 spetta al committente |
| S19 | Pre-arrivo spostato a mano, poi una modifica qualsiasi della prenotazione: la casa torna a vuoto, e la decisione dice «Arrivo spostato» anche se l'arrivo non è cambiato | P+T | bassa-media | Il ritorno a vuoto solo se il check-in è cambiato davvero |
| S20 | Chat con due azioni: dopo una decisione presa altrove i Sì/No passano alla seconda senza dirlo | interfaccia | bassa | Mostrare sempre «Ora: …» |
| S21 | Cancellazione ricevuta due volte con id diverso: annulla il comfort rimesso a mano. Prenotazione già finita ricevuta in ritardo: 4 comandi inutili | L | bassa | Ignorare la seconda cancellazione; non programmare niente se il check-out è passato |

## C. Dipendono da cosa manda Italianway

Il formato vero di Italianway non è noto (traduttore provvisorio, domanda aperta nel contratto). Il messaggio per
Leonardo (`docs/da-inviare/messaggio-italianway-per-leonardo.md`) **non è ancora partito**. Questi rilievi esistono
solo se Italianway manda gli orari effettivi di arrivo e partenza:

| N. | Rilievo | Gravità |
|---|---|---|
| S22 | Il check-in effettivo non porta il comfort: l'ospite arrivato in anticipo trova casa vuota fino al pre-arrivo; l'app mostra «Vuoto» | media (latente) |
| S23 | Il check-out effettivo non fa risparmiare: il comfort resta fino all'orario prenotato più 30 minuti. Sarebbe proprio il segnale che distingue l'ospite dalle pulizie (P-88) | bassa-media (latente) |
| S24 | Un check-in ritentato dopo una modifica viene scartato come vecchio: l'app resta su «Prenotato» | bassa (latente) |

La proposta inviata al cliente promette: «Italianway comunicherà il check-in: l'app passerà da «Prenotato» a «Occupato»».

## D. Solo testi (guida, app, email)

| N. | Rilievo | Nota |
|---|---|---|
| T1 | **Spegnere «Avviso dispositivo offline» spegne anche l'avviso «sistema domotico non raggiungibile».** È deciso (D-217), ma la descrizione della regola parla solo di «un dispositivo». Pesa insieme a S4. Trovato da due agenti | Testo nella regola. **Domanda al committente:** tenere D-217 o dare all'avviso di sistema una soglia fissa? |
| T2 | Appartamento disattivato: gli automatismi continuano, ma notifiche, riepiloghi, prenotazioni ed Excel si fermano. La guida dice solo «non spegne gli automatismi» | Una riga in guida e nella conferma |
| T3 | L'Excel usa il prezzo di oggi anche per i mesi passati | «Prezzo in vigore il giorno dello scaricamento» nel file e in guida |
| T4 | «Questa email non può essere invitata»: la guida (righe ~1300 e ~2588) la spiega solo come «persona di HQE» | Aggiungere «o email già usata altrove» |
| T5 | La guida (righe ~464 e ~2019) promette «Prenotato» durante il pre-arrivo; l'app mostra «Vuoto» | Correggere la guida |
| T6 | Tetto mensile: guida ed email dicono che l'assistente «si ferma», ma resta la risposta rapida (D-182). «Approvato: il comando parte» compare anche per le azioni programmate. In chat si vedono codici interni («blocked_by_rule», «no_confirmation») | Correggere i testi; in chat usare `_command_failure` |

## E. Osservazioni da decidere (non sono difetti)

1. **Il motore non sa in che stagione siamo:** in comfort la caldaia è abilitata a 21 °C tutto l'anno, quindi una
   notte fresca d'estate la accende. Va deciso insieme ai due intervalli inverno/estate.
2. **Nessun avviso se la temperatura resta sotto l'antigelo e non risale** (caldaia rotta con il comando che
   funziona). La guida non lo promette.
3. **Il check-out con movimento** (P-88) apre una richiesta che alla scadenza si approva; il riepilogo la conta come
   segnalazione, quindi ogni settimana con le pulizie risulta «da segnalare». Da guardare nel rodaggio.

## Scenari esaminati senza problemi

Circa 80 in tutto, elencati in fondo a ciascun rapporto. Tra questi: prenotazioni attaccate (10:00 → 15:00), webhook
doppi o fuori ordine, cambio dell'ora, forzatura su check-in e check-out, riavvio notturno, due operatori che
approvano insieme, privacy verso il gestore della piattaforma, accesso di assistenza che scade, consumi alla
mezzanotte e col cambio d'ora.

## Piano delle riparazioni (stime di o1 e o2, 07:53; ore NON misurate e probabilmente pessimiste)

o1 e o2 confermano tutti i rilievi sul main `1f79ba9`.

**Gruppo (a), senza decisioni: avviato subito (D-198).**

- **o1, circa 26 h:** S2, S3, S5, S7, S11, S12, S13, S14, S15, S17, S18 (solo la notifica «caldaia comandata a mano
  senza sensore»), S19, S21, T6, T1 (solo il testo, tenendo D-217).
- **o2:** S20 (1 h), T6 (0,5 h), S2 (testo, 0,5 h dopo o1). S7, S11 e S13 non toccano il sito.

**Gruppo (b), aspetta il committente.**

| Punto | Domanda | Consiglio | Ore |
|---|---|---|---|
| S1 | L'ospite spegne il clima col telecomando: resta spento fino al prossimo cambio di modalità, o il sistema lo riaccende dopo un certo tempo? | Resta spento; lo si considera spento solo dopo circa 5 minuti di consumo basso (S9) | o1 3,5 |
| S6 | Il contatto di una finestra aperta perde il segnale: la finestra va considerata chiusa (il riscaldamento riparte) o aperta finché il contatto non torna? | Chiusa, con una decisione; la notifica offline esiste già | o1 2,5 |
| S10 | Azione eco o casa vuota programmata a mano, che alla sua ora trova ospiti: chiedere al gestore o eseguirla? Senza risposta? | Chiedere; senza risposta, respinta | o1 2,5 |
| T1 | Spegnere «Avviso dispositivo offline» deve spegnere anche l'avviso «sistema domotico non raggiungibile» (D-217)? | No: l'avviso di sistema con una soglia fissa sempre attiva (pesa con S4) | o1 2, o2 0,25 |
| S18 | Comando a mano sulla caldaia, poi il sensore si spegne: la caldaia resta accesa (D-164) o si spegne? | Tenere D-164, con la notifica nuova | 0 |
| S16 | La sola lettura deve ricevere le notifiche di approvazione? | No: escluderla e nascondere l'interruttore | o1 1, o2 0,75 |
| T2 | Una conferma prima di disattivare un appartamento (oggi si disattiva al tocco)? | Sì | o2 1 |

**Gruppo (c), dipende da Youssouf, dal cliente o dall'hardware.**

- **S4:** spegnimento automatico sul relè dello Shelly 1 della caldaia, con il motore che rinnova l'«acceso». Serve
  che il connettore gestisca lo Shelly 1 (Youssouf), poi una prova in laboratorio; lato motore circa 2 h. Subito: una
  riga in limiti-noti.
- **S8:** chiedere al cliente se ha climatizzatori dual split. Lato motore 1,5–2 h, quando si vuole; la frase «un
  misuratore per split» in connector-v2 §2.2 (Youssouf).
- **S9:** soglia di consumo per modello, misurata al collaudo e scritta nella procedura del tecnico (P-91).
- **S22–S24:** dopo la risposta di Italianway (messaggio per Leonardo).
