"""
Text emotion classification using DistilBERT.

Input:
  - One or more text snippets (from Whisper segments or speaker turns).

Processing:
  - Use HF pipeline with an emotion‑finetuned DistilBERT/DistilRoBERTa model.
  - Get probabilities for emotions like anger, joy, sadness, etc.

Output (for one text):
  {
    "raw": {"anger": 3.2, "joy": 70.1, ...},  # % scores
    "dominant": "joy"
  }
"""

from transformers import pipeline
import torch

class TextEmotionClassifier:
    def __init__(self):
        # Good open model for emotion classification
        model_name = "j-hartmann/emotion-english-distilroberta-base"
        self.pipe = pipeline(
            "text-classification",
            model=model_name,
            top_k=None,  # return all labels with scores
            device=0 if torch.cuda.is_available() else -1,
        )

    def classify(self, text: str) -> dict:
        if not text or not text.strip():
            return {"raw": {}, "dominant": "neutral"}

        result = self.pipe(text)[0]  # list of dicts
        scores = {r["label"]: round(r["score"] * 100, 2) for r in result}
        dominant = max(scores, key=scores.get)

        return {"raw": scores, "dominant": dominant}

    def batch_classify(self, texts):
        return [self.classify(t) for t in texts]


if __name__ == "__main__":
    clf = TextEmotionClassifier()
    out = clf.classify("I'm excited, but a bit worried about the price.")
    print(out)
