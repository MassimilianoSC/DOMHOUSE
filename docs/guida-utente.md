# Guida all'app DOMHOUSE

Tutto quello che l'app sa fare, spiegato passo per passo e diviso per ruolo. Non servono conoscenze tecniche.
*Versione del 23 ottobre 2026 (lotto 34).*

> **Ambiente di prova**
>
> Oggi gli appartamenti sono simulati: nessun dispositivo reale viene acceso o spento.
> - **In alto su ogni pagina** una fascia gialla dice «Ambiente di prova» · «i dati sono separati da quelli veri».
> - **Gli appartamenti simulati** ripartono dallo stato iniziale ogni volta che il server dell'app viene riavviato,
>   per esempio a un aggiornamento.

## Come leggere questa guida

**Le convenzioni della guida: virgolette, puntini, ruoli, pagine facoltative.**

- **I testi fra «virgolette basse»** sono quelli esatti che vedi nell'app: pulsanti, etichette, messaggi.
- **I tre puntini «…» dentro le virgolette** stanno al posto di un nome, una data, un numero o un indirizzo email
  che l'app mette lì.
- **«Tocca» e «premi»** vogliono dire la stessa cosa: sul telefono tocchi, sul computer fai clic.

**La guida è divisa per ruolo:**

| Ruolo | Parti da leggere |
|---|---|
| **Sola lettura** | La parte 4 |
| **Operatore** | Le parti 4 e 5 |
| **Amministratore** | Le parti 4, 5 e 6 |
| **Gestore della piattaforma** (HQE) | La parte 7 |
| Tutti | Le parti 1 e 2 e tutte quelle dalla 9 in poi |

