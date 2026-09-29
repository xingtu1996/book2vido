"""环境装配：按 config 造出 LLM / TTS / 画面三个 provider，打包成一次运行共享的 `Stage`。

为什么单独成模块（AC-16 顺带暴露的结构问题）：这是「造对象」，不是「编排流程」。
pipeline 只该关心"先谁后谁"，不该同时负责"用哪个 provider、怎么 new"——两件事
塞在一个文件里，文件就一定超行数。

provider 无状态、构造一次即可跨章复用，`run_book` 的章节循环依赖这一点（T2V-002）。
"""
from __future__ import annotations

from dataclasses import dataclass

from . import narrator, scriptwriter, visualizer


@dataclass
class Stage:
    """一次运行共享的环节对象。"""

    cfg: dict
    llm: object
    tts: object
    viz: object


def build(cfg: dict, think: bool | None = None) -> Stage:
    """按 `cfg` 造 provider。`think` 传 None 时用配置值，传 bool 则覆盖配置。"""
    if think is not None:
        cfg["llm"]["think"] = think
    llm = (scriptwriter.OllamaProvider(cfg["llm"]["model"], cfg["llm"]["base_url"],
                                       think=cfg["llm"].get("think", True),
                                       # 提示词资产（T2V-007）：None = prompts/<name>.md。
                                       # 指到别处即可试不同提示词，不必改代码。
                                       prompt_file=cfg["llm"].get("prompt_file"))
           if cfg["llm"]["provider"] == "ollama" else scriptwriter.RuleFallbackProvider())
    tts = (narrator.EdgeTTSProvider(cfg["tts"]["voice"]) if cfg["tts"]["provider"] == "edge"
           else narrator.SayProvider())
    return Stage(cfg, llm, tts, visualizer.PillowProvider(**cfg["visual"]))
