"""Record a call on this computer: whatever plays through the speakers (the other side) + the microphone (you).

For calls you cannot record in the app itself: a Zoom meeting someone else hosts, Google Meet, Teams,
WhatsApp desktop. Nothing in the sound settings is changed and no virtual cable is used, so the speakers
are never muted - not when recording starts and not when it stops.

The result is a stereo file: left channel = you (microphone), right channel = the other side.
It is saved to <phone_inbox>/הקלטות מחשב/, so the regular nightly run picks it up like any other recording.

Usage:
    pythonw scripts/record_call.pyw                     # opens the small recording window
    python  scripts/record_call.pyw --install-shortcut  # creates a "הקלטת שיחה" shortcut on the desktop
Needs: pip install soundcard sounddevice  (and ffmpeg)
"""
import base64
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config  # noqa: E402

RATE = 48000
LOCK = Path(tempfile.gettempdir()) / "recordings_kit_record_call.lock"
NO_WINDOW = 0x08000000


def install_shortcut() -> None:
    pyw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve()
    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'הקלטת שיחה.lnk'));"
        f"$s.TargetPath='{pyw}';$s.Arguments='\"{script}\"';$s.WorkingDirectory='{script.parent}';"
        "$s.IconLocation=\"$env:SystemRoot\\System32\\SndVol.exe,0\";$s.Save();"
        "Write-Output (Join-Path $d 'הקלטת שיחה.lnk')"
    )
    # -EncodedCommand: a plain -Command/-File with Hebrew in it fails silently in Windows PowerShell 5.1
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    r = subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", enc], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())


def pid_alive(pid: int) -> bool:
    out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    return str(pid) in out


class Recorder:
    def __init__(self, workdir: Path):
        self.stop_flag = threading.Event()
        self.sys_path = workdir / "system.wav"
        self.mic_path = workdir / "mic.wav"
        self.errors = []
        self.mic_q = queue.Queue()
        self.t0 = {}  # רגע ההתחלה האמיתי של כל ערוץ, ליישור בסוף

    @staticmethod
    def _wav(path: Path):
        w = wave.open(str(path), "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        return w

    @staticmethod
    def _pcm(x):
        import numpy as np
        return (np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes()

    def system_loop(self):
        try:
            import ctypes
            import soundcard as sc
            ctypes.windll.ole32.CoInitializeEx(None, 0)  # WASAPI is COM; a worker thread must initialize it
            loop = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
            w = self._wav(self.sys_path)
            with loop.recorder(samplerate=RATE, channels=2) as rec:
                self.t0.setdefault("sys", time.monotonic())
                while not self.stop_flag.is_set():
                    w.writeframes(self._pcm(rec.record(numframes=RATE // 2).mean(axis=1)))
            w.close()
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"רמקולים: {e}")

    def mic_loop(self):
        # sounddevice and not soundcard: soundcard failed on a webcam microphone (format assertion)
        try:
            import sounddevice as sd
            w = self._wav(self.mic_path)
            with sd.InputStream(samplerate=RATE, channels=1, dtype="float32",
                                callback=lambda d, f, t, s: (self.t0.setdefault("mic", time.monotonic()), self.mic_q.put(d.copy()))):
                while not self.stop_flag.is_set() or not self.mic_q.empty():
                    try:
                        w.writeframes(self._pcm(self.mic_q.get(timeout=0.3)[:, 0]))
                    except queue.Empty:
                        pass
            w.close()
        except Exception as e:  # noqa: BLE001
            self.errors.append(f"מיקרופון: {e}")


def main():
    import tkinter as tk
    if LOCK.exists():
        try:
            if pid_alive(int(LOCK.read_text())):
                return  # already recording, the window is open
        except ValueError:
            pass
    LOCK.write_text(str(os.getpid()))
    dest = Path(load_config()["phone_inbox"]) / "הקלטות מחשב"

    workdir = Path(tempfile.mkdtemp(prefix="call_"))
    started = datetime.now()
    rec = Recorder(workdir)
    threads = [threading.Thread(target=rec.system_loop, daemon=True),
               threading.Thread(target=rec.mic_loop, daemon=True)]
    for t in threads:
        t.start()

    root = tk.Tk()
    root.title("הקלטת שיחה")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    w, h = 260, 120
    root.geometry(f"{w}x{h}+{root.winfo_screenwidth() - w - 30}+{root.winfo_screenheight() - h - 90}")
    status = tk.Label(root, text="● מקליט 00:00", fg="#c0392b", font=("Segoe UI", 15, "bold"))
    status.pack(pady=(14, 8))

    def tick():
        if rec.stop_flag.is_set():
            return
        s = int((datetime.now() - started).total_seconds())
        status.config(text=f"● מקליט {s // 60:02d}:{s % 60:02d}")
        root.after(500, tick)

    def finish():
        if rec.stop_flag.is_set():
            return
        rec.stop_flag.set()
        btn.config(state="disabled")
        status.config(text="שומר...", fg="#555555")
        root.update()
        for t in threads:
            t.join(timeout=5)
        dest.mkdir(parents=True, exist_ok=True)
        out = dest / f"הקלטת מחשב_{started:%y%m%d_%H%M%S}.m4a"
        secs = (datetime.now() - started).total_seconds()
        base = min(rec.t0.values()) if rec.t0 else 0
        dm = int((rec.t0.get("mic", base) - base) * 1000)
        ds = int((rec.t0.get("sys", base) - base) * 1000)
        inputs = [p for p in (rec.mic_path, rec.sys_path) if p.exists() and p.stat().st_size > 1000]
        cmd = None
        if len(inputs) == 2:
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(rec.mic_path), "-i", str(rec.sys_path),
                   "-filter_complex", f"[0:a]adelay={dm}:all=1,apad[m];[1:a]adelay={ds}:all=1,apad[s];[m][s]amerge=inputs=2,atrim=end={secs:.1f}[a]",
                   "-map", "[a]", "-c:a", "aac", "-b:a", "128k", str(out)]
        elif inputs:
            cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(inputs[0]), "-c:a", "aac", "-b:a", "96k", str(out)]
        ok = bool(cmd) and subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW).returncode == 0 \
            and out.exists()
        if ok:
            msg = f"נשמר:\n{out.name}"
            for p in inputs:
                p.unlink(missing_ok=True)
        else:
            msg = f"השמירה נכשלה. הקבצים הגולמיים ב:\n{workdir}"
        if rec.errors:
            msg += "\n" + "\n".join(rec.errors)
        LOCK.unlink(missing_ok=True)
        status.config(text=msg, fg="#2c3e50" if ok else "#c0392b", font=("Segoe UI", 9), wraplength=240)
        btn.config(text="סגירה", state="normal", command=root.destroy)

    btn = tk.Button(root, text="עצירה ושמירה", font=("Segoe UI", 11), command=finish, width=16)
    btn.pack()
    root.protocol("WM_DELETE_WINDOW", lambda: (finish(), root.after(1500, root.destroy)))  # X also saves
    tick()
    root.mainloop()
    LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    if "--install-shortcut" in sys.argv:
        install_shortcut()
    else:
        main()
