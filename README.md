# mcp-sc

SuperCollider ワークフロー用 **MCP サーバー (Python)**。

music-json (show-builder repo) を読み、**SuperCollider NRT (recordNRT)** で
WAV レンダリングする。MCP (JSON-RPC 2.0 over stdio) として動作するので、
opencode / Claude 等の MCP クライアントから `music_render` 等を呼べる。

## 構成

```
mcp-sc/
├── lib/mcp_sc.py            # MCP サーバー本体 (Python)
├── plugins/
│   ├── base.py              # PyPer 由来の Entry/FilterPlugin ベース
│   ├── mcp_base.py          # MCP JSON-RPC フレームワーク
│   ├── sc_bridge.py         # music-json → SuperCollider NRT bridge
│   └── langchain_music.py   # LangChain で music-json を生成/修正 (任意)
└── recipe/                  # YAML 指示ファイル
```

## 使い方（ローカル）

```bash
PYTHONPATH=. python3 lib/mcp_sc.py
```

JSON-RPC リクエストを stdio に流す:

```json
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"music_score_preview","arguments":{"music":"music/lo-fi-radio-amin.json"}}}
```

## MCP ツール

| tool | 説明 |
| --- | --- |
| `music_render` | music-json → SC NRT → WAV |
| `music_generate` | LangChain で音楽理論から music-json 生成（`LLM_PROVIDER` 参照） |
| `music_score_preview` | music-json → sclang Score テキスト確認（レンダリングなし） |
| `music_workflow_yaml` | YAML 指示ファイルからワークフロー実行 |

## SuperCollider NRT

- `sclang` / `scsynth` が必要: `sudo apt install supercollider`
- NRT なので音声デバイス不要（WSL / CI で動く設計）
- レンダリングは `recordNRT` の action 完了を待って WAV 書き出し

## LangChain (任意)

- 環境変数: `LLM_PROVIDER`（sakura / openai / anthropic / google_genai）
- `SAKURA_API_KEY` があればデフォルト `zundamon-qwen3-8b` で作曲

## show-builder repo

music-json スキーマ等は **show-builder repo**（`~/repo/show-builder`）が
ソース・オブ・トゥルース。