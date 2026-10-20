# Prompt di ripartenza

Dopo un riavvio delle sessioni, il committente incolla questo testo identico in o1 e in o2. Le fa presentare alla
memoria storica senza toccare niente.

```text
Lavori nel progetto DOMHOUSE (già Domotica appartamenti), cartella C:\Users\mcracchiolo\Desktop\DOMOTICA\app. Leggi CLAUDE.md, docs/regole-convivenza.md, docs/registro.md (sezioni 1 e 8) e gli ultimi 5 commit (git log --oneline -5). Non modificare nessun file e non fare commit. Poi usa ListAgents e trova la memoria storica: è la sessione che si presenta come tale (il nome cambia a ogni riavvio; se non sei sicura di quale sia, chiedilo al committente, non scrivere a caso). Presentati con SendMessage: il nome con cui ti vedi, la cartella in cui lavori, e conferma di aver letto i documenti. Poi aspetta il compito: ti dirà se sei o1 (server) o o2 (sito) e ti indicherà docs/prompt-o1.md o docs/prompt-o2.md.
```

La memoria storica, dopo il proprio riavvio, rilegge `docs/registro.md` e la propria memoria, poi usa ListAgents e
aspetta che o1 e o2 si presentino.
