# DOMHOUSE — sito (PWA)

Il sito dell'app: React 18, Vite, TypeScript, Tailwind, PWA con un solo service worker (`src/sw.ts`, cache e notifiche
push). Parla solo con il BFF (`../bff`), mai direttamente con il motore degli appartamenti. Il quadro generale è in
[`../README.md`](../README.md).

## Avvio in locale

```bash
cd frontend
cp .env.example .env    # BFF su http://localhost:8000, accesso di sviluppo (senza Firebase)
yarn install
yarn dev                # http://localhost:5173
```

Il BFF si avvia a parte; `make dev` dalla cartella principale avvia BFF e sito insieme. La porta del sito è **5173** e
non cambia da sola (`strictPort`): è l'unica ammessa dalla chiave web di Firebase (D-52, P-45).

## Comandi

| Comando | Cosa fa |
|---|---|
| `yarn typecheck` | controllo dei tipi |
| `yarn test` | prove del sito (Vitest) |
| `yarn test:ci` | le stesse, con il rapporto in `test-results/vitest.json` |
| `yarn gen:api` | rigenera `src/api/schema.ts` da `../contract/openapi.yaml` |
| `yarn build` | tipi dal contratto, controllo dei tipi e costruzione in `dist/` |
| `yarn size:check` | build e controllo del blocco principale (soglia 400 kB) |
| `yarn preview` | serve `dist/` per una prova locale |

Il giro completo del progetto (BFF, sito ed emulatore Firestore) è `python scripts/run_tests.py` dalla cartella
principale; si lancia una volta per lotto (D-83).

## Regole da ricordare

- Ogni testo che l'utente legge sta in `src/i18n/it.json`; `src/i18n/keys.test.ts` controlla chiavi e testi scritti a
  mano.
- `../contract/openapi.yaml` non si modifica: è il contratto con il motore.
- Nessun segreto e nessun file `.env*` nel repository (`.env.example` a parte).

## Documenti

In [`../docs/`](../docs/): `registro.md` (decisioni e stato), `guida-utente.md` (guida per chi usa l'app),
`regole-convivenza.md` (come lavorano insieme le sessioni), `note-tecniche-motore.md`.