> **Da sapere**
>
> - **Alcune pagine dell'appartamento** compaiono solo se la funzione è attiva per quell'appartamento (lo decide
>   l'amministratore nella scheda «Funzioni»): «Approvazioni», «Decisioni», «Consumi», «Programmazione», «Regole»,
>   «Assistente».
> - **«Riepiloghi»** c'è sempre.

## 1. Che cos'è DOMHOUSE

**L'app per controllare riscaldamento, clima e consumi degli appartamenti in affitto breve.**

DOMHOUSE è l'app con cui chi gestisce appartamenti in affitto breve controlla riscaldamento, clima e consumi di ogni
appartamento, anche da lontano.

### Le parole chiave

**Gli elementi di cui parla tutta la guida, uno per riga.**

- **Appartamento**: ha dei dispositivi collegati a un sistema domotico.
- **Dispositivi**: caldaia, climatizzatore, prese, sensori di temperatura, umidità, finestre, movimento e misuratori
  di consumo.
- **Sistema domotico**: legge e comanda i dispositivi.
- **Motore**: la parte automatica che lavora dentro il sistema domotico. Applica le regole, prepara la casa prima
  dell'arrivo degli ospiti e la mette a riposo dopo la partenza, seguendo le prenotazioni.
- **Regole**: automatismi già previsti, per esempio «finestra aperta spegne il clima».
- **Prenotazioni**: arrivano dal sistema Italianway.
- **Modalità**: l'appartamento ne ha sempre una: «comfort» quando ci sono o stanno per arrivare gli ospiti, «eco»
  per consumare meno, «casa vuota» quando non c'è nessuno. Chi lavora nell'app può cambiarla a mano.
- **Forzatura**: blocca gli automatismi per 30 minuti, 2 ore o 6 ore, tenendo la modalità attuale.
- **Programmazione**: una modalità cambiata a un orario scelto.
- **Decisioni**: lo storico dell'appartamento, dove finisce tutto quello che succede, fatto da una persona o dal
  motore.
- **Approvazione**: una richiesta che aspetta il tuo sì o il tuo no, aperta dal motore quando non vuole decidere da
  solo (per esempio spegnere un apparecchio che consuma a casa vuota).
- **Assistente**: una chat in italiano a cui puoi chiedere lo stato, i consumi o un comando.
- **Simulatore**: serve a provare tutto questo su appartamenti finti, detti «Dimostrativo».
- **Organizzazione**: le persone che usano l'app ne fanno parte (oggi Flatsharing) e hanno un ruolo: sola lettura,
  operatore o amministratore.
- **Gestore della piattaforma** (HQE): sta sopra le organizzazioni, le crea e collega gli appartamenti ai sistemi
  domotici.

### Chi fa cosa nel servizio

**Chi installa, chi attiva e chi configura un appartamento nuovo.**

*Decisione del 16 ottobre 2026.*

1. **Flatsharing**, il gestore degli appartamenti, installa sensori e dispositivi nell'appartamento e lo comunica a
   HQE.
2. **HQE** prepara il sistema domotico dell'appartamento e lo attiva nell'app da «Organizzazioni», inserendo anche il
   codice Italianway (il codice con cui arrivano le prenotazioni).
3. **L'appartamento compare** nell'elenco di Flatsharing. L'amministratore di Flatsharing gli dà nome e indirizzo,
   sceglie le funzioni attive e decide chi può vederlo.

> **Attenzione**
>
> L'amministratore **non può creare da solo un appartamento, né cambiarne il collegamento al sistema domotico o il
> codice Italianway**: lo fa solo HQE. È una garanzia: nessuno può collegare un appartamento a un sistema che non è
> il suo, né ricevere le prenotazioni di una struttura altrui. Vale anche nell'ambiente di prova.

> **Da sapere**
>
> Il gestore della piattaforma, da solo, non vede dispositivi, consumi, decisioni né utenti delle organizzazioni:
> può entrarci solo con un **accesso di assistenza** a tempo, che l'amministratore vede e può chiudere (parte 8).

## 2. Primi passi, uguali per tutti

### Ricevere l'invito ed entrare

**Si entra solo su invito, con Google o con una password.**

Non ci si registra da soli: si entra sempre con un invito di un amministratore (o di HQE per il primo amministratore
di un'organizzazione).

1. **Ricevi un'email** con oggetto «Invito a DOMHOUSE». Dentro ci sono il nome dell'organizzazione, il tuo ruolo e
   chi ti ha invitato. Controlla anche lo spam.
2. **Se la tua email è un account Google** (per esempio Gmail): premi «Apri l'app», poi «Accedi con Google» e scegli
   quello stesso indirizzo.
3. **Altrimenti premi «Scegli la password»** nell'email e scegli una password. Il link vale 1 ora.
4. **Poi apri l'app**, compila «Email» e «Password» e premi «Accedi».
5. **Se il link è scaduto**, nella pagina di accesso premi «Password dimenticata?» (vedi sotto).
6. **Al primo accesso**, se il tuo indirizzo non risulta confermato, l'app mostra «Conferma il tuo indirizzo: abbiamo
   inviato un link a …. Aprilo e poi accedi di nuovo.» e ti fa uscire: apri il link nell'email e accedi di nuovo.
7. **Entrato**, vedi «Appartamenti» (oppure «Organizzazioni» se sei un gestore della piattaforma senza
   organizzazione).

**La pagina di accesso:**

| Cosa vedi | Cosa vuol dire |
|---|---|
| L'indirizzo dell'ambiente di prova | [https://domotica-poc-511707.web.app](https://domotica-poc-511707.web.app) |
| Il marchio e il nome «DOMHOUSE» sopra la scheda | Ci sono a ogni larghezza di schermo |
| Su computer, a sinistra, un pannello scuro con «Riscaldamento, clima e consumi dei tuoi appartamenti» | Che cosa fa l'app |
| «Accedi» e, sotto, «Area riservata ai gestori degli appartamenti» | Il titolo della scheda di accesso |
| «Accesso di sviluppo» con «Modalità sviluppo: scegli un utente di prova, nessuna password richiesta.» | Esiste solo nell'ambiente di sviluppo tecnico: nell'ambiente di prova e in quello vero non c'è |

> **Attenzione**
>
> Se l'accesso non riesce, l'avviso in alto dice cosa fare e sotto mostra un «Codice» copiabile.
> - **Toccalo** (compare «Copiato») e mandalo all'assistenza HQE insieme alla segnalazione.
> - **Quel codice non è** l'«ID richiesta» delle altre pagine.
> - **Se chiudi tu** la finestra di Google, non compare nulla.
> - **I messaggi possibili** sono nella parte 11.

### Password dimenticata

**Scegliere una nuova password dalla pagina di accesso.**

1. **Nella pagina «Accedi»** premi «Password dimenticata?».
2. **Leggi** «Inserisci la tua email: ti mandiamo un link per scegliere una nuova password.».
3. **Compila «Email»** e premi «Invia il link». «Torna all'accesso» riporta al modulo.
4. **Leggi** «Se … ha un account, riceverai a breve un'email con il link. Controlla anche lo spam.».
5. **Apri il link** nell'email e scegli la nuova password, poi accedi.

> **Da sapere**
>
> La frase del passo 4 è la stessa anche se l'indirizzo non è registrato: è voluto.

### Installare l'app sul telefono o sul computer

**L'app si aggiunge alla schermata Home e si apre a schermo intero.**

La voce «Installa l'app» è in fondo alla barra laterale (sul telefono nel menu a tre righe) e in Impostazioni, con
la frase «Aggiungi l'app alla schermata Home: si apre a schermo intero e riceve le notifiche.».

| Dispositivo | Cosa fare | Cosa dice l'app |
|---|---|---|
| Android con Chrome | Premi «Installa l'app» e poi «Installa» nella finestra del browser; oppure apri il menu di Chrome e scegli «Installa app». | «Su Android: apri il menu di Chrome e scegli «Installa app».» |
| iPhone e iPad | Apri il sito con Safari, tocca Condividi e poi «Aggiungi alla schermata Home». | «Su iPhone: apri il sito in Safari, tocca Condividi e poi «Aggiungi alla schermata Home». Le notifiche push funzionano solo dall'app installata.» |
| Computer | Con Chrome o Edge premi «Installa l'app» oppure l'icona «Installa» nella barra degli indirizzi. | «Usa Chrome o Edge: nella barra degli indirizzi compare l'icona «Installa». Su Android apri il menu di Chrome e scegli «Installa app».» |

> **Da sapere**
>
> - **Quando l'app è installata**, in Impostazioni compare «App installata su questo dispositivo» e la voce
>   «Installa l'app» sparisce dal menu.
> - **Il pulsante «Installa»** compare solo se il browser lo permette; con altri browser restano le istruzioni
>   scritte.
> - **Installare l'app non attiva da sola le notifiche**: vedi «Notifiche sul telefono».

### Muoversi nell'app

**Dove sono le pagine: barra laterale sul computer, menu sul telefono.**

| Dove | Cosa vedi | Cosa puoi fare |
|---|---|---|
| Su computer | La barra laterale a sinistra con le pagine generali e, quando sei dentro un appartamento, le sue pagine | Tocca una pagina per aprirla |
| Sul telefono | Il pulsante con le tre righe in alto a sinistra («Apri il menu») | Si apre il menu con le stesse pagine. Si chiude con la X («Chiudi il menu»), toccando fuori, con il tasto Esc o scegliendo una pagina |
| In fondo al menu | **Il tuo nome** in grassetto (quello scelto nelle Impostazioni) con sotto l'email in piccolo; se non hai scelto un nome, solo l'email. Sotto ci sono i tuoi ruoli, per esempio «Amministratore · Flatsharing» e, se sei anche di HQE, «Gestore della piattaforma» | Solo leggere |
| Sopra il contenuto, nell'ambiente di prova | La fascia gialla «Ambiente di prova» · «i dati sono separati da quelli veri» | Solo leggere |

**Le pagine generali:**

| Pagina | Chi la vede |
|---|---|
| «Appartamenti» | Tutti |
| «Amministrazione» | Gli amministratori |
| «Organizzazioni» | I gestori della piattaforma |
| «Impostazioni» | Tutti |
| «Esci» | Tutti |

**Le pagine di un appartamento:**

| Pagina | Chi la vede |
|---|---|
| «Panoramica» | Tutti |
| «Approvazioni», «Decisioni», «Consumi» | Tutti, se la funzione è attiva per l'appartamento |
| «Riepiloghi» | Tutti, sempre |
| «Programmazione», «Regole», «Assistente» | Tutti, se la funzione è attiva per l'appartamento |
| «Simulatore» | Solo gli amministratori sui dimostrativi |

> **Da sapere**
>
> - **La pagina aperta** è bianca, con un filo arancione a sinistra.
> - **Se le schede di una pagina** non stanno nello schermo, la loro barra scorre in orizzontale.
> - **Mentre i dati arrivano** la pagina mostra già la sua forma (fascia, striscia, righe) in grigio chiaro, al
>   posto di un rettangolo grigio.

### Capire gli esiti: avvisi verdi, rossi e «ID richiesta»

**Come l'app dice se un'azione è riuscita o no.**

| Cosa vedi | Cosa vuol dire | Cosa fare |
|---|---|---|
| Un avviso verde in alto (per esempio «Azione approvata», «Regole aggiornate») | L'azione è riuscita | Niente |
| Un avviso rosso con il messaggio | C'è stato un errore | Leggi il messaggio; se c'è «ID richiesta», copialo |
| Il pulsante «ID richiesta» nell'avviso rosso | L'identificativo completo dell'operazione | Toccalo per copiarlo (compare «Copiato»); comunicalo all'assistenza insieme alla segnalazione e usalo nella ricerca delle Decisioni |
| «Riprova» | Il problema indicato si può risolvere | Premilo dopo aver risolto il problema |
| Una richiesta di conferma | Le eliminazioni chiedono sempre conferma | Conferma o annulla |
| «Pagina non trovata» e «L'indirizzo non corrisponde a nessuna schermata.» | Hai aperto un indirizzo che non esiste | Torna al menu |
| «Funzione non disponibile per questo appartamento» e «Questa sezione non è attiva per l'appartamento, oppure il suo sistema domotico non la offre ancora.» | Hai aperto la pagina di una funzione spenta | Chiedi all'amministratore |

> **Da sapere**
>
> - **Il pulsante «ID richiesta»** ne mostra solo l'inizio; passandoci sopra con il puntatore leggi il valore
>   intero.
> - **I messaggi comuni a tutte le pagine** sono spiegati nella parte 11: «Server non raggiungibile»,
>   «Operazione non riuscita», «Errore …», «Richiesta non accettata dal server: ricarica la pagina e riprova.»,
>   «Sessione non valida o scaduta».

### Impostazioni: i riquadri

**La pagina personale: profilo, password, sicurezza, notifiche, installazione.**

La pagina «Impostazioni» è uguale per tutti i ruoli e ha questi riquadri. Su computer ogni riquadro ha il titolo
a sinistra e il contenuto a destra.

| Riquadro | Cosa vedi | Cosa puoi fare |
|---|---|---|
| «Profilo» | «Email», «Ruolo», «Piattaforma» (solo se sei gestore della piattaforma), «Organizzazione», «Appartamenti», «Lingua» («Italiano») | Solo leggere |
| «Profilo», sotto una riga | «Nome visualizzato» e «Salva» | Cambiare il nome che vedono i colleghi |
| «Password ed email» | Solo per chi entra con email e password | Cambiare password ed email di accesso |
| «Sicurezza» | «Esci da tutti i dispositivi» ed «Elimina il mio account» | Chiudere tutte le sessioni; eliminare l'account |
| «Notifiche» | Quattro interruttori per categoria e l'attivazione sul dispositivo | Scegliere quali avvisi ricevere sul telefono |
| «Installa l'app» | Le istruzioni per iPhone, Android e computer (vedi sopra) | Installare l'app |
| «Esci», in fondo, dopo una riga | Il pulsante per uscire | Tornare alla pagina «Accedi» |

**«Profilo»:**

- **«Appartamenti»** dice quali appartamenti vedi: «tutti gli appartamenti», i nomi, «… appartamenti» oppure
  «nessun appartamento».
- **«Lingua»** dice «Italiano», l'unica lingua disponibile: non c'è nulla da scegliere.
- **Durante un accesso di assistenza** il profilo mostra l'organizzazione assistita.

**«Nome visualizzato»**, in fondo al «Profilo»:

- **Il campo** (al massimo 80 caratteri) e «Salva»; compare «Nome aggiornato».
- **È il nome** che vedono i colleghi nelle Decisioni, nelle approvazioni, nei registri e in fondo al menu.

### Impostazioni: password ed email

**Cambiare la password o l'indirizzo con cui entri.**

Il riquadro «Password ed email» c'è solo per chi entra con email e password.

1. **«Cambia password»** chiede «Password attuale», «Nuova password» e «Ripeti la nuova password» (almeno 8
   caratteri); compare «Password cambiata».
2. **«Email di accesso»** spiega «Oggi accedi con …. Il nuovo indirizzo diventa attivo quando apri il link che ti
   mandiamo lì.».
3. **Per cambiare email** compila «Nuova email» e «Password attuale», premi «Cambia email» e apri il link nella nuova
   casella.
4. **Intanto leggi** «Link inviato a …: aprilo per completare il cambio».

> **Da sapere**
>
> - **Chi entra con Google** legge «Accedi con Google: password ed email si gestiscono dal tuo account Google.».
> - **Il ruolo di gestore della piattaforma** è legato all'email: dopo un cambio di email va riassegnato da HQE.

### Impostazioni: sicurezza

**Uscire da tutti i dispositivi o eliminare il proprio account.**

**«Esci da tutti i dispositivi»:**

1. **La spiegazione**: «Chiude la sessione su tutti i telefoni e computer, compreso questo. Su ogni dispositivo
   dovrai accedere di nuovo.».
2. **Chiede** «Uscire da tutti i dispositivi?».
3. **Conferma** con «Sei uscito da tutti i dispositivi».

**«Elimina il mio account»:**

1. **La spiegazione**: «Elimina il tuo account e il tuo accesso all'app. L'operazione non si può annullare.».
2. **Chiede conferma** con «Eliminare definitivamente il tuo account?».
3. **Spiega**: «Vengono cancellati il tuo accesso, il tuo nome, la tua email e le tue preferenze di notifica. Resta
   quello che hai fatto (decisioni, approvazioni, registro attività), ma al posto del tuo nome comparirà «utente
   rimosso». Per rientrare servirà un nuovo invito.».
4. **Alla fine** compare «Account eliminato».

> **Attenzione**
>
> - **L'ultimo amministratore** non può eliminare l'account: «Sei l'unico amministratore: nomina un altro
>   amministratore prima di eliminare il tuo account».
> - **L'ultimo gestore della piattaforma** nemmeno: «Sei l'ultimo gestore della piattaforma: nomina un altro
>   gestore prima di eliminare il tuo account».
> - **Nell'ambiente di prova** l'eliminazione toglie le autorizzazioni di prova e conserva l'identità di accesso
>   condivisa con il sito vero; nel sito vero cancella anche quella.

### Impostazioni: notifiche e uscita

**Scegliere per categoria quali avvisi ricevere sul telefono.**

Il riquadro «Notifiche» ha quattro interruttori:

| Interruttore | Spiegazione nell'app |
|---|---|
| «Approvazioni richieste» | «Quando il motore chiede il tuo consenso» |
| «Dispositivi e sistema domotico offline» | «Dispositivo offline oltre la soglia della regola, sistema domotico non raggiungibile, antigelo non attivo» |
| «Prenotazioni» | «Avvisi sulle prenotazioni che cambiano il programma dell'appartamento» |
| «Riepilogo» | «Ogni lunedì, solo se la settimana ha qualcosa da segnalare» |

- **Sono tutti attivi** dall'inizio.
- **Ogni cambio** mostra «Preferenze salvate»; se non riesce, l'interruttore torna com'era.
- **Le scelte valgono** per le notifiche sul telefono: gli avvisi dentro l'app compaiono comunque.
- **Sotto** c'è l'attivazione sul dispositivo (vedi «Notifiche sul telefono»).
- **Il riquadro non compare** a un gestore della piattaforma senza organizzazione: le notifiche sono legate agli
  appartamenti.

**«Esci», in fondo:**

- **Torni** alla pagina «Accedi».
- **I tuoi dati** e le conversazioni con l'assistente vengono tolti da quel dispositivo.
- **Le notifiche** su quel dispositivo si spengono. Se rientri tu, si riaccendono da sole.

> **Da sapere**
>
> Un gestore della piattaforma che non fa parte di nessuna organizzazione vede i riquadri «Profilo» e «Sicurezza»,
> ma il salvataggio del nome e «Esci da tutti i dispositivi» rispondono «Account non abilitato: mancano tenant o
> ruolo»; «Elimina il mio account» funziona.

### Notifiche sul telefono

**Attivare le notifiche push su ogni dispositivo che usi.**

Le notifiche arrivano anche ad app chiusa, se le attivi su quel dispositivo.

1. **Apri** «Impostazioni» › «Notifiche», riquadro «Notifiche push su questo dispositivo».
2. **Premi «Attiva su questo dispositivo»** e consenti le notifiche quando il telefono o il browser lo chiede.
3. **Leggi** «Notifiche attive su questo dispositivo». «Dispositivi registrati: …» conta i tuoi dispositivi con le
   notifiche accese.
4. **Per fermarle** su quel dispositivo premi «Disattiva»: leggi «Notifiche disattivate su questo dispositivo».

**Se qualcosa non va:**

| Cosa vedi | Quando |
|---|---|
| «Permesso non concesso: su questo dispositivo le notifiche restano spente.» | Hai rifiutato il permesso |
| «Le notifiche per questo sito sono bloccate. Per riceverle consenti le notifiche nelle impostazioni del browser o del telefono, poi torna qui.» | Le notifiche sono bloccate dal telefono o dal browser |
| «Le notifiche su questo dispositivo sono state tolte dalle impostazioni del browser o del telefono. Premi «Attiva su questo dispositivo» per riattivarle.» | Le hai tolte dopo averle attivate |
| «Su iPhone e iPad le notifiche arrivano solo all'app installata: aggiungila alla schermata Home (vedi «Installa l'app» qui sotto), aprila dall'icona e attivale da qui.» | Su iPhone e iPad hai aperto il sito da Safari: le notifiche arrivano solo all'app installata |
| «Questo browser non può ricevere notifiche push: gli avvisi compaiono in alto nello schermo mentre l'app è aperta sulla pagina di un appartamento.» | Il browser non può ricevere notifiche |
| «Notifiche sul telefono non attive in questo ambiente» e «Gli avvisi compaiono in alto nello schermo mentre l'app è aperta sulla pagina di un appartamento.» | L'ambiente non ha le notifiche sul telefono |

### Cosa succede quando tocchi una notifica

**Ogni notifica apre la pagina giusta; uscita e rientro.**

- **Toccando una notifica** si apre l'app sulla pagina giusta: «Approvazioni», la «Panoramica» dell'appartamento,
  le «Decisioni» (prenotazione annullata, antigelo non attivo) o il riepilogo della settimana.
- **Se l'app è già aperta**, la notifica compare come avviso in alto con il pulsante «Apri» (su iPhone arriva
  comunque come notifica del telefono).
- **Se stai già guardando quell'appartamento** non compare un secondo avviso.
- **Se non sei collegato**, prima devi accedere e poi aprire la pagina da solo.

**Uscita e rientro:**

- **La scheda ricorda**: «Quando esci da questo dispositivo le notifiche si spengono; quando rientri tu, si
  riaccendono da sole.».
- **Al rientro leggi** «Notifiche riattivate su questo dispositivo, come prima della tua uscita.».
- **Se il browser non dà più il permesso** leggi «Notifiche non riattivate: il browser non ne dà più il permesso.
  Puoi riattivarle da Impostazioni › Notifiche.».
- **Non si riaccendono** se le avevi spente tu con «Disattiva».
- **Un'altra persona** che accede dallo stesso telefono non riceve le tue notifiche e non vede nulla della tua
  sessione.
- **Un calo di rete** non le spegne.

### Le notifiche che puoi ricevere

**L'elenco delle notifiche: quando arrivano e dove portano.**

Tutte hanno il nome dell'appartamento davanti.

| Categoria | Notifica | Quando arriva | Dove porta |
|---|---|---|---|
| «Approvazioni richieste» | «…: approvazione richiesta», con la proposta oppure «Il motore chiede il tuo consenso» | Quando il motore apre una richiesta (non per quelle in coda dietro un'altra) | «Approvazioni» |
| «Dispositivi e sistema domotico offline» | «…: dispositivo offline», «… non risponde da oltre … minuti» | Dopo i minuti della regola «Avviso dispositivo offline» (15 all'inizio); regola spenta, niente avviso | «Panoramica» |
| «Dispositivi e sistema domotico offline» | «…: sistema domotico non raggiungibile», «Il connettore domotico risulta fermo» | Sistema domotico fermo oltre la stessa soglia; una volta per episodio | «Panoramica» |
| «Dispositivi e sistema domotico offline» | «…: antigelo non attivo», «Sensore di temperatura mancante: antigelo non attivo» | A casa vuota, caldaia senza sensore utilizzabile; subito, una volta per episodio | «Decisioni» |
| «Prenotazioni» | «…: prenotazione annullata, appartamento rimesso a vuoto» | Disdetta dopo che l'appartamento era già stato preparato per l'arrivo | «Decisioni» |
| «Riepilogo» | «…: riepilogo della settimana», con la prima segnalazione e «E altre … voci.» | Il lunedì mattina, solo se la settimana ha qualcosa da segnalare | Il riepilogo di quella settimana |

> **Da sapere**
>
> - **Le notifiche arrivano** solo per gli appartamenti che vedi.
> - **Un gestore della piattaforma** in accesso di assistenza non riceve quelle dell'organizzazione assistita.

### Uscire

**«Esci» chiude la sessione su quel dispositivo.**

«Esci» è nel menu e in fondo alle Impostazioni.

- **Chiude la sessione** su quel dispositivo.
- **Toglie dalla scheda** i tuoi dati e le conversazioni con l'assistente.
- **Spegne le notifiche** su quel dispositivo.
- **Se eri in un accesso di assistenza**, lo chiude.
- **Per chiudere tutte le sessioni** usa «Esci da tutti i dispositivi» nelle Impostazioni.
## 3. Chi può fare cosa

**I quattro ruoli e l'accesso di assistenza, a confronto.**

| Ruolo | Pagine che vede | Che cosa può fare |
|---|---|---|
| «Sola lettura» | «Appartamenti», «Impostazioni», tutte le pagine dell'appartamento tranne «Simulatore» | Guardare tutto, scaricare i rendiconti Excel, gestire il proprio account e le proprie notifiche. Non comanda, non approva, non scrive all'assistente. |
| «Operatore» | Come sola lettura | In più: cambiare modalità, forzare, comandare i dispositivi, approvare, programmare, cambiare le regole, usare l'assistente. |
| «Amministratore» | Come l'operatore, più «Amministrazione» e «Simulatore» sui dimostrativi | In più: invitare e gestire gli utenti, nome e indirizzo degli appartamenti, funzioni, prezzi, copia delle regole, Simulatore. Vede tutti gli appartamenti dell'organizzazione. |
| «Gestore della piattaforma» (HQE) | «Organizzazioni», «Impostazioni» e, se fa parte anche di un'organizzazione, le pagine del suo ruolo lì | Crea le organizzazioni e i loro primi amministratori, nomina altri gestori, crea e collega gli appartamenti, sospende e riattiva, apre accessi di assistenza. Da solo non vede dispositivi, consumi, decisioni né utenti. |
| Accesso di assistenza | «Appartamenti», «Organizzazioni», «Impostazioni» e tutte le pagine dell'appartamento | Un gestore della piattaforma dentro un'organizzazione per 1–24 ore, con i permessi di un operatore, su tutti i suoi appartamenti. |

> **Da sapere**
>
> - **Gli operatori e chi ha sola lettura** vedono solo gli appartamenti che l'amministratore ha assegnato loro
>   (oppure tutti, se così impostato).
> - **Gli amministratori** vedono sempre tutti.

## 4. Sola lettura: che cosa vedi

**Le pagine come le vede chi può solo leggere: valgono per tutti.**

Chi ha il ruolo «Sola lettura» vede le stesse pagine dell'operatore.

- **I pulsanti che cambiano qualcosa** sono disattivati e, passandoci sopra, compare «Il tuo ruolo consente solo la
  lettura».
- **Questa parte descrive** che cosa c'è in ogni pagina: vale anche per operatori e amministratori.

### Appartamenti: che cosa vedi

**La prima schermata: una scheda per ogni appartamento, con stato e dati.**

La prima schermata, «Appartamenti», mostra «… appartamenti» e una scheda per appartamento.

| Cosa vedi | Cosa vuol dire |
|---|---|
| In alto: nome e indirizzo; a destra la pillola dello stato | «Online» (verde), «Non raggiungibile» oppure «Disattivato» (tortora) |
| «Dimostrativo» accanto al nome | Un appartamento finto usato per le prove |
| La striscia dei dati: «Modalità», nel colore della modalità | Comfort (arancione chiaro), Eco (verde salvia) o Casa vuota (azzurro ardesia) |
| «Occupazione», a fondo pieno | «Vuoto» (tortora: nessuno), «Occupato» (verde: ospiti dentro, dopo il check-in effettivo), «Prenotato» (ambra: c'è una prenotazione ma non è stato comunicato l'arrivo) |
| «Consumo di oggi», con il numero in arancione | Il consumo di oggi in kWh, non un importo |
| «Prossimo check-in», «Prossimo check-out» | I prossimi arrivo e partenza; «Prossimo check-out» occupa tutta la larghezza |
| In fondo, «1 approvazione in attesa» o «… approvazioni in attesa» con una freccia | Le richieste che aspettano una risposta; la riga non c'è se non ce ne sono |

- **I dati si aggiornano** ogni 20 secondi; un valore mancante è un trattino.
- **Una scheda offline** non è grigia: lo dicono la pillola e i dati scritti in grigio; la striscia perde i colori.
- **Tocca una scheda** per aprire l'appartamento («Apri …»).

**Quando l'elenco è vuoto o l'appartamento non si apre:**

| Cosa vedi | Cosa vuol dire | Cosa fare |
|---|---|---|
| «Nessun appartamento configurato» con «Per un nuovo appartamento scrivi all'assistenza HQE.» | Non c'è nessun appartamento (messaggio per gli amministratori) | Scrivi all'assistenza HQE |
| «Nessun appartamento configurato» con «Per un nuovo appartamento rivolgiti a un amministratore della tua organizzazione.» | Non c'è nessun appartamento (messaggio per operatori e lettori) | Rivolgiti a un amministratore |
| «Nessun appartamento assegnato al tuo account» e «Chiedi a un amministratore di assegnartene uno.» | L'amministratore non ti ha assegnato appartamenti: il tuo account esiste ancora | Chiedi a un amministratore |
| «Appartamento non disponibile», «Non esiste o non è tra quelli assegnati al tuo account.» e il pulsante «Torna agli appartamenti» | Hai aperto l'indirizzo di un appartamento che non puoi vedere | Premi «Torna agli appartamenti» |
| Il pulsante «Appartamento» | Sei un gestore della piattaforma con una propria organizzazione | Apre Organizzazioni (parte 7) |

### Panoramica: che cosa vedi

**Lo stato dell'appartamento in tempo reale: salute, modalità, dispositivi.**

| Zona della pagina | Cosa vedi | Cosa vuol dire |
|---|---|---|
| In alto | Il nome e «In tempo reale» | La pagina si aggiorna da sola |
| In alto | «Riconnessione…» | Sta ricollegandosi: non prendere per buono un valore vecchio |
| La striscia di salute | «In salute», «Degradata» o «Ferma», poi «… dispositivi connessi» | Lo stato del sistema domotico e il collegamento con i dispositivi |
| La striscia di salute | «Dettagli tecnici» | Apre «Connettore» («attivo» o «fermo»), «Modello», «Versione» con il contratto e «Ultimo evento» |
| La striscia di salute | «Sistema domotico non raggiungibile» | Il sistema domotico non risponde |
| La striscia di salute | «Versione del contratto non compatibile» e «Il sistema domotico dichiara il contratto …: questa app supporta solo la versione 1.x. Contatta il supporto tecnico.» | La versione del sistema non è compatibile |
| La fascia di stato | Sei caselle: «Modalità», «Occupazione», «Prossimo check-in» o «Prossimo check-out», «Finestre», «Consumo di oggi», «Dispositivi online» | Come sta la casa adesso (tabella sotto) |
| «Modalità» | La scelta fra Comfort, Eco e Casa vuota: quella in corso ha il colore della modalità (tabella sotto) | La modalità in corso |
| «Forza per…» | «Forzatura … attiva fino alle …» e «ancora …», in un riquadro ambra | C'è una forzatura in corso |
| «Dispositivi» | I dispositivi raggruppati per stanza («Senza stanza» per quelli senza); accanto al nome della stanza, in grigio, quanti sono | Vedi le tabelle sotto |

**La fascia di stato, casella per casella:**

| Casella | Cosa vedi | Di che colore è |
|---|---|---|
| «Modalità» | Comfort, Eco o Casa vuota; durante una forzatura, sotto, «forzata fino alle …» | Il colore della modalità: Comfort arancione chiaro, Eco verde salvia, Casa vuota azzurro ardesia |
| «Occupazione» | «Vuoto», «Occupato» o «Prenotato» | «Occupato» verde, «Prenotato» ambra, «Vuoto» tortora |
| «Prossimo check-in» o «Prossimo check-out» | Il primo fra arrivo e partenza; senza nessuno dei due, «Prossimo evento» con un trattino | Bianca |
| «Finestre» | «Tutte chiuse», «1 aperta» o «… aperte» con le stanze sotto; senza sensori, un trattino e «Nessun sensore» | Verde se sono tutte chiuse, ambra se una è aperta; bianca senza sensori |
| «Consumo di oggi» | I kWh di oggi; un trattino se la funzione Consumi è spenta | Bianca, con il numero in arancione |
| «Dispositivi online» | Quanti rispondono, per esempio 5/6; sotto, «… offline» se qualcuno manca | Verde se rispondono tutti, ambra se qualcuno è offline |

> **Da sapere**
>
> - **Le caselle che chiedono attenzione** (una finestra aperta, un dispositivo offline) sono ambra; verdi quando tutto è
>   a posto.
> - **Su computer** (da 1024 px) ogni stanza è un elenco con una riga per dispositivo; sul telefono e sul tablet
>   ogni dispositivo è una scheda.

**Che cosa mostra ogni dispositivo:**

| Dispositivo | Cosa vedi |
|---|---|
| Prese e interruttori | «Acceso» o «Spento» |
| Caldaia | «Riscaldamento abilitato» o «Riscaldamento disabilitato»; se il suo misuratore segna più di 30 W, «sta scaldando ora» |
| Climatizzatore | Acceso o spento |
| Climatizzatore, «Modo» | Una tendina con Caldo, Freddo, Deumidifica, Ventilazione |
| Climatizzatore, «Ventola» | Una tendina con Auto, Bassa, Media, Alta |
| Climatizzatore, «Temperatura» | La temperatura desiderata con «da … a … °C» |
| Misuratore di consumo | Una riga «Potenza» con i W (quanto consuma adesso) e, sotto, «Oggi» con i kWh di oggi |
| Sensori | Una riga «Temperatura» e una «Umidità», con il valore a destra (per esempio 16,9 °C) |
| Contatto finestra | «Aperta» o «Chiusa» «da …» |
| Sensore di movimento | «Movimento rilevato» o «Nessun movimento» (passando sopra leggi la data precisa) |

**Casi particolari:**

- **Un dispositivo che non risponde** ha il badge «Dispositivo offline» sotto il nome, con «Visto …» e, passando
  sopra, «Il dispositivo non è raggiungibile: i comandi sono disattivati»; la scheda non è sbiadita.
- **Una capacità che l'app non gestisce** è segnata «non supportata» («Capacità non gestita dall'app: …»).
- **Senza dispositivi** leggi «Nessun dispositivo in questo appartamento».

### Panoramica: l'esito sotto ogni comando

**Come leggere se un comando è riuscito, e perché no.**

- **Gli stati**: «in corso», «eseguito», «errore» o «nessuna risposta».
- **Il motivo**, se c'è (tabella sotto), e un «ID richiesta» copiabile.
- **Un climatizzatore comandato a infrarosso** può risultare «non verificato» («Lo split non conferma l'esecuzione:
  lo stato mostrato è quello richiesto»).

| Motivo | Cosa vuol dire |
|---|---|
| «dispositivo offline» | Il dispositivo è offline |
| «rifiutato dal dispositivo» | Il dispositivo non ha accettato il comando |
| «bloccato da una regola» | Una regola (per esempio finestra aperta o pausa del compressore) ha bloccato il comando |
| «bloccato da un'azione prioritaria» | Un'azione più importante ha bloccato il comando |
| «fuori dai limiti» | Temperatura fuori dai limiti |
| «nessuna conferma» | Il comando è partito ma non è stato confermato |
| «errore interno» | Un errore del sistema domotico |

> **Da sapere**
>
> Mentre guardi un appartamento possono comparire avvisi in alto: «Nuova approvazione richiesta», «… è offline»,
> «Sistema domotico non raggiungibile», «Sistema domotico di nuovo raggiungibile». Compaiono anche se hai spento la
> categoria nelle notifiche.

### Approvazioni: che cosa vedi

**Le richieste che il motore esegue solo con il tuo consenso.**

«Approvazioni» («Azioni che il motore esegue solo con il tuo consenso») elenca le richieste.

| Cosa vedi | Cosa vuol dire |
|---|---|
| La pillola «In attesa» (la scelta è scritta in scuro) | Le richieste aperte |
| La pillola «Tutte» | Anche quelle decise negli ultimi 7 giorni |
| In alto: lo stato, poi chi la propone e la data | «In attesa», «Approvata», «Respinta», «Scaduta»; «Motore AI», «Regola», «Assistente», «Modulo» |
| La descrizione, in grande | Che cosa chiede |
| «Perché il motore lo propone», con il testo sotto | Il motivo, senza riquadro |
| «Azione proposta» seguita dall'azione in grassetto | Che cosa partirà |
| «… rimasti» (in rosso sotto i 5 minuti) oppure «scaduta» | Quanto tempo resta per decidere |
| Accanto: «Alla scadenza verrà respinta», «Alla scadenza verrà eseguita» o «Alla scadenza resta in attesa» | Cosa succede se nessuno decide |
| Sotto una riga: «Nota (facoltativa)» e i pulsanti | Solo nelle richieste in attesa, per chi può decidere |
| In fondo: «Approvata da … …» o «Respinta da … …» con la nota, poi l'«ID richiesta» | Solo nelle richieste già decise o scadute |
| «Nessuna approvazione in attesa» o «Nessuna approvazione negli ultimi 7 giorni» | Non c'è nulla |

> **Da sapere**
>
> - **La pagina si aggiorna** ogni 30 secondi.
> - **C'è una sola richiesta aperta per volta**: le altre aspettano in coda e si aprono dopo.

### Decisioni: che cosa vedi

**Lo storico dell'appartamento: chi ha fatto cosa, perché, con quale esito.**

«Decisioni» («Tutto ciò che il motore e i gestori hanno fatto, e perché») è lo storico dell'appartamento, conservato
per 24 mesi.

| Ogni voce mostra | Valori possibili |
|---|---|
| Prima linea, in nero: il tipo di azione e i valori prima → dopo | Per esempio «Modalità» con «comfort → casa vuota» |
| Il tipo di azione, in italiano | Per esempio «Modalità», «Forzatura scaduta», «Programma: spostata», «Prenotazione annullata» |
| Altri esempi di tipo | «Disdetta dopo il pre-arrivo», «Antigelo: caldaia accesa», «Regolazione automatica disattivata», «Antigelo non attivo» |
| A destra della prima linea: l'esito, in un badge colorato | «Applicata» verde; «Respinta» e «Non riuscita» rosso mattone; «in attesa di approvazione» ambra; «Informativa» tortora |
| Seconda linea, in grigio: la data · chi ha deciso · su cosa | «Motore AI», «Regola «…»», «Gestore», «Assistente», «Sistema»; «appartamento», «dispositivo», «regole», «programmazione» |
| Chi ha deciso, se ha eliminato l'account | «utente rimosso» |
| Sotto: il motivo | Perché è successo |
| L'«ID richiesta» copiabile | L'identificativo dell'operazione |
| «Dettagli» | Apre «Comando» e «Approvazione» con i codici tecnici; c'è solo se ci sono |

- **Passando sopra il tipo** compare il codice tecnico.
- **Un'azione nuova** non ancora tradotta mostra il codice.
- **Non ci sono icone**: chi ha deciso si legge nella seconda linea.

**Tipi da conoscere:**

| Tipo | Cosa vuol dire |
|---|---|
| «Collegamento ai dispositivi perso» | Il sistema non parla più con i dispositivi: i comandi vengono rifiutati finché non torna |
| «Collegamento ai dispositivi ripristinato» | Il collegamento è tornato |
| «Comando non verificato: misuratore offline» | Il comando al climatizzatore è partito ma il misuratore che lo conferma non risponde |
| «Finestra: regola sospesa» | La regola della finestra è sospesa durante una forzatura |

> **Da sapere**
>
> Le accensioni e gli spegnimenti ordinari del termostato della caldaia non sono tutti registrati: trovi quelli
> dell'antigelo e i problemi del sensore.

### Decisioni: filtri e ricerca

**Trovare una decisione per periodo, autore, dispositivo o parola.**

**I filtri:**

- **«Chi»**, **«Dispositivo»** («Tutti i dispositivi») e **«Periodo»** («Tutto lo storico», «Ultimi 7 giorni»,
  «Ultimi 30 giorni», «Ultimi 90 giorni»). Si combinano.
- **Sul telefono** le tre tendine si aprono con il pulsante «Filtri», che diventa «Filtri (…)» con il numero dei
  filtri attivi.
- **La ricerca** occupa una riga intera.
- **«Carica altri»** mostra le righe precedenti.
- **Se nulla corrisponde**: «Nessuna decisione per i filtri scelti».

**La ricerca per parole:**

1. **Scrivi** nel campo «Cerca parole o un ID richiesta…».
2. **La ricerca guarda** nel motivo, nell'azione, in chi ha deciso, nel dispositivo, nei valori e nei codici, a
   blocchi di 1.000 decisioni dalle più recenti.
3. **Leggi** «Ricerca in corso…», poi «Risultati: … · cercato fino al … (… decisioni esaminate)».
4. **Premi «Cerca più indietro»** per continuare.
5. **Alla fine leggi** «Risultati: … · cercato in tutto lo storico disponibile (… decisioni esaminate)».

> **Da sapere**
>
> - **Oltre 3.000 risultati** compare «Raggiunti … risultati: restringi la ricerca con Periodo, Chi o
>   Dispositivo.».
> - **Le decisioni nuove** non entrano in una ricerca già iniziata: cancella la parola per vedere l'elenco
>   aggiornato.

**La ricerca per «ID richiesta»:**

- **Incolla l'identificativo completo** copiato da un errore: la ricerca ignora i filtri e guarda tutto lo storico in
  un colpo solo («Ricerca per ID richiesta in tutto lo storico · risultati: …»).
- **Un pezzo dell'identificativo** fa invece una ricerca di parole.

### Consumi: che cosa vedi

**I kWh misurati ora per ora, per periodo e per dispositivo.**

«Consumi» («Energia elettrica misurata dai dispositivi») mostra i kWh misurati dai misuratori, ora per ora.

| Cosa vedi | Cosa puoi fare | Cosa succede |
|---|---|---|
| Il periodo: «Oggi» (da mezzanotte), «7 giorni», «30 giorni» (compreso oggi) oppure «Soggiorno in corso» | Toccare una delle pillole: la scelta è scritta in scuro | «Soggiorno in corso» compare solo con ospiti dentro e una prenotazione conosciuta dall'app |
| La casella «Totale periodo» in «kWh», con il numero in arancione | Leggere il totale | I numeri si aggiornano ogni minuto |
| La casella «Ora con più consumo» (oggi) o «Giorno con più consumo» (periodi più lunghi) | Leggere il picco | Sotto il valore, «ore …» oppure la data |
| La casella «Ore di clima evitate» | Leggere le ore | Compare solo quando il motore le calcola; oggi non compare |
| Il grafico «Consumo per ora (kWh)» (oggi) o «Consumo per giorno (kWh)» (periodi più lunghi) | Passare con il puntatore: leggi «ore …» e i kWh | Le ore senza letture contano zero. Senza dati: «Nessun dato nel periodo» |
| «Per dispositivo» | Leggere il consumo di ogni dispositivo | Lo stesso periodo, diviso per dispositivo |
| «Consumi disponibili dal …», sotto il grafico | Sapere da quando ci sono misure | È la prima ora con un consumo maggiore di zero. Senza nessun dato la riga non compare |

> **Da sapere**
>
> Nei dimostrativi i consumi prima dell'avvio sono un profilo di esempio dal 1° gennaio 2026.

**Con «Soggiorno in corso»:**

- **Leggi** «Dal check-in del … a ora» e «… ospiti», con il pulsante «Excel del soggiorno».
- **Se c'è un soggiorno precedente** conosciuto dall'app, sotto le caselle compare una riga: la percentuale, poi
  «rispetto al soggiorno precedente (… → …, … kWh)» e «… ospiti».
- **Accanto** c'è il pulsante «Excel del soggiorno precedente».
- **La percentuale è in rosso** solo se il consumo è aumentato.
- **Il confronto** è fra i totali, senza correggere per durata o numero di ospiti; se il precedente era zero non c'è
  percentuale.
- **Un soggiorno molto lungo** (oltre 31 giorni) può non mostrare il grafico: «Periodo non valido: massimo 31 giorni
  per richiesta».

### Consumi: il rendiconto in Excel

**Scaricare i consumi di un mese o di un soggiorno in Excel.**

«Rendiconto in Excel» è per tutti i ruoli: «Consumi del mese scelto: riepilogo, giorno per giorno, ora per ora e per
dispositivo, con l'importo in euro se è impostato il prezzo per kWh.».

1. **Scegli «Mese del rendiconto»** (gli ultimi 12, compreso quello in corso).
2. **Premi «Scarica Excel»**.
3. **Apri il file**: ha i fogli «Riepilogo», «Giornaliero», «Orario» e «Dispositivi».

- **L'importo** è kWh per il prezzo dell'appartamento o dell'organizzazione; senza prezzo il file dice «prezzo non
  impostato».
- **«Excel del soggiorno»** (nel soggiorno in corso e nel confronto) è il rendiconto dall'ora esatta di arrivo a
  quella di partenza (o a ora), con identificativo del soggiorno, numero di ospiti e stato, senza nomi o contatti
  degli ospiti; al massimo un anno.

**Come il file spiega i buchi nei dati:**

| Cosa leggi nel file | Cosa vuol dire |
|---|---|
| «Consumi disponibili dal», in testa | Da quando ci sono misure: le ore precedenti restano vuote (non a zero) |
| «…: ore precedenti vuote», «…: nessun dato nel periodo» | Spiegano un buco nei dati |
| «Periodo in corso: i dati arrivano fino al momento della generazione» | Il periodo non è ancora finito |
| «Nessun consumo misurato finora» | Non c'è nessuna misura |

### Riepiloghi: che cosa vedi

**Il riepilogo di ogni settimana, pronto il lunedì mattina.**

«Riepiloghi» («Il riepilogo di ogni settimana, pronto il lunedì mattina») c'è sempre, anche senza la funzione
Consumi.

| Cosa vedi | Cosa vuol dire |
|---|---|
| «Settimana dal … al …» con «… segnalazioni», «1 segnalazione» o «Nessuna novità» | L'elenco delle settimane, dalla più recente |
| «Nessun riepilogo ancora. Ogni lunedì mattina arriva quello della settimana appena finita.» | Non c'è ancora nessun riepilogo |
| «Riepilogo della settimana», «calcolato il …», le frasi già pronte oppure «Settimana senza novità» | Una settimana aperta |
| «Tutti i riepiloghi» | Torna all'elenco |

- **L'elenco mostra** al massimo 20 settimane; i riepiloghi restano conservati 12 mesi.

**Il riquadro «Consumi a parità di occupazione»** («kWh per notte confrontati con la mediana delle stesse notti
nelle 4 settimane prima»):

- **«Notti con ospiti» e «Notti vuote»** con «… notti», «… per notte», «mediana prima …».
- **Lo stato**: «Nella norma», «Alto», «Confronto non disponibile» o «Nessuna notte».
- **«Per dispositivo»**: il dettaglio per dispositivo.
- **«Alto»** vuol dire almeno il 30 % sopra il valore tipico delle 4 settimane prima e almeno 5 kWh in più.
- **Nelle prime 5 settimane** di misure vere leggi «dati insufficienti: servono 5 settimane di consumi veri», con
  «, disponibili dal …».

**Le segnalazioni:**

| Segnalazione | Quando compare |
|---|---|
| «… è offline da più di 24 ore.» | Un dispositivo offline (non semplicemente spento) da più di 24 ore |
| «Approvazione scaduta senza risposta: ….» | Una richiesta scaduta senza risposta |
| «… aperta … volte con il clima spento dalla regola.» | Una finestra aperta almeno 3 volte nella settimana |

> **Da sapere**
>
> - **Il riepilogo si prepara** ogni lunedì dalle 8 del mattino, ora dell'appartamento; il controllo passa ogni
>   ora, quindi può arrivare un po' dopo le 8.
> - **Se il sistema domotico non risponde**, riprova al giro dopo.
> - **La notifica «Riepilogo»** parte solo se c'è almeno una segnalazione: apri la pagina anche senza notifica.

### Programmazione: che cosa vedi

**Le azioni pianificate dal motore e dal gestore, future e passate.**

«Programmazione» («Azioni pianificate dal motore e dal gestore») ha due riquadri a righe, «In programma» e
«Storico» (con sotto «Ultimi 7 giorni»), con aggiornamento ogni 30 secondi.

| Ogni riga mostra | Valori possibili |
|---|---|
| A sinistra, l'orario | Ora dell'appartamento |
| Poi l'azione | Che cosa farà |
| Sotto, in grigio, tipo e origine | «pre-arrivo», «check-out», «casa vuota», «manuale» · «prenotazione», «gestore», «assistente» |
| A destra, lo stato e i pulsanti | «In programma», «Eseguita», «Annullata», «Non riuscita» |

- **Passando sopra tipo e origine** leggi il codice della prenotazione, se l'azione nasce da una prenotazione.
- **Senza azioni**: «Nessuna azione in programma».
- **Le azioni nate da una prenotazione** hanno la nota «Ricalcolata a ogni modifica della prenotazione».

### Regole: che cosa vedi

**Le otto regole del motore, con interruttore, valori e limiti.**

«Regole» («Automatismi del motore: attiva, disattiva e regola i parametri entro i limiti») mostra le otto regole.

| Cosa vedi | Cosa vuol dire |
|---|---|
| Interruttore, descrizione, valori e limiti «da … a …» | Ogni regola con i suoi parametri |
| «Ultima modifica …» | Quando è stata cambiata |
| «Non modificabile» («Questa regola è fissata dal motore: puoi solo vederla») | La regola «Pausa minima del compressore» si può solo vedere |

- **Fino a 1024 px** (telefono e tablet) le regole stanno in una colonna; su schermi più larghi in due.
- **Sotto l'elenco**, per chi può modificare, ci sono «Chiedi all'assistente» e, per gli amministratori, «Applica
  le stesse regole ad altri appartamenti».
- **Le regole**, i loro valori e che cosa fanno davvero sono nella parte 10.
- **Gli operatori e gli amministratori** possono anche modificarle (parte 5).

### Assistente per chi ha sola lettura

**La chat si vede, ma non si può scrivere.**

- **La pagina «Assistente»** compare anche a chi ha sola lettura, se la funzione è attiva.
- **Non si possono inviare richieste** e non si vedono le domande dei colleghi: il server le rifiuta.
- **Resta visibile** solo una conversazione eventualmente già presente in quella scheda del browser.

### Il tuo account

**Anche in sola lettura gestisci tutto quello che riguarda te.**

- **Nome, password, email**, notifiche, installazione, uscita da tutti i dispositivi ed eliminazione dell'account:
  vedi la parte 2, «Impostazioni».
## 5. Operatore: che cosa puoi fare

**Tutto quello della parte 4, più i comandi.**

L'operatore vede tutto quello della parte 4 e in più comanda. Le stesse cose le fa anche l'amministratore e chi
lavora con un accesso di assistenza.

### Panoramica: cambiare modalità

**Scegliere comfort, eco o casa vuota con un tocco.**

1. **Sotto «Modalità»** tocca Comfort, Eco o Casa vuota.
2. **La scelta prende il colore della modalità** (tabella sotto) quando il sistema conferma (non c'è un avviso verde).
3. **Nelle Decisioni** compare «Modalità» con prima e dopo, per esempio «comfort → casa vuota».

| Modalità | Colore | In breve (i dettagli nella parte 10) |
|---|---|---|
| comfort | Arancione chiaro | Scalda alla temperatura di comfort |
| eco | Verde salvia | Abbassa la caldaia e spegne il clima |
| casa vuota | Azzurro ardesia | Spegne il clima e tiene solo l'antigelo |

> **Attenzione**
>
> - **I comandi partono** solo ai dispositivi online.
> - **Il cambio di modalità non garantisce** che ogni singolo comando riesca: controlla gli esiti sotto i
>   dispositivi e le Decisioni.
> - **Un cambio di modalità fatto a mano** non chiede conferma, anche con ospiti dentro.

### Panoramica: forzare per un po'

**Bloccare gli automatismi per 30 minuti, 2 ore o 6 ore.**

1. **Sotto «Forza per…»** premi «30 min», «2 h» o «6 h».
2. **Se c'è una finestra aperta**, prima di partire l'app avvisa con «Finestra aperta» e «Finestra aperta in …:
   durante la forzatura il clima resta acceso.» (o «Finestre aperte in …: …»): scegli «Forza comunque» o «Annulla».
3. **Compare** «Forzatura … attiva fino alle …» con «ancora …» e il pulsante «Annulla forzatura».

**Che cosa fa la forzatura:**

- **Tiene la modalità attuale** e sospende gli automatismi del comfort.
- **La regola della finestra aperta** non spegne il clima (nelle Decisioni «Finestra: regola sospesa», con l'ora in
  cui riparte).
- **La regolazione automatica del clima** si ferma.
- **Un cambio di modalità programmato** (per esempio il check-out) aspetta la fine della forzatura (nelle Decisioni
  «Azione rimandata», «rimandata per la forzatura»).
- **L'antigelo** resta attivo.

**Quando finisce:**

- **Alla scadenza** («Forzatura scaduta» nelle Decisioni) o con «Annulla forzatura» («Forzatura annullata») le
  regole ripartono.
- **Se la finestra è ancora aperta** oltre la soglia, il clima si spegne subito.

### Panoramica: comandare i dispositivi

**Accendere, spegnere e regolare i dispositivi online.**

I comandi funzionano solo sui dispositivi online e con la funzione «Comandi» attiva.

| Dispositivo | Cosa puoi fare | Cosa succede |
|---|---|---|
| Prese e interruttori | Tocca l'interruttore («Accendi …» / «Spegni …») | Lo stato diventa «Acceso» o «Spento» |
| Caldaia | «Attiva …» / «Disattiva …» abilita o disabilita il riscaldamento | Leggi «Riscaldamento abilitato» / «Riscaldamento disabilitato» |
| Caldaia e climatizzatore | «Diminuisci temperatura» e «Aumenta temperatura» accanto a «Temperatura», a passi di 0,5 °C, entro «da … a … °C» | Fuori dai limiti il comando è rifiutato («Il setpoint deve essere tra … e …») |
| Climatizzatore | L'interruttore | Dopo uno spegnimento la riaccensione aspetta la pausa del compressore (3 minuti all'inizio) |
| Climatizzatore, «Modo» | Scegli dalla tendina: Caldo, Freddo, Deumidifica, Ventilazione | Il modo cambia |
| Climatizzatore, «Ventola» | Scegli dalla tendina: Auto, Bassa, Media, Alta | La ventola cambia |

> **Da sapere**
>
> - **Abilitato vuol dire «può scaldare»**: è il termostato del sistema che accende e spegne davvero la caldaia
>   intorno alla temperatura voluta, usando il sensore della stanza.
> - **Senza un sensore utilizzabile** la caldaia segue il tuo comando così com'è, senza regolazione (parte 10).
> - **Pausa del compressore**: un comando automatico viene rimandato, uno tuo può essere rifiutato se manca più di
>   qualche secondo.

**Dopo ogni comando:**

- **Leggi l'esito**: «in corso», «eseguito», «errore» o «nessuna risposta», con il motivo.
- **Un climatizzatore a infrarosso** viene confermato dal suo misuratore entro una decina di secondi (consumo su di
  almeno 20 W per l'accensione, sotto 15 W per lo spegnimento); se il misuratore non risponde l'esito è «non
  verificato».
- **Un comando tuo** su un climatizzatore o sulla caldaia toglie quel dispositivo alla regolazione automatica della
  modalità fino al prossimo cambio di modalità: il sistema non va mai contro il comando di una persona.

### Panoramica: rinominare o spostare un dispositivo

**Cambiare il nome visibile o la stanza di un dispositivo.**

1. **Apri «Azioni per …»** (menu con i tre puntini) › «Rinomina o sposta».
2. **Si apre «Modifica dispositivo»** («Cambia il nome visibile o la stanza. La configurazione del dispositivo non
   viene toccata.»).
3. **Compila «Nome»** (da 1 a 60 caratteri) e «Stanza» (una stanza esistente).
4. **Premi «Salva»** o «Annulla»; compare «Dispositivo aggiornato».

> **Da sapere**
>
> Funziona anche con la funzione Comandi spenta.

### Approvazioni: approvare o respingere

**Dire sì o no a una richiesta del motore.**

1. **Apri la notifica** oppure «Approvazioni» › «In attesa».
2. **Leggi** la descrizione, «Perché il motore lo propone», «Azione proposta», il tempo rimasto e la frase sulla
   scadenza.
3. **Se vuoi, scrivi** una «Nota (facoltativa)» («Perché approvi o respingi…», al massimo 500 caratteri).
4. **Premi «Approva»** (compare «Azione approvata») o «Respingi» («Azione respinta»).
5. **La richiesta passa** a «Approvata» o «Respinta» con «… da … …», la nota e, in fondo, l'«ID richiesta»; la
   successiva in coda si apre.
6. **Controlla l'esito vero** in Panoramica e nelle Decisioni: un'azione approvata può non partire se nel frattempo
   il dispositivo è diventato irraggiungibile.

> **Da sapere**
>
> Se una richiesta è già stata decisa da un collega leggi «L'approvazione è già stata decisa».

**Alla scadenza** (30 minuti all'inizio):

| Richiesta | Che cosa succede alla scadenza |
|---|---|
| Le richieste dell'assistente | Vengono respinte |
| «Mettere l'appartamento a vuoto dopo il check-out» | Viene eseguita |
| «Spegnere …» di un apparecchio che consuma a casa vuota | Viene respinta, salvo un'impostazione diversa dell'appartamento |

Nelle Decisioni compare «Approvazione scaduta».

### Programmazione: aggiungere un'azione

**Programmare una modalità o un comando a un orario.**

«Nuova azione» apre «Programma un'azione» («L'azione verrà eseguita dal motore all'orario indicato (ora di …).»).

1. **Compila «Quando»**: un orario futuro, nel fuso dell'appartamento.
2. **Scegli «Cosa fare»**: «Cambia modalità» oppure «Comando a un dispositivo».
3. **Con «Cambia modalità»** scegli «Modalità»: «comfort», «eco», «casa vuota».
4. **Con «Comando a un dispositivo»** scegli «Dispositivo» e «Comando» (tabella sotto).
5. **Premi «Salva»**: compare «Azione programmata».

| Dispositivo | Comandi possibili |
|---|---|
| Prese | «Accendi» o «Spegni» |
| Clima e caldaia | «Spegni» oppure «Imposta temperatura» con «Temperatura (°C)», che accende anche l'apparecchio |

> **Attenzione**
>
> - **Un orario passato** dà «L'orario deve essere nel futuro».
> - **Un cambio di modalità programmato** durante una forzatura aspetta la sua fine.

### Programmazione: spostare o annullare un'azione

**Cambiare l'orario di un'azione in programma, o annullarla.**

**«Sposta»**, su una voce in programma:

- **Apre «Sposta l'azione»**: cambia «Quando» e premi «Salva» («Orario aggiornato»).
- **Il modulo parte** da un'ora dopo adesso, non dall'orario salvato: controlla la data.
- **Si possono spostare** anche le azioni nate da una prenotazione; una modifica della prenotazione può
  ricalcolarle.

**«Annulla azione»:**

- **Chiede** «Annullare questa azione programmata?» e mostra «Azione annullata»; la voce resta nello storico.
- **Vale solo** per le azioni ancora «in programma»; una voce già eseguita o annullata risponde «L'azione è già
  stata eseguita o annullata».

### Regole: cambiare i valori a mano

**Accendere, spegnere e regolare le regole entro i limiti.**

1. **Cambia gli interruttori** e i campi numerici delle regole modificabili (tabella sotto).
2. **Lungo il fondo dello schermo compare una barra** con «1 regola modificata» o «… regole modificate», «Salva le
   modifiche» e «Annulla le modifiche» (riporta i campi ai valori salvati).
3. **Premi «Salva le modifiche»** e leggi «Regole aggiornate»; la modifica è nelle Decisioni («Regole aggiornate»).

| Campo numerico | Regola |
|---|---|
| «Minuti» | «Finestra aperta spegne il clima», «Avviso dispositivo offline» |
| «Minimo (°C)», «Massimo (°C)» | «Limiti del setpoint» |
| «Temperatura in comfort (°C)», «Temperatura in eco (°C)» | «Limiti del setpoint» |
| «Raffrescamento in comfort (°C)» | «Limiti del setpoint» |
| «Temperatura (°C)» | «Antigelo a casa vuota» |
| «Umidità (%)» | «Antimuffa a casa vuota» |
| «Ore prima del check-in» | «Pre-arrivo» |
| «Minuti dopo il check-out», «Minuti di presenza dopo il check-out» | «Risparmio al check-out» |

**Gli errori segnalati sotto il campo** (finché c'è un errore il salvataggio resta disattivato):

| Messaggio | Quando |
|---|---|
| «Valore fuori dai limiti (…–…)» | Un valore fuori dai limiti |
| «Il minimo non può superare il massimo» | Minimo sopra il massimo |
| «La temperatura eco non può superare quella comfort» | Eco sopra comfort |
| «La temperatura di raffrescamento deve essere più alta di quella comfort» | Raffrescamento non sopra comfort |

> **Da sapere**
>
> - **I nuovi limiti minimo e massimo** si applicano subito ai climatizzatori.
> - **Le nuove temperature delle modalità** valgono dal prossimo cambio di modalità e, in comfort, dalla regolazione
>   automatica del clima.
> - **Sul telefono**, mentre scrivi in un campo, la barra «Salva le modifiche» non lo copre: il campo resta sopra
>   la barra.

### Regole: chiedere una proposta all'assistente

**Descrivere a parole la modifica: l'assistente la prepara, tu la applichi.**

Sotto l'elenco delle regole c'è «Chiedi all'assistente»: «Scrivi che cosa vuoi cambiare: l'assistente prepara la
modifica, tu la controlli e la applichi. Niente cambia finché non premi «Applica».».

1. **Scrivi in italiano** (esempio «la finestra aperta spegne dopo 10 minuti»; al massimo 500 caratteri, contatore
   «…/… caratteri») e premi «Proponi».
2. **Leggi** «Preparo la proposta…», poi «Modifiche proposte».
3. **Controlla** regola, campo, valore prima e dopo (per esempio «Finestra aperta spegne il clima, Minuti da 5 a
   10», «Stato» «attiva» o «spenta») e la spiegazione.
4. **Premi «Applica»** («Regole aggiornate come proposto») o «Scarta».

> **Esempio**
>
> - **Frasi semplici capite subito**: «finestra 10 minuti», «antigelo 10 gradi», «spegni la regola dell'antimuffa»,
>   «presenza al check-out 45 minuti».
> - **Anche**: «setpoint da 18 a 25», «comfort 22», «eco 17», «raffrescamento 26».
> - **«temperatura 22» da sola** fa chiedere «È la temperatura comfort, eco, di raffrescamento o un limite (minimo
>   o massimo)? Scrivilo, per esempio «comfort 22» o «massimo 24».».

**Cosa può succedere:**

| Cosa vedi | Cosa vuol dire |
|---|---|
| L'assistente dice che non propone nulla | La richiesta non riguarda le regole o è fuori dai limiti |
| «L'assistente non ha risposto in tempo: riprova con una frase più breve, oppure cambia la regola a mano qui sotto.» | Per le frasi più articolate risponde il modello, e non ha risposto in tempo |
| «Hai già chiesto 20 proposte oggi per questo appartamento: riprova domani o cambia le regole a mano» | Al massimo 20 richieste al giorno per appartamento, per tutti gli utenti insieme |
| «Applica» disattivato con «Salva o annulla prima le modifiche fatte a mano» | Hai modifiche a mano non salvate |
| «Le regole sono cambiate nel frattempo: rifai la richiesta» | Qualcuno ha cambiato le regole nel frattempo |
| «Le regole sono già così: non c'è niente da cambiare» | Le regole sono già come chiesto |

> **Da sapere**
>
> - **Una proposta non mostra mai** valori che il salvataggio rifiuterebbe (eco non sopra comfort, raffrescamento
>   sopra comfort).
> - **La modifica applicata** è nelle Decisioni e nel «Registro dell'organizzazione» con il tuo nome («… ha
>   modificato le regole dell'appartamento … su proposta dell'assistente»); quello che hai scritto non viene
>   conservato.
> - **Il riquadro «Applica le stesse regole ad altri appartamenti»** è riservato agli amministratori (parte 6).

### Assistente: chiedere e comandare in italiano

**Una chat per chiedere lo stato, i consumi o un comando.**

«Assistente» («Chiedi in italiano: spegnere, impostare una temperatura, programmare un'azione») è un solo
riquadro: la conversazione e, in fondo, il campo per scrivere.

1. **Scrivi nel campo** («Es. «Spegni il clima del soggiorno»», al massimo 500 caratteri) e premi «Invia», oppure
   tocca un suggerimento.
2. **La tua domanda** compare a destra, in una bolla colorata.
3. **Leggi** «Sto elaborando…», poi la risposta a sinistra sotto il nome «Assistente», senza bolla né icona.
4. **Un badge compare solo se serve**: «Richiede approvazione» (poi «Approvata», «Respinta» o «Scaduta») oppure
   «Non riuscita». Una risposta normale non ha badge.
5. **Se dopo 30 secondi** non c'è risposta leggi «Nessuna risposta dall'assistente: riprova».
6. **Controlla sempre** in Panoramica.

**I suggerimenti pronti:**

- **Spegnere**: «Spegni il clima del soggiorno», «Spegni la caldaia».
- **Regolare**: «Porta il soggiorno a 21 gradi».
- **Programmare**: «Alle 18 metti il clima a 22 gradi».

**Che cosa sa e che cosa può fare:**

- **Legge** stati, dispositivi, consumi (fino a 31 giorni per volta), programmazioni e Decisioni (le ultime 50).
- **Risponde** a domande come «perché si è spento il clima?».
- **Non riceve mai** dati personali degli ospiti.
- **Se non sa**, risponde «Non lo so: guarda nell'app.».
- **Ogni domanda è a sé**: non ricorda la chat precedente.
- **Può fare solo quello che fa un operatore**: cambiare modalità, comandare prese, clima e caldaia, programmare.
- **Non tocca** regole (rimanda alla pagina Regole), utenti e appartamenti.

**L'esito lo scrive il sistema, non il modello:**

| Cosa leggi | Cosa vuol dire |
|---|---|
| «Fatto: ….» | Solo quando il dispositivo ha confermato |
| «Comando inviato: …, l'esito arriva nell'app.» | La conferma non è ancora arrivata |
| «Non riuscito: … (…).» o «Non fatto: … (…).» | Non eseguito, con il motivo |
| «Programmato: ….» | Un'azione a orario |
| «Comando inviato», «Azione programmata» o «Regole modificate» sotto la risposta | Che cosa è stato fatto, a parole |
| «Dettagli» | Apre i codici («Comando», «Programmazione»), il motivo tecnico di un errore e l'«ID richiesta» |

> **Da sapere**
>
> Il modello propone le azioni in una forma controllata e il sistema le verifica una per una prima di eseguirle
> (limiti, conferme, regole): un'azione non ammessa non parte e viene detta con «Non fatto: … (…).».

### Assistente: conferme con ospiti dentro

**Con ospiti presenti l'assistente chiede un sì o un no in chat.**

1. **Spegnere il clima o la caldaia** e cambiare modalità non avviene da solo: l'assistente chiede in chat, per
   esempio «Spengo climatizzatore soggiorno con ospiti presenti? Rispondi Sì o No qui sotto, oppure dalla pagina
   Approvazioni.».
2. **Rispondi** con i pulsanti «Sì» e «No»; vedi «Scade alle …» e il link «Vai alle approvazioni».
3. **È la stessa richiesta** della pagina Approvazioni: la tua risposta compare lì e nelle Decisioni con il tuo nome;
   senza risposta entro 30 minuti è respinta.
4. **Dopo il clic** leggi «Approvato: il comando parte, l'esito arriva nell'app» o «Respinto» e poi «Ora: …» per la
   successiva.

| Riaprendo la conversazione leggi | Cosa vuol dire |
|---|---|
| «Approvata da te alle …», «Respinta da te alle …» | Hai deciso tu |
| «Già decisa: approvata», «Già decisa: respinta» | Un collega ha deciso |
| «Scaduta» | Nessuno ha risposto in tempo |

> **Da sapere**
>
> - **Due o più azioni in una stessa richiesta** («spegni clima e caldaia») chiedono una conferma ciascuna, in coda,
>   anche senza ospiti.
> - **Se davanti c'è un'altra approvazione** da decidere leggi «In attesa: prima va decisa l'approvazione aperta.».
> - **Chi gestisce il sistema domotico** può impostare la conferma in altro modo: sempre, oppure solo per più azioni
>   insieme.

**Programmare con ospiti** (dal lotto 30):

1. **Se chiedi un'azione a un orario** in cui, secondo le prenotazioni, ci saranno ospiti e l'azione tocca il loro
   comfort (cambio di modalità, clima o caldaia spenti), l'assistente chiede «Programmo …, con ospiti presenti a
   quell'ora? Rispondi Sì o No qui sotto, oppure dalla pagina Approvazioni.».
2. **In Approvazioni** la richiesta si legge «Programmare …».
3. **Con «Sì»** l'azione compare in Programmazione all'ora chiesta, con origine «assistente»; con «No» o senza
   risposta non viene programmata.

> **Da sapere**
>
> - **Accendere qualcosa** non chiede conferma.
> - **Il controllo si fa** quando chiedi, non all'ora dell'azione.
> - **L'orario** deve essere almeno 30 secondi avanti; senza fuso è l'ora dell'appartamento.

### Assistente: conversazione, limiti e risposta rapida

**Quanto dura la chat, quante domande al giorno, cosa succede se il modello tace.**

**La conversazione:**

- **«Svuota conversazione»** pulisce la vista («Nessuna conversazione in questa sessione»): non cancella le richieste
  né le Decisioni.
- **La conversazione resta** solo in quella scheda del browser (ultime 50 richieste per appartamento) e sparisce
  quando esci.

**I limiti:**

- **50 domande al giorno** per appartamento: «Limite di … domande al giorno raggiunto per questo appartamento:
  riprova domani.».
- **Un tetto di spesa mensile** per tutto il servizio: «Limite mensile raggiunto, riprova dal mese prossimo».

**La risposta rapida** (dal lotto 30):

- **Quando**: se l'assistente completo non risponde in tempo, non è raggiungibile o ha raggiunto il limite mensile,
  risponde il sistema da solo.
- **Esegue il comando** solo se la frase è inequivocabile: un verbo e un solo dispositivo (per tipo, stanza o nome)
  oppure una modalità, senza «non», condizioni od orari.
- **Con ospiti dentro** chiede conferma come sempre.
- **In fondo alla risposta** leggi «Risposta rapida: l'assistente completo non ha risposto in tempo.» (oppure «… non
  è raggiungibile ora.» o «… ha raggiunto il limite mensile.»).

> **Esempio**
>
> - **Partono**: «Spegni la caldaia», «Porta il soggiorno a 21 gradi».
> - **Non fanno nulla**: «non spegnere il clima», «alle 18 …», «se fa freddo …», «spegni tutto», «spegni il clima e
>   la presa». Leggi lo stato e un rimando ai pulsanti dell'app.

> **Attenzione**
>
> Se invece leggi «L'assistente non è disponibile ora, riprova più tardi», il sistema ha scartato una risposta
> arrivata da fuori Europa (una protezione: il modello lavora solo in Europa): riprova.

**Sui dimostrativi senza il modello configurato** risponde un riconoscitore semplice:

- **Capisce** «spegni …», «… a 21 gradi» e «alle 18 …» (se l'ora è già passata, programma per domani).
- **Se nomini la caldaia con ospiti dentro** chiede l'approvazione per spegnerla: «Spegnere la caldaia con ospiti
  presenti richiede la tua approvazione.», oppure «C'è già un'approvazione in attesa: decidi prima quella.».
- **Altrimenti** risponde «Non ho capito. Posso spegnere, impostare una temperatura o programmare un'azione.» o
  «Indica la temperatura, ad esempio «porta il soggiorno a 21 gradi».».

## 6. Amministratore: che cosa puoi fare in più

**La pagina «Amministrazione», la copia delle regole e il Simulatore.**

L'amministratore fa tutto quello delle parti 4 e 5 su tutti gli appartamenti dell'organizzazione e in più ha:

- **La pagina «Amministrazione»** («Utenti, appartamenti e funzioni della tua organizzazione»).
- **La copia delle regole** su altri appartamenti.
- **Il Simulatore** sugli appartamenti dimostrativi.

### Amministrazione: le sei schede

**Le schede della pagina, tutte riferite alla tua organizzazione.**

| Scheda | A cosa serve |
|---|---|
| «Appartamenti» (aperta all'inizio) | Nome, indirizzo, attivo o no, prezzo, verifica della connessione |
| «Utenti» | Invitare le persone, ruoli, appartamenti visibili |
| «Funzioni» | Quali schermate sono attive |
| «Prenotazioni ricevute» | Le prenotazioni arrivate da Italianway |
| «Registro dell'organizzazione» | Chi ha fatto cosa |
| «Assistente» (dal lotto 31) | Le domande all'assistente, settimana per settimana |

**Come sono fatte le schede:**

- **Sono linguette sottolineate** su una riga sotto il titolo; sul telefono la riga scorre di lato.
- **La scheda aperta resta nell'indirizzo** della pagina: ricaricando, o riaprendo un indirizzo salvato, torni alla
  stessa scheda.
- **L'indirizzo finisce** con `?scheda=utenti`, `?scheda=funzioni`, `?scheda=prenotazioni`, `?scheda=registro` o
  `?scheda=assistente`.

> **Da sapere**
>
> Chi non è amministratore non vede la pagina («Operazione riservata agli amministratori» se ci prova dal server).

### Assistente: domande, timeout, risposte rapide

**Quante domande all'assistente, quante senza risposta in tempo.**

La scheda spiega: «Le domande all'assistente nella tua organizzazione, settimana per settimana: quante, quante non
hanno avuto risposta in tempo dall'assistente completo e quante hanno avuto una risposta rapida.»

| Cosa vedi | Cosa vuol dire |
|---|---|
| Le ultime 8 settimane, da lunedì a domenica («dal 13 al 19 ottobre»; «(in corso)» sulla prima) | Una riga per settimana |
| «Settimana», «Domande», «Timeout», «Risposte rapide» e «% timeout» | Le colonne della tabella |
| «% timeout» in giallo con un pallino | Settimane sopra il 10 % di timeout: si colora solo quel numero |
| «Risposte rapide per causa, nelle settimane mostrate: tempo scaduto … · assistente non raggiungibile … · limite mensile … · risposta non valida …» | Il dettaglio delle risposte rapide, sotto la tabella |
| «Timeout oltre il 10 % per due settimane di fila: va riaperta la scelta del modello dell'assistente.» | In cima, con due settimane complete di fila sopra la soglia |
| «Nessuna domanda all'assistente nelle ultime settimane.» | Nessuna domanda |

- **I numeri** sono dell'intera organizzazione.
- **Sul telefono** la tabella scorre di lato nel suo riquadro.

### Utenti: invitare un collega

**Mandare un invito con email, nome, ruolo e appartamenti visibili.**

Il riquadro «Invita un utente» spiega: «L'utente riceve un'email con il link all'app: entra con Google o sceglie una
password. Il ruolo decide cosa può fare.».

1. **Compila «Email»**, «Nome» e «Ruolo» («Amministratore», «Operatore», «Sola lettura»).
2. **Per operatore e sola lettura** scegli «Appartamenti visibili» («Tutti gli appartamenti» oppure le caselle).
3. **Premi «Invita»** e leggi l'esito (tabella sotto).

| Esito | Cosa vuol dire |
|---|---|
| «Invito inviato a …» | Tutto a posto |
| «Invito registrato, ma l'email a … non è partita. Riprova con «Reinvia».» | L'invito c'è, l'email no: usa «Reinvia» |
| «Invito registrato. L'invio email non è attivo: avvisa tu …» | L'invito c'è, l'email non è attiva: avvisa tu la persona |
| «È già un utente della tua organizzazione» | Una persona può stare in una sola organizzazione |
| «Questa email non può essere invitata» | Le persone di HQE non si possono invitare |

> **Da sapere**
>
> L'invito resta registrato anche se l'email non parte.

**L'elenco degli utenti, una riga per persona:**

- **Prima linea**: l'email, con il badge «in attesa del primo accesso» finché la persona non entra, oppure «tu».
- **Seconda linea, in grigio**: nome, «… dispositivi push» (i dispositivi con le notifiche accese) e gli
  appartamenti visibili.
- **A destra**: la tendina del ruolo e il menu «⋯» («Altre azioni per …»).
- **Nel menu «⋯»**: «Appartamenti» (non per gli amministratori), «Reinvia» (solo per chi è in attesa) ed «Elimina»
  in rosso.
- **Sulla tua riga** il menu non c'è.

**«Reinvia»**, nel menu «⋯» di chi è in attesa:

- **Stessi esiti** dell'invito.
- **Le email hanno dei limiti**: al massimo 3 ogni 10 minuti e 10 ogni 24 ore per destinatario, 50 ogni ora per
  organizzazione; oltre, l'invito resta e l'email non parte: riprova più tardi.
- **Se la persona è già entrata**: «L'utente ha già effettuato l'accesso».

### Utenti: ruoli e appartamenti visibili

**Cambiare il ruolo di una persona e quali appartamenti vede.**

**Cambiare ruolo:**

1. **Usa il selettore «Ruolo»** accanto alla persona; compare «Ruolo aggiornato».
2. **La persona viene fatta uscire** da tutti i dispositivi entro circa un minuto e rientra con il ruolo nuovo.
3. **Chi diventa amministratore** vede tutti gli appartamenti.

> **Attenzione**
>
> - **Non puoi cambiare il tuo ruolo**: «Non puoi togliere a te stesso il ruolo di amministratore».
> - **Deve restare un amministratore**: «Deve restare almeno un amministratore nell'organizzazione».

**Appartamenti visibili:**

1. **Apri il menu «⋯»** di un operatore o di un lettore e scegli «Appartamenti».
2. **Si apre «Appartamenti di …»** («Scegli quali appartamenti vede questo utente. Gli amministratori vedono sempre
   tutti gli appartamenti.»).
3. **Scegli «Tutti gli appartamenti»** oppure le caselle, poi «Salva» («Appartamenti aggiornati»).
4. **Senza nessuna casella** leggi «Nessun appartamento scelto: l'utente non vedrà nessun appartamento finché non ne
   assegni almeno uno.».
5. **Devi confermare** «Nessun appartamento scelto: … non vedrà nessun appartamento finché non ne assegni almeno uno.
   Confermi?»: serve a sospendere un accesso senza cancellare la persona.

> **Esempio**
>
> Caso tipico: il proprietario di un immobile, invitato come «Sola lettura», che vede solo il suo appartamento.

> **Da sapere**
>
> - **Un utente limitato** vede, riceve notifiche e agisce solo sui suoi appartamenti.
> - **Se gli togli un appartamento mentre lo guarda**, entro mezzo minuto la pagina smette di aggiornarsi e compare
>   «Appartamento non disponibile».

### Utenti: rimuovere una persona

**Togliere accesso e notifiche a un utente.**

1. **Apri il menu «⋯»** della persona e scegli «Elimina» (in rosso): chiede «Rimuovere l'utente …?».
2. **Conferma**: compare «Utente rimosso».
3. **La persona perde** accesso e notifiche; le sue azioni restano nei registri per 24 mesi con il nome.

> **Attenzione**
>
> - **Non puoi eliminare te stesso**: «Non puoi eliminare il tuo stesso account».
> - **Una persona rimossa** non può più entrare nelle Impostazioni per cancellare da sola nome ed email: se serve, lo
>   chiede a HQE.

### Appartamenti: la scheda e «Modifica»

**Nome, indirizzo, prezzo e dati tecnici di ogni appartamento.**

Gli appartamenti stanno in un solo riquadro, una riga per appartamento.

| Cosa vedi nella riga | Cosa vuol dire |
|---|---|
| Il nome con i badge «Dimostrativo» e «disattivato», poi l'indirizzo | L'anagrafica; «Dimostrativo» è un appartamento finto per le prove |
| «Prezzo dell'energia: … (solo per questo appartamento)» o «Prezzo dell'energia: … (dell'organizzazione)» | Il prezzo che vale |
| «Ultima verifica» («mai eseguita», «riuscita il …», «non riuscita il …») | L'esito dell'ultima «Verifica connessione» |
| L'interruttore «Attivo» e «Modifica», a destra | Spegnere l'appartamento; cambiare nome, indirizzo e prezzo |
| «Verifica connessione» con la nota «Se la verifica non riesce, avvisa l'assistenza.» | Provare il collegamento |
| «Dettagli tecnici» | Apre «Codice», «Fuso orario», «Collegamento al sistema domotico», «ID Italianway» e «Funzioni» (con i nomi del menu, per esempio «Approvazioni, Consumi») |

- **Il «Codice»** dell'appartamento, in «Dettagli tecnici», si copia toccandolo (compare «Copiato»).
- **Non ci sono «Nuovo appartamento» né cestino**: «I nuovi appartamenti li aggiunge il gestore della piattaforma
  (HQE): per averne uno, scrivi all'assistenza.».

**«Modifica»** apre «Modifica appartamento»:

1. **Compila «Nome»**, «Indirizzo», «Attivo».
2. **Compila «Prezzo per kWh di questo appartamento (€)»** («Lascia vuoto per usare quello dell'organizzazione
   (…).»).
3. **Premi «Salva»** («Appartamento salvato»).

**Quello che si vede ma non si cambia:**

| Campo | Cosa dice l'app |
|---|---|
| «Fuso orario» (dal lotto 31) | «Impostato sul motore dell'appartamento. Se va cambiato, scrivi all'assistenza.» |
| «Collegamento al sistema domotico» | «Il collegamento al sistema domotico lo imposta il gestore della piattaforma (HQE). Se va cambiato, scrivi all'assistenza.» |
| Codice Italianway | «Il codice Italianway lo imposta il gestore della piattaforma (HQE). Se va cambiato, scrivi all'assistenza.» |

> **Da sapere**
>
> - **Quando il fuso cambia sul motore**, nel «Registro dell'organizzazione» compare «Fuso orario dell'appartamento
>   «…» cambiato sul motore: … → …».
> - **Un fuso non valido** dà «Fuso orario non valido».
> - **Il fuso salvato qui** vale per gli orari mostrati e scritti dall'app; il motore dell'appartamento usa il fuso
>   con cui è stato configurato da HQE.

### Appartamenti: attivo, verifica connessione, prezzo

**Spegnere un appartamento, provare il collegamento, impostare il prezzo.**

**«Attivo»** (l'interruttore nella riga, o in Modifica):

- **Spento**, l'appartamento ha il badge «disattivato» in Amministrazione e «Disattivato» nell'elenco
  «Appartamenti».
- **Le operazioni** rispondono «Appartamento disattivato» e le prenotazioni non vengono inoltrate.
- **Non spegne** i dispositivi né gli automatismi del sistema domotico.

**«Verifica connessione»:**

- **Controlla** che il sistema domotico risponda.
- **Leggi** «Connessione OK» o «Problema di connessione» («Se la verifica non riesce, avvisa l'assistenza.») e
  «Ultima verifica».
- **Un esito negativo** è un risultato, non un errore dell'app.
- **Messaggi possibili**: «Sistema domotico non raggiungibile», «Chiave del sistema domotico non configurata:
  contatta l'assistenza HQE».

**«Prezzo dell'energia»** (in cima): «Serve per l'importo in euro nei rendiconti Excel dei consumi. Vale per tutti gli
appartamenti; per un appartamento puoi impostarne uno diverso da «Modifica».».

1. **Compila «Prezzo per kWh (€)»**: da 0 a 10, al massimo 4 decimali, virgola o punto; esempio 0,25.
2. **Premi «Salva»** («Prezzo dell'energia salvato»).

> **Da sapere**
>
> - **Campo vuoto** = prezzo tolto («non impostato»); zero è un prezzo valido.
> - **Errore**: «Scrivi un numero da 0 a 10 con al massimo 4 decimali, per esempio 0,25.».
> - **Ogni cambio** resta nel «Registro dell'organizzazione».

### Funzioni

**Accendere o spegnere le schermate, per tutti o per un appartamento.**

«Funzioni dell'organizzazione …» spiega: «Disattiva qui una funzione per nasconderla in tutti gli appartamenti; ogni
appartamento può avere un'eccezione.».

| Cosa vedi | Cosa puoi fare | Cosa succede |
|---|---|---|
| Nove interruttori in colonna, con i nomi del menu e una riga di spiegazione sotto ciascuno (tabella sotto) | Accendere o spegnere una funzione per tutta l'organizzazione | Ogni cambio si salva subito («Funzioni aggiornate») |
| «Ripristina tutte» | Riaccendere tutto | Tutte le funzioni tornano accese |
| Lo stesso elenco per ogni appartamento, compatto e senza spiegazioni, con «eredita dall'organizzazione» oppure «eccezione per questo appartamento» | Fare un'eccezione per un appartamento | L'eccezione sostituisce la scelta dell'organizzazione e può anche riaccendere una funzione spenta per tutti |
| «Torna all'organizzazione» | Togliere l'eccezione | L'appartamento segue di nuovo l'organizzazione |

**Che cosa spiega l'app sotto ogni funzione:**

| Funzione | Spiegazione nell'app |
|---|---|
| Panoramica | «La fascia di stato della casa, la modalità e la forzatura.» |
| Dispositivi | «L'elenco dei dispositivi per stanza, con le letture.» |
| Comandi | «Accendere, spegnere e regolare i dispositivi dall'app.» |
| Consumi | «Consumi per ora, giorno e dispositivo, e il rendiconto in Excel.» |
| Programmazione | «Le azioni pianificate dal motore e dal gestore.» |
| Regole | «Gli automatismi del motore e i loro valori.» |
| Approvazioni | «Le azioni che il motore esegue solo con il consenso del gestore.» |
| Decisioni | «Il registro di ciò che il motore ha deciso e perché.» |
| Assistente | «Le richieste a parole all'assistente.» |

> **Da sapere**
>
> - **Riepiloghi** non ha interruttore: c'è sempre.
> - **Una funzione che il sistema domotico non ha** resta comunque non disponibile.

### Prenotazioni ricevute

**Le comunicazioni di Italianway per i tuoi appartamenti, e se sono passate al motore.**

La scheda spiega: «Le ultime 100 comunicazioni di prenotazione arrivate da Italianway per i tuoi appartamenti, e se
sono state trasmesse al motore che gestisce l'appartamento.»

- **Si aggiorna** ogni 30 secondi; le prove del Simulatore non passano da qui.
- **In cima**: «Ultime 24 ore: … ricevute, … trasmesse, … con problemi» (calcolato sulle 100 righe disponibili).
- **Ogni riga**: una frase come «Prenotazione creata · Milano Centro · dal 1 dic 2026 al 3 dic 2026», poi l'esito e la
  data di ricezione (fuso italiano).
- **Gli eventi**: «Prenotazione creata», «Prenotazione modificata», «Prenotazione cancellata», «Check-in»,
  «Check-out»; se il messaggio non si legge, «Evento ricevuto, formato non riconosciuto».
- **Senza righe**: «Nessuna prenotazione ricevuta».

**«Dettagli tecnici»**, per l'assistenza:

- **La firma**: «firma valida» o «firma non valida».
- **«Codice di risposta»**, «Codice Italianway», «Ospiti» (il numero).
- **Gli identificativi** (l'«ID richiesta» si copia).
- **«Inoltro a /bookings»** o «non inoltrato», «… tentativi», «Corpo grezzo».
- **I dati personali degli ospiti** sono oscurati. Non c'è un pulsante per ritrasmettere.

| Esito | Che cosa vuol dire |
|---|---|
| «Ricevuta e trasmessa al motore» | Tutto a posto: il sistema domotico l'ha ricevuta, anche se l'aveva già. |
| «Ricevuta ma il motore non l'ha accettata», «… (riprovato 1 volta)», «… (riprovato … volte)» | Il sistema domotico non ha risposto o ha dato errore, anche dopo i tentativi. Avvisa l'assistenza. |
| «Ricevuta ma non trasmessa: appartamento disattivato» | L'appartamento è spento con l'interruttore «Attivo». |
| «Ricevuta ma non trasmessa: formato non riconosciuto» | Il messaggio di Italianway non si è potuto leggere. Avvisa l'assistenza. |
| «Ricevuta ma rifiutata: firma non valida», «Ricevuta: appartamento non riconosciuto» | Qui quasi mai: queste comunicazioni non si possono attribuire a nessuna organizzazione e le vede HQE in «Prenotazioni non attribuite». |
| «Ricevuta ma non trasmessa» | Qualsiasi altro caso. Avvisa l'assistenza. |

### Registro dell'organizzazione

**Chi ha fatto cosa nella tua organizzazione, con i nomi.**

La scheda spiega: «Chi ha fatto cosa nella tua organizzazione: inviti, ruoli, appartamenti, funzioni e accessi di
assistenza.»

- **Ogni voce** è una frase con la data, dalla più recente, 50 per volta («Carica altri»).
- **Senza voci**: «Nessuna attività registrata».
- **Chi ha eliminato il proprio account** compare come «Utente rimosso».
- **Le modifiche delle regole fatte a mano** sono nelle Decisioni, non qui.
- **Conservazione** 24 mesi. Prima si chiamava «Registro attività».

> **Esempio**
>
> - «Anna Rossi ha cambiato il ruolo di bruno@… da «Sola lettura» a «Operatore»»
> - «… ha copiato le regole da «…» all'appartamento …»
> - «… ha modificato le regole dell'appartamento … su proposta dell'assistente»
> - «… ha aperto un accesso di assistenza a … fino al …»

### Copiare le regole su altri appartamenti

**Portare le regole di un appartamento su altri, con anteprima.**

Il riquadro «Applica le stesse regole ad altri appartamenti» è in fondo alla pagina «Regole»: «Copia le regole
salvate di questo appartamento (attive o spente e valori) sugli appartamenti che scegli. Prima vedi che cosa cambia
in ciascuno, poi confermi.».

1. **Salva o annulla** prima le modifiche fatte a mano.
2. **Scegli gli appartamenti di destinazione** o «Seleziona tutti» (al massimo 100 per volta, stessa
   organizzazione).
3. **Premi «Vedi che cosa cambia»** («Preparo l'anteprima…»).
4. **Leggi «Che cosa cambia copiando le regole di «…»»**: per ciascuno i valori che cambieranno, oppure uno degli
   esiti della tabella sotto.
5. **Premi «Copia su … appartamenti»** (o «Copia su 1 appartamento»); «Annulla» abbandona.
6. **Leggi «Copia in corso…»** e poi «Esito della copia», appartamento per appartamento.
7. **«Chiudi»** chiude gli esiti.

**Gli esiti possibili nell'anteprima**, per ciascun appartamento:

- **«Già uguale, nessuna modifica»**
- **«Appartamento disattivato: non verrà toccato»**
- **«Motore non raggiungibile: non verrà toccato»**
- **«Non applicabile a questo appartamento»**
- **«Ha regole personalizzate che verranno sovrascritte: …»**, se un appartamento ha valori personalizzati

**Gli esiti possibili della copia**, appartamento per appartamento:

- **«Regole copiate»**
- **«Regole cambiate dopo l'anteprima: non toccato»**
- **«Appartamento disattivato: non toccato»**
- **«Motore non raggiungibile: non toccato»**
- **«Già uguale, nessuna modifica»**

> **Da sapere**
>
> - **Senza altri appartamenti** leggi «Nessun altro appartamento nella tua organizzazione».
> - **L'anteprima controlla** anche che eco non superi comfort e che il raffrescamento sia sopra comfort.
> - **Si copiano** solo le regole modificabili e i valori che esistono nella destinazione.
> - **Se le regole di partenza sono cambiate**: «Le regole dell'appartamento di partenza sono cambiate: rifai
>   l'anteprima».
> - **Ogni appartamento toccato** ha una riga nelle sue Decisioni e nel «Registro dell'organizzazione».

### Simulatore: finestre, movimento, connettività, approvazione

**Provocare eventi su un appartamento dimostrativo.**

Gli appartamenti dimostrativi (etichetta «Dimostrativo» in ogni elenco) usano un sistema domotico simulato: servono
per le prove e le dimostrazioni, anche accanto agli appartamenti veri.

- **Su di loro** gli amministratori vedono «Simulatore» («Provoca eventi su questo appartamento dimostrativo: lo
  vedono solo gli amministratori.»).
- **Su un appartamento vero** la voce non c'è e l'indirizzo dà «Pagina non trovata».
- **Fino a 1024 px** (telefono e tablet) i riquadri stanno in una colonna; su schermi più larghi in due, senza
  spazi vuoti.

| Riquadro | Cosa dice l'app | Cosa puoi fare | Cosa succede |
|---|---|---|---|
| «Finestre» | «Apri una finestra: dopo i minuti della regola «finestra aperta» clima e caldaia si spengono» | L'interruttore di ogni sensore mostra «aperta» o «chiusa» («Finestra aperta», «Finestra chiusa») | Senza sensori: «Nessun sensore finestra» |
| «Movimento» | «Simula il passaggio di una persona davanti al sensore: il motore registra l'ora del movimento, come con un sensore vero» | «Simula movimento» per ogni sensore («Movimento simulato su …»), con «ultimo movimento …» o «nessun movimento» | Serve a provare «Mettere l'appartamento a vuoto dopo il check-out». Senza sensori: «Nessun sensore di movimento» |
| «Connettività dispositivi» | «Metti un dispositivo offline: i comandi vengono rifiutati e scatta l'avviso oltre la soglia» | Interruttore «online» / «offline» per ogni dispositivo («Dispositivo online», «Dispositivo offline») | Tornare online prima della soglia annulla l'avviso |
| «Approvazione» | «Fa nascere una richiesta reale di approvazione dal motore» | «Richiedi un'approvazione» crea una richiesta vera di spegnimento del primo apparecchio con misuratore («Approvazione generata») | Se non ce n'è, «Nessun apparecchio con misuratore da proporre nell'appartamento» |

### Simulatore: evento prenotazione e ripristino

**Simulare una prenotazione e riportare il dimostrativo all'inizio.**

**«Evento prenotazione»** spiega: «Prenotazione di prova come se arrivasse da Italianway: fa lo stesso percorso di
una prenotazione vera fino al motore dell'appartamento. Ripetere lo stesso invio non la duplica.».

1. **Scegli «Tipo evento»**: «Prenotazione creata», «Prenotazione modificata», «Prenotazione annullata», «Check-in
   effettivo», «Check-out effettivo».
2. **Compila «ID prenotazione»**, «Check-in», «Check-out», «Ospiti».
3. **Premi «Invia evento»**: leggi «Evento prenotazione inoltrato» e «… azioni programmate».

> **Da sapere**
>
> - **Ripremendo «Invia evento» senza cambiare nulla** leggi «Evento già elaborato (idempotente)»: è lo stesso
>   evento, non viene duplicato; cambiando un campo è un evento nuovo.
> - **Il check-out deve venire dopo il check-in** («Il check-out deve essere successivo al check-in»).
> - **Queste prove** non compaiono in «Prenotazioni ricevute».

**«Ripristina lo stato iniziale»** spiega: «Riporta l'appartamento dimostrativo com'era all'inizio, per ricominciare
una prova da capo.».

1. **Premi «Ripristina…»**: chiede «Ripristinare lo stato iniziale di «…»?».
2. **Leggi la spiegazione**: «Tornano come all'inizio: dispositivi e loro stati, modalità, forzatura, regole,
   approvazioni, programmazione, decisioni e comandi. Vengono cancellati tutti i soggiorni di questo appartamento,
   anche quelli arrivati da Italianway. Restano: nome, indirizzo e impostazioni dell'appartamento, prezzi, codice
   Italianway, utenti, registro attività ed elenco delle prenotazioni ricevute. I consumi non cambiano. Vale solo
   per questo appartamento simulato e non si può annullare.».
3. **Premi «Ripristina»** o «Annulla»; compare «Stato iniziale ripristinato» e tutti i dispositivi aperti su
   quell'appartamento si aggiornano.

> **Attenzione**
>
> Con un sistema domotico vero segnato dimostrativo il pulsante è disattivato («Il ripristino è disponibile solo con
> il motore simulato integrato.»).

### L'avviso di assistenza HQE

**Quando HQE entra nella tua organizzazione, lo vedi in ogni pagina.**

| Cosa vedi | Cosa puoi fare | Cosa succede |
|---|---|---|
| «L'assistenza HQE (…) ha accesso alla tua organizzazione fino al …, con i permessi di un operatore.» e «Motivo: …», in cima a ogni pagina | Leggere chi è entrato, fino a quando e perché | L'avviso si aggiorna ogni 2 minuti |
| «Chiudi accesso» | Chiudere l'accesso | Chiede «Chiudere l'accesso di assistenza di …? Potrà rientrare solo con un nuovo accesso.» e mostra «Accesso di assistenza chiuso» |
| «Nascondi l'avviso» | Nascondere il messaggio | Nasconde solo il messaggio |

> **Da sapere**
>
> - **Durante l'accesso** la persona di HQE vede e comanda come un operatore su tutti gli appartamenti, ma non
>   gestisce utenti, appartamenti né funzioni.
> - **Apertura, chiusura e scadenza** restano nel «Registro dell'organizzazione».
## 7. Gestore della piattaforma HQE: Organizzazioni

**La pagina «Organizzazioni»: organizzazioni, gestori, prenotazioni non attribuite, registro.**

Chi ha il ruolo di gestore della piattaforma vede nel menu «Organizzazioni» («Le organizzazioni che usano l'app e i
gestori della piattaforma»).

| Scheda | A cosa serve |
|---|---|
| «Elenco organizzazioni» | Creare, rinominare, sospendere, riattivare; appartamenti e accessi di assistenza |
| «Gestori della piattaforma» | Le persone di HQE |
| «Prenotazioni non attribuite» | Le prenotazioni che non corrispondono a nessun appartamento |
| «Registro della piattaforma» | Cosa è successo in un'organizzazione o nella piattaforma |

Le schede sono linguette sottolineate su una riga sotto il titolo. La scheda aperta resta nell'indirizzo della
pagina, che finisce con `?scheda=gestori`, `?scheda=non-attribuite` o `?scheda=registro`.

> **Da sapere**
>
> - **Chi non ha il ruolo**, aprendo l'indirizzo, vede «Pagina non trovata».
> - **Se il ruolo gli viene tolto** mentre è nella pagina legge «Non hai più accesso a questa pagina: il ruolo di
>   gestore della piattaforma ti è stato tolto.».
> - **Un gestore senza organizzazione** entra direttamente qui; se fa parte anche di un'organizzazione ha anche le
>   pagine del suo ruolo lì.
> - **Se quella organizzazione è sospesa** legge «La tua organizzazione «…» è sospesa: le sue pagine non sono
>   disponibili finché non la riattivi da qui.».

### Elenco organizzazioni: la scheda e la creazione

**Ogni organizzazione in una scheda; crearne una nuova.**

| Cosa vedi nella scheda | Cosa vuol dire |
|---|---|
| Nome, «Creata il …» | L'anagrafica |
| «Primo amministratore» con «in attesa del primo accesso», «attivo» o «nessun amministratore invitato» | Lo stato del primo amministratore |
| «Sospesa» | L'organizzazione è sospesa |
| Gli accessi di assistenza aperti | Chi di HQE è dentro, fino a quando |
| I pulsanti «Appartamenti» (con la freccia) e «Accesso di assistenza», oppure «Entra come assistenza» e «Chiudi accesso» | Le azioni più frequenti |
| Il menu «⋯» («Altre azioni per …») | «Rinomina», «Reinvia invito» (finché il primo amministratore non è entrato), «Sospendi» in rosso oppure «Riattiva» |
| «Nessuna organizzazione» | Non ce n'è nessuna |

**«Nuova organizzazione»** spiega: «L'organizzazione nasce con il suo primo amministratore: riceve un'email per
entrare, poi invita gli altri utenti.».

1. **Compila «Nome dell'organizzazione»**, «Email del primo amministratore», «Nome del primo amministratore
   (facoltativo)».
2. **Premi «Crea»** e leggi l'esito.

| Esito o errore | Cosa vuol dire |
|---|---|
| «Organizzazione «…» creata. Invito inviato a …» | Tutto a posto |
| «Organizzazione «…» creata, ma l'email a … non è partita: usa «Reinvia invito».» | L'organizzazione c'è, l'email no |
| «Organizzazione «…» creata. L'invio email non è attivo: avvisa tu …» | L'organizzazione c'è, l'invio email non è attivo |
| «Scrivi il nome dell'organizzazione» | Manca il nome |
| «Esiste già un'organizzazione con questo nome» | Nome duplicato |
| «Questa email non può essere invitata» | L'email non è ammessa |

**«Reinvia invito»**, nel menu «⋯», finché il primo amministratore non è entrato:

- **Esiti**: «Invito inviato di nuovo a …», «L'email a … non è partita: riprova più tardi.», «L'invio email non è
  attivo: avvisa tu …».
- **Se è già entrato**: «L'amministratore ha già effettuato l'accesso».

### Elenco organizzazioni: rinominare, sospendere, riattivare

**Le azioni sulla scheda di un'organizzazione, dal menu «⋯».**

**«Rinomina»:**

- **Apre «Rinomina l'organizzazione»**: «Nome dell'organizzazione», «Salva» («Nome aggiornato»).
- **Solo HQE** cambia il nome.

**«Sospendi»** (in rosso):

1. **Apre «Sospendere «…»?»** («I suoi utenti escono dall'app e non possono rientrare finché non la riattivi; le
   notifiche si fermano. Le prenotazioni continuano ad arrivare al motore degli appartamenti.»).
2. **Compila «Motivo (obbligatorio, resta nel registro attività)»**.
3. **Premi «Sospendi l'organizzazione»** («Organizzazione «…» sospesa»).
4. **La scheda mostra** «Sospesa» e «Sospesa il …. Motivo: …».

> **Da sapere**
>
> - **Gli utenti vedono** «La tua organizzazione è sospesa: l'app non è disponibile. Per informazioni contatta
>   l'assistenza HQE.».
> - **Gli accessi di assistenza** si chiudono; i dispositivi non vengono spenti.
> - **Se è la tua organizzazione** resti dentro Organizzazioni per poterla riattivare.

**«Riattiva»** (al posto di «Sospendi» in un'organizzazione sospesa):

- **Chiede** «Riattivare «…»? I suoi utenti potranno di nuovo entrare nell'app.» («Organizzazione «…» riattivata»).
- **Gli accessi di assistenza** chiusi dalla sospensione non riaprono da soli.

**Le altre azioni:**

- **«Accesso di assistenza»** e **«Entra come assistenza»**, pulsanti sulla scheda: parte 8.
- **«Appartamenti»**, il pulsante con la freccia: apre la parte tecnica (sotto) dentro la scheda.

### Appartamenti di un'organizzazione: creare un appartamento

**La parte tecnica: identificativo, collegamento, codice Italianway.**

**L'elenco, una riga per appartamento:**

- **Il nome** con i badge «Dimostrativo» e «disattivato» e il codice copiabile.
- **In grigio**: collegamento, porta, fuso e codice Italianway; poi «Ultima verifica».
- **I pulsanti** «Modifica collegamento» e «Verifica connessione» hanno il contorno; «Elimina» è rosso.
- **Senza appartamenti** leggi «Nessun appartamento in questa organizzazione».
- **Da qui** non si aprono Panoramica, dispositivi o consumi.

**«Nuovo appartamento»** apre «Nuovo appartamento per …» («L'identificativo non si potrà più cambiare: usa minuscole,
numeri e trattini; deve essere unico su tutta la piattaforma. Nome, stato e funzioni li gestirà poi l'amministratore
dell'organizzazione.»).

| Campo | Cosa scrivere |
|---|---|
| «ID» | Da 3 a 64 caratteri, minuscole, numeri e trattini, per esempio apt-milano-01; mai riutilizzabile |
| «Nome» | Fino a 120 caratteri |
| «Indirizzo del sistema domotico» | Nell'ambiente di prova «In questo ambiente usa mock://builtin» |
| «Porta» | Da 1 a 65535, facoltativa |
| «Fuso orario» | Europe/Rome all'inizio; «Valore iniziale: dopo la creazione il fuso orario si imposta sul motore.» |
| «ID Italianway» | Fino a 120 caratteri; «Decide a quale appartamento arrivano le prenotazioni di Italianway. Vuoto = nessun codice.» |
| «Attivo», «Appartamento dimostrativo» | Le due caselle |

1. **Compila i campi** e premi «Salva».
2. **Leggi «Appartamento … creato»** e, con un sistema domotico vero, «Prima di usarlo: crea la chiave del sistema
   domotico e poi premi Verifica connessione.»: la chiave la prepara il responsabile tecnico fuori dall'app.

> **Da sapere**
>
> Non c'è il campo Indirizzo: lo mette l'amministratore.

**Errori possibili:**

- «Identificativo non disponibile»
- «Collegamento già usato da un altro appartamento»
- «Codice Italianway già in uso»
- «Fuso orario non valido»
- «Indirizzo non valido: deve cominciare con http:// o https://»
- «In questo ambiente di prova scrivi mock://builtin nel campo Indirizzo del sistema domotico»

### Appartamenti di un'organizzazione: collegamento e dimostrativo

**Cambiare il collegamento tecnico e segnare un appartamento come dimostrativo.**

**«Modifica collegamento»** apre «Collegamento di «…»» («Qui cambi il collegamento al sistema domotico e il codice
Italianway: nome, stato e funzioni dell'appartamento li gestisce l'amministratore dell'organizzazione.»):

1. **Compila «Indirizzo del sistema domotico»**, «Porta», «ID Italianway».
2. **Premi «Salva»** («Collegamento aggiornato»).
3. **Un indirizzo senza http** diventa http; poi verifica la connessione.
4. **Il codice Italianway** deve essere unico su tutta la piattaforma.

**«Appartamento dimostrativo»** («Per prove e dimostrazioni: gli amministratori dell'organizzazione vedono il
Simulatore di questo appartamento, e ogni elenco lo segna «Dimostrativo».»):

- **Con il motore simulato integrato** è sempre accesa («Con un indirizzo mock:// l'appartamento è sempre
  dimostrativo.»).
- **Passando a un sistema domotico vero** l'appartamento torna reale, salvo lasciare accesa la casella.
- **Nel sito vero**, fino alla consegna al cliente, i dimostrativi con il motore simulato integrato sono ammessi
  come nell'ambiente di prova (dal 23 ottobre).
- **Un tale appartamento** non può avere un codice Italianway («In produzione un appartamento dimostrativo non può
  avere un codice Italianway»); un sistema domotico vero segnato dimostrativo può averlo.
- **Ogni cambio del tipo** resta nel registro («… ha segnato l'appartamento … come dimostrativo»).

**Com'è il dimostrativo all'inizio:**

| Nel campo «Indirizzo del sistema domotico» | Com'è all'inizio |
|---|---|
| `mock://builtin?variante=vuoto` | Nessun ospite, casa fredda |
| `mock://builtin?variante=occupato` | Soggiorno in corso, comfort |
| Senza variante | Parte vuoto se l'identificativo contiene «bologna», occupato altrimenti |

> **Da sapere**
>
> - **Per cambiare la variante a un dimostrativo esistente** salva il nuovo collegamento e fai premere «Ripristina»
>   nel Simulatore a un amministratore.
> - **Un valore sbagliato** dà «Variante sconosciuta: scrivi mock://builtin?variante=vuoto oppure
>   mock://builtin?variante=occupato».

### Appartamenti di un'organizzazione: verifica ed eliminazione

**Provare il collegamento ed eliminare un appartamento.**

**«Verifica connessione»:**

- **Leggi** «Connessione OK» o «Problema di connessione», con «Ultima verifica» condivisa con l'amministratore.
- **Il gestore legge anche** i problemi della chiave: «Chiave del sistema domotico non trovata in Secret Manager:
  crea il segreto …», «Chiave del sistema domotico non leggibile dal server: manca il permesso su …».

**«Elimina»:**

- **Chiede** «Eliminare l'appartamento … («…») dell'organizzazione …? Sparirà per tutti i suoi utenti. Il suo
  sistema domotico non viene toccato.».
- **Mostra** «Appartamento … eliminato». L'identificativo non si può riusare.

### Gestori della piattaforma

**Aggiungere o togliere le persone di HQE.**

La scheda spiega: «I gestori della piattaforma creano le organizzazioni e il loro primo amministratore. Aggiungi
l'email di una persona: il ruolo vale quando entra nell'app con quella email, anche se oggi non ha ancora un
account.»

1. **Compila «Email»** e premi «Aggiungi gestore».
2. **Leggi** «… è ora gestore della piattaforma: il ruolo vale quando entra con questa email.».
3. **Accanto a ogni gestore** leggi «già entrato» o «non ancora entrato». Non parte un'email.

**«Togli»:**

- **Chiede** «Togliere il ruolo di gestore della piattaforma a …?» (o «Togliere il ruolo di gestore della piattaforma
  a te stesso? Perderai l'accesso a questa pagina.»).
- **Mostra** «Ruolo di gestore tolto a …».
- **Chiude i suoi accessi di assistenza**, non il suo eventuale ruolo in un'organizzazione.
- **Deve restare almeno un gestore** («È l'ultimo gestore della piattaforma: nomina prima qualcun altro»).

### Prenotazioni non attribuite

**Le prenotazioni che non si possono assegnare a nessuna organizzazione.**

La scheda spiega: «Prenotazioni arrivate da Italianway che non si possono assegnare a nessuna organizzazione: codice
Italianway sconosciuto o collegato a più appartamenti, firma non valida, formato non riconosciuto. Gli amministratori
delle organizzazioni non le vedono.»

- **Le ultime 100**, con le stesse frasi, esiti e «Dettagli tecnici» di «Prenotazioni ricevute».
- **Al posto del nome dell'appartamento** c'è «codice Italianway …».
- **Serve** a scoprire un codice sbagliato.
- **Non c'è un pulsante** per assegnarle o ritrasmetterle.

### Registro della piattaforma

**Cosa è successo in un'organizzazione, con i soli ruoli.**

La scheda spiega: «Chi ha fatto cosa in un'organizzazione, oppure le azioni della piattaforma (gestori nominati e
tolti).»

- **Con «Registro di»** scegli un'organizzazione oppure «Azioni della piattaforma»; «Carica altri» mostra le 50
  successive.
- **Delle persone delle organizzazioni** vedi solo il ruolo («Un amministratore», «Un operatore», «Un lettore»,
  «Un utente»), non il nome né l'email.
- **Le azioni dei gestori** restano con il nome («… (gestore della piattaforma)»).
- **Conservazione** 24 mesi. Prima si chiamava «Registro attività».

> **Esempio**
>
> «Un amministratore ha invitato un utente come «Sola lettura»»

### Email che riceve il gestore

**Gli avvisi via email sulla spesa dell'assistente e sul servizio.**

**Avviso sulla spesa dell'assistente:**

- **Oggetto** «DOMHOUSE: assistente all'… % del tetto mensile», con mese, spesa e tetto.
- **Parte** una volta al mese all'80 % del tetto condiviso (20 € al mese all'inizio), solo se l'invio email è
  configurato.
- **Raggiunto il tetto**, l'assistente risponde «Limite mensile raggiunto, riprova dal mese prossimo».
- **Il tetto** non si cambia dall'app.

**Avvisi di monitoraggio del servizio**, ai responsabili indicati nella configurazione:

- **«BFF non raggiungibile»**: server dell'app fermo per 5 minuti, con l'email di chiusura quando torna.
- **«BFF: scrittura non riuscita»**.
- **«Motori: VM muta»**, «Motori: motore muto o giù».
- **«Motori: righe di errore»**, «Motori: backup mancato».
- **«Motori: disco della VM oltre l'80 %»**.

> **Da sapere**
>
> Questi avvisi non si impostano dalle preferenze personali.

### Amministrazione e Organizzazioni a confronto

**Le due pagine di gestione, scheda per scheda.**

Chi è sia amministratore di un'organizzazione sia gestore della piattaforma vede tutte e due le voci.

| Amministrazione (l'amministratore, per la sua organizzazione) | Organizzazioni (il gestore della piattaforma, per tutte) |
|---|---|
| «Appartamenti»: l'uso di ogni giorno: nome, indirizzo, attivo o no, prezzo, «Verifica connessione». | «Appartamenti» dentro ogni organizzazione: la parte tecnica: creare, collegare al sistema domotico, codice Italianway, eliminare, «Verifica connessione». |
| «Utenti»: le persone della propria organizzazione, con ruolo e appartamenti visibili. | «Gestori della piattaforma»: le persone di HQE. Della singola organizzazione il gestore vede solo il primo amministratore («Reinvia invito»). |
| «Funzioni»: quali schermate sono attive. | Nessuna scheda corrispondente. |
| «Prenotazioni ricevute»: le prenotazioni arrivate ai propri appartamenti. | «Prenotazioni non attribuite»: quelle che non corrispondono a nessun appartamento. Le due schede non si sovrappongono. |
| «Registro dell'organizzazione»: chi ha fatto cosa, con i nomi. | «Registro della piattaforma»: cosa è successo in un'organizzazione, con i soli ruoli; più le azioni della piattaforma. |
| L'avviso dell'accesso di assistenza, con «Chiudi accesso». | «Accesso di assistenza» in «Elenco organizzazioni»: aprirlo, entrare, chiuderlo. |
| Nessuna scheda corrispondente. | «Elenco organizzazioni»: creare, rinominare, sospendere, riattivare, invitare il primo amministratore. |

## 8. Accesso di assistenza

**Come HQE entra a tempo nei dati di un'organizzazione.**

È il modo in cui HQE entra nei dati di un'organizzazione quando c'è un problema: a tempo, con un motivo, visibile
all'amministratore. Non serve un'approvazione preventiva.

### Aprire l'accesso

**Il gestore della piattaforma apre l'accesso dalla scheda dell'organizzazione.**

1. **In «Elenco organizzazioni»** premi «Accesso di assistenza» sulla scheda.
2. **Si apre «Accesso di assistenza a «…»»** («Per il tempo scelto lavori dentro l'organizzazione con i permessi di
   un operatore. L'amministratore lo vede subito e può chiuderlo; apertura e chiusura restano nel registro
   attività.»).
3. **Scegli «Durata»** (da 1 a 24 ore, 2 all'inizio).
4. **Scrivi «Motivo (obbligatorio, lo vede l'amministratore)»** e premi «Apri l'accesso».
5. **Leggi** «Accesso di assistenza a «…» aperto fino al …».
6. **La scheda mostra** «Accesso di assistenza aperto fino al …» o, per un collega, «Accesso di assistenza di …
   aperto fino al …».

> **Attenzione**
>
> - **Un gestore può avere un solo accesso aperto** per organizzazione («Hai già un accesso di assistenza aperto in
>   questa organizzazione»).
> - **Con un'organizzazione sospesa** non si apre («L'organizzazione è sospesa»).

### Entrare e lavorare come assistenza

**Dentro l'organizzazione con i permessi di un operatore.**

1. **Premi «Entra come assistenza»** (solo chi ha aperto quell'accesso).
2. **L'app si svuota** come a un cambio di utente.
3. **In alto compare la fascia** «Stai lavorando come assistenza in «…» fino alle …, con i permessi di un
   operatore.» con «Termina».
4. **Vedi «Appartamenti»** dell'organizzazione assistita e lavori come un operatore su tutti.
5. **Il profilo mostra** l'organizzazione assistita, ma nome, password e notifiche restano i tuoi e le notifiche
   dell'organizzazione assistita non ti arrivano.

> **Da sapere**
>
> Intanto l'amministratore vede l'avviso descritto nella parte 6 e può premere «Chiudi accesso».

### Chiudere l'accesso

**Come finisce l'accesso: a mano, alla scadenza o per altri motivi.**

- **Per finire** premi «Termina», oppure «Chiudi accesso» dalla scheda in Organizzazioni («Accesso di assistenza
  chiuso»).
- **Finisce da solo** alla scadenza, alla chiusura dell'amministratore, a una sospensione o se ti viene tolto il
  ruolo di gestore.
- **In quel caso leggi** «L'accesso di assistenza a «…» è finito: ora vedi di nuovo la tua area.» e i dati
  dell'organizzazione assistita vengono tolti dalla scheda.
- **Se la chiusura non riesce** leggi «Chiusura dell'accesso sul server non riuscita: chiudilo da Organizzazioni.».
- **Anche «Esci»** chiude l'accesso.

**Tutto resta nel registro:**

- «… ha aperto un accesso di assistenza a … fino al …»
- «… ha chiuso l'accesso di assistenza a …»
- «L'accesso di assistenza a … è scaduto»
## 9. Passo per passo

**Le situazioni di ogni giorno, dall'inizio alla fine.**

### Arriva un ospite

**Dalla prenotazione al check-in, con il pre-arrivo automatico.**

1. **La prenotazione arriva** da Italianway (o dal Simulatore, nei dimostrativi). Nelle Decisioni leggi «Prenotazione
   creata».
2. **In «Programmazione»** compare l'azione «pre-arrivo» con origine «prenotazione»: comfort 2 ore prima del check-in
   (il numero di ore è nella regola «Pre-arrivo»).
3. **All'ora del pre-arrivo** il motore mette l'appartamento in «comfort»: la caldaia chiede la temperatura di
   comfort; il climatizzatore, se nella stanza c'è un sensore, scalda o raffresca da solo.
4. **Nella scheda** l'occupazione è «Prenotato».
5. **Quando Italianway comunica l'arrivo effettivo** («Check-in» nelle Decisioni) l'occupazione diventa «Occupato».
6. **Da ora** l'assistente chiede conferma prima di spegnere clima o caldaia o cambiare modalità.
7. **Se vuoi scaldare prima** o cambiare qualcosa, usa «Modalità» o i comandi in Panoramica, oppure l'assistente.

> **Da sapere**
>
> Se la prenotazione viene annullata dopo il pre-arrivo, il motore rimette l'appartamento a «casa vuota» (salvo un
> altro soggiorno in corso o un altro pre-arrivo già eseguito), lo scrive nelle Decisioni («Disdetta dopo il
> pre-arrivo») e manda la notifica «Prenotazioni». Se c'è una forzatura, aspetta la sua fine.

### L'ospite è partito

**Dal check-out al ritorno a casa vuota, con il controllo del movimento.**

1. **All'orario di partenza** della prenotazione più i «Minuti dopo il check-out» della regola «Risparmio al
   check-out» (30 all'inizio), in «Programmazione» c'è l'azione «check-out» verso «casa vuota».
2. **A quell'ora**, se il sensore di movimento ha visto qualcuno dopo l'orario di partenza negli ultimi «Minuti di
   presenza dopo il check-out» (30 all'inizio), il motore non va a casa vuota da solo.
3. **Apre la richiesta** «Mettere l'appartamento a vuoto dopo il check-out» (nella frase del motore «a vuoto» vuol
   dire la modalità casa vuota), con il sensore, i minuti dal movimento e l'orario di partenza, e manda la notifica
   «Approvazioni richieste».
4. **Premi «Approva»** se l'ospite è davvero andato via, «Respingi» se è ancora dentro.
5. **Senza risposta entro 30 minuti** la richiesta viene approvata e l'appartamento va a casa vuota.
6. **Senza movimento** l'appartamento passa a «casa vuota» da solo: clima spento, caldaia sull'antigelo.
7. **In «Consumi»** puoi scaricare «Excel del soggiorno» per riaddebitare l'energia.

> **Da sapere**
>
> Con una forzatura attiva il cambio aspetta la sua fine.

### Un dispositivo va offline

**Che cosa vedi e che cosa arriva quando un dispositivo non risponde.**

1. **In Panoramica** il dispositivo mostra «Dispositivo offline» e «Visto …»; i suoi comandi sono disattivati («Il
   dispositivo non è raggiungibile: i comandi sono disattivati»).
2. **Mentre guardi l'appartamento** compare l'avviso «… è offline».
3. **Se resta offline** oltre i minuti della regola «Avviso dispositivo offline» (15 all'inizio), nelle Decisioni
   compare «Dispositivo offline».
4. **A chi ha la categoria «Dispositivi e sistema domotico offline» attiva** arriva la notifica «…: dispositivo
   offline», «… non risponde da oltre … minuti».
5. **Se torna prima**, niente avviso. Con la regola spenta non arriva nulla.
6. **Un comando a un dispositivo offline** risponde «Il dispositivo non è raggiungibile; riprova quando torna
   online».
7. **Nel riepilogo del lunedì** un dispositivo ancora offline da più di 24 ore compare come «… è offline da più di
   24 ore.».
8. **Se il problema continua**, l'amministratore prova «Verifica connessione» in Amministrazione e avvisa
   l'assistenza.

**Se è l'intero sistema domotico a non rispondere:**

- **La striscia di salute** dice «Ferma» e «Sistema domotico non raggiungibile».
- **Compare l'avviso** «Sistema domotico non raggiungibile».
- **Dopo la stessa soglia** arriva la notifica «…: sistema domotico non raggiungibile», «Il connettore domotico
  risulta fermo».
- **Nelle Decisioni**: «Collegamento ai dispositivi perso» e poi «Collegamento ai dispositivi ripristinato».
- **Non arriva** una notifica di ritorno online.

### Approvare una richiesta

**In breve: notifica, lettura, nota, decisione, controllo.**

Vedi la parte 5, «Approvazioni: approvare o respingere». In breve:

1. **Apri la notifica** o «Approvazioni» › «In attesa».
2. **Leggi** descrizione, motivo e scadenza.
3. **Scrivi** una nota facoltativa.
4. **Premi «Approva»** o «Respingi».
5. **Controlla l'esito** in Panoramica e nelle Decisioni.

> **Da sapere**
>
> Alle richieste dell'assistente puoi rispondere anche in chat con «Sì» o «No».

### Chiedere qualcosa all'assistente

**Una domanda o un comando in italiano, poi il controllo.**

1. **Apri «Assistente»** e scrivi, per esempio, «perché si è spento il clima?», «quanto abbiamo consumato ieri?»,
   «spegni la caldaia» o «alle 18 metti la casa in eco». Premi «Invia».
2. **Per una domanda** ottieni una spiegazione presa da stati, consumi e Decisioni.
3. **Per un comando** leggi l'esito scritto dal sistema: «Fatto: ….», «Comando inviato: …, l'esito arriva
   nell'app.», «Non riuscito: … (…).» o «Programmato: ….».
4. **Se in fondo leggi «Risposta rapida: …»**, ha risposto il sistema da solo: un comando semplice è stato eseguito,
   uno complesso no; in quel caso usa i pulsanti dell'app.
5. **Se con ospiti dentro** chiedi di spegnere clima o caldaia o di cambiare modalità, o se programmi un'azione per
   un'ora in cui ci saranno ospiti, rispondi «Sì» o «No» alla domanda in chat.
6. **Controlla** in Panoramica o in Programmazione che sia successo davvero.

### Cambiare le temperature delle modalità

**Regolare comfort, eco e raffrescamento nella regola «Limiti del setpoint».**

1. **Apri «Regole»** e trova «Limiti del setpoint».
2. **Sotto «Minimo (°C)» e «Massimo (°C)»** ci sono «Temperatura in comfort (°C)», «Temperatura in eco (°C)» e
   «Raffrescamento in comfort (°C)».
3. **Scrivi i valori** entro i limiti di ogni campo (tabella sotto).
4. **Premi «Salva le modifiche»** e leggi «Regole aggiornate».
5. **I nuovi valori agiscono** dal prossimo cambio di modalità e, in comfort, dalla regolazione automatica del
   clima. Per applicarli subito scegli di nuovo la modalità in Panoramica.

| Campo | Limiti | All'inizio |
|---|---|---|
| «Temperatura in comfort (°C)» | Da 16 a 26 | 21 |
| «Temperatura in eco (°C)» | Da 10 a 22 | 18 |
| «Raffrescamento in comfort (°C)» | Da 22 a 28 | 25 |

> **Attenzione**
>
> Eco non può superare comfort; il raffrescamento deve essere più alto di comfort. Altrimenti leggi sotto il campo
> «La temperatura eco non può superare quella comfort» o «La temperatura di raffrescamento deve essere più alta di
> quella comfort» e il salvataggio resta disattivato.

> **Da sapere**
>
> In alternativa scrivi in «Chiedi all'assistente» «comfort 22» o «eco 17», premi «Proponi» e poi «Applica».

### Invitare un collega

**Dall'invito al primo accesso del collega.**

1. **Apri «Amministrazione» › «Utenti»**. In «Invita un utente» compila «Email», «Nome» e «Ruolo».
2. **Per operatore o sola lettura** scegli «Appartamenti visibili»: tutti oppure solo quelli che servono.
3. **Premi «Invita»** e leggi l'esito: «Invito inviato a …» oppure un messaggio sull'email non partita (l'invito
   resta: usa «Reinvia» più tardi).
4. **Il collega apre l'email** «Invito a DOMHOUSE» (anche nello spam).
5. **Entra** con «Accedi con Google» o sceglie la password con «Scegli la password» (link valido 1 ora; se scaduto,
   «Password dimenticata?»). Se serve conferma l'indirizzo e accede di nuovo.
6. **Al primo accesso** sparisce «in attesa del primo accesso».
7. **Il collega vede** solo gli appartamenti assegnati; può installare l'app e attivare le notifiche da
   «Impostazioni».

### Provare l'app con il Simulatore

**Finestra, dispositivo offline, approvazione e prenotazione su un dimostrativo.**

1. **Apri un appartamento** con l'etichetta «Dimostrativo» e la pagina «Simulatore» (solo amministratori).
2. **Finestra**: in «Finestre» apri un sensore. Dopo i minuti della regola «Finestra aperta spegne il clima» clima e
   caldaia si spengono; nelle Decisioni leggi la regola. Richiudi la finestra.
3. **Dispositivo offline**: in «Connettività dispositivi» metti un dispositivo «offline»: i comandi vengono rifiutati
   e dopo i minuti della regola arriva l'avviso. Rimettilo «online».
4. **Approvazione**: premi «Richiedi un'approvazione» e vai in «Approvazioni» per decidere.
5. **Prenotazione**: in «Evento prenotazione» scegli «Prenotazione creata», un «ID prenotazione», «Check-in» e
   «Check-out» futuri, «Ospiti» e premi «Invia evento»: leggi «… azioni programmate» e vai in «Programmazione».
6. **Arrivo**: invia «Check-in effettivo» con lo stesso identificativo: l'occupazione diventa «Occupato».
7. **Partenza**: invia «Check-out effettivo» o aspetta l'ora del check-out più i minuti della regola; con «Simula
   movimento» in «Movimento» provochi la richiesta «Mettere l'appartamento a vuoto dopo il check-out».
8. **Ricominciare**: «Ripristina…» in fondo riporta l'appartamento allo stato iniziale.

### Creare un'organizzazione e un appartamento (HQE)

**Dalla nuova organizzazione all'appartamento pronto per l'amministratore.**

1. **«Organizzazioni» › «Elenco organizzazioni» › «Nuova organizzazione»**: «Nome dell'organizzazione», «Email del
   primo amministratore», eventuale nome; «Crea». Leggi l'esito dell'invito.
2. **Il primo amministratore entra** come nella parte 2. Finché non entra puoi usare «Reinvia invito».
3. **Nella scheda dell'organizzazione** premi «Appartamenti» › «Nuovo appartamento».
4. **Compila** «ID» definitivo, «Nome», «Indirizzo del sistema domotico», eventuale «Porta», «Fuso orario», «ID
   Italianway» (deve essere quello giusto: decide dove vanno le prenotazioni), «Attivo», «Appartamento dimostrativo»;
   «Salva».
5. **Con un sistema domotico vero** leggi «Prima di usarlo: crea la chiave del sistema domotico e poi premi Verifica
   connessione.»: la chiave la prepara il responsabile tecnico fuori dall'app.
6. **Premi «Verifica connessione»** e vai avanti solo con «Connessione OK».
7. **L'amministratore completa** in «Amministrazione» › «Appartamenti»: «Indirizzo», prezzo, funzioni, e assegna
   l'appartamento agli utenti.
8. **Per un dimostrativo** l'amministratore prova il Simulatore.

> **Da sapere**
>
> Nel sito vero, fino alla consegna al cliente, i dimostrativi con il motore simulato integrato sono ammessi come
> nell'ambiente di prova.

### Quando qualcosa non funziona

**Leggere l'avviso, copiare l'identificativo, annotare, segnalare.**

1. **Leggi il testo esatto dell'avviso** e cercalo nella parte 11. Un pulsante disattivato per chi ha sola lettura
   non è un guasto.
2. **Se c'è «Riprova»**, usalo dopo aver risolto il problema indicato.
3. **Per un comando già approvato** o con esito incerto controlla prima Panoramica e Decisioni, per non ripetere
   l'azione alla cieca.
4. **Tocca «ID richiesta»** («Copiato») e incollalo nella ricerca delle Decisioni: trovi subito l'operazione.
   All'accesso copia invece il «Codice».
5. **Annota** appartamento, azione e passi, cosa è comparso, data e ora, telefono o computer e browser; se puoi, una
   schermata (parte 13).
6. **Amministratore**: prova «Verifica connessione» in Amministrazione e comunica «Ultima verifica». Per una
   prenotazione, apri «Dettagli tecnici».
7. **Se serve**, HQE apre un accesso di assistenza (parte 8).

### Una giornata tipo dell'operatore

**Il giro di controllo quotidiano, pagina per pagina.**

1. **Apri «Appartamenti»**: controlla la riga «… approvazioni in attesa», «Prossimo check-in», «Prossimo check-out»,
   lo stato e «Consumo di oggi».
2. **Apri l'appartamento**: in Panoramica guarda «In tempo reale», la salute e la fascia di stato («Occupazione»,
   «Finestre», «Dispositivi online»). Con «Riconnessione…» aspetta.
3. **In «Programmazione»** controlla pre-arrivo, check-out e azioni manuali; aggiungi o sposta solo se serve.
4. **Per intervenire** usa la modalità o la scheda del dispositivo; con «Forza per…» ricorda che i cambi programmati
   aspettano la fine della forzatura.
5. **Controlla gli esiti**; per capire un comportamento cerca nelle «Decisioni».
6. **Decidi le richieste** in «Approvazioni». Usa l'«Assistente» per domande e comandi.
7. **Guarda «Consumi»** e, il lunedì, «Riepiloghi» anche senza notifica.

## 10. Cosa fa il sistema da solo

**Modalità, regole, termostato, prenotazioni e conservazione dei dati.**

### Le tre modalità e le loro temperature

**Che cosa fanno caldaia e climatizzatore in ogni modalità.**

| Modalità | Caldaia | Climatizzatore |
|---|---|---|
| «comfort» | Abilitata alla «Temperatura in comfort (°C)» (21 all'inizio); il termostato la accende e spegne intorno a quel valore. | Con un sensore di temperatura nella stessa stanza: regolazione automatica (sotto). Senza sensore nella stanza non lo tocca e scrive una volta «Regolazione automatica disattivata». |
| «eco» | Abilitata alla «Temperatura in eco (°C)» (18 all'inizio). | Spento. |
| «casa vuota» | Abilitata alla temperatura dell'«Antigelo a casa vuota» (8 °C all'inizio). | Spento. |

**La regolazione automatica del clima in comfort:**

- **Scalda** alla temperatura di comfort quando la stanza è sotto.
- **Raffresca** alla «Raffrescamento in comfort (°C)» (25 all'inizio) quando è sopra.
- **Fra le due** lo lascia com'è.
- **Quando**: al cambio di modalità e poi ogni minuto.
- **Rispetta** l'isteresi (0,5 °C) e il tempo minimo fra due cambi (5 minuti).
- **Non agisce** durante una forzatura né con una finestra aperta e regola finestra attiva.
- **Non va mai contro un comando di una persona**: un clima che hai comandato tu resta com'è fino al prossimo cambio
  di modalità.
- **Ogni cambio automatico** è una decisione con la temperatura letta, per esempio «…: 19 °C, sotto 21 °C: scalda».

> **Da sapere**
>
> - **Le tre temperature** si regolano per appartamento nella regola «Limiti del setpoint» (parte 9).
> - **I valori chiesti** restano sempre entro i limiti del dispositivo e, con la regola accesa, entro il minimo e il
>   massimo che hai scelto.
> - **I pulsanti «−» e «+»** della temperatura non escono mai dai limiti (una caldaia a 8 °C con minimo 16 passa a
>   16 con un tocco).

### Le otto regole: descrizione e valori

**Ogni regola come la descrive l'app, con valori di partenza e limiti.**

Tutte partono attive. Sette si modificano dall'app, una no.

| Regola | Descrizione nell'app | Valori di partenza e limiti |
|---|---|---|
| «Finestra aperta spegne il clima» | «Spegne clima e caldaia se una finestra resta aperta più dei minuti indicati.» | «Minuti»: 5, da 1 a 30 |
| «Limiti del setpoint» | «Limita la temperatura impostabile da ospiti e app. In comfort la caldaia e il clima scaldano fino alla temperatura comfort; il clima raffresca sopra quella di raffrescamento, se nella stanza c'è un sensore di temperatura. In eco la caldaia sta alla temperatura eco.» | Vedi la tabella sotto |
| «Antigelo a casa vuota» | «Con la casa vuota mantiene almeno questa temperatura.» | «Temperatura (°C)»: 8, da 5 a 12 |
| «Antimuffa a casa vuota» | «Con la casa vuota, se l'umidità supera questa soglia registra un avviso nelle Decisioni, al massimo uno al giorno; non deumidifica da sola.» | «Umidità (%)»: 65, da 50 a 80 |
| «Pre-arrivo» | «Porta la casa in comfort prima dell'arrivo degli ospiti.» | «Ore prima del check-in»: 2, da 0 a 6 |
| «Risparmio al check-out» | «Passa a casa vuota dopo il check-out; se il sensore ha visto qualcuno negli ultimi minuti indicati, chiede prima a te.» | «Minuti dopo il check-out»: 30, da 0 a 180; «Minuti di presenza dopo il check-out»: 30, da 5 a 180 |
| «Pausa minima del compressore» | «Pausa minima tra spegnimento e riaccensione del compressore.» | «Minuti»: 3; «Non modificabile» (chi gestisce il sistema può impostare da 1 a 15) |
| «Avviso dispositivo offline» | «Avvisa quando un dispositivo resta offline oltre i minuti indicati.» | «Minuti»: 15, da 5 a 120 |

**I valori di «Limiti del setpoint»:**

| Campo | All'inizio | Limiti |
|---|---|---|
| «Minimo (°C)» | 16 | Da 7 a 20 |
| «Massimo (°C)» | 24 | Da 20 a 28 |
| «Temperatura in comfort (°C)» | 21 | Da 16 a 26 |
| «Temperatura in eco (°C)» | 18 | Da 10 a 22 |
| «Raffrescamento in comfort (°C)» | 25 | Da 22 a 28 |

### Le otto regole: che cosa fanno davvero

**L'effetto reale di ogni regola, oltre la descrizione.**

- **«Finestra aperta spegne il clima»**: spegne clima e riscaldamento di tutto l'appartamento, non solo della
  stanza. Sospesa durante una forzatura; alla fine riparte. L'antigelo è più forte.
- **«Antigelo a casa vuota»**: a casa vuota accende la caldaia sotto la soglia e la spegne sopra la soglia più
  0,5 °C, anche se il riscaldamento è disabilitato («Antigelo: caldaia accesa», «Antigelo: caldaia spenta»). Serve
  un sensore: senza, «Antigelo non attivo».
- **«Antimuffa a casa vuota»**: scrive «Avviso antimuffa» nelle Decisioni, al massimo una volta al giorno, a casa
  vuota; durante una forzatura scrive che è sospesa. Non comanda la deumidificazione.
- **«Pre-arrivo»**: ogni prenotazione creata o modificata programma il comfort. Cambiare le ore vale per le
  prenotazioni che arrivano o cambiano dopo: le azioni già in programma non vengono ricalcolate.
- **«Risparmio al check-out»**: programma casa vuota dopo la partenza. Con movimento recente apre la richiesta
  «Mettere l'appartamento a vuoto dopo il check-out»; senza risposta la approva.
- **«Pausa minima del compressore»**: dopo uno spegnimento la riaccensione del clima aspetta; un comando automatico
  viene rimandato, uno di una persona o dell'assistente può essere rifiutato se manca più di qualche secondo.
- **«Avviso dispositivo offline»**: dopo la soglia scrive «Dispositivo offline» nelle Decisioni e manda la notifica;
  la stessa soglia vale per il sistema domotico fermo. Il ritorno online prima della soglia annulla tutto.

**«Limiti del setpoint»** (con effetto dal lotto 31):

- **Acceso**: clima e caldaia restano fra il minimo e il massimo che scegli, sempre dentro i limiti del dispositivo;
  un comando fuori intervallo è rifiutato, i comandi automatici vengono riportati dentro.
- **Spento**: valgono solo i limiti del dispositivo.
- **Se i tuoi limiti sono tutti fuori** da quelli del dispositivo valgono quelli del dispositivo e nelle Decisioni
  compare «Limiti del setpoint ignorati».
- **L'antigelo a casa vuota** non segue questi limiti.
- **Le tre temperature** guidano le modalità.

### Caldaia e clima, con e senza sensore

**Il termostato della caldaia e cosa succede senza sensore.**

- **«Riscaldamento abilitato»** vuol dire che la caldaia può scaldare.
- **Il termostato del sistema** accende e spegne davvero la caldaia intorno alla temperatura voluta, con un'isteresi
  di 0,5 °C e almeno 5 minuti fra due cambi, usando il sensore di temperatura collegato.
- **Con il misuratore sopra 30 W** leggi «sta scaldando ora».
- **Il climatizzatore in comfort** segue il sensore della sua stanza (sopra). Senza sensore nella stanza lo comandi
  solo tu.
- **Un comando tuo** su caldaia o clima toglie quel dispositivo alla regolazione della modalità fino al prossimo
  cambio di modalità, anche dopo un riavvio del sistema.

> **Attenzione**
>
> **Senza un sensore utilizzabile** (manca o è offline) la caldaia non si accende mai da sola.
> - **La temperatura chiesta da una modalità** (comfort, eco o antigelo) la lascia spenta, con una decisione per
>   episodio: «…: sensore di temperatura mancante, regolazione automatica disattivata» (in comfort ed eco).
> - **A casa vuota**: «…: sensore di temperatura mancante, antigelo non attivo» (tipo «Antigelo non attivo», con
>   notifica nella categoria «Dispositivi e sistema domotico offline»).
> - **Un comando di una persona o programmato** viene invece eseguito così com'è, senza regolazione («…: …; segue il
>   comando manuale senza regolazione»).
> - **Quando il sensore torna** leggi «…: sensore di nuovo disponibile, regolazione ripresa».

### Prenotazioni: pre-arrivo, check-out, disdette

**Come le prenotazioni muovono le modalità.**

- **Ogni prenotazione creata o modificata** da Italianway programma il pre-arrivo in comfort e, dopo il check-out,
  il ritorno a casa vuota.
- **Le azioni** hanno origine «prenotazione» e si ricalcolano a ogni modifica («Ricalcolata a ogni modifica della
  prenotazione»).
- **Una disdetta** annulla le azioni aperte.
- **Se il pre-arrivo era già stato eseguito**, programma il ritorno a casa vuota («Disdetta dopo il pre-arrivo») e
  manda la notifica «Prenotazioni», salvo un altro soggiorno in corso o un altro pre-arrivo già eseguito.
- **Un cambio di modalità programmato durante una forzatura** aspetta la sua fine («Azione rimandata»).
- **Dopo un riavvio del sistema**, un'azione in ritardo di oltre 30 minuti viene saltata («Programma: saltata»).
- **L'occupazione «Occupato»** richiede il check-in effettivo comunicato da Italianway; la sola prenotazione dà
  «Prenotato».

### Approvazioni automatiche

**Le richieste che il motore apre da solo e cosa succede senza risposta.**

| Richiesta | Quando | Senza risposta |
|---|---|---|
| «Mettere l'appartamento a vuoto dopo il check-out» | Dopo la partenza, se c'è stato movimento | Viene approvata |
| «Spegnere …» con il nome dell'apparecchio, «… consuma … W da oltre … minuti con l'appartamento vuoto» | A casa vuota, senza forzatura, un apparecchio spegnibile con misuratore (mai la caldaia) consuma oltre 300 W per più di 15 minuti (valori impostati da chi gestisce il sistema) | Viene respinta e l'apparecchio resta acceso, salvo impostazione diversa |
| Le richieste dell'assistente | Con ospiti dentro, o per più azioni insieme | Vengono respinte |

> **Da sapere**
>
> - **Dopo un no** a «Spegnere …», nessuna nuova richiesta finché il consumo non scende e risale.
> - **Una sola richiesta aperta per volta**: le altre aspettano in coda.
> - **La scadenza** è 30 minuti all'inizio (chi gestisce il sistema può impostare da 5 a 720).

### Comandi confermati dal consumo

**Il misuratore conferma accensione e spegnimento del clima a infrarosso.**

- **L'accensione o lo spegnimento** di un climatizzatore comandato a infrarosso è confermata dal suo misuratore entro
  una decina di secondi.
- **Le soglie**: consumo su di almeno 20 W per l'accensione, sotto 15 W per lo spegnimento.
- **Se il misuratore è offline** il comando risulta «non verificato» e nelle Decisioni compare «Comando non
  verificato: misuratore offline».

> **Attenzione**
>
> Una conferma di invio non prova sempre l'effetto fisico: in caso di dubbio guarda le letture del dispositivo.

### Il riepilogo settimanale

**Ogni lunedì, per ogni appartamento attivo, il riepilogo della settimana.**

- **Quando**: ogni lunedì dalle 8 (ora dell'appartamento), per la settimana da lunedì a domenica.
- **Consumi**: per notte con ospiti e per notte vuota, confrontati con la mediana delle 4 settimane prima («Alto»
  solo con almeno il 30 % in più e almeno 5 kWh di eccedenza).
- **Segnalazioni**: dispositivi offline da più di 24 ore, approvazioni scadute senza risposta, finestre aperte
  almeno 3 volte con il clima spento dalla regola.
- **Notifica**: se c'è almeno una segnalazione arriva la notifica «Riepilogo».
- **Settimana senza novità**: il riepilogo dice «Settimana senza novità» e non manda avvisi.

### Valori impostati fuori dall'app

**I valori che imposta il responsabile tecnico del sistema domotico.**

| Valore | Impostazione |
|---|---|
| Pausa del compressore | 3 minuti, da 1 a 15 |
| Breve attesa finale | 7 secondi |
| Isteresi del termostato | 0,5 °C |
| Tempo minimo fra due cambi | 5 minuti |
| Soglie di conferma dal misuratore | 20 W e 15 W |
| Scadenza delle approvazioni | 30 minuti |
| Soglie del consumo a casa vuota | 300 W, 15 minuti |
| Ritardo oltre il quale un'azione programmata viene saltata dopo un riavvio | 30 minuti |
| Quando l'assistente chiede conferma | Con ospiti, sempre, oppure solo per più azioni insieme |
| Domande al giorno all'assistente | 50 |
| Tetto mensile di spesa | 20 € |

### Per quanto tempo l'app conserva i dati

**I termini di conservazione, oltre i quali i dati si cancellano da soli.**

*Decisione del 17 ottobre 2026.* Oltre questi termini i dati si cancellano da soli, entro circa un giorno.

| Dati | Per quanto tempo |
|---|---|
| Prenotazioni e presenze degli ospiti | 12 mesi dopo il check-out |
| Decisioni dell'appartamento | 24 mesi |
| Consumi | 24 mesi (li conserva il sistema domotico dell'appartamento) |
| Richieste all'assistente | 90 giorni |
| Riepiloghi settimanali | 12 mesi |
| Registro dell'organizzazione, registro della piattaforma e accessi di assistenza | 24 mesi |
| Prenotazioni ricevute da Italianway (senza dati personali degli ospiti) | 90 giorni, e al massimo le ultime 100 |

- **Utenti, organizzazioni e appartamenti** restano finché non vengono tolti.
- **Chi elimina il proprio account** viene cancellato subito.
- **I dati personali degli ospiti** non vengono salvati; il sistema domotico riceve un codice anonimo al posto
  dell'email di chi comanda.
## 11. Problemi e messaggi

**Ogni messaggio dell'app: che cosa significa e che cosa fare.**

### All'accesso

**I messaggi della pagina «Accedi».**

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «Accesso non riuscito: controlla email e password» | Email o password sbagliate | Riprova o usa «Password dimenticata?» |
| «Troppi tentativi: riprova tra qualche minuto» | Troppi tentativi in poco tempo | Aspetta qualche minuto |
| «Connessione assente: riprova» | Il telefono o il computer non ha rete | Controlla la connessione |
| «Il browser ha bloccato la finestra di Google: consenti le finestre pop-up per questo sito e riprova» | Il browser ha bloccato la finestra di accesso di Google | Consenti le finestre pop-up e riprova |
| «Accesso con Google non attivo: avvisa l'assistenza HQE», «Accesso con Google non riuscito» | L'accesso con Google non è disponibile o è fallito | Riprova; se continua, avvisa l'assistenza con il «Codice» |
| «Questo indirizzo del sito non è autorizzato per l'accesso: avvisa l'assistenza HQE» | Il sito è aperto da un indirizzo non previsto | Avvisa l'assistenza |
| «Firebase non è ancora configurato su questo ambiente» | L'ambiente non è pronto per l'accesso | Avvisa l'assistenza |
| «Non hai i permessi per accedere. Chiedi un invito.» | L'account esiste ma nessuno ti ha invitato in questo ambiente (un invito nell'ambiente di prova non vale nel sito vero) | Chiedi un invito a un amministratore |
| «Conferma il tuo indirizzo: abbiamo inviato un link a …. Aprilo e poi accedi di nuovo.» | Il tuo indirizzo non è ancora confermato | Apri il link nell'email, poi accedi di nuovo |
| «Devi confermare il tuo indirizzo email, ma l'invio del link non è riuscito. Riprova tra qualche minuto.» | L'email di conferma non è partita | Riprova tra qualche minuto |
| «Impossibile caricare il profilo, riprova tra poco» | Il server non risponde | Riprova dopo qualche minuto |
| «La tua organizzazione non è attiva: contatta HQE.» | L'organizzazione non è ancora pronta | Contatta HQE |
| «La tua organizzazione è sospesa: l'app non è disponibile. Per informazioni contatta l'assistenza HQE.» | HQE ha sospeso la tua organizzazione | Contatta l'assistenza HQE |
| «Indirizzo email non valido» | L'email scritta non è un indirizzo | Correggi l'indirizzo |

### In tutte le pagine

**I messaggi comuni a tutta l'app.**

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «Server non raggiungibile» | L'app non raggiunge il server | Controlla la rete e premi «Riprova» |
| «Operazione non riuscita», «Errore …» | Il server ha risposto con un errore senza spiegazione | Riprova; se continua, copia l'«ID richiesta» e segnala |
| «Richiesta non accettata dal server: ricarica la pagina e riprova.» | La pagina è vecchia rispetto al server | Ricarica la pagina |
| «Accesso richiesto», «Sessione non valida o scaduta» | La sessione è finita | Accedi di nuovo |
| «Organizzazione non attiva», «Organizzazione sospesa: contatta l'assistenza HQE» | La tua organizzazione non è disponibile | Contatta HQE |
| «L'accesso di assistenza è scaduto o è stato chiuso» | L'accesso di assistenza è finito | Torni alla tua area; se serve, aprine uno nuovo |
| «Il tuo ruolo consente solo la lettura» | Hai il ruolo sola lettura | Chiedi a un operatore o a un amministratore |
| «Operazione riservata agli amministratori», «Operazione riservata ai gestori della piattaforma» | Serve un ruolo più alto | Chiedi a chi ha quel ruolo |
| «Appartamento inesistente», «Appartamento non disponibile» | L'appartamento non esiste o non è fra i tuoi | «Torna agli appartamenti»; chiedi l'assegnazione a un amministratore |
| «Appartamento disattivato» | L'amministratore ha spento «Attivo» | Chiedi all'amministratore |
| «Funzione non disponibile per questo appartamento» | La funzione è spenta o il sistema domotico non la ha | Chiedi all'amministratore (scheda «Funzioni») |
| «Sistema domotico non raggiungibile» | Il sistema domotico dell'appartamento non risponde | Aspetta; se continua, «Verifica connessione» e assistenza |
| «Versione del contratto non compatibile» | Il sistema domotico è di una versione non supportata | Contatta il supporto tecnico |
| «Pagina non trovata» | L'indirizzo non esiste, oppure non hai il ruolo per quella pagina | Torna al menu |

### Sui comandi e in Panoramica

**Gli esiti dei comandi ai dispositivi.**

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «Il dispositivo non è raggiungibile; riprova quando torna online», «dispositivo offline» | Il dispositivo è offline | Aspetta che torni online |
| «Collegamento ai dispositivi non disponibile; riprova quando torna» | Il sistema non parla con i dispositivi | Aspetta «Collegamento ai dispositivi ripristinato» nelle Decisioni |
| «Il setpoint deve essere tra … e …», «fuori dai limiti» | Temperatura fuori dai limiti | Scegli un valore nell'intervallo «da … a … °C» |
| «rifiutato dal dispositivo» | Il dispositivo non ha accettato il comando | Riprova; controlla il dispositivo |
| «bloccato da una regola», «bloccato da un'azione prioritaria» | Una regola (per esempio finestra aperta o pausa del compressore) o un'azione più importante ha bloccato il comando | Leggi il motivo nelle Decisioni; riprova dopo |
| «nessuna conferma», «nessuna risposta» | Il comando è partito ma non è stato confermato | Controlla le letture del dispositivo |
| «non verificato» | Il comando è partito ma non è stato confermato | Controlla le letture del dispositivo |
| «errore interno» | Un errore del sistema domotico | Copia l'«ID richiesta» e segnala |
| «Modalità non valida» | Modalità non riconosciuta | Scegli «comfort», «eco» o «casa vuota» |
| «Il nome deve avere da 1 a 60 caratteri», «Stanza inesistente» | Dati della rinomina non validi | Correggi nome o stanza |
| «Dispositivo inesistente» | Dati della rinomina non validi | Correggi nome o stanza |

### In Approvazioni, Programmazione, Regole, Assistente e Simulatore

**I messaggi delle pagine dell'appartamento.**

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «L'approvazione è già stata decisa», «Approvazione inesistente» | Un collega ha già deciso, o la richiesta non c'è più | Rileggi l'elenco |
| «note troppo lunga» | La nota supera 500 caratteri | Accorcia la nota |
| «L'orario deve essere nel futuro» | L'orario scelto è passato | Scegli un orario futuro |
| «Azione programmata inesistente», «L'azione è già stata eseguita o annullata» | La voce non è più in programma | Rileggi l'elenco |
| «Valore fuori dai limiti (…–…)», ««…»: … deve essere tra … e …» | Un valore della regola è fuori dai limiti | Correggi il valore |
| «Il minimo non può superare il massimo» | Le temperature non sono coerenti | Correggi i valori |
| «La temperatura eco non può superare quella comfort», «La temperatura di raffrescamento deve essere più alta di quella comfort» | Le temperature non sono coerenti | Correggi i valori |
| «La regola «…» non è modificabile» | Regola fissata dal sistema | Non si cambia dall'app |
| «Salva o annulla prima le modifiche fatte a mano» | Hai modifiche non salvate nella pagina Regole | «Salva le modifiche» o «Annulla le modifiche», poi «Applica» |
| «Le regole sono cambiate nel frattempo: rifai la richiesta», «Le regole dell'appartamento di partenza sono cambiate: rifai l'anteprima» | Qualcuno ha cambiato le regole | Rifai la proposta o l'anteprima |
| «Le regole sono già così: non c'è niente da cambiare» | La proposta non cambia nulla | Niente da fare |
| «Al massimo 500 caratteri», «Scrivi che cosa vuoi cambiare» | Testo vuoto o troppo lungo | Scrivi una frase più corta |
| «Scrivi una richiesta», «text obbligatorio, massimo 500 caratteri» | Testo vuoto o troppo lungo | Scrivi una frase più corta |
| «Hai già chiesto 20 proposte oggi per questo appartamento: riprova domani o cambia le regole a mano» | Limite giornaliero delle proposte | Cambia la regola a mano o riprova domani |
| «L'assistente non ha risposto in tempo: riprova con una frase più breve, oppure cambia la regola a mano qui sotto.» | Il modello non ha risposto in tempo | Riprova con una frase più breve |
| «Nessuna risposta dall'assistente: riprova», «Non sono riuscito a rispondere in tempo: riprova, oppure fai dall'app.» | L'assistente non ha risposto | Riprova o usa i comandi dell'app |
| «L'assistente non è disponibile ora, riprova più tardi», «Non sono riuscito a rispondere: riprova.» | L'assistente non ha risposto | Riprova o usa i comandi dell'app |
| «Risposta rapida: l'assistente completo non ha risposto in tempo.» (in fondo alla risposta) | Ha risposto il sistema da solo: solo un comando semplice è stato eseguito | Per comandi complessi usa i pulsanti dell'app; riprova più tardi per le domande |
| «… non è raggiungibile ora.», «… ha raggiunto il limite mensile.» (le altre due varianti della risposta rapida) | Ha risposto il sistema da solo: solo un comando semplice è stato eseguito | Per comandi complessi usa i pulsanti dell'app; riprova più tardi per le domande |
| «Limite di … domande al giorno raggiunto per questo appartamento: riprova domani.» | Limite giornaliero dell'assistente | Usa i comandi dell'app |
| «Limite mensile raggiunto, riprova dal mese prossimo» | Tetto di spesa del servizio raggiunto | Usa i comandi dell'app; HQE riceve un'email |
| «Nessun altro appartamento nella tua organizzazione», «Scegli almeno un appartamento di destinazione» | Condizioni della copia delle regole | Correggi la scelta |
| «Al massimo 100 appartamenti alla volta», «Solo gli amministratori possono copiare le regole» | Condizioni della copia delle regole | Correggi la scelta |
| «Il simulatore è riservato agli amministratori», «Questo appartamento non è un dimostrativo» | Il Simulatore non è disponibile qui | Solo amministratori, solo dimostrativi |
| «Il check-out deve essere successivo al check-in» | Date della prenotazione di prova invertite | Correggi le date |
| «Nessun apparecchio con misuratore da proporre nell'appartamento» | Nessun apparecchio adatto alla prova | Usa un altro dimostrativo |
| «Il ripristino è disponibile solo con il motore simulato integrato.» | Il ripristino non è possibile su un sistema vero | Nessuna azione |

### In Amministrazione e Organizzazioni

**I messaggi delle pagine di gestione.**

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «È già un utente della tua organizzazione», «Questa email non può essere invitata» | La persona è già dentro, oppure è di HQE | Non invitare; per HQE serve la procedura tecnica |
| «Gli amministratori vedono sempre tutti gli appartamenti» | Non si limitano gli appartamenti di un amministratore | Cambia ruolo se serve |
| «Utente inesistente», «L'utente ha già effettuato l'accesso» | Il reinvio non è possibile | Rileggi l'elenco |
| «Non puoi togliere a te stesso il ruolo di amministratore», «Non puoi eliminare il tuo stesso account» | Protezioni sul proprio ruolo | Chiedi a un altro amministratore |
| «Deve restare almeno un amministratore nell'organizzazione» | Protezione sull'ultimo amministratore | Chiedi a un altro amministratore |
| «Ruolo non aggiornato, riprova tra poco», «Rimozione non riuscita, riprova tra poco» | Errore passeggero | Riprova |
| «Eliminazione non riuscita, riprova tra poco» | Errore passeggero | Riprova |
| «Fuso orario non valido», «Funzione sconosciuta» | Dati non validi | Correggi |
| «Appartamento inesistente: …» | Dati non validi | Correggi |
| «Prezzo non valido: da 0 a 10 € al kWh, al massimo 4 decimali» | Prezzo fuori formato | Scrivi per esempio 0,25 |
| «Chiave del sistema domotico non configurata: contatta l'assistenza HQE» | Manca la chiave del sistema domotico | Avvisa l'assistenza |
| «Scrivi il nome dell'organizzazione», «Esiste già un'organizzazione con questo nome» | Nome mancante o duplicato | Correggi |
| «Organizzazione inesistente» | Organizzazione non trovata | Correggi |
| «L'organizzazione è già sospesa», «L'organizzazione non è sospesa» | Stato non coerente | Rileggi la scheda |
| «Scrivi il motivo della sospensione» | Manca il motivo | Rileggi la scheda |
| «La durata va da 1 a 24 ore», «Scrivi il motivo dell'accesso di assistenza» | Condizioni dell'accesso di assistenza | Correggi o riprova |
| «L'organizzazione è sospesa», «Hai già un accesso di assistenza aperto in questa organizzazione» | Condizioni dell'accesso di assistenza | Correggi o riprova |
| «Accesso non aperto: riprova tra poco» | Condizioni dell'accesso di assistenza | Correggi o riprova |
| «Accesso di assistenza inesistente» | L'accesso è già chiuso | Niente da fare |
| «Identificativo non disponibile», «Collegamento già usato da un altro appartamento» | Valori già usati o non riusabili | Scegli valori diversi |
| «Codice Italianway già in uso» | Valori già usati o non riusabili | Scegli valori diversi |
| «Indirizzo non valido: deve cominciare con http:// o https://», «In questo ambiente di prova scrivi mock://builtin nel campo Indirizzo del sistema domotico» | Collegamento scritto male o non ammesso | Correggi il collegamento |
| «Ha già il ruolo di gestore della piattaforma», «Non è un gestore della piattaforma» | Condizioni sui gestori | Rileggi l'elenco |
| «È l'ultimo gestore della piattaforma: nomina prima qualcun altro» | Condizioni sui gestori | Rileggi l'elenco |

### Nelle Impostazioni e nelle notifiche

**I messaggi di account, password e notifiche.**

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «La password deve avere almeno … caratteri», «Le due password non coincidono» | La nuova password non va bene | Scegline una più lunga e ripetila uguale |
| «Password troppo debole: usa almeno 8 caratteri» | La nuova password non va bene | Scegline una più lunga e ripetila uguale |
| «Password attuale non corretta» | Hai sbagliato la password attuale | Riprova |
| «Questa email è già usata da un altro account» | Il nuovo indirizzo è di un altro account | Usa un altro indirizzo |
| «Per sicurezza esci e accedi di nuovo, poi riprova» | L'operazione richiede un accesso recente | «Esci», accedi e riprova |
| «Operazione non riuscita, riprova» | Errore passeggero | Riprova |
| «Sei l'unico amministratore: nomina un altro amministratore prima di eliminare il tuo account», «Sei l'ultimo gestore della piattaforma: nomina un altro gestore prima di eliminare il tuo account» | Non puoi lasciare l'organizzazione o la piattaforma senza nessuno | Nomina prima un altro |
| «Account non abilitato: mancano tenant o ruolo» | Il tuo account non appartiene a nessuna organizzazione in questo ambiente | Chiedi un invito; un gestore senza organizzazione non può salvare nome e preferenze |
| «Permesso non concesso: su questo dispositivo le notifiche restano spente.», «Attivazione delle notifiche non riuscita: riprova tra poco.» | Le notifiche non si sono attivate | Consenti il permesso e riprova |
| «Notifiche non riattivate: il browser non ne dà più il permesso. Puoi riattivarle da Impostazioni › Notifiche.» | Al rientro il browser non permette più le notifiche | Consenti le notifiche e premi «Attiva su questo dispositivo» |

## 12. Parole usate in questa guida

**Il significato delle parole ricorrenti, in ordine alfabetico.**

| Parola | Che cosa vuol dire |
|---|---|
| Accesso di assistenza | Ingresso temporaneo (da 1 a 24 ore) di un gestore della piattaforma in un'organizzazione, con i permessi di un operatore, motivo visibile all'amministratore. |
| Ambiente di prova | Il sito con dati separati da quelli veri, con la fascia gialla «Ambiente di prova». Non è un ruolo. |
| Antigelo | Protezione a casa vuota: la caldaia si accende sotto la soglia, se c'è un sensore. |
| Antimuffa | Un avviso di umidità sopra soglia a casa vuota, al massimo uno al giorno; non deumidifica. |
| Approvazione | Una richiesta che aspetta il sì o il no di una persona prima di un'azione; alla scadenza segue quanto scritto nella scheda. |
| Avviso nell'app | Messaggio temporaneo in alto nella pagina aperta; non è una notifica sul telefono. |
| Capacità | Una cosa che un dispositivo sa fare o misurare: interruttore, clima, riscaldamento, temperatura, umidità, contatto, movimento, potenza. |
| Casa vuota | La modalità per l'appartamento senza ospiti: clima spento, caldaia sull'antigelo. Nella scheda, «Vuoto» indica invece l'occupazione. |
| Check-in, check-out | Arrivo e partenza previsti dalla prenotazione; l'arrivo e la partenza effettivi sono comunicazioni a parte di Italianway. |
| Codice Italianway | Il codice con cui il sistema di prenotazioni Italianway riconosce una struttura: decide a quale appartamento arrivano le prenotazioni. Lo inserisce solo HQE. |
| Collegamento al sistema domotico | L'indirizzo (campo «Indirizzo del sistema domotico») del sistema che comanda davvero i dispositivi; nell'ambiente di prova `mock://builtin`. |
| Comfort | La modalità con gli ospiti: caldaia e clima alla temperatura di comfort; raffrescamento sopra la temperatura di raffrescamento. |
| Connettore | Il collegamento con cui il sistema domotico legge e comanda i dispositivi; «Connettore» «attivo» o «fermo» nella striscia di salute. |
| Decisione | Una riga dello storico: chi ha fatto o proposto cosa, su cosa, perché, con quale esito. |
| Dimostrativo | Appartamento finto per prove e dimostrazioni, con l'etichetta «Dimostrativo» e il Simulatore. |
| Eccezione per appartamento | Una scelta del singolo appartamento che sostituisce quella dell'organizzazione (funzioni o prezzo). |
| Eco | La modalità di risparmio: clima spento, caldaia alla temperatura di eco. |
| Forzatura | Un periodo (30 minuti, 2 ore, 6 ore) in cui la modalità resta e gli automatismi del comfort sono sospesi; l'antigelo resta. |
| Gestore della piattaforma | Chi gestisce il servizio per tutte le organizzazioni (HQE): crea organizzazioni e collega gli appartamenti. |
| ID richiesta | L'identificativo copiabile di un'operazione, per cercarla nelle Decisioni o aiutare l'assistenza. |
| Isteresi | La piccola differenza di temperatura (0,5 °C) che evita accensioni e spegnimenti continui intorno alla soglia. |
| Istanza | Nome tecnico del sistema domotico che gestisce un appartamento, vero o dimostrativo; l'app dice sempre «sistema domotico». |
| kWh | L'energia consumata in un periodo; l'importo dipende dal prezzo per kWh. |
| Mediana | Il valore centrale dei consumi delle stesse notti nelle settimane prima, usato dal riepilogo. |
| Modalità | La scelta complessiva dell'appartamento: «comfort», «eco», «casa vuota». |
| Motore | La parte automatica del sistema domotico: applica regole, modalità, programmi e comandi. |
| Non verificato | Lo stato mostrato è quello richiesto, senza una conferma del misuratore. |
| Notifica push | Avviso del telefono o del browser che arriva anche ad app chiusa. |
| Occupazione | Lo stato della prenotazione: «Vuoto», «Occupato», «Prenotato». |
| Offline | Dispositivo o collegamento non raggiungibile; non vuol dire spento. |
| Organizzazione | Un'azienda che usa l'app, con i suoi utenti e i suoi appartamenti (oggi Flatsharing). |
| Pausa del compressore | L'attesa di protezione (3 minuti) prima di riaccendere il climatizzatore. |
| Pre-arrivo | La preparazione automatica in comfort prima del check-in. |
| Proposta di regole | L'anteprima delle modifiche suggerita dall'assistente nella pagina Regole; cambia solo con «Applica». |
| Raffrescamento in comfort | La temperatura sopra la quale, in comfort, il climatizzatore raffresca (25 °C all'inizio). |
| Regola | Un automatismo già previsto dal motore, con interruttore e valori; dall'app non se ne creano di nuovi. |
| Regolazione automatica del clima | In comfort, il controllo ogni minuto dei climatizzatori secondo il sensore della stanza. |
| Rendiconto Excel | Il file scaricabile con riepilogo, consumi per giorno, ora e dispositivo e importi. |
| Riscaldamento abilitato | La caldaia può scaldare secondo il termostato; non vuol dire che stia scaldando adesso. |
| Setpoint | La temperatura desiderata, diversa da quella misurata. |
| Simulatore | La pagina, solo per amministratori, per provocare eventi sugli appartamenti dimostrativi. |
| Soggiorno | Il periodo fra arrivo e partenza di una prenotazione conosciuta dall'app. |
| W | La potenza in questo istante; non è il consumo del giorno. |

## 13. Segnalare un problema

**Che cosa annotare e a chi mandarlo.**

Per ogni problema annota:

1. **Cosa stavi facendo**, passo per passo.
2. **Cosa ti aspettavi e cosa è successo**, con il testo esatto dell'avviso.
3. **L'«ID richiesta»**, se compare (o il «Codice» della pagina di accesso).
4. **Dispositivo e browser** (per esempio «iPhone, Safari» o «PC, Chrome»), data e ora.
5. **Una schermata**, se possibile.

> **Da sapere**
>
> Manda tutto a **operations@hqe.it**, l'indirizzo dell'assistenza HQE.

## 14. Novità

**Che cosa è cambiato, aggiornamento per aggiornamento.**

### 23 ottobre 2026 (lotto 34)

**Colori caldi e un colore per ogni stato: modalità, occupazione, finestre, dispositivi, esiti.**

- **Aspetto**: un foglio bianco caldo dentro una cornice color sabbia; il menu laterale e, sul telefono, la barra in
  alto stanno sulla cornice (sul telefono la cornice è sottile).
- **Menu**: la voce aperta è bianca, con un filo arancione a sinistra.
- **Pulsanti principali** marrone scuro; testi e grigi in toni caldi.
- **Panoramica, «Modalità»**: Comfort arancione chiaro, Eco verde salvia, Casa vuota azzurro ardesia; così anche il
  selettore della modalità.
- **Panoramica, «Occupazione»**: «Occupato» verde, «Prenotato» ambra, «Vuoto» tortora.
- **Panoramica, «Finestre» e «Dispositivi online»**: verdi se tutto è a posto, ambra con una finestra aperta o un
  dispositivo offline.
- **Panoramica, «Consumo di oggi»**: il numero in arancione; così anche «Totale periodo» in Consumi.
- **Appartamenti**: in alto resta solo la pillola «Online» o «Non raggiungibile»; via la pillola «Vuoto»/«Occupato».
- **Appartamenti, la striscia**: «Modalità» nel colore della modalità, «Occupazione» a fondo pieno, «Consumo di oggi»
  in arancione, «Prossimo check-out» a tutta larghezza.
- **Decisioni**: l'esito è di nuovo un badge colorato: «Applicata» verde, «Respinta» e «Non riuscita» rosso mattone,
  «in attesa di approvazione» ambra, «Informativa» tortora.
- **Regole sul telefono**: mentre scrivi, la barra «Salva le modifiche» non copre il campo.
- **Simulatore**: una colonna fino a 1024 px e, sopra, due colonne senza spazi vuoti; icone senza riquadro colorato.
- **App installata**: la barra di stato del telefono è color sabbia, non più arancione.
- **Testi dell'app**: nessuno cambiato.

### 23 ottobre 2026 (lotto 33)

**Pagine riordinate: fascia di stato, righe al posto delle schede, codici dietro «Dettagli».**

- **Panoramica**: sotto il titolo la fascia di stato con «Modalità», «Occupazione», «Prossimo check-in» o «Prossimo
  check-out», «Finestre», «Consumo di oggi», «Dispositivi online»; via la riga con check-in, check-out e
  prenotazione.
- **Salute**: «In salute» e «… dispositivi connessi» in vista; connettore, modello e versione dietro «Dettagli
  tecnici».
- **Dispositivi**: su computer un elenco per stanza, una riga per dispositivo; letture a righe; «Modo» e
  «Ventola» del clima sono tendine; «Dispositivo offline» è un badge, la scheda non è più sbiadita.
- **Consumi**: le caselle «Totale periodo» e «Ora con più consumo» o «Giorno con più consumo»; «Ore di clima
  evitate» solo quando c'è; il confronto con il soggiorno precedente su una riga, con «Excel del soggiorno
  precedente».
- **Appartamenti**: il sottotitolo dice solo «… appartamenti»; dati in una striscia con «Consumo di oggi»; in
  fondo «1 approvazione in attesa» o «… approvazioni in attesa» con la freccia; via la campanella.
- **Decisioni**: azione e valori, esito a parole a destra (rosso, giallo o grigio), poi data · chi · dispositivo,
  motivo e «ID richiesta»; codici dietro «Dettagli»; sul telefono le tendine dietro «Filtri».
- **Approvazioni**: stato, fonte e data in alto; «Perché il motore lo propone» senza riquadro; «ID richiesta» solo
  nelle richieste decise; via il bordo arancione.
- **Programmazione**: «In programma» e «Storico» con «Ultimi 7 giorni» sono riquadri a righe.
- **Regole**: prima le regole, poi «Chiedi all'assistente» e la copia su altri appartamenti; barra «Salva le
  modifiche» lungo il fondo; «1 regola modificata» al singolare.
- **Assistente**: un solo riquadro; la risposta sotto il nome «Assistente», senza bolla; «Risposto» non compare
  più; «Comando inviato», «Azione programmata», «Regole modificate» al posto dei codici, che stanno in «Dettagli».
- **Impostazioni**: «Nome visualizzato» e «Lingua» dentro «Profilo»; via i riquadri «Account» e «Lingua»; su
  computer il titolo di ogni riquadro a sinistra.
- **Amministrazione e Organizzazioni**: linguette sottolineate e scheda aperta nell'indirizzo; appartamenti e
  utenti come righe; menu «⋯» con le azioni meno frequenti; una spiegazione sotto ogni funzione.
- **Accesso**: marchio e nome sopra la scheda; su computer il pannello scuro con «Riscaldamento, clima e consumi
  dei tuoi appartamenti».
- **Caricamento**: mentre arrivano i dati le pagine mostrano già la loro forma.

### 23 ottobre 2026 (lotto 32)

**Dimostrativi nel sito vero, «sistema domotico» ovunque, interfaccia ripulita.**

- **Dimostrativi anche nel sito vero**: fino alla consegna al cliente, gli appartamenti dimostrativi con il motore
  simulato integrato sono ammessi anche nel sito vero, non solo nell'ambiente di prova.
- **«Sistema domotico» al posto di «istanza»**, ovunque nell'app: «Sistema domotico non raggiungibile», «Dispositivi
  e sistema domotico offline», «Indirizzo del sistema domotico».
- **E anche**: «Appartamento dimostrativo», «Funzione non disponibile per questo appartamento», «Nessun dispositivo in
  questo appartamento».
- **Stati con l'iniziale maiuscola**: «In attesa», «Approvata», «Respinta», «Scaduta», «Applicata», «Non riuscita»,
  «In programma», «Eseguita».
- **E anche**: «Risposto», «Richiede approvazione».
- **E l'occupazione**: «Vuoto», «Occupato», «Prenotato», come «In salute» e «Online».
- **Interfaccia ripulita**: pulsante principale scuro, meno effetti, testi più leggibili sul telefono.
- **Via** la riga «Ambiente» dalle Impostazioni, il piè di pagina della pagina di accesso e i codici inglesi in
  Amministrazione › Funzioni: le funzioni si leggono con i nomi del menu.
- **Nome del gestore**: si aggiorna subito, anche durante un accesso di assistenza.
- **Simulatore**: l'evento prenotazione chiede almeno 1 ospite.
- **Contatore dell'assistente**: conta i timeout anche quando la domanda era già stata contata.

### 23 ottobre 2026 (lotto 31)

**Limiti del setpoint con effetto, fuso orario sul motore, scheda Assistente.**

- **«Limiti del setpoint» con effetto**: acceso, clima e caldaia restano fra il minimo e il massimo scelti, dentro i
  limiti del dispositivo; spento, valgono solo quelli del dispositivo; l'antigelo non li segue.
- **I pulsanti «−» e «+»** della temperatura non escono mai dai limiti.
- **Antimuffa**: la descrizione dice quello che fa davvero, un avviso al giorno nelle Decisioni.
- **Fuso orario sul motore**: in Amministrazione si vede e non si modifica; quando cambia, il registro
  dell'organizzazione lo annota.
- **Amministrazione › Assistente**: le domande all'assistente settimana per settimana (da lunedì a domenica), quante
  senza risposta in tempo dall'assistente completo, quante con una risposta rapida e per quale causa.
- **Nella stessa scheda** le righe sopra il 10 % sono in giallo; con due settimane complete di fila sopra la soglia
  compare l'avviso che va riaperta la scelta del modello.
- **Gestore della piattaforma senza organizzazione**: salva il nome ed esce da tutti i dispositivi senza errori.

### 22 ottobre 2026 (lotto 30)

**Temperature delle modalità regolabili, clima regolato in continuo, assistente più solido.**

- **Temperature delle modalità regolabili** per appartamento, nella regola «Limiti del setpoint»: «Temperatura in
  comfort (°C)», «Temperatura in eco (°C)», «Raffrescamento in comfort (°C)».
- **I valori incoerenti** vengono segnalati anche prima del salvataggio.
- **Clima in comfort regolato in continuo**: con il sensore della stanza il climatizzatore scalda o raffresca da
  solo, ogni minuto, mai contro un comando di una persona; senza sensore «Regolazione automatica disattivata».
- **Caldaia senza sensore**: non si accende più da sola; a casa vuota «Antigelo non attivo» con notifica.
- **Programmazioni dell'assistente con ospiti**: conferma in chat se all'ora programmata ci saranno ospiti.
- **Assistente più solido**: il modello propone le azioni in una forma controllata e il sistema le verifica una per
  una.
- **Risposta rapida**: se il modello non risponde, una «Risposta rapida» esegue solo i comandi semplici e
  inequivocabili. Il modello lavora soltanto in Europa.
- **Il tuo nome nel menu**, in grassetto, con sotto l'email.
- **Notifiche: quattro voci**: tolta «Decisioni del motore».
- **Due registri con nomi diversi**: «Registro dell'organizzazione» e «Registro della piattaforma».
- **Proposte delle regole**: l'assistente capisce «comfort 22», «eco 17», «raffrescamento 26»; «temperatura 22» da
  sola chiede quale temperatura.
- **Simulatore**: ripremere «Invia evento» senza cambiare nulla mostra «Evento già elaborato (idempotente)».
- **«Casa vuota»**: la modalità si chiama così (prima «vuoto»); «vuoto» è l'occupazione.
- **Assistente**: dopo «Sì» o «No» la chat dice com'è andata; riaprendo, «Approvata da te alle …» o «Respinta da te
  alle …»; «Già decisa» solo se ha deciso un'altra persona.

### 20 e 21 ottobre 2026

**Regole complete, decisioni in italiano, consumi veri, riepilogo settimanale.**

- **Regole complete** (otto regole con interruttore e valori).
- **Caldaia** con «Riscaldamento abilitato» / «Riscaldamento disabilitato», «sta scaldando ora» e termostato
  automatico; avviso prima di forzare con finestra aperta.
- **Decisioni** con il tipo di azione in italiano e i tipi «Collegamento ai dispositivi perso», «Collegamento ai
  dispositivi ripristinato», «Comando non verificato: misuratore offline».
- **Comandi del climatizzatore** confermati dal misuratore.
- **Approvazioni automatiche** «Mettere l'appartamento a vuoto dopo il check-out» e «Spegnere …»; notifiche
  «Prenotazioni».
- **Consumi veri** ora per ora con «Consumi disponibili dal …»; Simulatore con «Misuratore clima» e «Simula
  movimento».
- **Riepilogo settimanale** ogni lunedì con la pagina «Riepiloghi» e la notifica «Riepilogo».
- **Assistente vero** che legge stati, consumi e Decisioni; ambiente di prova separato con la fascia gialla.
- **Regole proposte dall'assistente** nella pagina Regole; copia delle regole su altri appartamenti; «Minuti di
  presenza dopo il check-out».
- **Schede degli appartamenti** tutte nello schermo del telefono.

### 16 ottobre 2026

**Organizzazioni, ruoli, privacy e dimostrativi.**

- **Organizzazioni**: più organizzazioni separate, gestite dal gestore della piattaforma (HQE); codice Italianway e
  nome dell'organizzazione solo da HQE; nuovi appartamenti solo da HQE, anche nell'ambiente di prova.
- **Cambio di ruolo** con uscita da tutti i dispositivi entro un minuto; notifiche su dispositivo condiviso al
  sicuro; notifiche riattivate al rientro.
- **«Elimina il mio account»** cancella davvero l'accesso; non per l'ultimo amministratore né per l'ultimo gestore.
- **Nome dell'app DOMHOUSE**; barra laterale con i ruoli; menu a tre righe sul telefono.
- **«Prenotazioni ricevute» e «Prenotazioni non attribuite»**; registro attività; sospensione delle organizzazioni;
  accesso di assistenza a tempo.
- **Privacy**: «utente rimosso», codice anonimo al sistema domotico, nessun dato personale degli ospiti;
  conservazione dei dati a termine.
- **Appartamenti dimostrativi** con etichetta, Simulatore e ripristino; rendiconti Excel mensili e per soggiorno.
