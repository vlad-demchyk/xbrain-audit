"""Rebuild `corpus/prose.jsonl`: human prose in the three supported languages,
on the subjects this tool is pointed at.

Why it exists, and why it is not `labelled.jsonl`. The human half of the
corpus is interface strings plus encyclopedic paragraphs about the web, and
"0 false alarms" was measured on that. It is a claim about the wrong text: a
scan is pointed at pages about tourism, software, marketing and usability,
and those are the subjects whose ordinary vocabulary overlaps a marketing
cliché list. Measured 2026-08-31 the first time this file existed - six human
paragraphs crossed the threshold, on words like `efficienza`, `scalable` and
`fondamentale`, which are simply the words those articles are written in.

Dated Wikipedia revisions again, for the provenance reason in
`fetch_foreign_corpus.py`, whose fetching and wikitext handling this reuses.

    python scripts/fetch_prose_corpus.py corpus/prose.jsonl

A yardstick, never a reference set: no detector reads it, and it is
deliberately **not** merged into `corpus/labelled.jsonl`, because that file is
a component of `EmbeddingDetector` and 334 new entries would silently be a
change to that detector rather than to the measurement.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.fetch_foreign_corpus import (  # noqa: E402
    MAX_PARAGRAPHS, USER_AGENT, fetch, paragraphs,
)

#: Subjects, not languages: the point is the vocabulary a page about
#: usability or tourism is written in, which is the vocabulary a cliché list
#: is most likely to collide with.
#:
#: The first Italian subject was the article on the town of a client's site;
#: its 12 rows in `prose.jsonl` keep their revid, with the town's name taken
#: out of the text and the source label. A rebuild fetches "Città ideale" in
#: its place, so it is a different measurement, not the same one again.
ARTICLES = {
    "en": ["Tourism", "Marketing", "Usability", "Software", "Cloud computing",
           "Productivity", "User experience", "Startup company", "Venice",
           "Renaissance architecture"],
    "it": ["Città ideale", "Venezia", "Fortificazione alla moderna", "Turismo",
           "Architettura rinascimentale", "Patrimonio dell'umanità",
           "Cicloturismo", "Friuli-Venezia Giulia", "Urbanistica", "Software",
           "Cloud computing", "Produttività", "Usabilità", "Marketing"],
    "uk": ["Туризм", "Маркетинг", "Програмне забезпечення", "Хмарні обчислення",
           "Стартап", "Венеція", "Юзабіліті", "Продуктивність праці"],
}


def main(out_path: str) -> int:
    rows = []
    for language, titles in ARTICLES.items():
        for title in titles:
            try:
                revid, timestamp, wikitext = fetch(language, title)
            except Exception as exc:  # noqa: BLE001 - one missing article is not a failed build
                print("skipped %s %s: %s" % (language, title, exc), file=sys.stderr)
                continue
            found = list(paragraphs(wikitext))[:MAX_PARAGRAPHS]
            for text in found:
                rows.append({
                    "text": text,
                    "label": "human",
                    "language": language,
                    "source": "%s.wikipedia %s revid %s %s"
                              % (language, title, revid, timestamp[:10]),
                    "register": "encyclopedic",
                })
            print("%s %-34s %2d paragraphs" % (language, title, len(found)),
                  file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("%d entries -> %s (agent: %s)" % (len(rows), out_path, USER_AGENT),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "corpus/prose.jsonl"))
