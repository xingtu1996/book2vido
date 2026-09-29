"""编排：extractor → outline → segmenter → scriptwriter → visualizer → narrator → compositor。

只做编排 + 缓存判断 + 进度打印，**不实现任何环节**（各环节的活在自己的模块里；
"造 provider" 的活也归 `providers.py`，不在这儿）。
三个入口：
  - `run()`         T2V-001 兼容入口：整篇当一章、单文件输出，行为与升级前一致
  - `run_book()`    按章批量：选章 → 每章一条片，章级串行、章内并行
  - `run_chapter()` 单章（被 run_book 复用，也便于外部直接调用）
"""
from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path

from . import cache as cache_mod
from . import compositor, extractor, narrator, outline, providers, segmenter
from .config import load
from .models import Chapter, MediaClip, ScriptDoc, now_stamp


def _stat(out_path, doc: ScriptDoc, t0: float, cache: str) -> dict:
    sec = round(time.time() - t0, 1)
    return {"out": str(out_path), "scenes": len(doc.scenes), "seconds": sec,
            "cost": round(0.03 * sec / 3600 * 0.6, 5),   # M1 ~30W, ¥0.6/kWh
            "cache": cache}


def _produce(ch: Chapter, cfg: dict, text: str, out_path, work, c: cache_mod.Cache,
             stage: providers.Stage, no_cache: bool) -> dict:
    """核心：文本 → 分镜 → 卡片 → 配音 → mp4。缓存判断集中在这里。"""
    out_path, work = Path(out_path), Path(work)
    t0 = time.time()
    use_cache = bool(c.enabled) and not no_cache

    if not text.strip():
        # 不静默出空片：页码区间取不到文本是要让用户看见的事（多为目录页码偏移）
        raise ValueError(f"第 {ch.index} 章「{ch.title}」页码范围 p{ch.start_page}-p{ch.end_page} "
                         f"内无可用文本")

    # ── 下限守卫：料不够就不做，而不是硬编 12 句
    # 上游只挡「空」，挡不住「只有 5 个字」——而「出 N 句」是硬约束，缺口只能靠编。
    # 实测 22 字的「附录D」被出了 12 句同义反复，故这里按「一句话换一句话」拦住。
    # 放在 _produce 而非 run_chapter：短料在三个入口都会靠编凑数，这不是链路差异。
    #
    # ⚠️ 对 T2V-001 兼容入口（`run()`）同样生效。这不违背「语义保持不变」（AC-14）——
    #    它是**内容可行性判断**，正常的长文/整篇素材永远满足；只有「参考文献」这类
    #    一行标题才会被拦，而那种输入在哪个入口都不该出片。
    reason = segmenter.insufficient_reason(text, cfg["limits"]["max_sentences"])
    if reason:
        raise segmenter.InsufficientMaterial(f"第 {ch.index} 章「{ch.title}」{reason}", reason)

    # ── 分镜（最贵，~36s）：命中则跳过 LLM
    # 键里带**提示词指纹**（T2V-007）：改了 prompts/*.md，这里就失配 → 自动重跑模型。
    # 没有它时，改提示词是"改了像没改"（静默命中旧分镜）——提示词是影响分镜内容最直接的因子，
    # 却曾经唯一没进键的那个。
    skey = c.script_key(ch.index, text, cfg, stage.llm.prompt_fingerprint) if use_cache else ""
    doc = c.hit_script(ch.index, skey) if use_cache else None
    if doc is not None:
        print(f"    · 分镜：缓存命中 {len(doc.scenes)} 句（跳过模型，省 ~36s）")
    else:
        # 标签与变量语义必须一一对应：`len(text)` 是**输入正文切片**的字数，
        # 不是分镜的大小（分镜大小 = `len(doc.scenes)`，缓存命中那行打的才是"句数"）。
        # 此前这行写「分镜：N 字」，会被读成"分镜只有 N 字" → 误判切片算错（错题库 L-17）。
        # 同时把**输入上限**打出来：读者一眼能看出这是"被截到上限的输入"，不是全文。
        print(f"    · 正文切片：{len(text)} 字（上限 {cfg['limits']['max_chars']}）"
              f" → 本地模型（think={cfg['llm']['think']}）…")
        pm = stage.llm.prompt          # 降级路径（rule）为 None
        doc = ScriptDoc(ch.index, ch.title,
                        stage.llm.script(text, cfg["limits"]["max_sentences"]),
                        cfg["llm"]["model"], bool(cfg["llm"]["think"]), now_stamp(),
                        prompt_version=(pm.version if pm else ""),
                        prompt_hash=(pm.body_hash if pm else ""))
        if use_cache:
            c.put_script(ch.index, doc, skey)
    if not doc.scenes:
        raise ValueError(f"第 {ch.index} 章未产出任何分镜（素材可能不适合口播化）")

    # ── 成片缓存：键挂**分镜内容指纹**，手改 script.json 会让它失效从而只重渲染
    fp = hashlib.sha256(doc.to_json().encode()).hexdigest()[:16]
    vkey = c.video_key(ch.index, fp, cfg) if use_cache else ""
    if use_cache:
        hit = c.hit_video(ch.index, vkey)
        if hit and hit.exists():
            if hit.resolve() != out_path.resolve():
                shutil.copy2(hit, out_path)     # 缓存落在 ch<NN>.mp4，用户要的可能是别的路径
            print(f"    · 成片：缓存命中 → {out_path}")
            return _stat(out_path, doc, t0, "hit")
    work.mkdir(parents=True, exist_ok=True)

    print(f"    · 画面：渲染 {len(doc.scenes)} 张卡…")
    images = [stage.viz.card(s, i + 1, work) for i, s in enumerate(doc.scenes)]

    items = [(i + 1, s.text, str(work / f"voice_{i + 1}.mp3"))
             for i, s in enumerate(doc.scenes)]
    print(f"    · 配音：{len(items)} 句并发（workers={cfg['concurrency']['tts_workers']}）…")
    try:
        durs = stage.tts.speak_many(items, max_workers=cfg["concurrency"]["tts_workers"])
    except Exception as e:
        # 并发最终失败 → 回退完全本地的 say（断网也能出片，宪法铁律九）。
        # 注意：这是**兜底**不是首选 —— edge 档断网时 12/12 句全失败才走到这里，
        # 实测多花 27.7s。离线场景应直接在 config.yaml 里把 provider 设为 say。
        print(f"[warn] TTS 并发最终失败（{e}）——回退完全本地的 say")
        stage.tts = narrator.SayProvider()
        durs = stage.tts.speak_many(items, max_workers=4)

    clips = [MediaClip(i + 1, images[i], items[i][2], durs[i + 1])
             for i in range(len(items))]
    print("    · 合成：FFmpeg concat…")
    compositor.compose(clips, str(out_path), str(work))
    if use_cache:
        c.put_video(ch.index, out_path, vkey)
    return _stat(out_path, doc, t0, "miss")


