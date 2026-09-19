"""BGM: SuperCollider NRT レンダリングで WAV を生成する。

SuperCollider を音声デバイス無し（ノンリアルタイム）で動かし、
コード進行から BGM を WAV 書き出しする。設計段階の起動器。

実装方針:
- sclang で Score を組み、scsynth に NRT レンダリングさせる（scsynth -N）。
- Go 側 plego プラグイン（Audio::BGM）から呼び出す想定。ここでは CLI で叩く。

依存: `sclang` / `scsynth` が PATH にあること（apt の supercollider パッケージ）。
"""

import os
import subprocess
import tempfile
from pathlib import Path

SCLANG = os.environ.get("SCLANG", "sclang")
PITCH_CLASS = ["c", "cs", "d", "ef", "e", "f", "fs", "g", "af", "a", "bf", "b"]


def chord_midi(root: int, quality: str) -> list[int]:
    """ルート音（MIDI note）とクオリティから構成音 MIDI を返す。"""
    intervals = {
        "maj": [0, 4, 7],
        "min": [0, 3, 7],
        "maj7": [0, 4, 7, 11],
        "min7": [0, 3, 7, 10],
        "sus4": [0, 5, 7],
        "dim": [0, 3, 6],
        "aug": [0, 4, 8],
    }.get(quality, [0, 4, 7])
    return [root + i for i in intervals]


def sclang_score(chords: list[tuple[int, str]], seconds_per_chord: float, out_wav: str) -> str:
    """コード進行から sclang の NRT Score スクリプトを生成する。"""
    events: list[str] = []
    start = 0.0
    for i, (root, quality) in enumerate(chords):
        midi = chord_midi(root, quality)
        dur = seconds_per_chord - 0.15 if seconds_per_chord > 0.25 else min(seconds_per_chord * 0.9, 2.0)
        for note in midi:
            events.append(
                f"[{start:0.3f}, [\\s_new, \\default, {i * 100 + note}, 0, 0, "
                f"\\freq, {440.0 * 2 ** ((note - 69) / 12):.2f}, \\dur, {dur:0.3f}, "
                f"\\amp, 0.15, \\pan, 0]]"
            )
        start += seconds_per_chord
    score_body = ",\n  ".join(events)
    return f"""// BGM NRT Score (sound-effect-generator)
(Score [
  {score_body}
]).recordNRT("{out_wav}");
quit;
"""


def render_bgm(
    chords: list[tuple[int, str]],
    out_wav: Path,
    seconds_per_chord: float = 2.0,
    *,
    sclang: str = SCLANG,
) -> Path:
    """コード進行を SuperCollider NRT で WAV レンダリングする。

    chords: [(root_midi, "maj|min|maj7|min7|sus4|dim|aug"), ...]
    """
    import shutil
    if shutil.which(sclang) is None:
        raise RuntimeError(
            f"{sclang} not found. Install supercollider:  sudo apt install supercollider"
        )
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "bgm.scd"
        script.write_text(
            sclang_score(chords, seconds_per_chord, str(out_wav)),
            encoding="utf-8",
        )
        subprocess.run(
            [sclang, "-d", str(tmp), str(script)],
            check=True,
            capture_output=True,
            text=True,
        )
    if not out_wav.exists():
        raise RuntimeError(f"NRT render produced no output: {out_wav}")
    return out_wav


NOTE_TO_MIDI = {
    "c": 0, "cs": 1, "db": 1, "d": 2, "ds": 3, "eb": 3, "e": 4, "ef": 4,
    "f": 5, "fs": 6, "gb": 6, "g": 7, "gs": 8, "ab": 8, "a": 9, "as": 10,
    "bb": 10, "b": 11,
}
SCALE_SEMITONES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
}


