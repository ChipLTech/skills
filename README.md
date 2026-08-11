# mattpocock/skills：面向真实工程的软件开发 Skills

[![skills.sh](https://skills.sh/b/mattpocock/skills)](https://skills.sh/mattpocock/skills)

这是一组面向真实软件工程工作的 Agent Skills。它们不试图用一个庞大流程接管开发，而是把需求澄清、研究、原型、规格、任务拆分、实现、测试、审查、排障和维护组织成可组合的小型能力。

当前仓库默认安装 **40 个稳定 skill**，其中 36 个属于 Claude 插件发布面，另有 4 个 Kilo 默认安装的 `misc/` 工具：

| 分类 | 数量 | 用途 |
|---|---:|---|
| `engineering/` | 28 | 通用工程流程、共享设计语言和 DLC/vLLM 专项能力 |
| `productivity/` | 8 | 访谈、沟通、教学、交接和 Agent 文档编写 |
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

**项目前置条件：** Skills 安装完成后，首次在一个业务仓库中运行通用工程 flow 前，执行 `/setup-matt-pocock-skills`。它配置 issue tracker、triage 标签和领域文档布局，不负责安装 Kilo Skills。Chipltech 只读知识路由可以先通过 `chipltech-context` 进行；后续 owning flow 是否需要项目 setup，以它的当前契约为准。

大多数功能开发沿下面的主干推进：

```text
选择流程
  ask-matt
      ↓
工作目录中的需求与领域澄清
  grill-with-docs
      ↓
按规模分流
  小型工作：implement
  多 session：to-spec → to-tickets → 每个 ticket 独立 implement
      ↓
implement 内部
  tdd（适用时）→ code-review
```

`prototype` 是必须用可运行代码回答设计问题时的临时绕行，`research` 为澄清阶段提供一手资料，`wayfinder` 用于路线尚不清晰的超大工作。Bug、外部 issue、merge/rebase 冲突和架构维护分别从自己的入口进入，不是功能开发结束后的固定步骤。没有工作目录时，使用无状态的 `grill-me` 代替 `grill-with-docs`。

### 如何选择入口

| 当前情况 | 推荐入口 |
|---|---|
| 不确定该使用哪个 skill | `ask-matt` |
| Chipltech-Family Accelerator、DLC Platform、DLC Runtime、Real DLC Hardware 或 vLLM-DLC 工作 | 先用 `chipltech-context` 读取当前知识和能力目录，再加载最窄 owning Skill |
| 已有代码库，需要把设计问清楚 | `grill-with-docs` |
| 没有代码库，需要压力测试计划 | `grill-me` |
| 问题必须通过运行实验才能回答 | `prototype` |
| 需要阅读官方文档、源码或规范 | `research` |
| 工作巨大、路线尚不清晰，需要跨 session 逐项解决决策问题 | `wayfinder` |
| 讨论已经成熟，需要形成正式规格 | `to-spec` |
| 需要将规格拆为可独立实现的垂直切片 | `to-tickets` |
| 已有明确 spec 或 ticket | `implement` |
| 只需要测试先行实现一个具体行为 | `tdd` |
| 需要审查分支或 PR | `code-review` |
| 出现顽固 bug、偶现失败或性能回退 | `diagnosing-bugs` |
| 已完成诊断，需要压缩已闭合证据为 Sprint、Issue、owner 或 handoff 简述 | `technical-issue-summary` |
| 外部进入的 bug report 或 feature request 尚未 agent-ready | `triage`；不要 triage `to-tickets` 生成的 tickets |
| Git 已进入 merge/rebase 冲突 | `resolving-merge-conflicts` |
| 系统难理解、难测试或模块边界混乱 | `improve-codebase-architecture` 做 survey；选中机会后回到 `grill-with-docs` |
| 需要设计深模块、接口或测试 seam | `codebase-design` |
| 需要更新项目术语或 ADR | `domain-modeling` |
| 需要固化人工 dashboard、凭据或 cutover 步骤 | `wizard` |
| 决策信息掌握在另一个人手里 | `to-questionnaire` |

### 上下文管理

`grill-with-docs → to-spec → to-tickets` 尽量保持在同一个完整上下文中，让访谈、领域决策、规格和 tickets 使用同一套思考。每张 implementation ticket 再开启独立 session 执行 `implement`。

只在 phase boundary 决定继续、`/clear`、`/handoff`、subagent 或 `/compact`。同一 Harness 和目录中需要保留相关上下文时通常使用 `/compact`；只有需要跨 Harness、目录、同事，或创建可移植侧任务时才使用 `handoff`。完整决策树见 [`PHASE-BOUNDARIES.md`](./skills/engineering/ask-matt/PHASE-BOUNDARIES.md)。

## DLC/vLLM 专项体系

Chipltech-Family Accelerator 和 DLC/vLLM 工作统一从 `chipltech-context` 进入：

```text
Chipltech / DLC / vLLM-DLC 任务
  → chipltech-context
  → 读取配置知识库的当前 capability catalog 与正式 Contract
  → 加载最窄 owning Skill
  → 在 owning Skill 的授权、停止条件和 Claim Boundary 内执行
```

完整业务路由由配置知识库中的 `prompt-examples/all-supported-capabilities-quickstart.md` 维护，README 不复制第二套路由表。`chipltech-context` 是只读 router，不是执行 Evidence；它会实际加载当前 owning Skill，再由 owner 委托环境、硬件观察、诊断或交付子问题。

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

以下是 owning Skill 可能建立的委托关系，不是固定顺序，也不要求用户逐个手工调用；实际路由以当前 capability catalog 和 owning Skill 契约为准。

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

**Main-to-Main 只读影响分析**

```text
main-to-main-upgrade
→ 完整 upstream delta 分类
→ Patch Import Manifest impact report
→ DeepSeek TP=2 与 Llama TP=1 mandatory assignments
→ model-adaptation child evidence
→ 只报告 finalize eligibility；alignment unchanged，manifest report-only，finalize action none
```

## 40 个稳定 Skill

### Engineering：28 个

| Skill | 调用方式 | 作用 |
|---|---|---|
| [`ask-matt`](./skills/engineering/ask-matt/SKILL.md) | 用户调用 | 根据当前工作选择正确的 skill 或 flow |
| [`chipltech-context`](./skills/engineering/chipltech-context/SKILL.md) | 自动或用户调用 | 使用带引用的 Chipltech 工程知识路由任务 |
| [`codebase-design`](./skills/engineering/codebase-design/SKILL.md) | 自动或用户调用 | 提供深模块、接口、seam、leverage 和 locality 的共享设计语言 |
| [`code-review`](./skills/engineering/code-review/SKILL.md) | 自动或用户调用 | 从 Standards 和 Spec 两条独立轴审查 diff |
| [`diagnosing-bugs`](./skills/engineering/diagnosing-bugs/SKILL.md) | 自动或用户调用 | 建立可靠复现循环，通过可证伪假设定位根因 |
| [`technical-issue-summary`](./skills/engineering/technical-issue-summary/SKILL.md) | 自动或用户调用 | 将已闭合诊断证据压缩成准确、可追溯的跨团队简述 |
| [`dlc-env-setup`](./skills/engineering/dlc-env-setup/SKILL.md) | 自动或用户调用 | 重建并验证 DLC 工具链、PyTorch wheel 和可选 vLLM 环境 |
| [`dlc-hardware-observability`](./skills/engineering/dlc-hardware-observability/SKILL.md) | 自动或用户调用 | 使用官方 `cltech_smi` 采集规范化、只读的硬件证据 |
| [`domain-modeling`](./skills/engineering/domain-modeling/SKILL.md) | 自动或用户调用 | 维护当前项目的领域术语、`CONTEXT.md` 和 ADR |
| [`grill-with-docs`](./skills/engineering/grill-with-docs/SKILL.md) | 用户调用 | 对照代码、领域模型和 ADR 逐项澄清设计 |
| [`implement`](./skills/engineering/implement/SKILL.md) | 用户调用 | 根据 spec/tickets 实现、验证、审查并交付 |
| [`improve-codebase-architecture`](./skills/engineering/improve-codebase-architecture/SKILL.md) | 用户调用 | 寻找浅模块、耦合泄漏和测试困难等架构深化机会 |
| [`main-to-main-upgrade`](./skills/engineering/main-to-main-upgrade/SKILL.md) | 自动或用户调用 | 分析 vllm-dlc main 对齐 exact upstream full SHA 的完整影响 |
| [`model-adaptation`](./skills/engineering/model-adaptation/SKILL.md) | 自动或用户调用 | 处理具体模型的 Attention、MLA、MoE、量化、多模态、MTP 和分布式兼容 |
| [`modelzoo-image-validation`](./skills/engineering/modelzoo-image-validation/SKILL.md) | 自动或用户调用 | 资格验证本地模型并按门禁交付独立 DLC/TYD 镜像 |
| [`pd-separation`](./skills/engineering/pd-separation/SKILL.md) | 自动或用户调用 | 部署和诊断 MooncakeDLCConnector Prefill/Decode 分离 |
| [`pytorch-dlc-plugin-migration`](./skills/engineering/pytorch-dlc-plugin-migration/SKILL.md) | 自动或用户调用 | 将现有生产 PyTorch DLC Backend 行为迁移为标准 PrivateUse1 插件 |
| [`prototype`](./skills/engineering/prototype/SKILL.md) | 自动或用户调用 | 创建可分享的单文件逻辑演示或多方案 UI 原型回答设计问题 |
| [`research`](./skills/engineering/research/SKILL.md) | 自动或用户调用 | 基于高可信一手来源生成带引用的研究笔记 |
| [`resolving-merge-conflicts`](./skills/engineering/resolving-merge-conflicts/SKILL.md) | 自动或用户调用 | 理解双方意图并完成整个 merge/rebase 冲突流程 |
| [`setup-matt-pocock-skills`](./skills/engineering/setup-matt-pocock-skills/SKILL.md) | 用户调用 | 初始化 issue tracker、triage 标签和领域文档布局 |
| [`tdd`](./skills/engineering/tdd/SKILL.md) | 自动或用户调用 | 在预先确认的公共 seam 上逐垂直切片执行红、绿循环 |
| [`to-spec`](./skills/engineering/to-spec/SKILL.md) | 用户调用 | 将已经澄清的讨论整理并发布成正式 spec |
| [`to-tickets`](./skills/engineering/to-tickets/SKILL.md) | 用户调用 | 将 spec 拆成 tracer-bullet tickets 和 blocking edges |
| [`triage`](./skills/engineering/triage/SKILL.md) | 用户调用 | 通过状态机整理外部进入的 issue |
| [`wayfinder`](./skills/engineering/wayfinder/SKILL.md) | 用户调用 | 为跨多个 session 的大型模糊工作建立决策地图 |
| [`wizard`](./skills/engineering/wizard/SKILL.md) | 自动或用户调用 | 为只有人能完成的配置、凭据或 cutover 操作生成交互式脚本 |
| [`zoom-out`](./skills/engineering/zoom-out/SKILL.md) | 用户调用 | 从局部代码上升到模块、调用关系和领域全景 |

### Productivity：8 个

| Skill | 作用 |
|---|---|
| [`caveman`](./skills/productivity/caveman/SKILL.md) | 持续使用超压缩表达减少 token，同时保留技术准确性 |
| [`grill-me`](./skills/productivity/grill-me/SKILL.md) | 在没有代码库的场景下穷尽式访谈计划或设计 |
| [`grilling`](./skills/productivity/grilling/SKILL.md) | 按决策前沿分轮完成无遗漏访谈 |
| [`handoff`](./skills/productivity/handoff/SKILL.md) | 将当前会话压缩为下一位 Agent 可直接接续的交接文件 |
| [`teach`](./skills/productivity/teach/SKILL.md) | 建立长期、有状态的个性化学习工作区 |
| [`to-questionnaire`](./skills/productivity/to-questionnaire/SKILL.md) | 为掌握缺失信息的人生成异步问卷 |
| [`wait-what`](./skills/productivity/wait-what/SKILL.md) | 使用项目语言和简化英语重新解释未传达清楚的信息 |
| [`writing-for-agents`](./skills/productivity/writing-for-agents/SKILL.md) | 指导编写 skills、`AGENTS.md` 和其他 Agent 消费的文档 |

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

这是项目初始化命令，不是 Kilo Skills 安装命令。

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

**Kilo 与 Hermes：** Kilo Code 可以直接加载 `chipltech-context` 和 owning Skills，是完整可用入口。Hermes 的 `chipltech-engineering` profile 是可选执行器，不是 Chipltech 工程能力的统一前置条件；只有明确选择 Hermes 时才单独安装和验收。任何 Harness 中的 Skill 可发现性都不构成业务执行或 Runtime Evidence。

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
| `write-a-skill` | `writing-for-agents` |
| `writing-great-skills` | `writing-for-agents` |
| `vllm-dlc-model-adapter` | `model-adaptation` |
| `vllm-dlc-main2main` | `main-to-main-upgrade` |

安装脚本会清理已退休的生成型 symlink 或 command wrapper，但不会删除用户维护的真实文件和目录。

## 许可证和来源

本仓库基于 [mattpocock/skills](https://github.com/mattpocock/skills) 的可组合工程方法，并加入 ChipLTech 的 DLC/vLLM 稳定工作流、契约、验证工具和中文使用文档。每个 skill 的实际行为以对应 `SKILL.md` 为准。