def run_chapter(pages, doc, ch: Chapter, cfg: dict, out_path, c,
                stage: providers.Stage, no_cache: bool = False) -> dict:
    """生成一章。工作目录：启用缓存时用 `ch<NN>/`（与缓存同址，便于人工检查），否则用旧式 `.work_*`。

    `pages` 可以是 list 或 `extractor.lazy_pages()`——命中 text.txt 缓存时不触发抽页。
    """
    use_cache = bool(c.enabled) and not no_cache
    work = (c.chapter_dir(ch.index) if use_cache
            else Path(out_path).parent / f".work_{Path(out_path).stem}")

    # 章文本缓存：内容只由 (书字节, 章, max_chars, **采样算法版本**) 决定，而缓存目录已按
    # 书字节分键，所以 text.txt 永不与当前 PDF 漂移。省掉命中路径的 348 页抽取；
    # 顺带成为口播稿的人工可改口子（改了 → script_key 变 → 重跑模型，语义正确）。
    # tkey 由这里拼（cache 不 import segmenter，依赖保持单向）。
    tkey = f"seg{segmenter.VERSION}|chars{cfg['limits']['max_chars']}"
    if use_cache and c.text_ok(ch.index, tkey):
        text = (work / "text.txt").read_text(encoding="utf-8")
    else:
        text = segmenter.slice_chapter(extractor.resolve_pages(pages), ch,
                                       cfg["limits"]["max_chars"])
        if use_cache:
            c.put_text(ch.index, text, tkey)

    return _produce(ch, cfg, text, out_path, work, c, stage, no_cache)


