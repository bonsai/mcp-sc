#!/usr/bin/env python3
"""
MCP SC Music Server — SuperCollider ワークフロー用 MCP プラグイン (Python)

music-json を「YAML 指示」で読み、LangChain で音楽理論から生成/修正し、
SuperCollider NRT で WAV 化する。JSON-RPC (stdio) MCP サーバー。

Tools:
  - music_render          : music-json → SC NRT → WAV（show-builder repo の JSON 指定）
  - music_generate        : LangChain でプロンプトから music-json 生成
  - music_score_preview   : music-json → sclang Score テキスト（レンダリングなし）
  - music_workflow_yaml   : YAML 指示ファイルからワークフロー実行
"""
import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from plugins.mcp_base import MCPServer
from plugins.sc_bridge import music_json_to_bars, chord_midi

ROOT_DIR = Path(__file__).resolve().parents[1]
DESIGN_DIR = Path(os.environ.get("SG_DESIGN_HOME", Path.home() / "repo" / "show-builder"))


def _load_music(path: Path) -> dict:
    p = path.expanduser()
    if not p.is_absolute():
        p = DESIGN_DIR / p
    if not p.exists():
        raise FileNotFoundError(f"music-json not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def _score_text(music: dict, out_wav: str) -> str:
    from plugins.sc_bridge import SYNTHDEF_SC, chord_midi, music_json_to_bars
    rows = music_json_to_bars(music)
    events: list[str] = []
    start = 0.0
    for i, (root, quality, secs, _voice) in enumerate(rows):
        midi = chord_midi(root, quality)
        dur = max(0.1, secs - 0.1)
        for note in midi:
            freq = 440.0 * 2 ** ((note - 69) / 12)
            events.append(
                f"[{start:0.3f}, [\\s_new, \\poc, {i * 100 + note}, 0, 0, "
                f"\\freq, {freq:.2f}, \\dur, {dur:0.3f}, \\amp, 0.15, \\pan, 0]]"
            )
        start += secs
    score_body = ",\n  ".join(events)
    out_osc = out_wav.replace(".wav", ".osc") if out_wav.endswith(".wav") else "/tmp/bgm.osc"
    return (
        f"// BGM NRT Score (music-json via mcp-sc)\n"
        f"(\n{SYNTHDEF_SC}\n"
        f"var score = Score([\n"
        f"  [0.0, [\\d_recv, def.asBytes]],\n"
        f"  {score_body},\n"
        f"  [{start + 0.1:0.3f}, [\\c_set, 0, 0]]\n"
        f"]);\n"
        f"score.writeOSCFile(\"{out_osc}\");\n"
        f"0.exit;\n"
        f")\n"
    )


def _render_sc(music: dict, out_wav: Path) -> str:
    # sc_bridge 経由で writeOSCFile → scsynth -N (2段階) 実行
    from plugins.sc_bridge import _render_events, chord_midi, music_json_to_bars
    rows = music_json_to_bars(music)
    events: list[str] = []
    start = 0.0
    end_t = start
    for i, (root, quality, secs, _voice) in enumerate(rows):
        midi = chord_midi(root, quality)
        dur = max(0.1, secs - 0.1)
        for note in midi:
            events.append(
                f"[{start:0.3f}, [\\s_new, \\poc, {i * 100 + note}, 0, 0, "
                f"\\freq, {440.0 * 2 ** ((note - 69) / 12):.2f}, \\dur, {dur:0.3f}, "
                f"\\amp, 0.15, \\pan, 0]]"
            )
        start += secs
        end_t = start
    _render_events(events, out_wav,
                   sclang=os.environ.get("SCLANG", "sclang"),
                   scsynth=os.environ.get("SCSYNTH", "scsynth"),
                   end_t=end_t + 0.1)
    return f"rendered: {out_wav} ({out_wav.stat().st_size} bytes)"


def main():
    server = MCPServer(name="pyper-mcp-music", version="0.1.0")

    def tool_music_render(music: str = "music/lo-fi-radio-amin.json",
                          out: str = "out/bgm/bgm.wav") -> str:
        """music-json を SC NRT で WAV レンダリング（design repo 内相対 path）"""
        music_dict = _load_music(Path(music))
        return _render_sc(music_dict, Path(out))

    def tool_music_generate(prompt: str,
                            model: str = "zundamon-qwen3-8b") -> str:
        """LangChain で音楽理論から music-json を生成"""
        from plugins.langchain_music import Plugin
        plugin = Plugin({"model": model, "prompt": prompt})
        entry = type("E", (), {"metadata": {}})()
        out = next(plugin.execute(iter([entry])))
        return json.dumps(out.metadata["music"], ensure_ascii=False, indent=2)

    def tool_music_score_preview(music: str = "music/lo-fi-radio-amin.json") -> str:
        """music-json → sclang Score テキストを表示（レンダリングなし）"""
        music_dict = _load_music(Path(music))
        return _score_text(music_dict, "/tmp/bgm.wav")

    def tool_music_workflow_yaml(yaml_file: str) -> str:
        """YAML 指示ファイルからワークフロー実行。recipe/music.yaml 形式"""
        import yaml
        cfg_path = Path(yaml_file).expanduser()
        if not cfg_path.is_absolute():
            cfg_path = ROOT_DIR / cfg_path
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        pipeline = cfg.get("pipeline", cfg)
        results = []
        # subscription: music-json 読み込み
        music = None
        for sub_cfg in pipeline.get("subscription", []):
            if sub_cfg["module"] == "subscription.music_json.Plugin":
                music = _load_music(Path(sub_cfg["config"].get("path", "music/lo-fi-radio-amin.json")))
        if music is None:
            raise ValueError("no subscription.music_json in yaml")
        # filter: langchain
        from plugins.langchain_music import Plugin
        for flt in pipeline.get("filters", []):
            if flt["module"] == "filter.langchain_music.Plugin":
                plugin = Plugin({"model": flt["config"].get("model", "zundamon-qwen3-8b"),
                                 "prompt": flt["config"].get("prompt", "")})
                entry = type("E", (), {"metadata": {"music": music}})()
                next(plugin.execute(iter([entry])))
                music = entry.metadata["music"]
            results.append(f"filter: {flt['module']}")
        # publish: SC NRT
        for pub in pipeline.get("publish", []):
            if pub["module"] == "publish.supercollider.Plugin":
                out_dir = Path(pub["config"].get("out_dir", "out/bgm"))
                out_name = pub["config"].get("out_name", "bgm.wav")
                results.append(_render_sc(music, out_dir / out_name))
            else:
                results.append(f"publish: {pub['module']}")
        return "\n".join(results)

    server.register_tool(
        "music_render",
        "music-json を SuperCollider NRT で WAV レンダリング",
        {"properties": {
            "music": {"type": "string", "description": "design repo 内 music-json path"},
            "out": {"type": "string", "description": "出力 WAV path"}},
         "required": []},
        tool_music_render,
    )
    server.register_tool(
        "music_generate",
        "LangChain で音楽理論から music-json を生成",
        {"properties": {
            "prompt": {"type": "string", "description": "作曲リクエスト"},
            "model": {"type": "string", "description": "LLM モデル名"}},
         "required": ["prompt"]},
        tool_music_generate,
    )
    server.register_tool(
        "music_score_preview",
        "music-json → sclang Score テキスト確認",
        {"properties": {
            "music": {"type": "string", "description": "design repo 内 music-json path"}},
         "required": []},
        tool_music_score_preview,
    )
    server.register_tool(
        "music_workflow_yaml",
        "YAML 指示ファイルから音楽ワークフロー実行",
        {"properties": {
            "yaml_file": {"type": "string", "description": "recipe YAML の path"}},
         "required": ["yaml_file"]},
        tool_music_workflow_yaml,
    )

    server.run()


if __name__ == "__main__":
    main()