def music_json_to_bars(music: dict) -> list[tuple[int, str, float, list[str]]]:
    """音楽JSON → [(root_midi, quality, seconds, voice_ids), ...]"""
    tempo = music.get("tempo", 72)
    key = music.get("key", "A").lower().replace("♭", "b").replace("♯", "s")
    scale = music.get("scale", "minor")
    form = music.get("form", {})
    total_seconds = float(form.get("total_seconds", 60))
    intro = form.get("intro", 0)
    outro = form.get("outro", 0)
    loop_bars = form.get("loop_bars", [b["bar"] for b in music.get("bars", [])])
    bars_by_num = {b["bar"]: b for b in music.get("bars", [])}

    key_root = NOTE_TO_MIDI[key]
    scale_tones = SCALE_SEMITONES.get(scale, SCALE_SEMITONES["minor"])
    beat_sec = 60.0 / tempo

    sequence: list[tuple[int, str, float, list[str]]] = []
    used: list[int] = []
    periods = []
    if intro:
        periods += [("intro", bars_by_num.get(intro, music["bars"][0]))] if intro in bars_by_num else []
    for bnum in loop_bars:
        if bnum in bars_by_num:
            periods.append(("loop", bars_by_num[bnum]))
    if outro and outro in bars_by_num:
        periods.append(("outro", bars_by_num[outro]))

    # 尺に収まるまでループ: intro + loop巴 + outro
    available = []
    if intro in bars_by_num:
        available.append(("intro", bars_by_num[intro]))
    for bnum in loop_bars:
        if bnum in bars_by_num:
            available.append(("loop", bars_by_num[bnum]))
    if outro in bars_by_num:
        available.append(("outro", bars_by_num[outro]))

    total_beats = sum(b.get("chord", {}).get("beats", 4) for _, b in available)
    full_cycle = total_beats * beat_sec
    cycles = max(1, int(total_seconds / full_cycle)) if full_cycle else 1
    t = 0.0
    for _ in range(cycles):
        for label, bar in available:
            chord = bar["chord"]
            qual = chord.get("quality", "maj")
            beats = chord.get("beats", 4)
            deg = (_resolve_degree(chord.get("root"), key_root, scale_tones))
            root = deg
            secs = beats * beat_sec
            if t + secs > total_seconds:
                secs = total_seconds - t
            if secs > 0.05:
                sequence.append((root, qual, round(secs, 3), bar.get("voice", [])))
                t += secs
    return sequence


def _resolve_degree(root_spec, key_root: int, scale_tones: list[int]) -> int:
    """root を 'A' 等の音名または 'I' 'iv' 等の度数から MIDI に解決する。"""
    raw = str(root_spec).strip()
    deg_roman = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6,
                 "I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6}
    if raw in deg_roman:
        return key_root + scale_tones[deg_roman[raw]] + 12  # オクターブ上げて安定域
    base = NOTE_TO_MIDI.get(raw.lower().replace("♭", "b").replace("♯", "s"))
    if base is None:
        raise ValueError(f"unknown root: {root_spec!r}")
    while base < key_root + 12:
        base += 12
    return base


def render_bgm_json(music_path: Path, out_wav: Path, *, sclang: str = SCLANG) -> Path:
    """音楽JSON を読み、SuperCollider NRT で WAV レンダリングする。

    music_json_to_bars は (root, quality, seconds, voice) を返すため、
    可変長の chords を直接 sclang_score に流す。
    """
    import json
    music = json.loads(Path(music_path).read_text(encoding="utf-8"))
    rows = music_json_to_bars(music)
    events: list[str] = []
    start = 0.0
    for i, (root, quality, secs, _voice) in enumerate(rows):
        midi = chord_midi(root, quality)
        dur = max(0.1, secs - 0.1)
        for note in midi:
            events.append(
                f"[{start:0.3f}, [\\s_new, \\default, {i * 100 + note}, 0, 0, "
                f"\\freq, {440.0 * 2 ** ((note - 69) / 12):.2f}, \\dur, {dur:0.3f}, "
                f"\\amp, 0.15, \\pan, 0]]"
            )
        start += secs
    score_body = ",\n  ".join(events)
    script_text = f"""// BGM NRT Score (music-json)
(Score [
  {score_body}
]).recordNRT("{out_wav}");
quit;
"""
    import shutil
    if shutil.which(sclang) is None:
        raise RuntimeError(f"{sclang} not found. Install supercollider:  sudo apt install supercollider")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "bgm.scd"
        script.write_text(script_text, encoding="utf-8")
        subprocess.run([sclang, "-d", str(tmp), str(script)], check=True, capture_output=True, text=True)
    if not out_wav.exists():
        raise RuntimeError(f"NRT render produced no output: {out_wav}")
    return out_wav


if __name__ == "__main__":
    import sys
    progression = [("maj" if q else "maj") for q in sys.argv[2:]] or ["maj", "min", "maj7", "sus4"]
    roots = [60, 57, 62, 60]  # C A D C 的な進行 (MIDI)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/bgm.wav")
    print(render_bgm(list(zip(roots, progression)), out))