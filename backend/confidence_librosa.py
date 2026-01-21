"""
Confidence analysis from raw audio using Librosa.

Input:
  - Path to mono audio file.

Processing:
  - Extract pitch contour (F0) via librosa.pyin
  - Compute jitter = pitch variability
  - Extract RMS energy (volume) per frame
  - Compute shimmer = volume variability
  - Combine into overall confidence_score (0-100)

Output:
  {
    "confidence_score": float,
    "pitch_stability": float,
    "volume_stability": float,
    "avg_pitch_hz": float,
    "avg_rms": float,
  }
"""

from typing import Dict

import librosa
import numpy as np


class ConfidenceAnalyzer:
    def __init__(self, sample_rate: int = 16000):
        self.sr = sample_rate

    def analyze(self, audio_path: str) -> Dict:
        y, sr = librosa.load(audio_path, sr=self.sr)

        pitch = self._pitch_features(y, sr)
        volume = self._volume_features(y)

        confidence = (
            0.5 * pitch["stability"] + 0.3 * volume["stability"] + 0.2 * pitch["range_score"]
        )

        return {
            "confidence_score": round(confidence, 2),
            "pitch_stability": pitch["stability"],
            "volume_stability": volume["stability"],
            "avg_pitch_hz": pitch["avg_hz"],
            "avg_rms": volume["avg_rms"],
            "jitter": pitch["jitter"],
            "shimmer": volume["shimmer"],
        }

    def _pitch_features(self, y, sr):
        f0, voiced_flag, _ = librosa.pyin(
            y,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
            sr=sr,
        )
        f0 = f0[~np.isnan(f0)]
        if len(f0) == 0:
            return {"stability": 0.0, "avg_hz": 0.0, "jitter": 1.0, "range_score": 0.0}

        avg = float(np.mean(f0))
        std = float(np.std(f0))
        jitter = std / avg if avg > 0 else 1.0
        stability = max(0.0, 100.0 - jitter * 500.0)
        pitch_range = float(np.max(f0) - np.min(f0))
        range_score = min(100.0, (pitch_range / 100.0) * 100.0)

        return {
            "stability": round(stability, 2),
            "avg_hz": round(avg, 2),
            "jitter": round(jitter, 4),
            "range_score": round(range_score, 2),
        }

    def _volume_features(self, y):
        rms = librosa.feature.rms(y=y)[0]
        avg_rms = float(np.mean(rms))
        std_rms = float(np.std(rms))
        shimmer = std_rms / avg_rms if avg_rms > 0 else 1.0
        stability = max(0.0, 100.0 - shimmer * 200.0)

        return {
            "stability": round(stability, 2),
            "avg_rms": round(avg_rms, 5),
            "shimmer": round(shimmer, 4),
        }


if __name__ == "__main__":
    a = ConfidenceAnalyzer()
    print(a.analyze("example_sales_call.wav"))
