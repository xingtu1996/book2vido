"""配置加载：用户 config.yaml 覆盖默认。"""
import yaml
from pathlib import Path

DEFAULT = {
    # think: qwen3 思考模式。显式声明，不依赖模型模板隐式默认（本机实测见 doc/01-llm-local.md）
    # prompt_file: 提示词资产路径（T2V-007）。null = <项目根>/prompts/scriptwriter.md。
    #   提示词是唯一影响「模型行为」的输入，独立成文件 + 带逐条注释，换模型时改它即可。
    "llm": {"provider": "rule", "model": "qwen3:8b", "base_url": "http://localhost:11434",
            "think": True, "prompt_file": None},
    "tts": {"provider": "edge", "voice": "zh-CN-XiaoyiNeural"},
    # theme: ink（深底炭黑红）/ paper（浅底纸白红）/ blue（行途蓝，旧）/ custom（用 accent 覆盖）。
    # 色板 SSoT：`03_运营工具箱/02_排版与设计/行途公众号封面设计规则_V1.md` V1.2（黑红灰）。
    # ⚠️ 改 theme 必须同时确认它进了成片缓存键（cache.video_key）——否则「改了像没改」。
    "visual": {"theme": "ink", "accent": "#056DE8", "font": None, "w": 1080, "h": 1920,
               "icons": True, "icon_dir": None, "icon_size": 430, "allow_network": True},
    # max_chars: 送本地模型的正文上限。4K ctx 是硬约束——超了模型会截断你的输入，
    # 还不如自己按「首/中/尾均匀采样」主动裁（见 segmenter.py）。
    "limits": {"max_sentences": 12, "max_chars": 2500},
    # cache: 三层缓存开关。dir=null → <项目根>/cache（可选产物，删掉即回到无缓存行为）
    "cache": {"enabled": True, "dir": None},
    # concurrency: 只作用于 TTS。**不要用来并发调模型**——Ollama 服务端串行，实测省 5%＝噪声
    # （见 doc/10-目录索引与按需生成.md 探针 2）。
    "concurrency": {"tts_workers": 12, "tts_retry": 2},
}


def load(path=None):
    cfg = {k: dict(v) for k, v in DEFAULT.items()}
    if path and Path(path).exists():
        with open(path, encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg
