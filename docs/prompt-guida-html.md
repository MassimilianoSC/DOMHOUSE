# Prompt: versione HTML della guida all'app

Da dare a Sol, che lavora in VS Code nella cartella del progetto. Scritto dalla memoria storica il 16 ottobre 2026
(decisione D-74). La fonte resta `docs/guida-utente.md`; l'HTML si rigenera da lì con uno script, così ogni
aggiornamento della guida arriva anche all'HTML.

---

```text
Devi trasformare la guida all'app «Domotica appartamenti» in una pagina HTML bella e leggibile. La pagina la riceverà
il cliente finale (Flatsharing, gestore di appartamenti in affitto breve), che non è tecnico. La guida cambierà spesso:
l'HTML non va scritto a mano, va GENERATO dalla guida in Markdown con uno script che si rilancia a ogni modifica.

Lavori nella cartella C:\Users\mcracchiolo\Desktop\DOMOTICA\app, branch main, dove lavorano anche altre sessioni.
Regole ferme:
- Crei SOLO questi tre file: docs/strumenti/guida_html.py (lo script), docs/strumenti/guida_modello.html (il modello
  grafico) e docs/guida-utente.html (il risultato). Non modifichi nessun altro file, e soprattutto NON docs/guida-utente.md.
- Niente commit, niente git add, niente comandi verso l'esterno. Il commit lo fa la memoria storica.
- Il testo della guida NON si cambia: né riscritto, né riassunto, né aggiunto. Se trovi errori o frasi poco chiare,
  elencali nella risposta finale: li corregge la memoria storica nel Markdown.

## 1. Lo script docs/strumenti/guida_html.py
- Python 3, SOLO libreria standard: nessun pacchetto da installare.
- `python docs/strumenti/guida_html.py` legge docs/guida-utente.md e docs/strumenti/guida_modello.html, e scrive
  docs/guida-utente.html.
- `python docs/strumenti/guida_html.py --check` non scrive niente: esce con codice 1 se docs/guida-utente.html non
  corrisponde a quello che lo script genererebbe ora (la guida è cambiata e l'HTML no), con codice 0 se è aggiornato.
  Il risultato deve quindi essere deterministico: niente data e ora di generazione dentro l'HTML. La data di versione si
  prende dal testo della guida.
- Converte il sottoinsieme di Markdown che la guida usa davvero: titoli #, ## e ###; paragrafi; elenchi puntati e
  numerati, anche annidati; **grassetto**, *corsivo*, `codice`; tabelle; citazioni (>); righe orizzontali (---);
  link. Leggi tutta la guida per vedere cosa compare.
- Se incontra una sintassi che non sa convertire, si ferma con un messaggio chiaro che indica la riga. Non deve
  produrre in silenzio un HTML rovinato.
- Riconosce i segni usati nella guida e li rende visibili:
  - le parti marcate «in arrivo» (*In arrivo:* …, «(in arrivo)» nei titoli) diventano un'etichetta o un riquadro
    «In arrivo»;
  - la citazione «Ambiente di prova» diventa un riquadro di avviso;
  - i nomi dei ruoli (Amministratore, Operatore, Sola lettura, Gestore della piattaforma) diventano piccole etichette
    dove sono intestazioni di sezione.
  Se un segno non c'è più nella guida, lo script non deve fallire.
- Genera l'indice dai titoli ## e ### con ancore stabili: lo stesso titolo dà sempre la stessa ancora.
- Codice leggibile e commentato in italiano. Le istruzioni d'uso stanno in cima al file.

## 2. Il modello grafico docs/strumenti/guida_modello.html e il risultato
- Un solo file HTML autosufficiente: CSS dentro il file, nessun JavaScript obbligatorio, nessuna risorsa esterna
  (niente CDN, niente font da internet: usa i font di sistema). Deve aprirsi con un doppio clic, anche senza rete, e
  si deve poter mandare per email.
- In italiano, `<html lang="it">`, titolo «Guida all'app Domotica appartamenti».
- Aspetto curato e sobrio, da documento professionale per un cliente:
  - copertina o intestazione con il titolo, il sottotitolo della guida e la data di versione;
  - indice laterale fisso su schermo largo, indice in cima su telefono;
  - buona tipografia: righe di 65-75 caratteri, spaziature generose, titoli gerarchici chiari;
  - tabelle leggibili anche su telefono, con scorrimento orizzontale solo dentro la tabella;
  - riquadri distinti per «Ambiente di prova» e «In arrivo»;
  - le sezioni «Chi fa cosa nel servizio», «Parole usate in questa guida» e «Cosa cambia con il prossimo
    aggiornamento» devono saltare all'occhio.
- Colori come variabili CSS su :root, con un tema scuro automatico (prefers-color-scheme) altrettanto curato.
- Stampa: un foglio di stile @media print che dia un PDF pulito, con l'indice in testa, senza la barra laterale, senza
  colori di sfondo pesanti, con interruzioni di pagina sensate (mai un titolo in fondo pagina da solo). Il
  committente potrà stampare in PDF dal browser.
- Accessibilità: contrasto sufficiente, ordine dei titoli corretto, link dell'indice usabili da tastiera.
- Niente loghi o marchi inventati. HQE, Flatsharing e Italianway compaiono solo come testo, come nella guida.
- Deve funzionare bene su telefono (larghezza 360 px) e su computer, in Chrome, Edge e Safari.

## 3. Prima di consegnare
- Lancia lo script, poi `--check` (deve dare 0). Modifica una parola in una COPIA temporanea della guida, fuori dalla
  cartella del progetto, e verifica che `--check` su quella copia dia 1. Per questo lo script accetta anche i
  percorsi come argomenti facoltativi.
- Confronta il testo dell'HTML con la guida: nessuna frase persa, nessuna aggiunta. Indica come l'hai verificato.
- Apri l'HTML e controllalo a larghezza da telefono e da computer, in tema chiaro e scuro, e in anteprima di stampa,
  se hai un modo per farlo.

## 4. Cosa restituire
1. In cima, per il committente non tecnico, al massimo 5 righe: cosa hai fatto e come aprire la guida.
2. Il comando per rigenerare l'HTML e quello di controllo.
3. Le sintassi del Markdown che lo script riconosce, e cosa succede se la guida ne usa una nuova.
4. Gli errori o le frasi poco chiare trovati nella guida (testo, riga, proposta), senza averli corretti.
5. Cosa non hai potuto verificare.
Scrivi tutto in italiano.
```
