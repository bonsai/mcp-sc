# src/plugins/filter/langchain_music.py

"""
Filter plugin: LangChain で音楽理論から music-json を生成/修正する。

PyPer (Plagger の Python 版) のフィルタとして動作する。
Entry.metadata["music"] があればそれを踏まえて LLM が修正し、
なければ条件から新規生成する。結果は metadata["music"] に返す。
"""

import json
import logging
import os
from typing import Dict, Any, Iterator

from .base import Entry, FilterPlugin

logger = logging.getLogger(__name__)

MUSIC_JSON_SCHEMA_HINT = """あなたは音楽理論に詳しい作曲家です。
指定された条件で music-json を生成してください。以下のスキーマに従ってください。

{
  "$schema": "music-json.schema.json",
  "title": "曲名",
  "tempo": 72,
  "key": "A",
  "scale": "minor",
  "instruments": [
    { "id": "pad",  "synth": "saw",  "amp": 0.12 },
    { "id": "bass", "synth": "sine", "amp": 0.20 }
  ],
  "bars": [
    { "bar": 1, "chord": { "root": "A", "quality": "min",  "beats": 4 }, "voice": ["pad", "bass"] }
  ],
  "form": { "intro": 0, "loop_bars": [1], "outro": 0, "total_seconds": 60 }
}

ルール:
- quality は maj / min / maj7 / min7 / 7 / sus4 / dim / aug のいずれか
- コード進行は音楽理論的に自然なもの（ii-V-I など）
- ルート音名は C, C#, Db, D, ... B のいずれか
- reply は JSON のみ。マークダウンや説明は不要。"""


class Plugin(FilterPlugin):
    name = "filter.langchain_music.Plugin"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_name = self.config.get("model", "zundamon-qwen3-8b")
        self.prompt = self.config.get("prompt", "lo-fi 深夜ラジオ BGM。A minor、72 BPM、60秒")
        self.chain = self._build_chain()

    def _build_chain(self):
        from langchain_core.output_parsers import JsonOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        provider = os.environ.get("LLM_PROVIDER", "sakura").lower()
        if provider == "sakura":
            from langchain_openai import ChatOpenAI
            model = ChatOpenAI(
                model=self.model_name,
                base_url="https://api.ai.sakura.ad.jp/v1",
                api_key=os.environ.get("SAKURA_API_KEY"),
                temperature=0.7,
            )
        elif provider == "openai":
            from langchain_openai import ChatOpenAI
            model = ChatOpenAI(model=self.model_name, temperature=0.7)
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            model = ChatAnthropic(model=self.model_name, temperature=0.7)
        elif provider == "google_genai":
            from langchain_google_genai import ChatGoogleGenerativeAI
            model = ChatGoogleGenerativeAI(model=self.model_name, temperature=0.7)
        else:
            raise ValueError(f"unsupported LLM_PROVIDER: {provider}")

        prompt = ChatPromptTemplate.from_messages(
            [("system", MUSIC_JSON_SCHEMA_HINT), ("human", "{request}")]
        )
        return prompt | model | JsonOutputParser()

    def execute(self, entries: Iterator[Entry]) -> Iterator[Entry]:
        for entry in entries:
            music = (entry.metadata or {}).get("music")
            req = self.prompt
            if music:
                req = (
                    "以下の既存 music-json を踏まえて条件に合わせて修正し、"
                    "同じスキーマで出力してください。\n"
                    + json.dumps(music, ensure_ascii=False)
                    + "\n\n修正条件: " + self.prompt
                )
            result = self.chain.invoke({"request": req})
            entry.metadata["music"] = result
            yield entry