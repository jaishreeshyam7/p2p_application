"""
Objection classifier - LIGHTWEIGHT VERSION using keyword matching.

Replaces heavy spaCy NLP with pattern-based detection.
No spaCy required!

Input:
  - Text snippet

Objection Types:
  - PRICE_OBJECTION
  - TIMING_OBJECTION
  - AUTHORITY_OBJECTION
  - NEED_OBJECTION
  - COMPETITION_OBJECTION
  - NO_OBJECTION

Output:
  {
    "label": "PRICE_OBJECTION",
    "score": 85,
    "all_scores": {...}
  }
"""

import re

class ObjectionClassifier:
    """Lightweight objection detector using keyword and pattern matching."""
    
    def __init__(self):
        # Define objection patterns and keywords
        self.objection_patterns = {
            "PRICE_OBJECTION": {
                "keywords": [
                    "expensive", "cost", "price", "budget", "afford",
                    "cheap", "money", "investment", "roi", "value",
                    "cheaper", "discount", "paying", "worth"
                ],
                "patterns": [
                    r"too (expensive|costly|much|pricey)",
                    r"(can't|cannot|won't) afford",
                    r"(out of|over|beyond) (our |my )?budget",
                    r"don't have (the |enough )?money",
                    r"looking for (something |a )?cheaper"
                ]
            },
            "TIMING_OBJECTION": {
                "keywords": [
                    "later", "time", "busy", "now", "wait",
                    "think", "consider", "month", "year", "soon",
                    "rush", "hurry", "schedule"
                ],
                "patterns": [
                    r"(not |no )(the |a )?(right |good )?time",
                    r"(call|contact|reach) (me |us )?(back |later)",
                    r"(let me|i'll|we'll) think about",
                    r"(maybe |perhaps )(later|next (week|month|year))",
                    r"(too |so )(busy|swamped)",
                    r"(not |no )(ready|prepared)"
                ]
            },
            "AUTHORITY_OBJECTION": {
                "keywords": [
                    "manager", "boss", "team", "partner", "decision",
                    "discuss", "approve", "authorization", "board",
                    "committee", "stakeholder"
                ],
                "patterns": [
                    r"(talk|speak|discuss) (to|with) (my |the |our )(boss|manager|team)",
                    r"(need|have) to (get |receive )?approval",
                    r"(not |can't )(my |the )?decision",
                    r"(run|check) (it |this )?by (my |the )",
                    r"(don't|doesn't) have (the |that )?(authority|power)"
                ]
            },
            "NEED_OBJECTION": {
                "keywords": [
                    "need", "want", "necessary", "require", "use",
                    "looking", "already", "have", "don't", "working"
                ],
                "patterns": [
                    r"(don't|do not|doesn't|does not) (really |actually )?(need|want|require)",
                    r"(not |no )(sure|certain) (if |that |whether )?(we |i )(need|want)",
                    r"(already|currently) (have|using|working with)",
                    r"(happy|satisfied) with (what|current|existing)",
                    r"(not |no )(interested|looking)"
                ]
            },
            "COMPETITION_OBJECTION": {
                "keywords": [
                    "competitor", "alternative", "comparing", "other",
                    "vendor", "provider", "option", "choice",
                    "versus", "better", "different"
                ],
                "patterns": [
                    r"(using|working with|have) (a |another |other )(vendor|provider|solution)",
                    r"(comparing|looking at|considering) (other |different )?options",
                    r"(what makes|why is) (you|this|your) (better|different)",
                    r"(already|currently) (use|using|with) \w+",
                    r"(heard|seen|know) about \w+"
                ]
            }
        }
    
    def predict(self, text: str) -> dict:
        """Predict objection type from text."""
        if not text or not text.strip():
            return {
                "label": "NO_OBJECTION",
                "score": 100,
                "all_scores": {"NO_OBJECTION": 100}
            }
        
        text_lower = text.lower()
        scores = {}
        
        # Calculate scores for each objection type
        for objection_type, criteria in self.objection_patterns.items():
            score = 0
            
            # Check keywords
            keyword_matches = sum(1 for keyword in criteria["keywords"] if keyword in text_lower)
            score += keyword_matches * 10
            
            # Check patterns
            pattern_matches = sum(1 for pattern in criteria["patterns"] if re.search(pattern, text_lower))
            score += pattern_matches * 30
            
            scores[objection_type] = min(100, score)
        
        # Determine dominant objection
        max_score = max(scores.values()) if scores else 0
        
        if max_score < 20:
            return {
                "label": "NO_OBJECTION",
                "score": 100,
                "all_scores": {"NO_OBJECTION": 100, **scores}
            }
        
        dominant_objection = max(scores, key=scores.get)
        
        return {
            "label": dominant_objection,
            "score": scores[dominant_objection],
            "all_scores": scores
        }
    
    def batch_predict(self, texts):
        """Predict objections for multiple texts."""
        return [self.predict(t) for t in texts]


if __name__ == "__main__":
    clf = ObjectionClassifier()
    
    # Test cases
    test_texts = [
        "This is too expensive for our budget.",
        "Let me think about it and get back to you.",
        "I need to discuss this with my manager first.",
        "We don't really need this right now.",
        "We're currently using a different solution.",
        "Sounds great, let's move forward!"
    ]
    
    for text in test_texts:
        result = clf.predict(text)
        print(f"Text: {text}")
        print(f"Objection: {result['label']} (Score: {result['score']})")
        print(f"All scores: {result['all_scores']}")
        print()
