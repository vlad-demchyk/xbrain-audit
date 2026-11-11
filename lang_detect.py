"""Cheap language guess shared by the extractors and the detectors.

Lives at top level rather than inside detectors/ so the crawler and the
repo scanner can tag each extracted block with a language without
importing a detector — the tag then flows through to the rewrite provider,
which needs it to answer in the right language.
"""
from __future__ import annotations

import re

_CYRILLIC_RE = re.compile(r"[А-Яа-яЇїІіЄєҐґ]")

#: Returned when the text is positively some other language. Not the same
#: answer as `None`: `None` means "too short to tell", and the callers that
#: see it check every list to be safe. This one means the opposite - we read
#: enough to know we are not equipped, so nothing language-specific applies.
UNSUPPORTED = "other"

# Function words that are common in Italian and rare/absent in English.
#
# Extended 2026-08-31. The first list was built from Italian *prose*, and
# Italian marketing copy turned out not to contain it: "La nostra
# infrastruttura robusta garantisce sicurezza di livello aziendale" carries
# not one of the original fourteen and was read as English, so the Italian
# cliché list never ran on it and two corpus positives went undetected. Same
# gap, three ways: `P-04` sees it as recall, `P-06` as an Italian page the
# offline pass returns nothing for.
#
# Measured over corpus entries of 5+ words, which is where a reading is
# attempted at all: Italian read as Italian **68/98 -> 85/98**, with English
# 124/124, Ukrainian 157/157 and foreign text 249/257 all unchanged. Every
# word is absent from the English and Ukrainian halves of the corpus *and*
# from `corpus/foreign.jsonl`, so it can neither pull another language in nor
# push a foreign paragraph out.
#
# ` una ` was measured and left out. It buys one more Italian entry and costs
# a Spanish paragraph, which starts reading as Italian - the same trade the
# `_OTHER_LATIN_MARKERS` comment warns about from the other side.
_ITALIAN_MARKERS = (
    " è ", " non ", " che ", " della ", " gli ", " sono ", " perché ",
    " degli ", " nella ", " questo ", " anche ", " più ", " con ", " per ",
    " di ", " nel ", " nostra ", " nostro ", " tuo ", " tuoi ", " tra ",
    " dei ", " ogni ", " senza ", " stesso ", " può ", " dal ", " dalla ",
    " sulla ", " agli ",
)

#: Letters that exist in Ukrainian and not in Russian, and the reverse. A
#: share of Cyrillic said "Ukrainian" for any Cyrillic at all, so every
#: Russian page was scored with Ukrainian cliché lists and, worse, handed to
#: the rewrite provider as "(language: uk)" - a request to answer a Russian
#: page in Ukrainian.
#:
#: Measured on `corpus/labelled.jsonl` (155 Ukrainian human entries) against
#: 42 Russian paragraphs from dated Wikipedia revisions: the Ukrainian half
#: contains **no** Russian-only letter at all, and every Russian entry has at
#: least 0.75 per 100 letters. The two sets do not overlap on real text, so
#: the comparison needs no threshold - whichever side has more, wins.
_UKRAINIAN_ONLY = set("іїєґІЇЄҐ")
_RUSSIAN_ONLY = set("ыэъёЫЭЪЁ")

#: The tie-breaker for the case the letters above cannot read: a paragraph
#: that carries **no** letter unique to either side. `P-34`: one of the 48
#: Russian paragraphs is written entirely in shared letters ("вид
#: человеческой деятельности, направленной на удовлетворение нужд и
#: потребностей"), and a bare `>` on the letter counts hands 0-0 to the left
#: operand, so it read as Ukrainian. Inverting the comparison is not the fix
#: - 11 of the Ukrainian entries carry no unique letter either, and short UI
#: strings are the bulk of them.
#:
#: So the tie asks words instead. Every marker below is a function word or an
#: ending that belongs to one side and is **absent from the other side of the
#: corpus**: measured over 506 Ukrainian entries (`labelled`, `prose`,
#: `promotional`, `unlabelled`, `negative_pool`) and the 48 Russian
#: paragraphs of `corpus/foreign.jsonl`, the split is 506/506 and 48/48.
#:
#: Three words were measured and removed: `ого ` (Ukrainian "повного",
#: "чистого"), ` все ` (ordinary Ukrainian) and ` также ` - each one pulled
#: real Ukrainian entries over the line on an ending both languages share.
_RUSSIAN_WORD_MARKERS = (
    " и ", " что ", " это ", " как ", " или ", " был ", " была ", " были ",
    " они ", " она ", " его ", " если ", " который ", " которая ",
    " которые ", " ещё ", " еще ", " только ", " может ", " быть ", " нет ",
    " чем ", " этой ", " этот ", " эти ", " таких ", " такой ",
    "ение ", "ения ", "ений ", "ению ", "ание ", "ания ", "аний ", "ённ",
)
_UKRAINIAN_WORD_MARKERS = (
    " та ", " що ", " як ", " із ", " він ", " ця ", " цей ", " ці ",
    " лише ", " дуже ", " його ", " щоб ", " може ", " треба ", " бути ",
    " усі ", " всі ", " який ", " яка ", " які ", " ніж ", " але ",
    " тому ", " після ", " перед ", " через ", " від ", " немає ", " є ",
    "ення ", "ції ", " ваш ", " наш ",
)

