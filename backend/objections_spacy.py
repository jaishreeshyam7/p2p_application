"""
Custom SpaCy text categorizer for sales objections.

Goal:
  Detect categories like PRICE, TIMING, AUTHORITY, NEED, COMPETITION.

This file shows:
  - how to define & train textcat
  - how to run prediction.

IMPORTANT:
  In production you should train offline, save the model to disk, and
  load it in your API process instead of retraining every time.
"""

import random
from typing import List, Tuple, Dict

import spacy
from spacy.training import Example

LABELS = [
    "PRICE_OBJECTION",
    "TIMING_OBJECTION",
    "AUTHORITY_OBJECTION",
    "NEED_OBJECTION",
    "COMPETITION_OBJECTION",
    "NO_OBJECTION",
]

# A tiny toy dataset; you MUST expand this with many real sentences.
TRAIN_DATA: List[Tuple[str, Dict]] = [
    ("It's too expensive for us.", {"cats": {"PRICE_OBJECTION": 1, "NO_OBJECTION": 0}}),
    ("We don't have the budget.", {"cats": {"PRICE_OBJECTION": 1, "NO_OBJECTION": 0}}),
    ("Let me think about it.", {"cats": {"TIMING_OBJECTION": 1, "NO_OBJECTION": 0}}),
    ("I need to talk to my boss.", {"cats": {"AUTHORITY_OBJECTION": 1, "NO_OBJECTION": 0}}),
    ("We are looking at other vendors.", {"cats": {"COMPETITION_OBJECTION": 1, "NO_OBJECTION": 0}}),
    ("This looks great, let's proceed.", {"cats": {"NO_OBJECTION": 1}}),
]


class ObjectionClassifier:
    def __init__(self, model_path: str = None):
        if model_path:
            self.nlp = spacy.load(model_path)
        else:
            self.nlp = spacy.blank("en")
            self._init_textcat()

    def _init_textcat(self):
        textcat = self.nlp.add_pipe("textcat")
        for label in LABELS:
            textcat.add_label(label)

    def train(self, n_iter: int = 20):
        textcat = self.nlp.get_pipe("textcat")
        optimizer = self.nlp.begin_training()

        for i in range(n_iter):
            random.shuffle(TRAIN_DATA)
            losses = {}
            batches = spacy.util.minibatch(TRAIN_DATA, size=4)
            for batch in batches:
                examples = []
                for text, annotations in batch:
                    cats = {label: 0.0 for label in LABELS}
                    cats.update(annotations["cats"])
                    doc = self.nlp.make_doc(text)
                    examples.append(Example.from_dict(doc, {"cats": cats}))
                self.nlp.update(examples, sgd=optimizer, losses=losses)
            print(f"Iter {i+1} Loss: {losses['textcat']:.4f}")

    def save(self, path: str):
        self.nlp.to_disk(path)

    def predict(self, text: str) -> dict:
        doc = self.nlp(text)
        cats = doc.cats
        top_label = max(cats, key=cats.get)
        return {
            "label": top_label,
            "score": round(cats[top_label] * 100, 2),
            "all_scores": {k: round(v * 100, 2) for k, v in cats.items()},
        }


if __name__ == "__main__":
    clf = ObjectionClassifier()
    clf.train(n_iter=10)
    print(clf.predict("The pricing is a bit high, honestly."))
