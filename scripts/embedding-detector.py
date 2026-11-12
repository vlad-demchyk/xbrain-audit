#!/usr/bin/env python3
"""Embedding-based AI text detection.

Approach:
1. Compute embeddings for AI texts in corpus (reference)
2. For new text, compute embedding
3. Compare with reference using cosine similarity
4. High similarity → likely AI-generated

This is a complementary signal to the heuristic detector.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
from sentence_transformers import SentenceTransformer


# Default model - small, fast, good quality
DEFAULT_MODEL = "all-MiniLM-L6-v2"


class EmbeddingDetector:
    """Embedding-based AI text detector."""
    
    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model = SentenceTransformer(model_name)
        self.reference_embeddings = None
        self.reference_labels = None
    
    def fit(self, texts: list[str], labels: list[str]) -> None:
        """Compute reference embeddings from labeled texts."""
        self.reference_embeddings = self.model.encode(texts, show_progress_bar=True)
        self.reference_labels = labels
    
    def predict(self, text: str) -> dict:
        """Predict if text is AI-generated."""
        if self.reference_embeddings is None:
            raise ValueError("Call fit() first with labeled data")
        
        # Compute embedding for input text
        text_embedding = self.model.encode([text])
        
        # Compute similarities with all reference texts
        similarities = self.model.similarity(text_embedding, self.reference_embeddings)[0]
        
        # Find most similar AI and human texts
        ai_sims = [s for s, l in zip(similarities, self.reference_labels) if l == "model"]
        human_sims = [s for s, l in zip(similarities, self.reference_labels) if l == "human"]
        
        ai_max = max(ai_sims) if ai_sims else 0.0
        human_max = max(human_sims) if human_sims else 0.0
        ai_mean = np.mean(ai_sims) if ai_sims else 0.0
        human_mean = np.mean(human_sims) if human_sims else 0.0
        
        # Score: how much more similar to AI than to human
        # Range: -1 (very human) to +1 (very AI)
        score = float(ai_max - human_max)
        
        # Normalize to 0..1
        normalized_score = max(0.0, min(1.0, (score + 1.0) / 2.0))
        
        return {
            "score": round(normalized_score, 3),
            "ai_similarity": round(float(ai_max), 3),
            "human_similarity": round(float(human_max), 3),
            "ai_mean": round(float(ai_mean), 3),
            "human_mean": round(float(human_mean), 3),
        }
    
    def predict_batch(self, texts: list[str]) -> list[dict]:
        """Predict for multiple texts."""
        return [self.predict(text) for text in texts]


def load_corpus(corpus_path: str) -> tuple[list[str], list[str]]:
    """Load labeled corpus."""
    texts = []
    labels = []
    with open(corpus_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                texts.append(row["text"])
                labels.append(row["label"])
    return texts, labels


def main() -> int:
    import argparse
    
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("text", help="text to analyze")
    parser.add_argument("--corpus", default="corpus/labelled.jsonl",
                        help="path to labeled corpus")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="sentence-transformers model name")
    args = parser.parse_args()
    
    # Load corpus
    print(f"Loading corpus from {args.corpus}...")
    texts, labels = load_corpus(args.corpus)
    print(f"Loaded {len(texts)} texts ({sum(1 for l in labels if l == 'model')} model, "
          f"{sum(1 for l in labels if l == 'human')} human)")
    
    # Create detector
    print(f"Loading model {args.model}...")
    detector = EmbeddingDetector(args.model)
    
    # Fit on corpus
    print("Computing reference embeddings...")
    detector.fit(texts, labels)
    
    # Predict
    print(f"\nAnalyzing: {args.text[:80]}...")
    result = detector.predict(args.text)
    
    print(f"\nResult:")
    print(f"  Score: {result['score']:.3f}")
    print(f"  AI similarity: {result['ai_similarity']:.3f}")
    print(f"  Human similarity: {result['human_similarity']:.3f}")
    print(f"  AI mean: {result['ai_mean']:.3f}")
    print(f"  Human mean: {result['human_mean']:.3f}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
