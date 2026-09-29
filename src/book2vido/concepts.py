"""受控概念清单：`Scene.concept` 的合法值域（领域资产）。

为什么它独立成模块，而不留在 `icons.py` 里
────────────────────────────────────────────
这份清单曾经住在 `icons.py`（图标资产层）里。那是个**位置错误**，而且在第二个
消费者出现之前不会暴露：

    分镜层（scriptwriter）要的是「有哪些合法概念」→ 注入提示词，防模型自由发挥
    画面层（visualizer）  要的是「概念对应哪个图标」→ 渲染时查表

被两个消费者共享的数据，**住在任何一方家里都是错的** —— 留在 icons 里，
分镜层就被迫 `import icons`（生成层跨界引用资产层，依赖方向被拉弯）。

更实质的问题是**领域契约归属错了**：`models.Scene.concept` 的约束
（"须落在受控清单内"）指向了另一个模块的内部常量。一个核心数据结构的值域，
应该由它自己所在的层定义，而不是由某个下游消费者代管。

现在两个消费者**平级依赖本模块**：

    scriptwriter ─┐
                  ├─→ concepts（本模块）      ← 依赖是直的
    visualizer ─→ icons ─→ concepts           ← 依赖也是直的（icons 只借它扩充词表）

本模块**只依赖标准库**，不 import 任何包内模块 —— 所以谁都可以依赖它，不产生环。
（同型教训见 `doc/17-结构诊断与重构方案.html` §S-2、
`~/.workbuddy/skills/hidden-contract-audit`「共享数据寄居在消费者家里」。）


清单本身的来龙去脉（★ 语义层的关键补丁，2026-09-15）
────────────────────────────────────────────────────
**病灶**：LLM 自由生成的 keyword 是「叙事型中文概念」（定义/心态/观察/动机…），
而 `icons.KEYWORD_ICONS` 是按「AI/工程化主题词」建的。两者交集小 → `resolve()` 全部
未命中 → 走 `fallback_for()` 散列，12 张卡散进 16 个中性图形里，实测撞车严重
（「表达/应用/改变」三张同为拼图，「心态」被散列成六边形）。

**药方（架构级，不是补字典）**：
  1. 本清单是**给 LLM 的受控选项表**，由提示词注入，要求 concept 必须从中选；
  2. 清单里的每个词都是「叙事高频概念」，命中率接近 100%；
  3. concept 与 keyword 解耦 —— keyword 仍自由生成（做卡片大标题，读起来更自然），
     concept 只负责选图标。见 `scriptwriter.Scene` 与 `visualizer.card()`。

本清单**覆盖** `icons.KEYWORD_ICONS` 中的同名词条（同义词以这里的语义为准），
覆盖动作由 `icons.py` 在导入后执行（见该模块 `KEYWORD_ICONS.update(CONCEPTS)`）。
"""
from __future__ import annotations

CONCEPTS: dict[str, str] = {
    # —— 定义 / 认知对象 ——
    "定义": "tabler:book-2", "概念": "tabler:book-2", "含义": "tabler:book-2",
    "特征": "tabler:fingerprint", "特点": "tabler:fingerprint",
    "本质": "tabler:target-arrow", "原理": "tabler:atom-2", "性质": "tabler:atom-2",
    # —— 因果 / 逻辑 ——
    "原因": "tabler:help-circle", "为什么": "tabler:help-circle",
    "结果": "tabler:arrow-down-right", "影响": "tabler:ripple",
    "对比": "tabler:arrows-diff", "区别": "tabler:arrows-diff",
    "结论": "tabler:flag-3", "总结": "tabler:flag-3", "要点": "tabler:list-check",
    # —— 方法 / 行动 ——
    "方法": "tabler:route-2", "技巧": "tabler:tool", "步骤": "tabler:list-numbers",
    "行动": "tabler:run", "实践": "tabler:hammer", "落地": "tabler:hammer",
    "案例": "tabler:box", "例子": "tabler:box", "应用": "tabler:apps",
    "目标": "tabler:target", "目的": "tabler:target", "方案": "tabler:clipboard-check",
    # —— 人 / 心理 ——
    "心态": "tabler:mood-smile", "态度": "tabler:mood-smile",
    "情绪": "tabler:mood-heart", "感受": "tabler:mood-heart",
    "动机": "tabler:bolt", "意愿": "tabler:heart",
    "观察": "tabler:eye", "发现": "tabler:eye", "注意": "tabler:eye",
    "表达": "tabler:message-circle", "沟通": "tabler:messages", "倾听": "tabler:ear",
    "团队": "tabler:users", "协作": "tabler:users-group", "人": "tabler:user",
    # —— 安全 / 风险 ——
    "安全": "tabler:shield-lock", "保护": "tabler:shield-lock",
    "风险": "tabler:alert-triangle", "问题": "tabler:circle-x", "难题": "tabler:circle-x",
    "对策": "tabler:key", "成本": "tabler:coin-yuan",
    # —— 时间 / 变化 ——
    "时间": "tabler:clock", "效率": "tabler:bolt", "速度": "tabler:gauge",
    "改变": "tabler:refresh", "变化": "tabler:refresh", "转变": "tabler:refresh",
    "成长": "tabler:trending-up", "进步": "tabler:trending-up", "趋势": "tabler:trending-up",
    # —— 认知 / 学习 ——
    "认知": "tabler:brain", "思考": "tabler:brain", "记忆": "tabler:brain",
    "学习": "tabler:school", "知识": "tabler:books", "洞察": "tabler:bulb",
    "反思": "tabler:message-question", "复盘": "tabler:message-question",
    # —— 工程 / 工具 ——
    "工具": "tabler:tools", "技能": "tabler:puzzle", "模型": "tabler:cpu",
    "代码": "tabler:code", "数据": "tabler:chart-bar", "配置": "tabler:settings",
    "验证": "tabler:shield-check", "上线": "tabler:rocket", "流程": "tabler:git-branch",
    # —— 内容 / 载体 ——
    "书": "tabler:book", "文章": "tabler:file-text", "视频": "tabler:video",
    "画面": "tabler:photo", "网络": "tabler:network", "未来": "tabler:rocket",
    "价值": "tabler:diamond", "选择": "tabler:arrows-split",
}

# 按长度降序的键列表。**当前没有任何调用点**（T2V-007 核过全仓，仅本处定义）——
# 提示词注入走的是 CONCEPTS 的**插入顺序**（按语义分组，人读友好，见 scriptwriter.py），
# 本地匹配走 icons.py 的 _SORTED（那是对 KEYWORD_ICONS 整体排序，与它无关）。
# 保留它的理由：**长词优先注入**是个合理选项——若将来发现模型容易忽略清单尾部的词，
# 把 scriptwriter 里的 join 源换成它就够了。
# ⚠️ 别在注释里声称它"已在用"：本行原来就写着「供 prompt 注入使用」，而实际没有调用点，
#    属错题库 L-15「注释声称的用途 ≠ 实际用途」。注释也要跟代码一起维护。
CONCEPT_KEYS = sorted(CONCEPTS.keys(), key=len, reverse=True)
