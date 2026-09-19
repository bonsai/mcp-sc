# mcp-sc — 型宣言 (Types & Schemes)

MCP サーバーが公開する **ツール型**・**入力スキーマ**・**レンダリングプロトコル** の正。

## MCP ツール

| tool | params (型) | returns (型) |
| --- | --- | --- |
| `music_render` | `music: string`, `out: string` | `string`（`rendered: <path> (<bytes> bytes)` または `Error: ...`） |
| `music_generate` | `prompt: string`, `model: string` | `string`（JSON文字列: music-json） |
| `music_score_preview` | `music: string` | `string`（sclang Score スクリプト） |
| `music_workflow_yaml` | `yaml_file: string` | `string`（結果の結合） |

全ツールの応答は MCP 規約に従い `result.content[0].text: string` に収まる。

## music_render 引数スキーマ（inputSchema 正）

```json
{
  "type": "object",
  "properties": {
    "music": { "type": "string", "description": "music-json の path（絶対 or SG_DESIGN_HOME 相対）" },
    "out":   { "type": "string", "description": "出力 WAV path" }
  },
  "required": []
}
```

## SG_DESIGN_HOME 解決規則

- `SG_DESIGN_HOME` 環境変数があればそれを正とする。
- 無ければ `~/repo/show-builder`。
- `music` 引数が絶対 path ならそのまま。相対なら `SG_DESIGN_HOME / <path>`。

## SC NRT レンダリングプロトコル（2段階）

```
sclang: Score + SynthDef(\poc) → writeOSCFile(score.osc)
scsynth: -N <score.osc> _ <out.wav> 44100 wav int16
```

- SynthDef は必ず Score 先頭に `[0.0, [\d_recv, def.asBytes]]` で埋め込む（`\default` は NRT 不採用）。
- 末尾に `[<end_t>, [\c_set, 0, 0]]` を追加してレンダリング終端を保証。
- 環境変数: `SCLANG`(default `sclang`) / `SCSYNTH`(default `scsynth`)。

## 内部関数型

`plugins/sc_bridge.py`:

| 関数 | シグネチャ |
| --- | --- |
| `chord_midi` | `(root: int, quality: str) -> list[int]` |
| `music_json_to_bars` | `(music: dict) -> list[tuple[int, str, float, list[str]]]` （root_midi, quality, seconds, voice） |
| `render_bgm` | `(chords: list[tuple[int, str]], out_wav: Path, seconds_per_chord: float = 2.0) -> Path` |
| `render_bgm_json` | `(music_path: Path, out_wav: Path) -> Path` |
| `_render_events` | `(events: list[str], out_wav: Path, *, sclang: str, scsynth: str, end_t: float) -> Path` |

## quality → 構成音（interval）スキーム

| quality | semitones |
| --- | --- |
| `maj` | 0,4,7 |
| `min` | 0,3,7 |
| `maj7` | 0,4,7,11 |
| `min7` | 0,3,7,10 |
| `7` | 0,4,7,10 |
| `sus4` | 0,5,7 |
| `dim` | 0,3,6 |
| `aug` | 0,4,8 |

## scale → semitones（root 解決用）

| scale | semitones |
| --- | --- |
| `major` | 0,2,4,5,7,9,11 |
| `minor` | 0,2,3,5,7,8,10 |
| `dorian` | 0,2,3,5,7,9,10 |
| `mixolydian` | 0,2,4,5,7,9,10 |