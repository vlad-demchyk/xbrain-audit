"""Embedding-based AI text detector.

Uses sentence-transformers to compute embeddings and compare with reference
AI/human texts from the corpus. Complementary to the heuristic detector.

The corpus is a component here as well as a yardstick: the reference is the
tune half of `corpus/labelled.jsonl` and the threshold below was measured on the
other half. See `corpus_split` for why the halves exist.

Approach:
1. Compute embeddings for AI texts in corpus (reference)
2. For new text, compute embedding
3. Compare with reference using cosine similarity
4. High similarity to AI texts → likely AI-generated

This detector is language-agnostic and works without explicit word lists.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from lang_detect import guess_language_safe
from models import TextBlock, TextSpan, score_to_confidence
from corpus_split import is_reference
from .base import Detector
from .factory import DetectorFactory

# Default model - multilingual, good quality for uk/it/en
DEFAULT_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Path to corpus relative to project root
CORPUS_PATH = Path(__file__).resolve().parent.parent / "corpus" / "labelled.jsonl"

#: The half of the corpus this detector is allowed to be built from.
#:
#: The score below is a nearest-neighbour margin: `similarity to the closest
#: model entry` minus `similarity to the closest human entry`. That makes the
#: corpus a *component* of this detector as well as the yardstick it is judged
#: by, and the two roles pull opposite ways. Measured 2026-08-31: adding 95
#: correct human paragraphs to `labelled.jsonl` raised the human side of the
#: margin from 0.461 to 0.541 and dropped the score on the same AI passage from
#: 0.590 to 0.549. Nothing about the detector changed. The corpus got better and
#: the score got worse.
#:
#: The answer is not to hide entries from the reference - that was tried, as a
#: register exclusion, and measurement showed it did the opposite of its
#: purpose: with the encyclopedic paragraphs *in* the reference the highest
#: human score on held-out text fell from 0.598 to 0.547, which is what let the
#: threshold come down to 0.55 and recall rise from 68.9% to 88.9%. Human
#: paragraphs are the thing a human paragraph should be nearest to.
#:
#: The answer is that the reference and the yardstick are different halves.
#: `corpus_split` decides which, by a hash of the text, so a new entry lands in
#: one half and stays there, and the threshold below is measured on text this
#: detector has never been shown.
REFERENCE_HALF = "the tune half of corpus/labelled.jsonl (see corpus_split)"

#: Measured, not chosen. On the 232 held-out entries, `python scripts/calibrate.py
#: --detector embedding --holdout --sweep` reads:
#:
#:     0.50   precision  84.6%   recall  97.8%   false alarms  8/187
#:     0.55   precision 100.0%   recall  88.9%   false alarms  0/187
#:     0.60   precision 100.0%   recall  60.0%   false alarms  0/187
#:
#: 0.55 is where precision reaches 1.0 and every step above it buys nothing and
#: costs recall. Per language it is en 85.0%, uk 85.7%, **it 100.0%** - which is
#: worth naming, because the offline detector's Italian recall is 36.4% (`P-04`)
#: and this is the same corpus.
#:
#: The margin is thin and must be read as thin: the highest-scoring human entry
#: in the held-out half is 0.547, three thousandths below the line. "0 false
#: alarms" here means no human entry crossed, not that none nearly did. Re-run
#: the sweep after any change to the corpus - by construction, a corpus change
#: is a change to this detector.
THRESHOLD = 0.55


class EmbeddingDetector(Detector):
    """Embedding-based AI text detector."""

    name = "embedding"
    display_name = "Embedding — semantic similarity to known AI texts"
    #: The reference set is `corpus/labelled.jsonl`, which holds Ukrainian,
    #: Italian and English and nothing else. A paragraph in a fourth language
    #: is scored by how much closer it sits to the model entries than to the
    #: human ones - in a set where *neither* side speaks its language.
    supported_languages = ("uk", "it", "en")
    uses_corpus_as_reference = True

    @classmethod
    def calibration_config(cls) -> dict:
        """`threshold=0.0`, because the score is what is being calibrated.

        With the production cut-off in place every entry below it reads as 0.0
        and a sweep over those zeros measures the old threshold rather than the
        detector. Nothing else changes: the reference is the tune half in a run
        exactly as it is here, so the number measured is the number that runs.
        """
        return {"threshold": 0.0}

    def __init__(self, model_name: str = DEFAULT_MODEL,
                 corpus_path: str | None = None,
                 threshold: float = THRESHOLD, **config):
        super().__init__(**config)
        self.model_name = model_name
        self.corpus_path = Path(corpus_path) if corpus_path else CORPUS_PATH
        self.threshold = threshold
        self._model = None
        self._reference_embeddings = None
        self._reference_labels = None
        self._reference_texts = None

    def _load_model(self):
        """Lazy-load the sentence-transformers model."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        except ImportError as exc:
            from .base import DetectorUnavailable
            raise DetectorUnavailable(
                "The 'sentence-transformers' package is not installed. "
                "Run: pip install sentence-transformers"
            ) from exc

    def _load_corpus(self):
        """Load reference corpus and compute embeddings."""
        if self._reference_embeddings is not None:
            return

        self._load_model()

        texts = []
        labels = []
        if self.corpus_path.exists():
            with open(self.corpus_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        if not is_reference(row["text"]):
                            continue
                        texts.append(row["text"])
                        labels.append(row["label"])

        if not texts:
            from .base import DetectorUnavailable
            raise DetectorUnavailable(
                f"Corpus not found or empty: {self.corpus_path}"
            )

        self._reference_texts = texts
        self._reference_labels = labels
        self._reference_embeddings = self._model.encode(texts)

    def analyze_block(self, block: TextBlock) -> list[TextSpan]:
        """Analyze a single text block."""
        self._load_corpus()
        self._load_model()

        text = block.text
        if not text.strip():
            return []

        # Outside the reference languages the margin is not a weak signal, it
        # is a comparison between two sets that are both foreign to the text.
        # Measured 2026-08-31 on 257 paragraphs from dated 2018 Wikipedia
        # revisions in de/fr/es/pl/ru - human by date, written before any of
        # this existed: five of them crossed 0.55 (German 0.564, Spanish
        # 0.558 three times, Russian 0.553). Unlike the wording pass, this one
        # was not silent by luck; it was reporting.
        language = block.language_hint or guess_language_safe(text)
        if not self.supports_language(language):
            return []

        # Skip short texts - embeddings are unreliable for single words
        # or very short phrases. Minimum 5 words for meaningful analysis.
        word_count = len(text.split())
        if word_count < 5:
            return []

        # Compute embedding for input text
        text_embedding = self._model.encode([text])

        # Compute similarities with all reference texts
        similarities = self._model.similarity(text_embedding, self._reference_embeddings)[0]

        # Find most similar AI and human texts
        ai_sims = [float(s) for s, l in zip(similarities, self._reference_labels) if l == "model"]
        human_sims = [float(s) for s, l in zip(similarities, self._reference_labels) if l == "human"]

        ai_max = max(ai_sims) if ai_sims else 0.0
        human_max = max(human_sims) if human_sims else 0.0

        # Score: how much more similar to AI than to human
        score_raw = ai_max - human_max

        # Normalize to 0..1
        score = max(0.0, min(1.0, (score_raw + 1.0) / 2.0))

        # Skip if below threshold
        if score < self.threshold:
            return []

        # Find the most similar AI text for explanation
        ai_idx = np.argmax([float(s) for s, l in zip(similarities, self._reference_labels) if l == "model"])
        ai_texts = [t for t, l in zip(self._reference_texts, self._reference_labels) if l == "model"]
        similar_text = ai_texts[ai_idx][:80] if ai_idx < len(ai_texts) else ""

        details = {
            "source": "embedding",
            "ai_similarity": round(ai_max, 3),
            "human_similarity": round(human_max, 3),
            "model": self.model_name,
            "similar_to": similar_text,
        }

        explanation = (
            f"ai_similarity={ai_max:.3f}, human_similarity={human_max:.3f}"
            f" (similar to: {similar_text}...)"
        )

        return [
            TextSpan(
                block_id=block.block_id,
                start=0,
                end=len(text),
                score=score,
                confidence=score_to_confidence(score),
                detector_name=self.name,
                explanation=explanation,
                details=details,
            )
        ]


DetectorFactory.register(EmbeddingDetector.name, EmbeddingDetector)
