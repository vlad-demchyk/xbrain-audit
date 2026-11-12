"""Rebuild `corpus/foreign.jsonl`: human text in languages this tool has no
lists for.

Why it exists. `lang_detect` answers `UNSUPPORTED` for a language it has no
cliché list, punctuation table or reference set for, and two detectors go
silent on that answer. Both of those are claims about behaviour on text
nobody here writes, so they need a corpus like every other claim in this
project - and the one thing that corpus must not be is invented examples,
which would measure the example writer rather than the detector.

Dated Wikipedia revisions solve the provenance problem the same way they
solved it for the human half of `corpus/labelled.jsonl`: a revision from 2018
was written by a person, and the revision id in `source` says which text was
read, so the fetch is repeatable and the entry is checkable.

    python scripts/fetch_foreign_corpus.py corpus/foreign.jsonl

The file is a yardstick, never a reference set: no detector reads it.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request

#: Articles that exist in every one of these languages and are the same kind
#: of prose as the corpus: technical and marketing subjects, not biographies.
ARTICLES = {
    "de": ["Webbrowser", "Freie Software", "Suchmaschine", "Benutzerfreundlichkeit", "Marketing"],
    "fr": ["Navigateur web", "Logiciel libre", "Moteur de recherche", "Ergonomie", "Marketing"],
    "es": ["Navegador web", "Software libre", "Motor de búsqueda", "Usabilidad", "Mercadotecnia"],
    "pl": ["Przeglądarka internetowa", "Wolne oprogramowanie", "Wyszukiwarka internetowa", "Marketing"],
    "ru": ["Браузер", "Свободное программное обеспечение", "Поисковая система", "Маркетинг"],
}

#: The last revision before this date is taken. 2018 is far enough back that
#: no part of the text can have been written by the thing being detected.
BEFORE = "2018-06-01T00:00:00Z"

#: Wikipedia rejects a request with no identifying agent.
USER_AGENT = "XAnalyze corpus builder (https://github.com/vladyslav/ai-content-scanner)"

#: Below this a paragraph is a caption or a stub heading, not prose, and the
#: language reading of it would be a reading of three words.
MIN_WORDS = 12

#: Per article, so no single page can dominate its language's half.
MAX_PARAGRAPHS = 12


def fetch(lang: str, title: str, site: str = "wikipedia",
          before: str = BEFORE) -> tuple[int, str, str]:
    """The last revision of one article before a date, with its id.

    `site` and `before` are parameters rather than constants because the same
    provenance argument holds on any MediaWiki: `fetch_promotional_corpus`
    reads Wikivoyage, where the prose is written to make somebody want to go
    somewhere - which is the register a cliché list is most likely to collide
    with, and the one this corpus had none of.
    """
    url = ("https://%s.%s.org/w/api.php?action=query&prop=revisions"
           "&titles=%s&rvlimit=1&rvstart=%s&rvdir=older"
           "&rvprop=ids|timestamp|content&rvslots=main&format=json"
           % (lang, site, urllib.parse.quote(title), before))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    page = next(iter(data["query"]["pages"].values()))
    revision = page["revisions"][0]
    return (revision["revid"], revision["timestamp"],
            revision["slots"]["main"]["*"])


def strip_wikitext(text: str) -> str:
    """Enough of a wikitext stripper for prose. Templates are removed twice
    because they nest one level in practice."""
    for _ in range(2):
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\{\|.*?\|\}", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<ref.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[\[(?:[^\[\]|]*\|)?([^\[\]|]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[[^\[\]]*\]\]", "", text)
    return re.sub(r"'{2,}", "", text)


def paragraphs(wikitext: str):
    for raw in strip_wikitext(wikitext).split("\n"):
        line = raw.strip()
        # Lists, tables, headings and infobox leftovers are markup, and a
        # surviving `|` or URL means the stripper missed something.
        if not line or line.startswith(("=", "*", "#", "|", "!", ":", ";", "[")):
            continue
        if "|" in line or "http" in line:
            continue
        if len(line.split()) < MIN_WORDS:
            continue
        yield line


def main(out_path: str) -> int:
    rows = []
    for lang, titles in ARTICLES.items():
        for title in titles:
            try:
                revid, timestamp, wikitext = fetch(lang, title)
            except Exception as exc:  # noqa: BLE001 - one missing article is not a failed build
                print("skipped %s %s: %s" % (lang, title, exc), file=sys.stderr)
                continue
            found = list(paragraphs(wikitext))[:MAX_PARAGRAPHS]
            for text in found:
                rows.append({
                    "text": text,
                    "label": "human",
                    "language": lang,
                    "source": "%s.wikipedia %s revid %s %s"
                              % (lang, title, revid, timestamp[:10]),
                    "register": "encyclopedic",
                })
            print("%s %-38s %2d paragraphs" % (lang, title, len(found)), file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("%d entries -> %s" % (len(rows), out_path), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "corpus/foreign.jsonl"))
