"""三层缓存：成片 / 分镜 / 无。

为什么分键（本模块存在的唯一理由）：
  三类产物失效条件不同——分镜（script）是最贵的 LLM 产物（本机 ~36s），
  而配色/音色只影响下游画面与配音。若把 accent/voice 也塞进 script_key，
  用户改一句配色就会让最贵的 LLM 产物一起失效、白跑一遍。
  所以 script_key 只含「影响分镜内容」的因子，video_key 在其上叠加视觉/配音因子。

为什么 book_hash 取文件字节而非路径：同一本书挪目录/改名不该废缓存；
  换书（字节变）才该废——内容哈希比路径更稳。

为什么 root 默认走 paths.project_root()：这里**曾经抄过一份** `parents[2]`，当时的理由是
  "不 import visualizer 去取，保持依赖单向" —— 那个理由在**当时是对的**
  （visualizer 是画面层，cache 不该依赖它）。但正解不是"各抄一份"，
  而是把"项目根在哪"上提到中立的 paths.py：
  **共享的东西住在中立位置，不住在某个消费者家里**（同 doc/17 §S-2）。
  paths 只依赖标准库，所以 cache 依然只向下依赖，依赖方向没有被拉弯。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import ScriptDoc
from .paths import project_root


class Cache:
    def __init__(self, input_path: str, cfg: dict, root: str | None = None, enabled: bool = True):
        # book_hash 用字节哈希：换书才失效，挪目录/改名都不该废缓存。
        self.book_hash = hashlib.sha256(Path(input_path).read_bytes()).hexdigest()[:16]
        # root 默认 None → <项目根>/cache；项目根来自 paths（唯一来源，见该模块 docstring）。
        self._root = Path(root) if root else project_root() / "cache"
        self.cfg = cfg
        self.enabled = enabled

    @property
    def dir(self) -> Path:
        """本书专属缓存根：<root>/<book_hash>。"""
        return self._root / self.book_hash

    def chapter_dir(self, i: int) -> Path:
        """章目录 <dir>/ch<NN>（NN 两位左补零）。

        自动 mkdir：不同章走不同目录，并发写互不干扰（02 §四 幂等条件）。
        """
        d = self.dir / f"ch{i:02d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def script_key(self, i: int, chapter_text: str, cfg: dict, prompt_fp: str = "") -> str:
        # 只含影响「分镜内容」的因子：model/think/句数/章节文本/**提示词**。
        # 故意不放 accent/voice/w/h 等视觉或配音因子——
        # 否则改配色会把最贵的 LLM 产物一起废掉（见模块 docstring）。
        #
        # `prompt_fp`（T2V-007 补录）：提示词是影响分镜内容**最直接**的因子，原先却漏在键外——
        # 于是"改提示词"会静默命中旧分镜，表现为**改了像没改**。
        # 宪法铁律六要求「新增任何缓存必须回答：人改它生效吗」，这一条当时就是不达标的。
        # 指纹由调用方算好传进来（cache 不 import promptlib，依赖保持单向），
        # 与 `text_key` 让调用方拼 `segmenter.VERSION` 是同一套做法。
        # 默认空串：兼容不传的旧调用点，行为与升级前一致。
        raw = f"{self.book_hash}|{cfg['llm']['model']}|{cfg['llm']['think']}|" \
              f"{cfg['limits']['max_sentences']}|" \
              f"{hashlib.sha256(chapter_text.encode()).hexdigest()}|{prompt_fp}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def video_key(self, i: int, script_fp: str, cfg: dict) -> str:
        """str 参数是**分镜内容指纹**（`sha256(ScriptDoc.to_json())`），不是 `script_key`。

        口径务必读准：指纹取自**规范化 JSON**（`asdict` 后 `json.dumps(indent=2)`），
        不是 `script.json` 的原始字节。差别有意义——手工改完只动空白/缩进**不该**废掉成片，
        改内容才该废。

        为什么挂分镜内容而不是输入键（实测追调用流才发现的原设计缺陷）：
        `script_key` 由**章节输入文本**推导，手工改 `script.json` 不会改它——
        于是 `hit_script` 会（正确地）返回改后的分镜，但 `video_key` 也不变，
        `hit_video` 就会命中**由旧分镜渲染出的成片**，用户的改动被静默丢弃。
        改挂分镜指纹后：改一句 → 指纹变 → 只重渲染下游（画面/配音/合成），
        LLM 仍然不跑——「人改一句、十几秒看到新片」才真正成立。
        """
        # `theme` 必须进键（2026-09-16 补）：主题换整套色板，但 `accent` 可能一字未变
        # （ink/paper 的 accent 同为 #F2644F）→ 若不进键，切主题会命中旧成片，
        # 表现为**改了像没改**。与 `prompt_fp` 同为「人改它必须生效」类因子（宪法铁律六）。
        # 用 .get 兜底：旧配置无此键时行为与升级前一致，不炸。
        raw = f"{script_fp}|{cfg['tts']['voice']}|{cfg['visual'].get('theme', '')}|" \
              f"{cfg['visual']['accent']}|" \
              f"{cfg['visual']['w']}|{cfg['visual']['h']}|{cfg['visual']['icon_size']}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _keys_path(self, i: int) -> Path:
        return self.chapter_dir(i) / ".keys.json"

    def _load_keys(self, i: int) -> dict:
        p = self._keys_path(i)
        if p.exists():
            try:
                return json.loads(p.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_keys(self, i: int, **kv) -> None:
        # 增量更新：put_script 与 put_video 各自只动已知键，互不覆盖。
        keys = self._load_keys(i)
        keys.update(kv)
        self._keys_path(i).write_text(json.dumps(keys, ensure_ascii=False, indent=2))

    def hit_script(self, i: int, script_key: str) -> ScriptDoc | None:
        # enabled=False → 直接不透传任何命中，上层每次都重跑（--no-cache）。
        if not self.enabled:
            return None
        sj = self.chapter_dir(i) / "script.json"
        if not sj.exists():
            return None
        # 键须一致才认：`script_key` 由**章节输入文本**推导，故意不看 script.json 正文——
        # 于是手工改过的 script.json 仍然命中，改动被**保留**而不是被重跑 LLM 覆盖掉。
        # 真正的失效由 `video_key`（挂分镜指纹）负责：只重渲染下游，不跑模型。
        if self._load_keys(i).get("script_key") != script_key:
            return None
        return ScriptDoc.from_json(sj.read_text())

    def hit_video(self, i: int, video_key: str) -> Path | None:
        if not self.enabled:
            return None
        mp4 = self.chapter_dir(i) / f"ch{i:02d}.mp4"
        if not mp4.exists():
            return None
        if self._load_keys(i).get("video_key") != video_key:
            return None
        return mp4

    def text_ok(self, i: int, text_key: str) -> bool:
        """`text.txt` 是否可直接复用（键一致且文件在）。

        `text_key` 由**调用方**拼好传进来（`segmenter.VERSION + max_chars`），
        cache 不 import segmenter —— 保持依赖单向（本模块只向下依赖 models）。
        为什么要带算法版本：见 `segmenter.VERSION` 的说明，防「改了算法旧切片还在用」。
        """
        if not self.enabled:
            return False
        if self._load_keys(i).get("text_key") != text_key:
            return False
        return (self.chapter_dir(i) / "text.txt").exists()

    def put_text(self, i: int, text: str, text_key: str) -> Path:
        if not self.enabled:
            return self.dir / f"ch{i:02d}" / "text.txt"
        p = self.chapter_dir(i) / "text.txt"
        p.write_text(text, encoding="utf-8")
        self._save_keys(i, text_key=text_key)
        return p

    def put_script(self, i: int, doc: ScriptDoc, script_key: str) -> Path:
        # enabled=False → 空操作，不写盘（--no-cache 走这条）。
        if not self.enabled:
            return self.dir / f"ch{i:02d}" / "script.json"
        p = self.chapter_dir(i) / "script.json"
        p.write_text(doc.to_json())
        self._save_keys(i, script_key=script_key)
        return p

    def put_video(self, i: int, src: Path, video_key: str) -> Path:
        if not self.enabled:
            return self.dir / f"ch{i:02d}" / f"ch{i:02d}.mp4"
        dst = self.chapter_dir(i) / f"ch{i:02d}.mp4"
        dst.write_bytes(Path(src).read_bytes())
        self._save_keys(i, video_key=video_key)
        return dst
