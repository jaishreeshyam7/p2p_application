"""
Speaker diarization with pyannote.audio.

Input:
  - Path to audio file.

Processing:
  - Run pre-trained diarization pipeline from Hugging Face.
  - Group segments by speaker.
  - Optionally relabel speakers as "user" and "prospect".

Output:
  {
    "segments": [{"speaker": "SPEAKER_00", "start": float, "end": float}, ...],
    "stats": {
        "SPEAKER_00": {"total_time": float, "percentage": float, ...},
        ...
    },
    "labeled_segments": [{"speaker": "user" / "prospect", ...}, ...]
  }
"""

from typing import Dict, List
from pyannote.audio import Pipeline
import torch

class Diarizer:
    def __init__(self, hf_token: str):
        self.pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        if torch.cuda.is_available():
            self.pipeline.to(torch.device("cuda"))

    def diarize(self, audio_path: str, num_speakers: int = 2) -> Dict:
        diarization = self.pipeline(audio_path, num_speakers=num_speakers)

        segments = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                {
                    "speaker": speaker,
                    "start": round(turn.start, 2),
                    "end": round(turn.end, 2),
                    "duration": round(turn.end - turn.start, 2),
                }
            )

        stats = self._compute_stats(segments)
        labeled = self._label_user_prospect(segments)

        return {
            "segments": segments,
            "stats": stats,
            "labeled_segments": labeled,
        }

    @staticmethod
    def _compute_stats(segments: List[Dict]) -> Dict:
        stats: Dict[str, Dict] = {}
        for s in segments:
            spk = s["speaker"]
            stats.setdefault(spk, {"total_time": 0.0, "turns": 0})
            stats[spk]["total_time"] += s["duration"]
            stats[spk]["turns"] += 1

        total_time = sum(v["total_time"] for v in stats.values()) or 1.0
        for spk, v in stats.items():
            v["total_time"] = round(v["total_time"], 2)
            v["avg_turn"] = round(v["total_time"] / v["turns"], 2)
            v["percentage"] = round((v["total_time"] / total_time) * 100, 1)
        return stats

    @staticmethod
    def _label_user_prospect(segments: List[Dict]) -> List[Dict]:
        """Simple heuristic: first speaker -> user, second -> prospect."""
        speaker_ids = list({s["speaker"] for s in segments})
        if not speaker_ids:
            return segments

        mapping = {speaker_ids[0]: "user"}
        if len(speaker_ids) > 1:
            mapping[speaker_ids[1]] = "prospect"

        labeled = []
        for s in segments:
            labeled.append({**s, "speaker": mapping.get(s["speaker"], s["speaker"])})
        return labeled


if __name__ == "__main__":
    diar = Diarizer(hf_token="YOUR_HF_TOKEN")
    out = diar.diarize("example_sales_call.wav")
    print("Stats:", out["stats"])
