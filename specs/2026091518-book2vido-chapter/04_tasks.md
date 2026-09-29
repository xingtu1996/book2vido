# 04 · 任务清单：目录索引与按需生成

> Ticket: T2V-002 | 日期: 2026-09-15 18:51 | 状态: ✅ **AC 16/16 通过**（见 `verification-report.md`）→ 待 Phase 6 提交（`push` 待 boss 拍板）

> 📜 **Check**：每阶段完成前对照 [laws.md](./laws.md) 与项目宪法逐项确认。并行阶段额外对照 laws §三 并行门禁。

## 依赖关系

```
Phase 0 (契约冻结·串行)
      │
      ├──────────────┬──────────────┬──────────────┐
      ▼              ▼              ▼              ▼
 Phase 1         Phase 2        Phase 2b       Phase 3        ← ∥ 四单元并行
 outline.py      segmenter.py   cache.py       narrator.py
 + extractor.py                               (+speak_many)
      └──────────────┴──────────────┴──────────────┘
                              │
                              ▼
                    Phase 4 (串行收口：pipeline/__main__/config/scriptwriter)
                              │
                              ▼
                    Phase 5 (验证关闭 · Loop Engineering)
                              │
                              ▼
                    Phase 6 (提交 — 待 boss 拍板)
```

> ∥ = 可并行。依据 `01_analysis` §四-B：四个单元文件冲突交集 = ∅，并发上限 4。
> **Phase 4 之前不得触碰 `pipeline.py` / `__main__.py`**（多单元共享，串行门禁）。

## Phase 0: 契约冻结（串行 · 不可跳过）

- [x] 0.1 对照 laws.md 五条宪法 + 三铁律确认——本变更不违反护栏
- [x] 0.2 安全三条件确认（来自 02 §五）：退出（--no-cache / 降并发上限）/ 幂等（分键覆盖写）/ 回滚（只增不删 + .backups）
- [x] 0.3 **冻结 `models.py`**：按 `03_design` §3.0 落盘 5 个契约（Chapter/OutlineDoc/Scene/ScriptDoc/MediaClip）
- [x] 0.4 断言 `models.py` 不 import 任何同包模块（AC-13）
- [x] 0.5 备份：`src/book2vido/*.py` → `.backups/2026091518-chapter/`
- [x] 0.6 更新文档回写清单（`03_design` §八）
- [x] 0.7 **续接前置**：读 00_README「交接与续传」+ execution-log 尾部（本 spec 首会话剧齐）

## Phase 1 ∥ · Unit A：结构层（`outline.py` + `extractor.py`）

- [x] 1.1 `extractor.extract_pages()` 页文本列表（保留页边界）；`extract()` 改为 `join(extract_pages())` 保持兼容
- [x] 1.2 `extractor.page_slice(pages, start, end)`；`body()` 标 deprecated（**不删**）
- [x] 1.3 `outline.build()` 三层兜底：PDF outline → 正文正则 → 整本
- [x] 1.4 `outline.render_tree()` 两级树文本
- [x] 1.5 `outline.save()` / `load()` JSON 往返
- [x] 1.6 单元：`origin` 三态 + `depth` 正确 + 页码单调不减

## Phase 2 ∥ · Unit B：切分层（`segmenter.py`）

- [x] 2.1 `slice_chapter()` 均匀采样首/中/尾（**替换 `[:2500]` 截头**）
- [x] 2.2 `pick()` 便捷封装
- [x] 2.3 单元：短章原样 / 长章超限时首中尾均被代表 / 越界裁剪 / 空章返回空串

## Phase 2b ∥ · Unit C：缓存层（`cache.py`）

- [x] 2b.1 `Cache` 类 + `book_hash`（文件字节）+ 目录布局
- [x] 2b.2 **分键**：`script_key` / `video_key` 分离（改配色不得使 LLM 产物失效）
- [x] 2b.3 `.keys.json` 元数据 + `hit_script` / `hit_video` / `put_*`
- [x] 2b.4 `enabled=False` 全透传（`--no-cache`）
- [x] 2b.5 单元：全未命中 / 二跑命中 / 手改 script 只重跑下游 / 改配色 script 仍命中

## Phase 3 ∥ · Unit D：配音层（`narrator.py`）

- [x] 3.1 `TTSProvider.speak_many()`（基类实现一次，两 provider 共用）
- [x] 3.2 重试 ≤2 次 + 失败率 >50% 自适应降并发 + 最终串行 + 仍失败抛错
- [x] 3.3 `on_progress` 回调（进度可见）
- [x] 3.4 单元 + 实测：12 句 ≤5s、12/12 成功

## Phase 4: 串行收口（**并行门禁：共享文件只在此阶段动**）

