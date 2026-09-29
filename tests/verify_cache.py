"""cache.py 可重跑验证脚本。

覆盖 03_design §3.3 + 02 §6.3 的关键行为：分层命中、分键（改配色不动 LLM 产物）、
手改脚本只重跑下游、enabled=False 不写盘。全部跑在临时目录，不污染项目根 cache/。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from book2vido.cache import Cache
from book2vido.models import Scene, ScriptDoc


def base_cfg(accent="#056DE8", model="qwen3:8b"):
    return {
        "llm": {"model": model, "think": True},
        "limits": {"max_sentences": 12},
        "tts": {"voice": "zh-CN-YunxiNeural"},
        "visual": {"accent": accent, "w": 1080, "h": 1920, "icon_size": 430},
    }


def make_book(td: str, text: str = "关键对话 第1章 正文") -> str:
    p = Path(td) / "book.txt"
    p.write_text(text)
    return str(p)


def make_script() -> ScriptDoc:
    return ScriptDoc(chapter_index=1, title="第1章", scenes=[
        Scene(text="第一句口播。", keyword="开场", concept="idea"),
        Scene(text="第二句口播。", keyword="展开", concept="book"),
    ], model="qwen3:8b", think=True, created="2026-09-15 18:00")


def main() -> int:
    # ⚠️ ⑦ 的断言曾写成「项目根 cache/ 不存在」——那是**错的判据**：
    # 开发态跑过一次出片后，项目根本来就有一个（已 gitignore 的）cache/，
    # 于是这条断言在开发机上**永远为红**，而它真正想守的是"本脚本没往里写东西"。
    # 正确判据是「跑之前 vs 跑之后，条目集合不变」——先拍快照。
    proj_cache = Path(__file__).resolve().parents[1] / "cache"
    before = sorted(p.name for p in proj_cache.iterdir()) if proj_cache.exists() else None

    tmp = tempfile.mkdtemp(prefix="t2v_cache_")
    book = make_book(tmp)

    # ① 全新输入三层全未命中
    c = Cache(book, base_cfg(), root=tmp)
    assert c.hit_script(1, c.script_key(1, "正文", c.cfg)) is None
    assert c.hit_video(1, c.video_key(1, c.script_key(1, "正文", c.cfg), c.cfg)) is None
    print("① 全新输入：hit_script / hit_video 均 None  PASS")

    # ② put_script 后命中且内容一致
    skey = c.script_key(1, "正文", c.cfg)
    doc = make_script()
    c.put_script(1, doc, skey)
    got = c.hit_script(1, skey)
    assert got is not None and got.scenes[0].text == doc.scenes[0].text
    print("② put_script 后 hit_script 命中且内容一致  PASS")

    # ③ 只改 accent → script_key 不变，video_key 变（分键生效的证明）
    cfg_accent = base_cfg(accent="#FF0000")
    skey2 = c.script_key(1, "正文", cfg_accent)
    vkey1 = c.video_key(1, skey, c.cfg)
    vkey2 = c.video_key(1, skey2, cfg_accent)
    print(f"   script_key(原配色) = {skey}")
    print(f"   script_key(改accent) = {skey2}")
    print(f"   video_key(原) = {vkey1}")
    print(f"   video_key(改accent) = {vkey2}")
    assert skey == skey2, "改配色不该让 script_key 变"
    assert vkey1 != vkey2, "改配色必须让 video_key 变"
    assert c.hit_script(1, skey2) is not None, "script 仍应命中"
    print("③ 只改 accent：script_key 不变、video_key 变、script 仍命中  PASS")

    # ④ 改 model → script_key 变
    cfg_model = base_cfg(model="qwen3:14b")
    skey3 = c.script_key(1, "正文", cfg_model)
    print(f"   script_key(改model) = {skey3}")
    assert skey3 != skey, "改模型必须让 script_key 变"
    print("④ 改 model：script_key 变  PASS")

    # ⑤ 手改 script.json 内容（章节文本变）→ script_key 变 → 未命中
    changed_text = "正文被手工改动了"
    skey_changed = c.script_key(1, changed_text, c.cfg)
    assert skey_changed != skey
    assert c.hit_script(1, skey_changed) is None, "手改后键不匹配应未命中"
    print("⑤ 手改内容：键变 → hit_script 未命中（只重跑下游）  PASS")

    # ⑥ enabled=False 全透传且不写盘（用独立干净目录，证明 put 不落任何文件）
    tmp_off = tempfile.mkdtemp(prefix="t2v_cache_off_")
    book_off = make_book(tmp_off)
    c_off = Cache(book_off, base_cfg(), root=tmp_off, enabled=False)
    skey_off = c_off.script_key(1, "正文", c_off.cfg)
    assert c_off.hit_script(1, skey_off) is None
    assert c_off.hit_video(1, c_off.video_key(1, skey_off, c_off.cfg)) is None
    c_off.put_script(1, make_script(), skey_off)
    c_off.put_video(1, Path(book_off), c_off.video_key(1, skey_off, c_off.cfg))
    assert not c_off.dir.exists(), "enabled=False 不应创建任何缓存目录"
    print("⑥ enabled=False：hit 全 None、put 不写盘（目录未创建）  PASS")

    # ⑦ 临时目录隔离（不污染项目根 cache/）
    after = sorted(p.name for p in proj_cache.iterdir()) if proj_cache.exists() else None
    assert after == before, f"验证不应改动项目根 cache/（前 {before} → 后 {after}）"
    print("⑦ 临时目录隔离，项目根 cache/ 条目数未变  PASS")

    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
