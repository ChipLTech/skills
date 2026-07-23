# mattpocock/skills：面向真实工程的软件开发 Skills

[![skills.sh](https://skills.sh/b/mattpocock/skills)](https://skills.sh/mattpocock/skills)

这是一组面向真实软件工程工作的 Agent Skills。它们不试图用一个庞大流程接管开发，而是把需求澄清、研究、原型、规格、任务拆分、实现、测试、审查、排障和维护组织成可组合的小型能力。

当前仓库默认发布并安装 **31 个稳定 skill**：

| 分类 | 数量 | 用途 |
|---|---:|---|
| `engineering/` | 22 | 通用工程流程和 DLC/vLLM 专项能力 |
| `productivity/` | 5 | 沟通、教学、交接和 skill 编写 |
| `misc/` | 4 | Git、测试夹具、课程和提交工具 |

`personal/`、`in-progress/` 和 `deprecated/` 默认不安装。完整的 Kilo Code 安装、命令包装器和验证方法见 [《mattpocock/skills 在 Kilo Code 中的安装与验证》](./kilo-code-installation-and-validation.md)。

## 核心理念

- **小而可组合**：每个 skill 只负责一种清晰工作，不把整个软件生命周期塞进一个提示词。
- **反馈优先**：先建立可运行、可失败的反馈循环，再推断、修改和验收。
- **领域语言优先**：通过 `CONTEXT.md` 和 ADR 保持人、Agent、代码和文档使用同一套语言。
- **证据分层**：静态检查、包导入、设备执行、模型正确性和性能结论不能互相替代。
- **失败关闭**：缺少身份、资产、硬件、授权、观测或契约时明确停止，不把未执行包装成通过。
- **保留人的控制权**：流程给出纪律和停止条件，但不会隐藏决策、风险和证据边界。

## 软件工程主链路

大多数功能开发沿下面的主链路推进：

```text
选择流程
  ask-matt
      ↓
需求与领域澄清
  grill-with-docs / grill-me
      ↓
消除未知
  research / prototype / wayfinder
      ↓
形成方案
  to-spec → to-tickets
      ↓
开发交付
  implement → tdd → code-review
      ↓
维护与排障
  diagnosing-bugs / resolving-merge-conflicts
  improve-codebase-architecture
```

### 如何选择入口

| 当前情况 | 推荐入口 |
|---|---|
| 不确定该使用哪个 skill | `ask-matt` |
| 已有代码库，需要把设计问清楚 | `grill-with-docs` |
| 没有代码库，需要压力测试计划 | `grill-me` |
| 问题必须通过运行实验才能回答 | `prototype` |
| 需要阅读官方文档、源码或规范 | `research` |
| 工作过大，单个 session 无法容纳 | `wayfinder` |
| 讨论已经成熟，需要形成正式规格 | `to-spec` |
| 需要将规格拆为可独立实现的垂直切片 | `to-tickets` |
| 已有明确 spec 或 ticket | `implement` |
| 只需要测试先行实现一个具体行为 | `tdd` |
| 需要审查分支或 PR | `code-review` |
| 出现顽固 bug、偶现失败或性能回退 | `diagnosing-bugs` |
| Git 已进入 merge/rebase 冲突 | `resolving-merge-conflicts` |
| 系统难理解、难测试或模块边界混乱 | `improve-codebase-architecture` |

### 上下文管理

`grill-with-docs → to-spec → to-tickets` 尽量保持在同一个完整上下文中，让访谈、领域决策、规格和 tickets 使用同一套思考。每张 implementation ticket 再开启独立 session 执行 `implement`。

当会话接近有效推理上限时，使用 `handoff` 把当前事实、决定、修改、验证和下一步保存到临时交接文件，再由新 session 接续。`handoff` 用于跨 session；内置 `/compact` 用于保留当前会话但压缩历史。

## DLC/vLLM 专项体系

当前版本新增并稳定发布了五个 DLC/vLLM 专项 skill，与已有的 `dlc-env-setup` 组成完整协作网络：

```text
环境和包健康
  dlc-env-setup
      ↓
只读硬件证据
  dlc-hardware-observability
      ↓
特定模型兼容
  model-adaptation
      ↓
专项交付或部署
  ├── modelzoo-image-validation
  ├── pd-separation
  └── main-to-main-upgrade
```

这些 skill 不是简单线性调用。顶层编排器会把子问题委托给明确的 owner，避免重复探测和互相覆盖结论。

### 专项路由

| 用户目标 | 应使用的 Skill | 不负责什么 |
|---|---|---|
| 重建或修复 DLC、PyTorch 2.5.0、可选 vLLM 环境 | `dlc-env-setup` | 不证明模型语义正确 |
| 采集设备、HBM、进程、链路和 cleanup 证据 | `dlc-hardware-observability` | 不执行 reset、驱动维护或模型验收 |
| 适配一个具体新模型或不兼容模型 | `model-adaptation` | 不更新 Verified vLLM Alignment |
| 从本地模型资格验证到 DLC/TYD 镜像交付 | `modelzoo-image-validation` | 不把 ModelZoo 当作本地执行权威 |
| 部署或诊断 Prefill/Decode 分离 | `pd-separation` | 不以 HTTP 200 或非空输出代替 KV transfer 证据 |
| 对齐 exact upstream vLLM full SHA | `main-to-main-upgrade` | 当前流程只读、no-finalize，不修改 alignment 或 manifest |

### DLC 证据边界

```text
C1a：package/import evidence
C1b：bounded DLC Runtime execution
SMI：query-only hardware observation
Model acceptance：真实权重和语义断言
Performance：声明 workload 下的性能证据
```

以上证据必须分别报告：

- import 成功不等于设备执行成功；
- 设备执行成功不等于模型正确；
- HTTP 200、权重加载或非空输出不等于语义正确；
- 单次 benchmark 通过不等于稳定性能基线；
- Dummy、fake server、DLCsim 和静态证据不等于 Real DLC Hardware acceptance；
- SMI 观测能证明有界库存、HBM 和进程归属，但不能单独证明 DLC Runtime dispatch、KV transfer 或模型正确性。

### 推荐组合

**新模型适配**

```text
dlc-env-setup
→ dlc-hardware-observability
→ model-adaptation
→ diagnosing-bugs（仅在已建立可失败反馈环时）
```

**ModelZoo 到 DLC/TYD 镜像**

```text
modelzoo-image-validation
├── dlc-env-setup
├── dlc-hardware-observability
└── model-adaptation
```

**Prefill/Decode 分离**

```text
pd-separation
├── 建立 monolithic baseline
├── dlc-env-setup
├── model-adaptation
├── dlc-hardware-observability
└── transport + request-correlated KV transfer evidence
```

**Main-to-main 对齐**

```text
main-to-main-upgrade
→ 完整 upstream delta 分类
→ Patch Import Manifest impact report
→ DeepSeek TP=2 与 Llama TP=1 mandatory assignments
→ model-adaptation child evidence
→ 只报告 finalize eligibility
```

## 31 个稳定 Skill

### Engineering：22 个

| Skill | 调用方式 | 作用 |
|---|---|---|
| [`ask-matt`](./skills/engineering/ask-matt/SKILL.md) | 用户调用 | 根据当前工作选择正确的 skill 或 flow |
| [`code-review`](./skills/engineering/code-review/SKILL.md) | 自动或用户调用 | 从 Standards 和 Spec 两条独立轴审查 diff |
| [`diagnosing-bugs`](./skills/engineering/diagnosing-bugs/SKILL.md) | 自动或用户调用 | 建立可靠复现循环，通过可证伪假设定位根因 |
| [`dlc-env-setup`](./skills/engineering/dlc-env-setup/SKILL.md) | 自动或用户调用 | 重建并验证 DLC 工具链、PyTorch wheel 和可选 vLLM 环境 |
| [`dlc-hardware-observability`](./skills/engineering/dlc-hardware-observability/SKILL.md) | 自动或用户调用 | 使用官方 `cltech_smi` 采集规范化、只读的硬件证据 |
| [`grill-with-docs`](./skills/engineering/grill-with-docs/SKILL.md) | 用户调用 | 对照代码、领域模型和 ADR 逐项澄清设计 |
| [`implement`](./skills/engineering/implement/SKILL.md) | 用户调用 | 根据 spec/tickets 实现、验证、审查并交付 |
| [`improve-codebase-architecture`](./skills/engineering/improve-codebase-architecture/SKILL.md) | 用户调用 | 寻找浅模块、耦合泄漏和测试困难等架构深化机会 |
| [`main-to-main-upgrade`](./skills/engineering/main-to-main-upgrade/SKILL.md) | 自动或用户调用 | 分析 vllm-dlc main 对齐 exact upstream full SHA 的完整影响 |
| [`model-adaptation`](./skills/engineering/model-adaptation/SKILL.md) | 自动或用户调用 | 处理具体模型的 Attention、MLA、MoE、量化、多模态、MTP 和分布式兼容 |
| [`modelzoo-image-validation`](./skills/engineering/modelzoo-image-validation/SKILL.md) | 自动或用户调用 | 资格验证本地模型并按门禁交付独立 DLC/TYD 镜像 |
| [`pd-separation`](./skills/engineering/pd-separation/SKILL.md) | 自动或用户调用 | 部署和诊断 MooncakeDLCConnector Prefill/Decode 分离 |
| [`prototype`](./skills/engineering/prototype/SKILL.md) | 自动或用户调用 | 创建明确可丢弃的终端或 UI 原型回答设计问题 |
| [`research`](./skills/engineering/research/SKILL.md) | 自动或用户调用 | 基于高可信一手来源生成带引用的研究笔记 |
| [`resolving-merge-conflicts`](./skills/engineering/resolving-merge-conflicts/SKILL.md) | 自动或用户调用 | 理解双方意图并完成整个 merge/rebase 冲突流程 |
| [`setup-matt-pocock-skills`](./skills/engineering/setup-matt-pocock-skills/SKILL.md) | 用户调用 | 初始化 issue tracker、triage 标签和领域文档布局 |
| [`tdd`](./skills/engineering/tdd/SKILL.md) | 自动或用户调用 | 使用公共接口逐行为执行红、绿、重构 |
| [`to-spec`](./skills/engineering/to-spec/SKILL.md) | 用户调用 | 将已经澄清的讨论整理并发布成正式 spec |
| [`to-tickets`](./skills/engineering/to-tickets/SKILL.md) | 用户调用 | 将 spec 拆成 tracer-bullet tickets 和 blocking edges |
| [`triage`](./skills/engineering/triage/SKILL.md) | 用户调用 | 通过状态机整理外部进入的 issue |
| [`wayfinder`](./skills/engineering/wayfinder/SKILL.md) | 用户调用 | 为跨多个 session 的大型模糊工作建立决策地图 |
| [`zoom-out`](./skills/engineering/zoom-out/SKILL.md) | 用户调用 | 从局部代码上升到模块、调用关系和领域全景 |

### Productivity：5 个

| Skill | 作用 |
|---|---|
| [`caveman`](./skills/productivity/caveman/SKILL.md) | 持续使用超压缩表达减少 token，同时保留技术准确性 |
| [`grill-me`](./skills/productivity/grill-me/SKILL.md) | 在没有代码库的场景下穷尽式访谈计划或设计 |
| [`handoff`](./skills/productivity/handoff/SKILL.md) | 将当前会话压缩为下一位 Agent 可直接接续的交接文件 |
| [`teach`](./skills/productivity/teach/SKILL.md) | 建立长期、有状态的个性化学习工作区 |
| [`writing-great-skills`](./skills/productivity/writing-great-skills/SKILL.md) | 指导设计、精简和审查可预测的高质量 skill |

### Misc：4 个

| Skill | 作用 |
|---|---|
| [`git-guardrails-claude-code`](./skills/misc/git-guardrails-claude-code/SKILL.md) | 为 Claude Code 拦截 push、hard reset、clean 等危险 Git 操作 |
| [`migrate-to-shoehorn`](./skills/misc/migrate-to-shoehorn/SKILL.md) | 将 TypeScript 测试中的 `as` 断言迁移到 `@total-typescript/shoehorn` |
| [`scaffold-exercises`](./skills/misc/scaffold-exercises/SKILL.md) | 创建符合课程规范的 section、problem、solution 和 explainer |
| [`setup-pre-commit`](./skills/misc/setup-pre-commit/SKILL.md) | 配置 Husky、lint-staged、Prettier、类型检查和测试 |

## 安装

### 通用 Agent 安装

```bash
npx skills@latest add mattpocock/skills
```

首次在一个仓库中使用通用工程 flow 时，运行：

```text
/setup-matt-pocock-skills
```

它会配置 issue tracker、triage 标签映射和领域文档布局。

### Kilo Code 全局安装

仅安装 skills：

```bash
./scripts/link-kilo-skills.sh
```

同时生成显式 slash-command wrappers：

```bash
./scripts/link-kilo-skills.sh --with-commands
```

安装到单个项目：

```bash
./scripts/link-kilo-skills.sh --project /path/to/project --with-commands
```

默认只安装 `engineering/`、`productivity/` 和 `misc/`。如需包含 `personal/` 和 `in-progress/`，使用 `--all`；`deprecated/` 始终不会安装。

安装后请重启 Kilo Code 或打开新 session。详细目录、验证命令、常见问题和卸载方法见 [Kilo Code 安装与验证手册](./kilo-code-installation-and-validation.md)。

## 验证原则

本仓库中的 DLC/vLLM 能力不再只是 Markdown 说明，还包含共享契约、fake server、smoke runner、long-prefix 构造、依赖审计、publication validator 和自动测试。

验证结论必须说明层级：

| 层级 | 能证明什么 |
|---|---|
| 静态和发布验证 | skill 包结构、frontmatter、catalog、plugin、SkillHub、链接器和契约一致 |
| Fake server/fixture | CLI、退出码、失败状态、身份链和停止语义 |
| Dummy/DLCsim | 有限结构或诊断路径，不是 Real DLC Hardware acceptance |
| C1a | package/import 可用 |
| C1b | 有界 DLC Runtime device execution |
| 真实权重 | 声明模型和部署 profile 下的功能证据 |
| 性能 workload | 声明 workload 下的结果，不自动成为稳定基线 |

任何未执行层级都应报告为 `not_verified`，不能由较弱证据推断为通过。

## 旧名称迁移

| 旧名称 | 当前名称 |
|---|---|
| `diagnose` | `diagnosing-bugs` |
| `to-prd` | `to-spec` |
| `to-issues` | `to-tickets` |
| `write-a-skill` | `writing-great-skills` |
| `vllm-dlc-model-adapter` | `model-adaptation` |
| `vllm-dlc-main2main` | `main-to-main-upgrade` |

安装脚本会清理已退休的生成型 symlink 或 command wrapper，但不会删除用户维护的真实文件和目录。

## 许可证和来源

本仓库基于 [mattpocock/skills](https://github.com/mattpocock/skills) 的可组合工程方法，并加入 ChipLTech 的 DLC/vLLM 稳定工作流、契约、验证工具和中文使用文档。每个 skill 的实际行为以对应 `SKILL.md` 为准。
