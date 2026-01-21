"""
Transcription + basic timing metrics using faster-whisper.

Input:
  - Path to an audio file (wav, mp3, m4a, etc.)

Processing:
  - Transcribe with Whisper via faster-whisper, with word timestamps.
  - Compute:
      * total_words
      * words_per_minute (WPM)
      * list of long pauses (> threshold seconds).

Output (dict):
  {
    "full_text": str,
    "segments": [...],
    "words": [...],
    "metrics": {"total_words": int, "wpm": float, "duration": float},
    "pauses": [{"start": float, "end": float, "duration": float}, ...]
  }
"""

from faster_whisper import WhisperModel
import numpy as np

class WhisperTranscriber:
    def __init__(self, model_size: str = "base", device: str = "cuda"):
        # model_size: tiny / base / small / medium / large-v2
        self.model = WhisperModel(
            model_size,
            device=device,          # "cuda" or "cpu"
            compute_type="float16"  # "int8" for even faster but slightly less accurate
        )

    def transcribe(self, audio_path: str, language: str = "en",
                   pause_threshold: float = 1.0) -> dict:
        # --- Transcription with word-level timestamps ---
        segments_gen, info = self.model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500}
        )
        segments = list(segments_gen)

        words = self._extract_words(segments)
        metrics = self._compute_metrics(words)
        pauses = self._detect_pauses(words, pause_threshold)

        return {
            "full_text": " ".join(seg.text.strip() for seg in segments),
            "segments": self._format_segments(segments),
            "words": words,
            "metrics": metrics,
            "pauses": pauses,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
        }

    # ---------- helpers ----------

    @staticmethod
    def _extract_words(segments):
        words = []
        for seg in segments:
            if getattr(seg, "words", None):
                for w in seg.words:
                    words.append(
                        {
                            "word": w.word.strip(),
                            "start": round(w.start, 2),
                            "end": round(w.end, 2),
                            "prob": round(w.probability, 3),
                        }
                    )
        return words

    @staticmethod
    def _format_segments(segments):
        return [
            {
                "id": seg.id,
                "text": seg.text.strip(),
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "duration": round(seg.end - seg.start, 2),
            }
            for seg in segments
        ]

    @staticmethod
    def _compute_metrics(words):
        if not words:
            return {"total_words": 0, "wpm": 0.0, "duration": 0.0}

        total_words = len(words)
        duration = words[-1]["end"] - words[0]["start"]
        wpm = (total_words / duration) * 60 if duration > 0 else 0.0

        return {
            "total_words": total_words,
            "wpm": round(wpm, 1),
            "duration": round(duration, 2),
        }

    @staticmethod
    def _detect_pauses(words, threshold: float):
        """
        Long pauses = gap between word_end[i] and word_start[i+1] > threshold.
        """
        pauses = []
        for i in range(len(words) - 1):
            gap = words[i + 1]["start"] - words[i]["end"]
            if gap > threshold:
                pauses.append(
                    {
                        "start": words[i]["end"],
                        "end": words[i + 1]["start"],
                        "duration": round(gap, 2),
                        "before": words[i]["word"],
                        "after": words[i + 1]["word"],
                    }
                )
        return pauses


if __name__ == "__main__":
    t = WhisperTranscriber(model_size="tiny", device="cpu")
    out = t.transcribe("example_sales_call.wav")
    print("WPM:", out["metrics"]["wpm"])
    print("Long pauses:", out["pauses"][:5])
