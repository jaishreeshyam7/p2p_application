"""
Sarcasm & sentiment detector using RoBERTa-based models.

Input:
  - Text snippet (usually 1 sentence / segment).

Processing:
  - RoBERTa model #1: irony/sarcasm classifier.
  - RoBERTa model #2: sentiment classifier (neg / neu / pos).

Output:
  {
    "sarcasm": {"score": float, "is_sarcastic": bool},
    "sentiment": {"label": str, "scores": {...}}
  }
"""

from typing import Dict

import torch
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForSequenceClassification


class SarcasmSentimentModel:
    def __init__(self):
        # Twitter RoBERTa models work well on conversational language
        sarcasm_name = "cardiffnlp/twitter-roberta-base-irony"
        sent_name = "cardiffnlp/twitter-roberta-base-sentiment-latest"

        self.sarcasm_tok = AutoTokenizer.from_pretrained(sarcasm_name)
        self.sarcasm_model = AutoModelForSequenceClassification.from_pretrained(
            sarcasm_name
        )

        self.sent_tok = AutoTokenizer.from_pretrained(sent_name)
        self.sent_model = AutoModelForSequenceClassification.from_pretrained(sent_name)

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.sarcasm_model.to(self.device)
        self.sent_model.to(self.device)

    def _predict(self, text: str, tok, model, labels) -> Dict:
        inputs = tok(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=128,
            padding=True,
        ).to(self.device)

        with torch.no_grad():
            logits = model(**inputs).logits
            probs = F.softmax(logits, dim=-1)[0].cpu().numpy()

        scores = {label: round(float(p) * 100, 2) for label, p in zip(labels, probs)}
        dominant = max(scores, key=scores.get)
        return scores, dominant

    def analyze(self, text: str) -> Dict:
        # Sarcasm: labels [0=non-ironic, 1=ironic]
        sarc_labels = ["not_sarcastic", "sarcastic"]
        sarc_scores, sarc_label = self._predict(
            text, self.sarcasm_tok, self.sarcasm_model, sarc_labels
        )
        sarcasm_score = sarc_scores["sarcastic"]

        # Sentiment: labels [negative, neutral, positive]
        sent_labels = ["negative", "neutral", "positive"]
        sent_scores, sent_label = self._predict(
            text, self.sent_tok, self.sent_model, sent_labels
        )

        return {
            "sarcasm": {
                "score": sarcasm_score,
                "is_sarcastic": sarcasm_score > 50,
                "scores": sarc_scores,
            },
            "sentiment": {"label": sent_label, "scores": sent_scores},
        }


if __name__ == "__main__":
    m = SarcasmSentimentModel()
    t1 = "Oh great, another sales pitch. Wonderful."
    print(m.analyze(t1))
