#!/usr/bin/env python3
"""环境体检：断言「能不能开工」——Ollama 在不在、模型在不在、FFmpeg 能不能用。

为什么需要它（doc/26 的处方）
──────────────────────────────────
环境类问题有一个共同特征：**在交互式终端里一切正常，换到自动化/Agent/cron 就全挂**。
2026-09-19 实测：交互 shell 里 `ollama` / `ffmpeg` / `rsvg-convert` 都能用，
但在非登录非交互 shell 里**三个全部 `command not found`** ——
因为它们在 Homebrew 前缀（`/opt/homebrew/bin`）下，而该前缀不进非交互 shell 的 PATH。

后果是**静默的**：文档里写 `ollama pull xxx`，自动化场景拿到的是退出码 127，
报错信息跟「模型没装」长得一模一样，排查方向直接跑偏。

So 本脚本所有二进制定位都走 `src/book2vido/binpaths.py`（环境变量 → 随包 vendor →
包管理器路径 → PATH 四级），**不在测试里重建第二套查找逻辑**；
本文件只做断言，并把「缺了该怎么补」说清楚。

断言清单（必选项任一失败 → 退出码 1；可选项只 WARN）
────────────────────────────────────────────────
  必选 A. Ollama 二进制存在（按 PATH → Homebrew 前缀 → 常见安装位 依次找）
  必选 B. Ollama 服务在跑（HTTP `base_url/api/tags` 有响应）
  必选 C. `config.yaml` 的 `llm.model` **确实已拉取**（最容易踩：config 写了 8b，机器上是 4b）
  必选 D. FFmpeg 可用（并执行 `-version`，防“文件在但依赖 dylib 缺失”）
  必选 E. 分镜提示词资产在位（`prompt_file`，默认 `prompts/scriptwriter.md`）
  可选 F. rsvg-convert（图标渲染；缺失会自动降级为「关键词首字大字」版式，不中断出片）
  信息 G. 打印本机已拉取的全部模型（不断言，只让人看见家底）

用法：
    python tests/verify_env.py                    # 体检（改动环境 / 换机器 / 换 harness 时）
    python tests/verify_env.py --config config.yaml
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]

# ⚠️ **二进制定位复用 `src/book2vido/binpaths.py`，本文件不自己实现第二套。**
# 为什么：binpaths 已有「环境变量 → 随包 vendor → 常见包管理器路径 → PATH」四级解析，
# 是**打包分发 / 跨机器 / CI 覆盖**的唯一实现。在这里再写一遍 = 多一个会各自漂移的副本
# （铁律八「不为性能牺牲可读性」的反面：也不为便利制造重复）。
# 本文件只负责**断言与解释**：这些二进制解析到了哪，缺了该怎么补。
sys.path.insert(0, str(ROOT / "src"))
from book2vido.binpaths import resolve as resolve_bin  # noqa: E402

# 体检目标：可执行文件名 → 缺失时的补救说明（binpaths 只管解析，解释留在这里）
TOOLS = {
    "ollama": "brew install ollama   （或 https://ollama.com 下载 .app）",
    "ffmpeg": "brew install ffmpeg   （注意：分发时不能用 brew 版，它绑 dylib，见 doc/12）",
    "rsvg-convert": "brew install librsvg  （图标 SVG→PNG；缺失时图标层自动降级，不中断出片）",
}


def http_json(url: str, timeout: float = 3.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="环境体检（不依赖 PATH）")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = ap.parse_args()

    fails: list[str] = []
    warns: list[str] = []

    # ── A. 二进制在位 ────────────────────────────────────────────────
    print("A 运行时二进制（按绝对路径找，不依赖 PATH）")
    paths: dict[str, str | None] = {}
    for tool, hint in TOOLS.items():
        p = resolve_bin(tool)          # ← 复用 binpaths，不在这里重建查找逻辑
        paths[tool] = p
        if p:
            print(f"   ✓ {tool:<13} {p}")
        elif tool == "rsvg-convert":
            warns.append(f"{tool} 缺失 → {hint}")
            print(f"   ⚠ {tool:<13} 未找到（可选，图标层会降级）")
        else:
            fails.append(f"{tool} 未找到 → {hint}")
            print(f"   ✗ {tool:<13} 未找到")
    print()

    # ── 读 config ───────────────────────────────────────────────────
    cfg_path = pathlib.Path(args.config)
    model = "qwen3:8b"
    base_url = "http://localhost:11434"
    prompt_file: str | None = None
    if cfg_path.exists():
        try:
            import yaml  # 只在配置存在时才需要；项目依赖里已有（requirements.txt）
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            llm = raw.get("llm") or {}
            model = llm.get("model", model)
            base_url = llm.get("base_url", base_url)
            prompt_file = llm.get("prompt_file")
        except Exception as exc:                       # 极端情况：yaml 坏了
            fails.append(f"config.yaml 无法解析：{exc}")
    else:
        warns.append(f"未找到 {cfg_path.name} → 将按默认值体检（{model}）")

    # ── B. 服务在跑 + C. 目标模型已拉取 + G. 家底清单 ───────────────
    print("B Ollama 服务")
    tags = http_json(f"{base_url}/api/tags")
    if tags is None:
        fails.append(
            f"Ollama 服务未响应（{base_url}）。"
            f"启动：{'/opt/homebrew/bin/ollama serve' if not paths['ollama'] else paths['ollama'] + ' serve'}"
        )
        print(f"   ✗ 未响应 {base_url}")
    else:
        print(f"   ✓ 在跑 {base_url}")
        models = tags.get("models", [])
        print()
        print("C 目标模型是否在位")
        names = [m.get("name", "") for m in models]
        if model in names or f"{model}:latest" in names:
            hit = next(m for m in models if m.get("name") in (model, f"{model}:latest"))
            size_gb = hit.get("size", 0) / 1e9
            print(f"   ✓ {model}（{size_gb:.1f} GB · {hit.get('details', {}).get('parameter_size', '?')} 参数）")
        else:
            fails.append(
                f"config 里写的是 {model}，但本机没有。"
                f"拉取：{paths['ollama'] or 'ollama'} pull {model}"
            )
            print(f"   ✗ {model} 不在本机")
        print()
        print("G 本机已拉取的模型（家底）")
        if not models:
            print("   （一个都没有）")
        for m in models:
            size_gb = m.get("size", 0) / 1e9
            print(f"   · {m.get('name', '?'):<20} {size_gb:>5.1f} GB")
        if len(models) <= 1:
            warns.append(
                "本机只有一个模型 → 没有降级备选。"
                "它一旦被删/损坏，链路只能退到 rule（规则截取，质量低）。"
                "建议再拉一个小模型做备选（16 GB 机器拉 4b 级，别上 14b）。"
            )
    print()

    # ── D. FFmpeg 真能跑 ────────────────────────────────────────────
    print("D FFmpeg 可执行")
    ffmpeg = paths.get("ffmpeg")
    if ffmpeg:
        try:
            out = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=10)
            first = (out.stdout or "").splitlines()[0] if out.stdout else "（无输出）"
            if out.returncode == 0:
                print(f"   ✓ {first}")
            else:
                fails.append(f"ffmpeg 存在但执行失败（退出码 {out.returncode}）")
                print(f"   ✗ 执行失败：{out.stderr[:200]}")
        except Exception as exc:
            fails.append(f"ffmpeg 执行异常：{exc}")
            print(f"   ✗ {exc}")
    else:
        print("   ✗ 跳过（二进制未找到，见 A）")
    print()

    # ── E. 提示词资产在位 ───────────────────────────────────────────
    print("E 分镜提示词资产")
    prompt_path = pathlib.Path(prompt_file) if prompt_file else ROOT / "prompts" / "scriptwriter.md"
    if prompt_path.exists():
        print(f"   ✓ {prompt_path}")
    else:
        fails.append(f"提示词资产不存在：{prompt_path}（分镜是唯一用模型的环节，缺它必然降级 rule）")
        print(f"   ✗ {prompt_path}")
    print()

    # ── 结论 ────────────────────────────────────────────────────────
    for w in warns:
        print(f"⚠  {w}")
    if warns:
        print()

    if fails:
        print("✗ 环境体检未通过，阻塞项：")
        for f in fails:
            print(f"   · {f}")
        print("\n修复后重跑：python tests/verify_env.py")
        return 1

    print("✓ 环境体检通过 —— 可以开工")
    print("（本机实况的完整事实源：doc/26-本机环境实况.md）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
