"""口播稿 / 分镜生成。LLM 可插拔：Ollama（本地）| Rule（无模型降级）。

这是链路上唯一依赖 AI 的环节。MVP 默认 rule 降级，保证没装模型也能跑通端到端。

**提示词不在这里**（T2V-007）：它是资产，住在 `prompts/scriptwriter.md` ——
逐条约束旁边写着"为什么这么写、改它会怎样"，有版本号可追溯，改它不需要动 Python。
本模块只负责「加载 → 渲染 → 调用 → 解析」，是**管道**不是**内容**。
"""
import re
import json
import urllib.request

from . import promptlib
from .concepts import CONCEPTS
from .models import Scene

# `Scene` 的契约已上移到 `models.py`（依赖图塔尖，T2V-002）：
# 它是「生成 → 画面 → 配音」三方对齐的契约，不该由生成层持有。
# 但 `tools/probe_perf.py` 等外部脚本仍从本模块导入，故保留 re-export——本项目回滚条件是「只增不删」。
__all__ = ["Scene", "LLMProvider", "RuleFallbackProvider", "OllamaProvider"]


class LLMProvider:
    """provider 的公共契约。

    `prompt` / `prompt_fingerprint` 是 T2V-007 加的，两者分工不同：
      - `prompt`            → 把「这版分镜出自哪版提示词」记进 `script.json`（人工追溯）
      - `prompt_fingerprint`→ 拼进缓存键，**改提示词自动失效**（不靠人记得升版本号）

    降级路径（rule）不用模型、没有提示词，故两者取基类默认值（空）。
    """

    prompt: "promptlib.Prompt | None" = None
    prompt_fingerprint: str = ""

    def script(self, text: str, max_n: int) -> list[Scene]:
        raise NotImplementedError


class RuleFallbackProvider(LLMProvider):
    """无本地模型时的降级：按标点切句，取前 N 句做口播。

    ⚠️ 它**不读提示词**——所以改提示词不会影响它的产出（也就不会让它缓存失效）。
    这是有意的：降级路径的目标是"没模型也能出片"，不是"复刻模型效果"。
    """

    def script(self, text: str, max_n: int = 12) -> list[Scene]:
        sents = re.split(r"(?<=[。！？])", text)
        sents = [s.strip() for s in sents if s.strip()]
        out: list[Scene] = []
        for s in sents:
            if len(s) < 6:  # 跳过太短碎片
                continue
            out.append(Scene(s, self._keyword(s)))
            if len(out) >= max_n:
                break
        return out

    def _keyword(self, s: str) -> str:
        clean = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", s)
        return clean[:4] if clean else "要点"


class OllamaProvider(LLMProvider):
    """本地 Ollama（Qwen3-8B 等），零公司资源。失败自动回退 rule。

    think 参数必须显式传：
      qwen3 系模型在 Ollama 里「思考模式」默认是开的。本机实测（M1 Pro 16GB /
      qwen3:8b Q4_K_M）同一口播稿任务 —— think=true 36s / 568 tok，
      think=false 18s / 152 tok。速度差 2 倍，但句子质量明显下降
      （思考版：「六层框架散在 6 个工具里」；非思考版：「用户上手要查六仓」）。
      所以：口播稿主链路默认开启思考（质量优先），批量初筛可 --fast 关闭。
      不显式声明 = 依赖模型模板隐式默认，换模型/版本会静默改行为。

    ⚠️ 换模型时要**同时**看提示词：不同模型对同一段提示词的服从度不同
    （尤其"严格 ≤20 字"这类硬约束）。改法见 `prompts/scriptwriter.md` 的「模型适配记录」。
    """

    def __init__(self, model: str = "qwen3:8b", base_url: str = "http://localhost:11434",
                 think: bool = True, prompt_file: str | None = None,
                 prompt_name: str = "scriptwriter"):
        self.model = model
        self.url = base_url.rstrip("/") + "/api/generate"
        self.think = think
        # 提示词只加载一次（provider 一次运行只造一个、跨章复用）。
        # 读不到就**当场报错**，不退回任何内置文本：静默降级会让人以为"我改的生效了"，
        # 而真相是改的那份根本没被读到（本项目的头号缺陷类型）。
        self.prompt = promptlib.load(prompt_name, prompt_file)
        # 受控概念清单来自 concepts.py（领域资产），**不是**从 icons 借用 ——
        # 生成层与图标资产层之间没有依赖（档 1 整改，见 doc/17 §S-2）。
        self._concepts = "、".join(CONCEPTS.keys())
        # 缓存键因子 = 模板 + concept 清单。**不含章节文本**：那已在 script_key 里，
        # 且本指纹必须能在"调模型之前"算出来（否则没法先查缓存再决定要不要跑模型）。
        self.prompt_fingerprint = self.prompt.fingerprint(concept_list=self._concepts)

    def script(self, text: str, max_n: int = 12) -> list[Scene]:
        # 取料（跳版权/目录、按章切片、截断）已上移到调用方——本函数只做「文本 → 分镜」一件事。
        # 理由：①「整本取料」与「按章取料」才能共用同一个 provider（T2V-002）
        #       ② 不再有「provider 偷偷吃掉 N 字之外的正文」这种隐形行为
        prompt = self.prompt.render(max_n=max_n, concept_list=self._concepts, chunk=text)
        payload = {"model": self.model, "prompt": prompt, "stream": False,
                   "think": self.think}
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            raw = urllib.request.urlopen(req, timeout=240).read().decode()
            resp_text = json.loads(raw).get("response", "")
            m = re.search(r"\[.*\]", resp_text, re.DOTALL)
            arr = json.loads(m.group()) if m else []
            scenes = [Scene(str(a.get("text", "")).strip(),
                            str(a.get("keyword", "")).strip(),
                            str(a.get("concept", "")).strip())
                      for a in arr if isinstance(a, dict)]
            scenes = [s for s in scenes if 2 <= len(s.text) <= 60][:max_n]
            return scenes or RuleFallbackProvider().script(text, max_n)
        except Exception as e:
            import sys
            print(f"[warn] Ollama 调用失败，回退 rule 降级：{e}", file=sys.stderr)
            return RuleFallbackProvider().script(text, max_n)
