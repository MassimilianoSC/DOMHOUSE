# Standard frontend UX/UI DOMHOUSE

Questa guida definisce dove intervenire per i cambiamenti grafici e come mantenere il frontend semplice da correggere.
La struttura corrente è la base: si aggiungono cartelle o fogli CSS solo quando un'esigenza reale lo giustifica.

## Perimetro

- Il lavoro UX/UI riusa schermate, contenuti, dati e comportamenti già presenti.
- Sono ammessi interventi di presentazione: gerarchia, spaziatura, tipografia, colori, layout responsive, accessibilità
  visiva e motion leggero.
- Restano fuori da una modifica grafica le query, l'autenticazione, lo stato applicativo, le API, il BFF, il motore e il
  contratto in `contract/`. Se un intervento sembra richiederli, prima si descrive l'impatto e si chiede una decisione.
- Non si aggiungono dipendenze o nuove funzionalità per ottenere un effetto puramente visivo quando bastano le
  tecnologie già presenti.

## Mappa dei file

| Percorso | Responsabilità | Regola pratica |
| --- | --- | --- |
| `frontend/src/theme/palettes.ts` | Valori delle palette e token cromatici semantici | È la sorgente dei colori; i componenti usano token, non codici colore duplicati. |
| `frontend/src/theme/appearance.ts` e `appearanceBootstrap.ts` | Scelta e inizializzazione del tema | Modificare solo se il comportamento dei temi è parte esplicita del lavoro. |
| `frontend/tailwind.config.cjs` | Collegamento dei token semantici alle classi Tailwind e definizioni condivise | Non duplicare qui i valori delle palette. |
| `frontend/src/index.css` | Unico ingresso CSS, direttive Tailwind, stili globali e classi nominate necessarie | Tenere ordinati gli stili base e le utility condivise; niente foglio nuovo per una singola correzione locale. |
| `frontend/src/pages/` | Composizione delle pagine e collegamento ai componenti già esistenti | Le modifiche visive restano vicine alla pagina; non spostare logica dati per rifinire il layout. |
| `frontend/src/components/ui/` | Primitive condivise dell'interfaccia | Cambiarle solo quando il miglioramento è coerente in tutte le schermate che le usano. |
| `frontend/src/components/<area>/` | Componenti riusabili di una specifica area | Tenere qui i dettagli di quell'area; promuoverli a condivisi solo dopo un uso reale in più punti. |
| `frontend/src/i18n/` | Testi localizzati dell'interfaccia | Riutilizzare le diciture presenti e aggiornare la traduzione corrispondente quando cambia un testo visibile. |
| `frontend/src/content/` | Contenuti statici e riferimenti di presentazione del frontend | Non usarla come seconda sorgente dei dati applicativi. |
| `frontend/public/` | Immagini, icone e altri asset serviti dal frontend | Ogni asset usato dall'app deve essere presente qui e versionato. |
| `frontend/src/api/`, `auth/`, `hooks/`, `store/` | Integrazioni, autenticazione e stato | Non modificarli per un intervento solo grafico. |
| `docs/` | Documentazione condivisa e versionata | Le regole e le decisioni utili a tutto il team vivono qui. |
| `/codex/` | Appunti e prove locali dell'assistente | È esclusa da Git; non inserirvi codice o asset necessari a ricostruire l'app. |

## Regole CSS e token

1. Per un valore già rappresentato da un token, usare la classe semantica esistente (`bg-background`, `text-foreground`,
   `border-border`, `rounded-*`, `font-*`) invece di introdurre un valore locale.
2. Una correzione che deve valere in più schermate si fa nel token condiviso, una sola volta. I colori di palette si
   cambiano in `theme/palettes.ts`; la famiglia tipografica condivisa si regola in `tailwind.config.cjs` e il raggio nei
   token già definiti in `index.css` e `tailwind.config.cjs`.
3. Una regola usata una sola volta resta vicino al componente con le classi Tailwind già in uso. Una regola nominata in
   `index.css` è appropriata quando rappresenta un comportamento visivo riutilizzato o una composizione complessa.
4. Non aggiungere un foglio CSS per pagina o componente per una singola modifica; non copiare classi lunghe in più punti.
   Se una classe si ripete, valutare prima un componente condiviso o un token semantico.
5. Evitare selettori globali che influenzano componenti non coinvolti e valori colore letterali dentro le pagine. Le
   eccezioni tecniche, come colori dinamici passati via custom property, devono essere circoscritte al componente.
6. Le modifiche devono restare leggibili: nomi descrittivi, un solo punto di verità per ogni scelta condivisa e nessuna
   astrazione creata senza un secondo uso concreto.

## Responsive, accessibilità e prestazioni

- Progettare dal mobile e verificare almeno una larghezza mobile e una desktop; evitare overflow, testi tagliati e
  controlli troppo vicini.
- Conservare le diciture e i dati esistenti. Non nascondere informazioni necessarie solo per far entrare un layout.
- Preferire transizioni brevi su `opacity` e `transform`; rispettare `prefers-reduced-motion`.
- Limitare filtri costosi, blur estesi, ombre sovrapposte, animazioni continue e nuove immagini pesanti. Gli effetti su
  un'immagine grande vanno verificati anche su dispositivi mobili.
- Non introdurre JavaScript o una dipendenza per un'animazione ottenibile con CSS già presente.
- Ogni modifica deve avere uno scopo leggibile e un impatto misurato: niente animazioni decorative che rallentano la
  lettura o la risposta ai comandi.

## Revisione e verifica

- Prima di modificare una regola condivisa, cercare tutti i suoi usi e verificare l'impatto sulle schermate esistenti.
- Dopo il lavoro, controllare il diff per confermare che non siano cambiati query, API, schema o file generati non
  pertinenti.
- Usare gli script già presenti in `frontend/package.json` in base al tipo di modifica e controllare il rendering in
  browser su mobile e desktop. La build completa include `gen:api`: se viene usata, verificare che non abbia prodotto
  modifiche al contratto o allo schema API in un lavoro esclusivamente grafico.
- Aggiornare questa guida solo quando cambia una regola condivisa; aggiornare la guida utente quando cambia qualcosa che
  l'utente vede o può fare.

## Flusso Git

Il lavoro segue `docs/regole-convivenza.md`: ramo dedicato, pull request verso `main`, revisione e merge a cura di
Massimiliano. Dopo il merge si sincronizza `main` approvato prima di creare il ramo del lavoro successivo. `/codex/`
non entra mai nella pull request.