- [x] 4.1 `scriptwriter.py`：`Scene` 改为 `from .models import Scene`（**保留 re-export**，`tools/probe_perf.py:37` 不破）
- [x] 4.2 `scriptwriter.py`：`script()` 接受外部传入文本（不再内部 `[:2500]`）+ `ScriptDoc` 往返
- [x] 4.3 `config.py` / `config.yaml`：新增 `cache` / `concurrency` 段 + `limits.max_chars`
- [x] 4.4 `compositor.py`：`compose()` 收 `list[MediaClip]`，`from_any` 兼容三元组
- [x] 4.5 `pipeline.py`：拆 `run_chapter()` / `run_book()`；**`run()` 签名与语义不变**
- [x] 4.6 `__main__.py`：新增 `outline` / `list`；`run` 增 `--chapter/--chapters/--all/--jobs/--no-cache/--cache-dir`
- [x] 4.7 影响面复验：重查调用链，确认无新增波及点（AC-14）

## Phase 5: 验证关闭（Loop Engineering）

- [x] 5.1 `python -c "import book2vido"` — 零错误
- [x] 5.2 执行 05_validator §二 全部 TC（TC-01 ~ TC-08）——结果见 `verification-report.md`
- [x] 5.3 执行 05_validator §三 数据一致性（outline ↔ segmenter ↔ script ↔ 成片 四链对账）
  - `render_tree(build)` ≡ `render_tree(load(outline.json))`：93 条 / 22 顶层 / 页码逐条相同 → 读缓存无漂移
- [x] 5.4 执行 05_validator §四 安全三条件 + §五 合规检查
  - AC-15 关键词扫描零命中；外部端点仅 localhost(Ollama) / api.iconify.design / 自有 GitHub 仓
- [x] 5.5 真出片验收：`run --chapter N` 产出合法 mp4（ffprobe 校验时长/编码）
- [x] 5.6 `wc -l` 核对模块 ≤200 行（AC-16，`icons.py` 豁免）
- [x] 5.7 `.app` 重建（带 5 个新模块，含 `providers.py`）+ `--selftest` 全绿
  - 产物 `dist/Book2Vido.app` **115 MB**；包内 16 个 .py 与仓库源码**哈希逐一致**
  - `--selftest` **7/7 绿**（runtime 3.13.12 / 依赖 / ollama 二进制 / ollama 服务 / ffmpeg / qwen3:8b / 图标 118）
  - 旧产物**未删除**，改名让位 → `dist/Book2Vido.app.bak-20260915-191713`（可回滚）
  - ⚠️ 构建脚本「清理旧产物」触发安全钩子（2817 文件超阈值）→ 采用**改名让位**而非删除

## Phase 6: 提交（待 boss 拍板）

- [ ] 6.1 `git status` / `git diff` 确认变更范围（无调试残留、无硬编码密钥）
- [ ] 6.2 按项目 git 规范提交（**push 需 boss 明确批准**）

## 覆盖矩阵

| 验收标准 | 单元测试 | 运行时验证（05_validator） | 覆盖状态 |
|---------|:-----------:|:-----------:|:-------:|
| AC-1 outline.json 93 条 | — | TC-01 | ✅ |
| AC-2 list 两级树 **顶层 22 条**（小节 71 / 合计 93） | — | TC-02 | ✅ |
| AC-3 兜底链三态 | TC-03 | TC-03 | ✅ |
| AC-4 `--chapter 3` 文本不越界 | — | TC-04 + §三链2 | ✅ |
| AC-5 `--chapters 1,3,5` + 越界报错（含 `--chapter 0/-1`、`--chapters abc/''`） | — | TC-05 | ✅ |
| AC-6 `--all` 单章失败不阻塞 | — | TC-06 | ✅ |
| AC-7 长章均匀采样（**首/正中/末 12 字**均被代表） | TC-07 | TC-07 | ✅ |
| AC-8 TTS 并发 ≤5s 12/12 | — | TC-08 + §三链4 | ✅ |
| AC-9 重试/降并发/不静默 | TC-09 | §四 4.1 | ✅ |
| AC-10 缓存三层语义 | TC-10 | TC-10 | ✅ |
| AC-11 改一句重跑 ≤15s | — | TC-11 | ✅ |
| AC-12 MediaClip 契约 + 兼容 | TC-12 | TC-12 | ✅ |
| AC-13 models 零同包 import | TC-13 | §五 5.4 | ✅ |
| AC-14 旧 CLI 行为不变 | — | TC-14 | ✅ |
| AC-15 零公司 key + 离线可出片 | — | §五 5.1/5.2 | ✅ |
| AC-16 模块 ≤200 行 | — | §五 5.3 | ✅ |

## 扩展

- [ ] **影响面复验**：Phase 4 完成后重查调用链，与 `01_analysis` §四 逐行比对（跨模块变更必做）
- [ ] **性能验证**：首跑 / 重跑 / TTS 三档计时，写入 `doc/10` 与 skill
- [x] **实施期追加**：`providers.py` 拆分（AC-16 关注点分离）
- [x] **实施期追加**：消除命中路径冗余（`outline.json` 读缓存 + `text.txt` + `extract_pages` 延迟）
- [x] **实施期追加**：`video_key` 改挂分镜指纹（修「手改分镜被静默丢弃」）
- [x] **实施期追加**：`_looks_like_toc` 替换失效的「章标记 ≥3 条」判据
- [x] **实施期追加**：`outline.build` 非 PDF 语义写实（一律 `whole-doc`）+ 改掉误导性文档
