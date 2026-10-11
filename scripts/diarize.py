"""Who said what: speaker separation (pyannote) + Hebrew Whisper with a timestamp per word.

For recordings where everyone is on one audio track: phone calls, in-person meetings recorded on the phone,
a meeting someone else hosted. Output next to the normal transcript: <name>.speakers.txt, lines like
"[03:12] Speaker 2: ...". Real names are assigned afterwards from the content (who introduced themselves,
how people address each other, who was invited in the calendar).

Usage:
    python scripts/diarize.py "<recording>" [number of speakers, if known - 2 for a phone call]
Needs: HF_TOKEN saved with secrets_store.py, and the model terms accepted on Hugging Face (see START-HERE.md).
"""
import subprocess
import sys
import tempfile
import wave
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import fmt, get_secret, load_config, load_model, utf8_console


def main() -> None:
    utf8_console()
    cfg = load_config()
    src = Path(sys.argv[1])
    num_speakers = int(sys.argv[2]) if len(sys.argv) > 2 else None
    label = cfg.get("speaker_label", "דובר")

    import numpy as np
    import torch
    from pyannote.audio import Pipeline

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(wav)], check=True)

        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-community-1", token=get_secret("HF_TOKEN"))
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        # On Windows torchcodec usually fails to load, so the audio is handed over already decoded
        with wave.open(str(wav)) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        kwargs = {"num_speakers": num_speakers} if num_speakers else {}
        result = pipeline({"waveform": torch.from_numpy(pcm).unsqueeze(0), "sample_rate": 16000}, **kwargs)
        diar = getattr(result, "speaker_diarization", result)
        turns = [(t.start, t.end, spk) for t, _, spk in diar.itertracks(yield_label=True)]

        model = load_model(cfg)
        # a timestamp per word, so a short "yes" from the other person is not swallowed inside a long sentence
        segments, _ = model.transcribe(str(wav), language=cfg.get("language", "he"), vad_filter=True,
                                       beam_size=5, word_timestamps=True)

        order = {}
        for _, _, spk in sorted(turns):
            order.setdefault(spk, f"{label} {len(order) + 1}")

        def speaker_at(a: float, b: float, fallback: str) -> str:
            best, best_overlap = None, 0.0
            for x, y, spk in turns:
                overlap = min(y, b) - max(x, a)
                if overlap > best_overlap:
                    best, best_overlap = spk, overlap
            if best is None:  # a word between turns - take the nearest speaker in time
                mid = (a + b) / 2
                near = min(turns, key=lambda t: min(abs(t[0] - mid), abs(t[1] - mid)), default=None)
                return order[near[2]] if near else fallback
            return order[best]

        lines, talk, prev = [], defaultdict(float), None
        for s in segments:
            for w in (s.words or []):
                who = speaker_at(w.start, w.end, prev or "?")
                talk[who] += w.end - w.start
                if who == prev and lines:
                    lines[-1] += w.word
                else:
                    lines.append(f"[{fmt(w.start)}] {who}:{w.word}")
                prev = who

    target = cfg["transcripts_root"] / src.parent.name / f"{src.stem}.speakers.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    total = sum(talk.values()) or 1
    print(f"{len(order)} speakers: " + ", ".join(f"{k} {v / total:.0%}" for k, v in sorted(talk.items())))
    print(f"saved: {target}")


if __name__ == "__main__":
    main()
