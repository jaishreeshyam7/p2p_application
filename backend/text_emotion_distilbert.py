"""
Text emotion classification - LIGHTWEIGHT VERSION using TextBlob.

This replaces the heavy DistilBERT model with a simple, fast alternative.
No PyTorch or Transformers required!

Input:
  - Text snippet

Output:
  {
    "raw": {"joy": 70.1, "anger": 5.2, ...},
    "dominant": "joy"
  }
"""

try:
    from textblob import TextBlob
    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False

class TextEmotionClassifier:
    """Lightweight emotion classifier using TextBlob sentiment analysis."""
    
    def __init__(self):
        if not TEXTBLOB_AVAILABLE:
            raise ImportError("TextBlob not available. Install with: pip install textblob")
        
        # Download required data
        try:
            import nltk
            nltk.download('brown', quiet=True)
            nltk.download('punkt', quiet=True)
        except:
            pass
    
    def classify(self, text: str) -> dict:
        """Classify emotions in text using sentiment analysis."""
        if not text or not text.strip():
            return {"raw": {}, "dominant": "neutral"}
        
        # Get sentiment
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity  # -1 to 1
        subjectivity = blob.sentiment.subjectivity  # 0 to 1
        
        # Convert sentiment to emotion scores
        emotions = self._sentiment_to_emotions(polarity, subjectivity)
        
        # Find dominant emotion
        dominant = max(emotions, key=emotions.get)
        
        return {
            "raw": emotions,
            "dominant": dominant
        }
    
    def _sentiment_to_emotions(self, polarity: float, subjectivity: float) -> dict:
        """
        Map sentiment polarity/subjectivity to emotion categories.
        
        Polarity: -1 (negative) to +1 (positive)
        Subjectivity: 0 (objective) to 1 (subjective)
        """
        emotions = {
            "anger": 0,
            "joy": 0,
            "sadness": 0,
            "fear": 0,
            "surprise": 0,
            "neutral": 50
        }
        
        # Positive emotions
        if polarity > 0.3:
            emotions["joy"] = min(100, int(polarity * 100))
            emotions["neutral"] = max(0, 50 - emotions["joy"])
            if subjectivity > 0.7:
                emotions["surprise"] = int(subjectivity * 30)
        
        # Negative emotions
        elif polarity < -0.3:
            anger_score = min(100, int(abs(polarity) * 100))
            
            # High subjectivity = anger, low = sadness
            if subjectivity > 0.6:
                emotions["anger"] = anger_score
            else:
                emotions["sadness"] = anger_score
            
            emotions["neutral"] = max(0, 50 - anger_score)
        
        # Mildly negative
        elif polarity < -0.1:
            if subjectivity > 0.5:
                emotions["fear"] = int(abs(polarity) * 60)
            else:
                emotions["sadness"] = int(abs(polarity) * 50)
            emotions["neutral"] = 40
        
        # Mildly positive
        elif polarity > 0.1:
            emotions["joy"] = int(polarity * 60)
            emotions["neutral"] = 40
        
        # Neutral
        else:
            emotions["neutral"] = 70
        
        return emotions
    
    def batch_classify(self, texts):
        """Classify multiple texts."""
        return [self.classify(t) for t in texts]


if __name__ == "__main__":
    clf = TextEmotionClassifier()
    
    # Test cases
    test_texts = [
        "I'm so excited about this!",
        "This is terrible and makes me angry.",
        "I'm worried about the price.",
        "The product looks okay.",
        "This is amazing and wonderful!"
    ]
    
    for text in test_texts:
        result = clf.classify(text)
        print(f"Text: {text}")
        print(f"Dominant: {result['dominant']}")
        print(f"Scores: {result['raw']}")
        print()