#: Function words of languages this tool has no lists for. Only words that
#: are *not* also ordinary Italian: `del`, `una`, `se`, `su` and `le` were in
#: here first and pulled 13 Italian entries out of the corpus with them.
#:
#: Extended 2026-08-31 against 257 paragraphs from dated Wikipedia revisions
#: in de/fr/es/pl/ru. The first list read 234 of them as foreign; the eight
#: French, eight Spanish and eight Polish words added below took that to 249
#: (91.1% -> 96.9%) and cost nothing on the supported side - all 731 corpus
#: entries in `uk`, `it` and `en` still read as their own language. Every
#: added word was picked the same way: frequent in that language's half of
#: the foreign set and **absent from the whole corpus**, so a word that is
#: also ordinary English or Italian could not get in by eye.
_OTHER_LATIN_MARKERS = {
    "es": (" el ", " los ", " las ", " que ", " para ", " pero ", " está ",
           " esta ", " sus ", " por ", " con el ", " de la ",
           " como ", " más ", " también ", " ser ", " puede ", " este ",
           " sin ", " sobre "),
    "fr": (" les ", " des ", " est ", " une ", " dans ", " pour ", " qui ",
           " sur ", " du ", " aux ", " cette ",
           " par ", " au ", " ou ", " comme ", " ce ", " avec ", " ainsi ",
           " sont "),
    "de": (" der ", " die ", " das ", " und ", " von ", " mit ", " ist ",
           " den ", " ein ", " auf ", " eine "),
    "pl": (" nie ", " jest ", " się ", " oraz ", " przez ", " które ",
           " lub ", " jako ", " są ", " do ", " na ",
           " że ", " często ", " także ", " ponieważ ", " których ",
           " jego ", " od ", " za "),
}

#: Markers per 100 words before a foreign language is called. Swept against
#: 439 supported-language entries and 172 foreign paragraphs: at 6.0 nothing
#: in English, Italian or Ukrainian is misread (0/439) and 89% of the foreign
#: text is caught. Lower cut-offs catch a little more and start costing
#: English entries, and a wrong language is worse than a missing one here.
#:
#: Re-swept 2026-08-31 on the larger sets (731 supported entries, 257 foreign
#: paragraphs) and left where it is. Below 5.5 the supported side starts to
#: pay: 5.0 misreads one English entry and 4.0 misreads two, for 96.1% ->
#: 97.3% on the foreign side. The 5.8-point gain that was actually available
#: came from the marker lists above, which cost nothing on either side, so
#: the cut-off did not have to move to get it.
_OTHER_PER_100_WORDS = 6.0


# Minimum word count for language detection to be meaningful. Below this,
# the guess is too noisy to be useful: a short UI string like "OK" or
# "Save" contains no marker words, and treating it as English would
# suppress the Italian or Ukrainian cliché lists that might actually match.
_MIN_WORDS_FOR_DETECTION = 5

#: How many words one Italian marker is allowed to speak for. See
#: `guess_language_safe` for the measurement behind the number.
_ITALIAN_WORDS_PER_MARKER = 50
#: How many different markers a longer text must use to read as Italian.
_ITALIAN_DISTINCT_MARKERS = 3


def _density(padded: str, word_count: int, markers) -> float:
    """Marker hits per 100 words. Density, not presence: see below."""
    hits = sum(padded.count(marker) for marker in markers)
    return hits / max(word_count, 1) * 100


