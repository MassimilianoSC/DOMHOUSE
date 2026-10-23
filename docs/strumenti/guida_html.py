#!/usr/bin/env python3
"""Genera la guida HTML usando soltanto la libreria standard di Python 3.

Uso, dalla cartella app (funziona anche da altre cartelle):
    python docs/strumenti/guida_html.py
    python docs/strumenti/guida_html.py --check
Percorsi facoltativi, anche per verificare copie temporanee senza scrivere:
    python docs/strumenti/guida_html.py --source guida.md --template modello.html --output guida.html --check

La guida Markdown resta la fonte. --check restituisce 0 se l'HTML è aggiornato,
1 se manca o è diverso, 2 per errori di lettura, modello o sintassi Markdown.
Le sintassi fuori dal sottoinsieme dichiarato sono errori, con riga della fonte.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import html
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlsplit


class ErroreGuida(ValueError):
    """Errore leggibile della fonte o del modello."""


def errore(riga: int, messaggio: str) -> None:
    raise ErroreGuida(f"Riga {riga}: {messaggio}")


@dataclass
class Blocco:
    tipo: str
    testo: str = ""
    riga: int = 1
    livello: int = 0
    figli: list[Blocco] = field(default_factory=list)
    righe: list[list[str]] = field(default_factory=list)
    allineamenti: list[str] = field(default_factory=list)
    numero: int = 1


ELENCO = re.compile(r"^( *)([-+*]|\d+[.)]) +(.*)$")
TITOLO = re.compile(r"^(#{1,6}) +(.*)$")
RUOLI = re.compile(r"\b(amministratore|operatore|sola lettura|gestore della piattaforma)\b", re.I)
IN_ARRIVO = re.compile(r"\bin arrivo\b", re.I)
SEZIONI_EVIDENTI = {
    "Chi fa cosa nel servizio", "Parole usate in questa guida",
    "Cosa cambia con il prossimo aggiornamento",
}


def testo_html(testo: str, etichette: bool = False) -> str:
    """Le etichette avvolgono le parole originali, senza aggiungerne altre."""
    if not etichette:
        return html.escape(testo)
    segni = re.compile(f"({RUOLI.pattern}|{IN_ARRIVO.pattern})", re.I)
    parti, inizio = [], 0
    for segno in segni.finditer(testo):
        parti.append(html.escape(testo[inizio:segno.start()]))
        classe = "upcoming-label" if IN_ARRIVO.fullmatch(segno[0]) else "role-label"
        parti.append(f'<span class="{classe}">{html.escape(segno[0])}</span>')
        inizio = segno.end()
    parti.append(html.escape(testo[inizio:]))
    return "".join(parti)


def controlla_link(indirizzo: str, riga: int) -> str:
    if re.search(r'[\s<>"\x00-\x1f]', indirizzo):
        errore(riga, "indirizzo del link non valido; usare %20 per gli spazi.")
    if urlsplit(indirizzo).scheme.lower() not in {"", "http", "https", "mailto"}:
        errore(riga, "protocollo del link non supportato.")
    return html.escape(indirizzo, quote=True)


def inline(testo: str, riga: int, etichette: bool = False) -> str:
    """Piccolo lettore esplicito: grassetto, corsivo, codice, link ed escape.

    Il codice è opaco: eventuali segni Markdown al suo interno sono letterali.
    Anche <data>, usato dalla guida come segnaposto, resta testo visibile.
    """
    def leggi(pos: int, chiusura: str = "") -> tuple[str, int]:
        parti, letterali = [], []

        def scarica() -> None:
            parti.append(testo_html("".join(letterali), etichette))
            letterali.clear()

        while pos < len(testo):
            attuale = riga + testo[:pos].count("\n")
            if chiusura and testo.startswith(chiusura, pos):
                # Un grassetto può stare dentro un corsivo.
                if not (chiusura == "*" and testo.startswith("**", pos)):
                    scarica()
                    return "".join(parti), pos + len(chiusura)
            carattere = testo[pos]
            if carattere == "\\":
                if pos + 1 >= len(testo) or testo[pos + 1] not in r'\`*_{}[]()#+-.!|>':
                    errore(attuale, "escape Markdown non supportato.")
                letterali.append(testo[pos + 1])
                pos += 2
                continue
            if testo.startswith("![", pos):
                errore(attuale, "immagini Markdown non supportate.")
            if testo.startswith("~~", pos) or testo.startswith("***", pos):
                errore(attuale, "barrato o enfasi tripla non supportati.")
            if carattere == "`":
                scarica()
                fine = testo.find("`", pos + 1)
                if fine < 0 or fine == pos + 1 or "\n" in testo[pos + 1:fine]:
                    errore(attuale, "codice inline non chiuso o delimitatore non supportato.")
                parti.append(f"<code>{html.escape(testo[pos + 1:fine])}</code>")
                pos = fine + 1
                continue
            if carattere == "*":
                scarica()
                segno = "**" if testo.startswith("**", pos) else "*"
                contenuto, fine = leggi(pos + len(segno), segno)
                if not contenuto:
                    errore(attuale, "enfasi vuota.")
                tag = "strong" if segno == "**" else "em"
                prossimo = re.match(r"\(?in arrivo\b", testo[pos + len(segno):], re.I)
                classe = ' class="upcoming-note"' if prossimo else ""
                parti.append(f"<{tag}{classe}>{contenuto}</{tag}>")
                pos = fine
                continue
            if carattere == "[":
                scarica()
                # Le destinazioni possono avere parentesi bilanciate, senza titolo opzionale.
                fine_etichetta = testo.find("]", pos + 1)
                if fine_etichetta < 0 or testo[fine_etichetta + 1:fine_etichetta + 2] != "(":
                    errore(attuale, "link incompleto, riferimento o nota non supportati.")
                fine, profondita = fine_etichetta + 2, 1
                while fine < len(testo) and profondita:
                    profondita += (testo[fine] == "(") - (testo[fine] == ")")
                    fine += 1
                if profondita:
                    errore(attuale, "destinazione del link non chiusa.")
                href = controlla_link(testo[fine_etichetta + 2:fine - 1], attuale)
                etichetta = inline(testo[pos + 1:fine_etichetta], attuale, etichette)
                parti.append(f'<a href="{href}">{etichetta}</a>')
                pos = fine
                continue
            if carattere == "<" and not testo.startswith("<data>", pos):
                fine = testo.find(">", pos + 1)
                valore = testo[pos + 1:fine] if fine >= 0 else ""
                if valore.startswith(("https://", "http://", "mailto:")):
                    scarica()
                    href = controlla_link(valore, attuale)
                    parti.append(f'<a href="{href}">{html.escape(valore)}</a>')
                    pos = fine + 1
                    continue
                if re.match(r"/?[A-Za-z!][^>]*>", testo[pos + 1:]):
                    errore(attuale, "HTML incorporato non supportato (solo <data> è un segnaposto letterale).")
            if carattere == "_" and (pos == 0 or not testo[pos - 1].isalnum()):
                if re.match(r"_+\S", testo[pos:]):
                    errore(attuale, "enfasi con underscore non supportata: usare * o **.")
            if carattere == "]":
                errore(attuale, "parentesi di link senza apertura; per testo letterale usare \\].")
            letterali.append(carattere)
            pos += 1
        if chiusura:
            errore(riga, f"delimitatore {chiusura!r} senza chiusura.")
        scarica()
        return "".join(parti), pos

    return leggi(0)[0]


def celle(testo: str, riga: int) -> list[str]:
    """Divide la tabella senza spezzare barre protette da escape o codice."""
    testo = testo.strip()
    if testo.startswith("|"):
        testo = testo[1:]
    if testo.endswith("|") and not testo.endswith("\\|"):
        testo = testo[:-1]
    risultato, corrente, codice, escape = [], [], False, False
    for carattere in testo:
        if carattere == "|" and not codice and not escape:
            risultato.append("".join(corrente).strip())
            corrente = []
        else:
            corrente.append(carattere)
        if carattere == "`" and not escape:
            codice = not codice
        escape = carattere == "\\" and not escape
    risultato.append("".join(corrente).strip())
    if codice:
        errore(riga, "codice non chiuso nella tabella.")
    return risultato


def barre_tabella(testo: str) -> bool:
    """Una barra dentro codice o preceduta da escape non apre una tabella."""
    codice, escape = False, False
    for carattere in testo:
        if carattere == "|" and not codice and not escape:
            return True
        if carattere == "`" and not escape:
            codice = not codice
        escape = carattere == "\\" and not escape
    return False


def separatore_tabella(testo: str) -> bool:
    return barre_tabella(testo) and all(re.fullmatch(r":?-{3,}:?", c) for c in celle(testo, 1))


def speciale(testo: str) -> bool:
    return bool(TITOLO.match(testo) or ELENCO.match(testo) or testo.startswith(">")
                or testo.strip() == "---" or barre_tabella(testo))


def blocchi(righe: list[tuple[int, str]]) -> list[Blocco]:
    risultato, indice = [], 0
    while indice < len(righe):
        numero, testo = righe[indice]
        if not testo.strip():
            indice += 1
            continue
        if "\t" in testo:
            errore(numero, "tabulazione non supportata: usare spazi per i rientri.")
        if re.match(r"\s*(```|~~~|!\[|\[\^|\[[^]]+\]:|={3,}\s*$|:::)", testo):
            errore(numero, "blocco Markdown non supportato (codice, immagine, nota, riferimento o estensione).")
        if re.match(r"\s*([-+*]|\d+[.)]) +\[[ xX]\]", testo):
            errore(numero, "caselle di spunta non supportate.")
        titolo = TITOLO.match(testo)
        if titolo:
            livello = len(titolo[1])
            if livello > 3 or re.search(r"\s#+$", titolo[2]):
                errore(numero, "sono supportati solo titoli #, ##, ### senza # finali.")
            risultato.append(Blocco("titolo", titolo[2], numero, livello))
            indice += 1
        elif testo.strip() == "---":
            risultato.append(Blocco("linea", riga=numero))
            indice += 1
        elif testo.startswith(">"):
            citazione = []
            while indice < len(righe) and righe[indice][1].startswith(">"):
                n, r = righe[indice]
                citazione.append((n, re.sub(r"^> ?", "", r)))
                indice += 1
            risultato.append(Blocco("citazione", riga=numero, figli=blocchi(citazione)))
        elif ELENCO.match(testo):
            primo = ELENCO.match(testo)
            rientro, ordinato = len(primo[1]), primo[2][0].isdigit()
            if rientro:
                errore(numero, "elenco rientrato senza un elemento padre.")
            lista = Blocco("ol" if ordinato else "ul", riga=numero,
                           numero=int(primo[2][:-1]) if ordinato else 1)
            while indice < len(righe):
                n, r = righe[indice]
                voce = ELENCO.match(r)
                if not voce or len(voce[1]) != rientro or voce[2][0].isdigit() != ordinato:
                    break
                if re.match(r"\[[ xX]\]", voce[3]):
                    errore(n, "caselle di spunta non supportate.")
                if ordinato and int(voce[2][:-1]) != lista.numero + len(lista.figli):
                    errore(n, "numerazione non consecutiva: l'HTML ne cambierebbe i numeri.")
                larghezza = voce.start(3)
                contenuto = [(n, voce[3])]
                indice += 1
                while indice < len(righe):
                    n2, r2 = righe[indice]
                    if not r2.strip():
                        prossimo = indice + 1
                        while prossimo < len(righe) and not righe[prossimo][1].strip():
                            prossimo += 1
                        if prossimo < len(righe) and righe[prossimo][1].startswith(" " * larghezza):
                            contenuto.append((n2, ""))
                            indice += 1
                            continue
                        break
                    if r2.startswith(" " * larghezza):
                        contenuto.append((n2, r2[larghezza:]))
                        indice += 1
                    elif r2.startswith(" "):
                        errore(n2, f"rientro ambiguo: servono almeno {larghezza} spazi per continuare l'elemento.")
                    else:
                        break
                lista.figli.append(Blocco("voce", riga=n, figli=blocchi(contenuto)))
                while indice < len(righe) and not righe[indice][1].strip():
                    indice += 1
            risultato.append(lista)
        elif barre_tabella(testo):
            if indice + 1 >= len(righe) or not separatore_tabella(righe[indice + 1][1]):
                errore(numero, "tabella senza riga separatrice valida; usare \\| per una barra letterale.")
            intestazione = celle(testo, numero)
            separatori = celle(righe[indice + 1][1], numero + 1)
            if len(intestazione) != len(separatori):
                errore(numero, "numero di colonne diverso fra intestazione e separatori.")
            tabella = Blocco("tabella", riga=numero, righe=[intestazione])
            tabella.allineamenti = ["center" if s.startswith(":") and s.endswith(":")
                                      else "right" if s.endswith(":") else "left" for s in separatori]
            indice += 2
            while indice < len(righe) and barre_tabella(righe[indice][1]) and righe[indice][1].strip():
                n, r = righe[indice]
                valori = celle(r, n)
                if len(valori) != len(intestazione):
                    errore(n, f"tabella: attese {len(intestazione)} colonne, trovate {len(valori)}.")
                tabella.righe.append(valori)
                indice += 1
            risultato.append(tabella)
        else:
            if testo.startswith(" ") or re.match(r"^([#]{1,6}$|[-*_]{3,}$|: )", testo):
                errore(numero, "rientro, titolo o separatore non supportato.")
            parti = [testo]
            indice += 1
            while indice < len(righe) and righe[indice][1].strip() and not speciale(righe[indice][1]):
                n, r = righe[indice]
                if r.startswith(" ") or re.match(r"(```|~~~|={3,}$|:::|\[[^]]+\]:|: )", r):
                    errore(n, "blocco Markdown non supportato nel paragrafo.")
                parti.append(r)
                indice += 1
            if any(r.endswith("  ") or r.endswith("\\") for r in parti):
                errore(numero, "interruzione di riga forzata non supportata.")
            risultato.append(Blocco("paragrafo", "\n".join(parti), numero))
    return risultato


def ancora(titolo: str) -> str:
    # Il digest distingue titoli con punteggiatura diversa senza dipendere dall'ordine.
    base = unicodedata.normalize("NFKD", titolo).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-") or "sezione"
    return f"{base}-{hashlib.sha256(titolo.encode('utf-8')).hexdigest()[:8]}"


ETICHETTE_RIQUADRO = {"Attenzione": "note-warning", "Da sapere": "note-info", "Esempio": "note-example"}
RIGA_GUIDA = re.compile(r"\*\*[^*\n]+\*\*")


def classe_riquadro(figli: list[Blocco]) -> str:
    """Un riquadro che inizia con **Attenzione**, **Da sapere** o **Esempio** prende la sua tinta."""
    if any("Ambiente di prova" in b.testo for b in figli):
        return "test-notice"
    if figli and figli[0].tipo == "paragrafo":
        for etichetta, classe in ETICHETTE_RIQUADRO.items():
            if figli[0].testo.startswith(f"**{etichetta}"):
                return classe
    return ""


def rendi(blocco: Blocco, guida: bool = False) -> str:
    if blocco.tipo == "paragrafo":
        # La riga guida è il paragrafo tutto in grassetto subito dopo un titolo.
        classe = ' class="lead"' if guida and RIGA_GUIDA.fullmatch(blocco.testo) else ""
        return f"<p{classe}>{inline(blocco.testo, blocco.riga)}</p>"
    if blocco.tipo == "titolo":
        n = blocco.livello
        return f'<h{n} id="{ancora(blocco.testo)}">{inline(blocco.testo, blocco.riga, True)}</h{n}>'
    if blocco.tipo == "linea":
        return "<hr>"
    if blocco.tipo in {"ol", "ul", "voce"}:
        tag = "li" if blocco.tipo == "voce" else blocco.tipo
        attributi = f' start="{blocco.numero}"' if tag == "ol" and blocco.numero != 1 else ""
        return f"<{tag}{attributi}>\n" + "\n".join(map(rendi, blocco.figli)) + f"\n</{tag}>"
    if blocco.tipo == "citazione":
        nome = classe_riquadro(blocco.figli)
        classe = f' class="{nome}"' if nome else ""
        return f"<blockquote{classe}>\n" + "\n".join(map(rendi, blocco.figli)) + "\n</blockquote>"
    if blocco.tipo == "tabella":
        righe = []
        for i, valori in enumerate(blocco.righe):
            tag = "th" if i == 0 else "td"
            celle_html = []
            for colonna, (valore, allineamento) in enumerate(zip(valori, blocco.allineamenti)):
                # Sul telefono ogni cella ripete la propria intestazione (data-label): la tabella si impila in
                # schede senza scorrimento orizzontale. L'intestazione è ripetuta come testo, senza Markdown.
                attributi = (' scope="col"' if i == 0
                             else f' data-label="{html.escape(blocco.righe[0][colonna], quote=True)}"')
                celle_html.append(f'<{tag}{attributi} class="align-{allineamento}">'
                                  f'{inline(valore, blocco.riga + i + (i > 0))}</{tag}>')
            righe.append("<tr>" + "".join(celle_html) + "</tr>")
        return ('<div class="table-scroll" role="region" aria-label="Tabella della guida" tabindex="0">'
                '<table>\n<thead>' + righe[0] + '</thead>\n<tbody>\n' + "\n".join(righe[1:])
                + "\n</tbody></table></div>")
    raise ErroreGuida(f"Blocco interno sconosciuto: {blocco.tipo}")


def genera(fonte: str, modello: str) -> str:
    righe = list(enumerate(fonte.splitlines(), 1))
    elementi = blocchi(righe)
    if not elementi or elementi[0].tipo != "titolo" or elementi[0].livello != 1:
        errore(1, "la guida deve iniziare con un titolo #.")
    precedenti, livello, titoli = set(), 1, []
    for b in elementi[1:]:
        if b.tipo != "titolo":
            continue
        if b.livello == 1 or b.livello > livello + 1:
            errore(b.riga, "gerarchia dei titoli non valida: usare un solo # e non saltare livelli.")
        if ancora(b.testo) in precedenti:
            errore(b.riga, "titolo ripetuto: impossibile creare un'ancora univoca e stabile.")
        precedenti.add(ancora(b.testo))
        livello = b.livello
        titoli.append(b)

    copertina = [rendi(elementi.pop(0))]
    # Sottotitolo e versione vengono esclusivamente dalle righe introduttive.
    if elementi and elementi[0].tipo == "paragrafo":
        intro = elementi.pop(0)
        for i, riga in enumerate(intro.testo.splitlines()):
            classe = "version" if re.match(r"\*?Versione\b", riga) else "subtitle"
            copertina.append(f'<p class="{classe}">{inline(riga, intro.riga + i)}</p>')

    indice, sottolista = [], False
    for i, titolo in enumerate(titoli):
        link = f'<a href="#{ancora(titolo.testo)}">{inline(titolo.testo, titolo.riga)}</a>'
        if titolo.livello == 2:
            if sottolista:
                indice.append("</ol></li>")
                sottolista = False
            elif i:
                indice.append("</li>")
            indice.append(f"<li>{link}")
        else:
            if not sottolista:
                indice.append("<ol>")
                sottolista = True
            indice.append(f"<li>{link}</li>")
    if titoli:
        indice.append("</ol></li>" if sottolista else "</li>")

    contenuto, sezione, dopo_titolo = [], False, False
    for b in elementi:
        if b.tipo == "titolo" and b.livello == 2:
            if sezione:
                contenuto.append("</section>")
            classe = ' class="featured-section"' if b.testo in SEZIONI_EVIDENTI else ""
            contenuto.append(f'<section{classe} aria-labelledby="{ancora(b.testo)}">')
            sezione = True
        contenuto.append(rendi(b, guida=dopo_titolo))
        dopo_titolo = b.tipo == "titolo"
    if sezione:
        contenuto.append("</section>")

    valori = {"COPERTINA": "\n".join(copertina), "INDICE": "\n".join(indice),
              "CONTENUTO": "\n".join(contenuto)}
    segnaposti = re.findall(r"\{\{([A-Z_]+)\}\}", modello)
    if sorted(segnaposti) != sorted(valori):
        raise ErroreGuida("Il modello deve contenere una sola volta {{COPERTINA}}, {{INDICE}} e {{CONTENUTO}}.")
    # Un'unica sostituzione impedisce di interpretare come modello il testo della guida.
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: valori[m[1]], modello)


def main() -> int:
    radice = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=radice / "docs/guida-utente.md", help="fonte Markdown")
    parser.add_argument("--template", type=Path, default=radice / "docs/strumenti/guida_modello.html", help="modello HTML")
    parser.add_argument("--output", type=Path, default=radice / "docs/guida-utente.html", help="HTML da scrivere o controllare")
    parser.add_argument("--check", action="store_true", help="controlla senza scrivere alcun file")
    args = parser.parse_args()
    try:
        # Protegge la fonte e il modello anche quando si usano percorsi personalizzati.
        if args.output.resolve() in {args.source.resolve(), args.template.resolve()}:
            raise ErroreGuida("Il percorso HTML deve essere diverso dalla fonte e dal modello.")
        atteso = genera(args.source.read_text(encoding="utf-8-sig"),
                        args.template.read_text(encoding="utf-8-sig")).encode("utf-8")
        if args.check:
            if not args.output.exists() or args.output.read_bytes() != atteso:
                print(f"HTML non aggiornato o mancante: {args.output}", file=sys.stderr)
                return 1
            print(f"HTML aggiornato: {args.output}")
            return 0
        args.output.write_bytes(atteso)
        print(f"Guida HTML generata: {args.output}")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Impossibile generare la guida: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