def run_book(input_path: str, out_root, cfg: dict, indices=None, single_file: bool = False,
             no_cache: bool = False, think: bool | None = None) -> dict:
    """按章批量出片。

    章级**串行**、章内并行：实测给 Ollama 加并发无效（服务端串行，省 5%＝噪声），
    而 TTS 并发有 13x 收益——所以并发只给章内 TTS，章之间老老实实排队。
    """
    c = cache_mod.Cache(input_path, cfg, root=cfg["cache"].get("dir"),
                        enabled=bool(cfg["cache"]["enabled"]))
    use_cache = bool(c.enabled) and not no_cache

    # 大纲优先读缓存：①省 ~6s 全书解析 ②让 outline.json 成为**真正生效**的人工改口
    # （此前每次都重建，落盘文件白存——与 video_key 同类的"改了不生效"缺陷）。
    op = c.dir / "outline.json"
    if use_cache and op.exists():
        try:
            doc = outline.load(op)
            print(f"大纲：缓存命中 {len(doc.chapters)} 章（读 {op.name}，手改生效）")
        except Exception as e:
            print(f"[warn] outline.json 不可用（{e}）——重新解析目录")
            doc = outline.build(input_path)
            outline.save(doc, op)
    else:
        doc = outline.build(input_path)
        if use_cache:
            outline.save(doc, op)                   # 落盘 = 人工可改的口子

    pages = extractor.lazy_pages(input_path)                  # 命中缓存的章不会触发抽页
    stage = providers.build(cfg, think)

    tops = doc.top()
    sel = [t.index for t in tops] if indices is None else list(indices)
    out_root = Path(out_root)
    if not single_file:
        out_root.mkdir(parents=True, exist_ok=True)

    ok, failed, skipped = [], [], []
    for k, idx in enumerate(sel, start=1):
        ch = doc.by_index(idx)
        if ch is None:
            # 越界必须明确报错，不静默跳过（AC-5）
            raise ValueError(f"章号 {idx} 越界：本书顶层章为 1–{len(tops)}（共 {len(tops)} 章）")
        out = out_root if single_file else out_root / f"ch{idx:02d}.mp4"
        print(f"[{k}/{len(sel)}] 第 {idx} 章「{ch.title}」p{ch.start_page}-p{ch.end_page}")
        try:
            ok.append(run_chapter(pages, doc, ch, cfg, out, c, stage, no_cache))
        except segmenter.InsufficientMaterial as e:
            # 「跳过」与「失败」必须分开汇报：跳过是我们**主动的判断**（料不够，不出比硬出好），
            # 失败是**意外**（TTS 挂了、磁盘满了）。混在一个列表里，用户会以为工具坏了。
            # 仍然打印原因 —— 跳过不等于静默（军规 progress_visibility）。
            skipped.append({"chapter": idx, "title": ch.title, "reason": e.reason})
            print(f"⊘ 第 {idx} 章跳过：{e}")
        except Exception as e:
            # 单章失败不阻塞其余章，末尾统一汇总（AC-6）
            failed.append({"chapter": idx, "title": ch.title, "error": str(e)})
            print(f"🔴 第 {idx} 章失败：{e}")

    sec = round(sum(r["seconds"] for r in ok), 1)
    return {"ok": ok, "failed": failed, "skipped": skipped, "seconds": sec,
            "cost": round(0.03 * sec / 3600 * 0.6, 5)}


def run(input_path: str, out_path: str, config_path=None, think: bool | None = None) -> dict:
    """T2V-001 兼容入口：整篇当一章、单文件输出。**签名与语义保持不变。**

    刻意不走新链路：①不读目录（整本即一章）②不启用缓存（保持旧副作用面，
    工作目录仍是 `.work_<文件名>`）③保留旧取料口径——Ollama 吃
    `body()` 跳正文后的片段，规则降级吃全文。这样老调用方的产出与升级前可比（AC-14）。
    """
    cfg = load(config_path)
    if think is not None:
        cfg["llm"]["think"] = think
    pages = extractor.extract_pages(input_path)
    full = "\n".join(pages)
    p = Path(input_path)
    ch = Chapter(1, p.stem, 1, max(1, len(pages)), 0, "whole")

    text = (extractor.body(full)[:cfg["limits"]["max_chars"]]
            if cfg["llm"]["provider"] == "ollama" else full)
    out_path = Path(out_path)
    work = out_path.parent / f".work_{out_path.stem}"
    c = cache_mod.Cache(input_path, cfg, root=None, enabled=False)
    return _produce(ch, cfg, text, out_path, work, c, providers.build(cfg, think), True)
