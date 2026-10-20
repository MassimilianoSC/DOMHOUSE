#!/usr/bin/env python3
"""Genera la checklist HTML offline (Python 3, sola libreria standard).

Il Markdown è la fonte. --check: 0 aggiornato, 1 diverso/mancante,
2 errore di sintassi o lettura. Nessun file viene scritto da --check.
Sintassi: #/##, paragrafi, elenchi semplici, separatori, tabelle;
in linea **grassetto**, *corsivo*, _corsivo_, __grassetto__, codice,
link e escape. HTML, immagini, barrato, note e blocchi ignoti sono errori.
<appartamento> e <mese>, presenti nella fonte, sono testo letterale.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


class ErroreChecklist(ValueError):
    """Errore della fonte con il numero di riga."""


def errore(riga: int, messaggio: str) -> None:
    raise ErroreChecklist(f"Riga {riga}: {messaggio}")


def impronta(testo: str) -> str:
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()


def inline(testo: str, riga: int) -> str:
    """Parser esplicito: mai eseguire HTML proveniente dalla fonte."""
    def leggi(pos: int, chiusura: str = "") -> tuple[str, int]:
        parti = []
        while pos < len(testo):
            nr = riga + testo[:pos].count("\n")
            if chiusura and testo.startswith(chiusura, pos) and not (
                len(chiusura) == 1 and testo.startswith(chiusura * 2, pos)
            ):
                return "".join(parti), pos + len(chiusura)
            c = testo[pos]
            if c == "\\":
                if pos + 1 >= len(testo) or testo[pos + 1] not in r'\`*_{}[]()#+-.!|>':
                    errore(nr, "escape non supportato.")
                parti.append(html.escape(testo[pos + 1]))
                pos += 2
                continue
            if testo.startswith(("![", "~~", "***", "___"), pos):
                errore(nr, "immagini, barrato o enfasi tripla non supportati.")
            if c == "`":
                fine = testo.find("`", pos + 1)
                if fine <= pos + 1 or "\n" in testo[pos + 1:fine]:
                    errore(nr, "codice in linea non chiuso o delimitatore non supportato.")
                parti.append("<code>" + html.escape(testo[pos + 1:fine]) + "</code>")
                pos = fine + 1
                continue
            if c in "*_" and not (c == "_" and pos and testo[pos - 1].isalnum()):
                segno = c * 2 if testo.startswith(c * 2, pos) else c
                valore, fine = leggi(pos + len(segno), segno)
                if not valore:
                    errore(nr, "enfasi vuota.")
                tag = "strong" if len(segno) == 2 else "em"
                parti.append(f"<{tag}>{valore}</{tag}>")
                pos = fine
                continue
            if c == "[":
                fine = testo.find("](", pos + 1)
                if fine < 0:
                    errore(nr, "link incompleto, riferimento o nota non supportati.")
                end, livello = fine + 2, 1
                while end < len(testo) and livello:
                    livello += (testo[end] == "(") - (testo[end] == ")")
                    end += 1
                if livello:
                    errore(nr, "destinazione del link non chiusa.")
                href = testo[fine + 2:end - 1]
                if (not href or re.search(r'[\s<>"\x00-\x1f]', href)
                        or urlsplit(href).scheme.lower() not in {"", "http", "https", "mailto"}):
                    errore(nr, "indirizzo del link non supportato.")
                label = inline(testo[pos + 1:fine], nr)
                parti.append(f'<a href="{html.escape(href, quote=True)}">{label}</a>')
                pos = end
                continue
            if c == "<":
                placeholder = re.match(r"<(appartamento|mese)>", testo[pos:])
                if placeholder:
                    parti.append(html.escape(placeholder[0]))
                    pos += len(placeholder[0])
                    continue
                if re.match(r"(?:</?[A-Za-z!]|<!--|<https?://)", testo[pos:]):
                    errore(nr, "HTML incorporato o autolink non supportato: usare [testo](link).")
            if c in "[]" or testo.startswith("{{", pos):
                errore(nr, "sintassi in linea non supportata.")
            parti.append(html.escape(c))
            pos += 1
        if chiusura:
            errore(riga, f"enfasi {chiusura} non chiusa.")
        return "".join(parti), pos

    return leggi(0)[0]


def celle(testo: str, riga: int) -> list[str]:
    if not testo.startswith("|") or not testo.endswith("|"):
        errore(riga, "le righe della tabella devono iniziare e finire con |.")
    # Le barre nel codice o precedute da escape non separano le celle.
    valori, corrente, codice, escape = [], [], False, False
    for c in testo[1:-1]:
        if c == "|" and not codice and not escape:
            valori.append("".join(corrente).strip())
            corrente = []
        else:
            corrente.append(c)
        if c == "`" and not escape:
            codice = not codice
        escape = c == "\\" and not escape
    valori.append("".join(corrente).strip())
    return valori


def analizza(fonte: str) -> dict:
    righe = fonte.splitlines()
    documento = {"versione": impronta(fonte.replace("\r\n", "\n")), "prove": [], "sezioni": []}
    intro, blocchi, ids, sezioni = [], None, set(), set()
    titolo, sezione, i = None, None, 0
    while i < len(righe):
        testo, nr = righe[i].strip(), i + 1
        if not testo:
            i += 1
            continue
        if righe[i].startswith(("    ", "\t")) or (righe[i].startswith(" ") and testo.startswith("- ")):
            errore(nr, "blocchi di codice indentati o elenchi annidati non supportati.")
        if re.fullmatch(r"(?:={3,}|\*\s*\*\s*\*.*|_\s*_\s*_.*)", testo):
            errore(nr, "titolo sottolineato o separatore non supportato; usare #/## e ---.")
        if testo.startswith("# "):
            if titolo is not None or intro or sezione:
                errore(nr, "serve un solo titolo # all'inizio.")
            titolo = inline(testo[2:], nr)
            i += 1
            continue
        if titolo is None:
            errore(nr, "la checklist deve iniziare con # Titolo.")
        if testo.startswith("## "):
            nome = testo[3:]
            if nome == "Come si usa":
                if blocchi is not None:
                    errore(nr, "Come si usa deve precedere le sezioni delle prove.")
                blocchi = intro
                blocchi.append("<h2>Come si usa</h2>")
            else:
                m = re.fullmatch(r"([A-Z])\. (.+)", nome)
                if not m or m[1] in sezioni:
                    errore(nr, "sezione attesa: ## X. Titolo, con lettera univoca.")
                sezioni.add(m[1])
                sezione = {"id": m[1], "titolo": nome, "html": inline(nome, nr), "contesto": []}
                documento["sezioni"].append(sezione)
                blocchi = sezione["contesto"]
            i += 1
            continue
        destinazione = intro if blocchi is None else blocchi
        if re.fullmatch(r"-{3,}", testo):
            destinazione.append("<hr>")
            i += 1
            continue
        if testo.startswith("|"):
            if not sezione:
                errore(nr, "tabella di prove fuori da una sezione.")
            colonne = celle(testo, nr)
            if colonne not in (["N.", "Ruolo", "Passi", "Risultato atteso", "Esito"],
                               ["N.", "Dispositivo", "Passi", "Risultato atteso", "Esito"],
                               ["N.", "Passi", "Risultato atteso", "Esito"]):
                errore(nr, "colonne della tabella non supportate.")
            if i + 1 >= len(righe):
                errore(nr, "separatore della tabella mancante.")
            separatori = celle(righe[i + 1].strip(), nr + 1)
            if len(separatori) != len(colonne) or not all(re.fullmatch(r":?-{3,}:?", c) for c in separatori):
                errore(nr + 1, "separatore della tabella non valido.")
            i += 2
            inizio = len(documento["prove"])
            while i < len(righe) and righe[i].strip().startswith("|"):
                valori = celle(righe[i].strip(), i + 1)
                if len(valori) != len(colonne):
                    errore(i + 1, "numero di celle diverso dall'intestazione.")
                row = dict(zip(colonne, valori))
                sigla = re.fullmatch(r"([A-Z][0-9]+[a-z]?)(?: (📱))?", row["N."])
                if not sigla or sigla[1][0] != sezione["id"] or sigla[1] in ids:
                    errore(i + 1, "sigla non valida, duplicata o estranea alla sezione.")
                if row["Esito"] or not row["Passi"] or not row["Risultato atteso"]:
                    errore(i + 1, "Esito deve essere vuoto; passi e risultato sono obbligatori.")
                ids.add(sigla[1])
                p = {"sigla": sigla[1], "sezione": sezione["id"], "ripetuta": bool(sigla[2]),
                     "ruolo": row.get("Ruolo", ""), "dispositivo": row.get("Dispositivo", ""),
                     "passi": row["Passi"], "atteso": row["Risultato atteso"], "riga": i + 1}
                for campo in ("ruolo", "dispositivo", "passi", "atteso"):
                    p[campo + "_html"] = inline(p[campo], i + 1)
                # JSON canonico evita collisioni dovute alla concatenazione dei due campi.
                p["impronta"] = impronta(json.dumps([p["passi"], p["atteso"]], ensure_ascii=False, separators=(",", ":")))
                documento["prove"].append(p)
                i += 1
            if inizio == len(documento["prove"]):
                errore(nr, "tabella priva di prove.")
            continue
        if re.match(r"(?:#{1,6}\s|>|```|~~~|\d+[.)]\s|\+\s|\*\s|\[.*\]:)", testo):
            errore(nr, "blocco Markdown non supportato.")
        elenco = testo.startswith("- ")
        parti = [testo[2:] if elenco else testo]
        i += 1
        while i < len(righe) and righe[i].strip():
            prossima = righe[i].strip()
            if righe[i].startswith(("    ", "\t")) or (righe[i].startswith(" ") and prossima.startswith("- ")):
                errore(i + 1, "blocchi di codice indentati o elenchi annidati non supportati.")
            if re.fullmatch(r"={3,}", prossima):
                errore(i + 1, "titolo sottolineato non supportato; usare #/##.")
            if prossima.startswith(("#", "|", "- ")) or re.fullmatch(r"-{3,}", prossima):
                break
            if elenco and not righe[i].startswith("  "):
                break
            if re.match(r"(?:>|```|~~~|\d+[.)]\s|\+\s|\*\s|\[.*\]:)", prossima):
                errore(i + 1, "blocco Markdown non supportato.")
            parti.append(prossima)
            i += 1
        valore = inline("\n".join(parti), nr)
        destinazione.append(f"<ul><li>{valore}</li></ul>" if elenco else f"<p>{valore}</p>")
    if not documento["prove"]:
        errore(1, "nessuna prova trovata.")
    for s in documento["sezioni"]:
        if not any(p["sezione"] == s["id"] for p in documento["prove"]):
            errore(1, f"la sezione {s['id']} non contiene prove.")
    documento["copertina"] = f"<h1>{titolo}</h1>\n" + "\n".join(intro)
    return documento


def genera(fonte: str, modello: str) -> str:
    d = analizza(fonte)
    contenuto = []
    for s in d["sezioni"]:
        contenuto.append(f'<section class="test-section" id="sezione-{s["id"]}" aria-labelledby="titolo-{s["id"]}">'
                         f'<h2 id="titolo-{s["id"]}">{s["html"]}</h2>'
                         f'<p class="section-progress" data-section="{s["id"]}"></p>'
                         f'<progress data-section-meter="{s["id"]}" value="0" max="1" aria-label="Prove completate sezione {s["id"]}"></progress>'
                         + "\n".join(s["contesto"]))
        for p in (p for p in d["prove"] if p["sezione"] == s["id"]):
            sid = p["sigla"]
            metadati = ""
            if p["ruolo"]:
                metadati += f'<p class="role"><strong>Ruolo:</strong> {p["ruolo_html"]}</p>'
            if p["dispositivo"]:
                metadati += f'<p><strong>Dispositivo:</strong> {p["dispositivo_html"]}</p>'
            contenuto.append(
                f'<article class="test-card" id="prova-{sid}" data-id="{sid}" data-fingerprint="{p["impronta"]}" aria-labelledby="titolo-{sid}">'
                f'<h3 id="titolo-{sid}">{sid}{" 📱" if p["ripetuta"] else ""}</h3>{metadati}'
                f'<p class="steps"><strong>Passi:</strong> <span>{p["passi_html"]}</span></p>'
                f'<p class="expected"><strong>Risultato atteso:</strong> <span>{p["atteso_html"]}</span></p>'
                f'<div class="test-controls" data-controls="{sid}"></div><div class="print-results" data-print="{sid}"></div></article>')
        contenuto.append("</section>")
    # JSON non eseguibile; < impedisce che la fonte possa chiudere lo script.
    dati = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    valori = {"COPERTINA": d["copertina"], "CONTENUTO": "\n".join(contenuto), "DATI": dati}
    if sorted(re.findall(r"\{\{([A-Z_]+)\}\}", modello)) != sorted(valori):
        raise ErroreChecklist("Il modello deve contenere una volta {{COPERTINA}}, {{CONTENUTO}} e {{DATI}}.")
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: valori[m[1]], modello)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "docs/checklist-collaudo.md")
    parser.add_argument("--template", type=Path, default=root / "docs/strumenti/checklist_modello.html")
    parser.add_argument("--output", type=Path, default=root / "docs/checklist-collaudo.html")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.output.resolve() in {args.source.resolve(), args.template.resolve()}:
            raise ErroreChecklist("L'output deve essere diverso dalla fonte e dal modello.")
        atteso = genera(args.source.read_text(encoding="utf-8-sig"), args.template.read_text(encoding="utf-8-sig")).encode("utf-8")
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != atteso:
                print(f"HTML non aggiornato o mancante: {args.output}", file=sys.stderr)
                return 1
            print(f"HTML aggiornato: {args.output}")
            return 0
        args.output.write_bytes(atteso)
        print(f"Checklist generata: {args.output}")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Impossibile generare la checklist: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
