"""Rebuild `corpus/promotional.jsonl`: human writing whose job is to make you
want something.

Why it exists. Every human entry in this project's corpora is one of three
registers - interface strings, documentation, or encyclopedic paragraphs -
and none of them is the register a scan is actually pointed at. `P-03` said
so and `P-06` measured the cost: on a live Italian hotel page the offline
pass found nothing while a model judge named five phrases, and the reason
was not the language label or the length ceiling. The Italian cliché lists
simply do not hold what that copy is made of - `atmosfera senza tempo`, `nel
cuore di`, `ogni angolo racconta`.

Adding those phrases is a two-sided change, and only one side was
measurable. Recall against the corpus' own positives could be computed; the
false-alarm price could not, because there was no human text in that
register to charge it against. A phrase like `nel cuore di` is not evidence
of a model - it is how a person writes about a town square - and a list that
gains it without measuring what it costs is a list that has traded precision
for recall without saying so.

**Wikivoyage is that register, with the provenance this corpus requires.**
It is a travel guide: the prose exists to make a place sound worth the trip,
which is marketing writing by function even though nobody sold anything. And
it is a MediaWiki, so the same argument that makes the encyclopedic half
checkable works here unchanged - a dated revision id, years before language
models were writing this kind of copy, quoted with attribution under CC
BY-SA.

    python scripts/fetch_promotional_corpus.py corpus/promotional.jsonl

A yardstick, never a reference set: no detector reads this file, and it is
deliberately not merged into `corpus/labelled.jsonl`, which *is* a component
of `EmbeddingDetector`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_foreign_corpus import (  # noqa: E402
    MAX_PARAGRAPHS, USER_AGENT, fetch, paragraphs,
)

#: Later than the 2018 the encyclopedic half uses. Wikivoyage is a smaller
#: project and its pages were still thin in 2018; 2021-06 is still a year
#: before this kind of copy could have been generated, and the revision date
#: travels with every entry so the claim stays checkable per row rather than
#: resting on this constant.
BEFORE = "2021-06-01T00:00:00Z"

#: Destinations, because a destination page is where the register is
#: strongest: a list of transport connections is not the writing that
#: collides with a cliché list, and a description of a square at dusk is.
ARTICLES = {
    "it": ["Venezia", "Roma", "Firenze", "Napoli", "Bologna", "Verona",
           "Trieste", "Siena", "Matera", "Lecce", "Palermo", "Torino",
           "Genova", "Costiera amalfitana", "Cinque Terre", "Toscana",
           "Sicilia", "Umbria", "Lago di Como", "Val d'Orcia"],
    "en": ["Venice", "Rome", "Florence", "Naples", "Kyoto", "Barcelona",
           "Lisbon", "Prague", "Amsterdam", "Istanbul", "Marrakech",
           "Tuscany", "Sicily", "Andalusia", "Provence"],
    "uk": ["Київ", "Львів", "Одеса", "Чернівці", "Кам'янець-Подільський",
           "Ужгород", "Венеція", "Рим", "Прага", "Краків"],
}


def main(out_path: str) -> int:
    rows = []
    for language, titles in ARTICLES.items():
        for title in titles:
            try:
                revid, timestamp, wikitext = fetch(language, title,
                                                   site="wikivoyage",
                                                   before=BEFORE)
            except Exception as exc:  # noqa: BLE001 - one missing page is not a failed build
                print("skipped %s %s: %s" % (language, title, exc),
                      file=sys.stderr)
                continue
            found = list(paragraphs(wikitext))[:MAX_PARAGRAPHS]
            for text in found:
                rows.append({
                    "text": text,
                    "label": "human",
                    "language": language,
                    "source": "%s.wikivoyage %s revid %s %s"
                              % (language, title, revid, timestamp[:10]),
                    "register": "promotional",
                })
            print("%s %-24s %2d paragraphs" % (language, title, len(found)),
                  file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("%d entries -> %s (agent: %s)" % (len(rows), out_path, USER_AGENT),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1
                  else "corpus/promotional.jsonl"))
