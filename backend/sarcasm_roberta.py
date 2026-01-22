"""
Sarcasm detector - LIGHTWEIGHT VERSION using pattern matching.

Replaces heavy RoBERTa model with rule-based detection.
No PyTorch or Transformers required!

Input:
  - Text snippet

Output:
  {
    "sarcasm": {"score": 65.0, "is_sarcastic": True},
    "sentiment": {"label": "negative", "scores": {...}}
  }
"""

import re

class SarcasmSentimentModel:
    """Lightweight sarcasm detector using pattern matching and keywords."""
    
    def __init__(self):
        # Sarcasm indicators
        self.sarcasm_patterns = [
            # Exaggeration
            r"\b(oh (yeah|sure|great|wonderful|perfect))",
            r"\b(totally|absolutely|definitely|obviously)\b.*\b(not|never)",
            r"\b(right|sure),?\s+(because|like)",
            
            # Rhetorical questions
            r"\b(what could (possibly|possibly|ever) go wrong)",
            r"\b(who would have thought)",
            r"\b(how surprising)",
            
            # Negative framing of positive words
            r"\b(great|wonderful|amazing|fantastic),\s*just\s+(great|wonderful)",
            r"\b(love|loving)\s+how",
            
            # Repetition for emphasis
            r"(great|wonderful|perfect|fantastic).*\1",
        ]
        
        # Sarcasm keywords
        self.sarcasm_keywords = [
            "obviously", "clearly", "brilliant", "genius", 
            "shocker", "shocking", "surprise surprise",
            "thrilled", "delighted", "exactly"
        ]
        
        # Negative sentiment keywords
        self.negative_words = [
            "bad", "terrible", "awful", "worst", "hate", "annoying",
            "frustrating", "disappointed", "useless", "waste"
        ]
        
        # Positive sentiment keywords
        self.positive_words = [
            "good", "great", "excellent", "awesome", "love", "amazing",
            "wonderful", "fantastic", "perfect", "best"
        ]
    
    def analyze(self, text: str) -> dict:
        """Analyze text for sarcasm and sentiment."""
        if not text or not text.strip():
            return {
                "sarcasm": {"score": 0, "is_sarcastic": False, "scores": {"not_sarcastic": 100, "sarcastic": 0}},
                "sentiment": {"label": "neutral", "scores": {"negative": 33, "neutral": 34, "positive": 33}}
            }
        
        text_lower = text.lower()
        
        # Detect sarcasm
        sarcasm_score = self._detect_sarcasm(text_lower)
        
        # Detect sentiment
        sentiment = self._detect_sentiment(text_lower)
        
        return {
            "sarcasm": {
                "score": sarcasm_score,
                "is_sarcastic": sarcasm_score > 50,
                "scores": {
                    "not_sarcastic": 100 - sarcasm_score,
                    "sarcastic": sarcasm_score
                }
            },
            "sentiment": sentiment
        }
    
    def _detect_sarcasm(self, text: str) -> float:
        """Calculate sarcasm score (0-100)."""
        score = 0
        
        # Check patterns
        for pattern in self.sarcasm_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                score += 30
        
        # Check keywords
        for keyword in self.sarcasm_keywords:
            if keyword in text:
                score += 15
        
        # Check for punctuation indicators
        if text.count('!') >= 2:
            score += 20
        if '...' in text:
            score += 10
        
        # Check for contradictory sentiment
        # Positive words with negative context
        has_positive = any(word in text for word in self.positive_words)
        has_negative = any(word in text for word in self.negative_words)
        
        if has_positive and has_negative:
            score += 25
        
        # Exclamation + question mark (e.g., "Great!?")
        if '!' in text and '?' in text:
            score += 15
        
        return min(100, score)
    
    def _detect_sentiment(self, text: str) -> dict:
        """Detect sentiment (positive/neutral/negative)."""
        positive_count = sum(1 for word in self.positive_words if word in text)
        negative_count = sum(1 for word in self.negative_words if word in text)
        
        total = positive_count + negative_count
        
        if total == 0:
            return {
                "label": "neutral",
                "scores": {"negative": 33, "neutral": 34, "positive": 33}
            }
        
        # Calculate percentages
        positive_pct = (positive_count / total) * 100 if total > 0 else 0
        negative_pct = (negative_count / total) * 100 if total > 0 else 0
        neutral_pct = 100 - positive_pct - negative_pct
        
        # Determine dominant
        if positive_pct > negative_pct and positive_pct > 40:
            label = "positive"
        elif negative_pct > positive_pct and negative_pct > 40:
            label = "negative"
        else:
            label = "neutral"
        
        return {
            "label": label,
            "scores": {
                "negative": round(negative_pct, 2),
                "neutral": round(neutral_pct, 2),
                "positive": round(positive_pct, 2)
            }
        }


if __name__ == "__main__":
    model = SarcasmSentimentModel()
    
    # Test cases
    test_texts = [
        "Oh great, another sales pitch. Wonderful.",
        "This product is absolutely fantastic!",
        "Yeah, sure, because that totally makes sense.",
        "I love how you completely ignored my concerns.",
        "The product works well and I'm satisfied."
    ]
    
    for text in test_texts:
        result = model.analyze(text)
        print(f"Text: {text}")
        print(f"Sarcasm: {result['sarcasm']['score']}% - {result['sarcasm']['is_sarcastic']}")
        print(f"Sentiment: {result['sentiment']['label']}")
        print()