def guess_language(text: str) -> str:
    """Return 'uk', 'it', 'en' or `UNSUPPORTED`.

    Text too short to read is named English, as it always was: a caller that
    needs a string cannot be handed None. `UNSUPPORTED` is different - it is
    a reading, not a fallback, and callers must not print it or send it to a
    model as a language.

    Cyrillic is decided by *share* of the letters, not by presence of a
    single one. That matters more than it looks: a lone Cyrillic character
    hidden inside an English word is exactly the homoglyph defect this app
    hunts for, and treating that one character as proof of Ukrainian would
    flip the whole block's language — which in turn suppressed the
    language-specific checks for the rest of the block.
    """
    result = guess_language_safe(text)
    return result if result is not None else "en"


def guess_language_safe(text: str) -> str | None:
    """Return 'uk', 'it', 'en', `UNSUPPORTED`, or None when too short to tell.

    None rather than a default language: a short string like "Save" or
    "Копіювати" contains no Italian markers and no Cyrillic at all, but
    treating it as English would silently suppress the Italian and Ukrainian
    cliché lists. Returning None tells the caller to check all lists.

    Cyrillic is decided by *share* of the letters, not by presence of a
    single one. That matters more than it looks: a lone Cyrillic character
    hidden inside an English word is exactly the homoglyph defect this app
    hunts for, and treating that one character as proof of Ukrainian would
    flip the whole block's language — which in turn suppressed the
    language-specific checks for the rest of the block.
    """
    letters = [c for c in text if c.isalpha()]
    word_count = len(text.split())

    # Cyrillic detection: needs enough letters for the share to be meaningful
    if letters:
        cyrillic = sum(1 for c in letters if _CYRILLIC_RE.match(c))
        if cyrillic / len(letters) >= 0.30:
            # Cyrillic is not Ukrainian. Russian, Bulgarian and Serbian all
            # pass the share test, and calling them Ukrainian is not a
            # harmless label: it picks the cliché list and it is what the
            # rewrite provider is told to answer in.
            russian = sum(1 for c in letters if c in _RUSSIAN_ONLY)
            ukrainian = sum(1 for c in letters if c in _UKRAINIAN_ONLY)
            if russian != ukrainian:
                return UNSUPPORTED if russian > ukrainian else "uk"
            # 0-0, or the same count on both sides: the letters cannot read
            # this paragraph, so ask the words. See `_RUSSIAN_WORD_MARKERS`.
            padded_cyrillic = f" {text.lower()} "
            if (sum(padded_cyrillic.count(m) for m in _RUSSIAN_WORD_MARKERS)
                    > sum(padded_cyrillic.count(m)
                          for m in _UKRAINIAN_WORD_MARKERS)):
                return UNSUPPORTED
            return "uk"

    # For Italian and English: need enough words for marker detection to work
    if word_count < _MIN_WORDS_FOR_DETECTION:
        return None

    padded = f" {text.lower()} "

    # A language we have no lists for is not English. Checked before the
    # Italian test because Spanish trips it: measured on 48 Spanish
    # paragraphs, 13 of them read as Italian on shared function words.
    italian_density = _density(padded, word_count, _ITALIAN_MARKERS)
    foreign = max(_density(padded, word_count, markers)
                  for markers in _OTHER_LATIN_MARKERS.values())
    if foreign >= _OTHER_PER_100_WORDS and foreign > italian_density:
        return UNSUPPORTED

    # Density, not presence. One marker anywhere used to be enough, and on a
    # short string that is right - but on a long English page the words
    # "per", "che" and "con" turn up once by accident, and `wordpress.org`
    # and `squarespace.com` were both being read as Italian on the strength
    # of a single hit in several hundred words.
    #
    # The rate is what separates them, and it is measured rather than
    # chosen: on `corpus/labelled.jsonl` the English half contains **no**
    # marker at all (0.0 per 100 words, at the maximum) while the Italian
    # half runs to a median of 5.9. One per fifty words sits far below the
    # real Italian floor and far above accidental English.
    hits = sum(padded.count(marker) for marker in _ITALIAN_MARKERS)
    needed = max(1, word_count // _ITALIAN_WORDS_PER_MARKER)
    # And from more than one word. An English page whose header and footer
    # both say "Youtube di Città di Esempio" and "Comune di Esempio"
    # carries ` di ` seven times in 300 words - the rate of real Italian,
    # from one name repeated. Italian prose that long uses several of its
    # function words; a proper name repeats one. Only where the rate asks
    # for several hits, so a short Italian string still reads on one.
    distinct = sum(1 for marker in _ITALIAN_MARKERS if marker in padded)
    if hits >= needed and distinct >= min(needed, _ITALIAN_DISTINCT_MARKERS):
        return "it"
    return "en"
