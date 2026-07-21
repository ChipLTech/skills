# mattpocock/skills 在 Kilo Code 中的安装与验证

这份文档面向使用 Kilo Code 的用户，说明如何把本仓库里的 Matt Pocock skills 安装到 Kilo Code，并验证是否安装成功。

如果你还没有拉取仓库，可以先克隆：

```bash
git clone https://github.com/ChipLTech/skills.git
cd skills
```

后续命令默认都在仓库根目录执行。

## 1. 你会安装什么

本仓库里的 skills 位于：

```text
./skills/
```

主要分为几类：

- `engineering/`：工程开发类，例如 `ask-matt`、`implement`、`research`、`resolving-merge-conflicts`、`wayfinder`、`diagnosing-bugs`、`code-review`、`tdd`、`to-spec`、`to-tickets`，并保留本地的 `dlc-env-setup`、`model-adaptation`、`modelzoo-image-validation`、`main-to-main-upgrade` 和 `zoom-out`
- `productivity/`：生产力类，例如 `grill-me`、`handoff`、`teach`、`writing-great-skills`，并保留本地的 `caveman`
- `misc/`：杂项工具类，例如 `setup-pre-commit`、`git-guardrails-claude-code`
- `personal/`：Matt 个人工作流，默认不安装
- `in-progress/`：草稿技能，默认不安装
- `deprecated/`：废弃技能，默认不安装

本仓库已经提供 Kilo Code 安装脚本：

```text
./scripts/link-kilo-skills.sh
```

脚本默认会把正式可用的 skills 链接到 Kilo Code 的全局配置目录：

```text
~/.config/kilo/skills/
```

如果加上 `--with-commands`，还会生成 Kilo slash command 包装器：

```text
~/.config/kilo/command/
```

生成后你可以在 Kilo Code 里使用类似下面的命令：

```text
/diagnosing-bugs 支付成功后偶尔生成两个订单，请帮我定位原因
/tdd 实现课程收藏功能，优先测试刷新后仍保持收藏状态
/grill-with-docs 我想给订单系统增加部分退款能力
/model-adaptation 请只路由：这个特定新模型在 DLC Platform 上加载失败，检查模型级兼容边界
/modelzoo-image-validation Qwen2-7B，先只读解析 ModelZoo；同名时阻断并要求 framework selector
/main-to-main-upgrade 请只路由：分析 vllm-dlc main 对齐 exact upstream full SHA 的完整兼容影响
```

## 2. 推荐安装方式：全局安装

如果你希望所有 Kilo Code 项目都能使用这些 skills，执行：

```bash
./scripts/link-kilo-skills.sh --with-commands
```

这个命令会做两件事：

1. 把 skills 链接到：

```text
~/.config/kilo/skills/<skill-name>
```

2. 把 slash command 包装器写到：

```text
~/.config/kilo/command/<command-name>.md
```

例如：

```text
~/.config/kilo/skills/diagnosing-bugs -> <repo>/skills/engineering/diagnosing-bugs
~/.config/kilo/skills/model-adaptation -> <repo>/skills/engineering/model-adaptation
~/.config/kilo/skills/modelzoo-image-validation -> <repo>/skills/engineering/modelzoo-image-validation
~/.config/kilo/skills/main-to-main-upgrade -> <repo>/skills/engineering/main-to-main-upgrade
~/.config/kilo/command/diagnosing-bugs.md
~/.config/kilo/command/model-adaptation.md
~/.config/kilo/command/modelzoo-image-validation.md
~/.config/kilo/command/main-to-main-upgrade.md
```

安装完成后，重启 Kilo Code 或打开一个新 session。

## 3. 只给当前项目安装

如果你只想在某个项目中使用，不想污染全局配置，可以安装到项目的 `.kilo/` 目录。

示例：

```bash
./scripts/link-kilo-skills.sh --project /path/to/your-project --with-commands
```

安装后目录结构类似：

```text
/path/to/your-project/
└── .kilo/
    ├── skills/
    │   ├── diagnosing-bugs -> <repo>/skills/engineering/diagnosing-bugs
    │   ├── tdd -> <repo>/skills/engineering/tdd
    │   └── grill-with-docs -> <repo>/skills/engineering/grill-with-docs
    └── command/
        ├── diagnosing-bugs.md
        ├── tdd.md
        └── grill-with-docs.md
```

项目级安装适合团队仓库，因为配置可以跟项目放在一起。

## 4. 只安装 skills，不生成 slash commands

如果你不需要 `/diagnosing-bugs` 这种 slash command，只想让 Kilo Code 能读取 skills，可以执行：

```bash
./scripts/link-kilo-skills.sh
```

这种情况下，建议在对话里明确点名 skill：

```text
请使用 diagnosing-bugs skill 来诊断这个 bug：支付成功后偶尔生成两个订单。
```

或者：

```text
请使用 tdd skill，按红绿重构流程实现课程收藏功能。
```

## 5. 安装全部 skills

默认安装范围是：

- `engineering/`
- `productivity/`
- `misc/`

因此默认安装不需要 `--all`，会包含 `model-adaptation`、`modelzoo-image-validation` 和 `main-to-main-upgrade` 这些 stable engineering skills 及其 slash command 包装器。ModelZoo 模型名解析和 DLC/TYD 镜像 workflow 应路由到 `modelzoo-image-validation`；特定模型加载/服务兼容问题应路由到 `model-adaptation`；exact upstream full SHA 对齐或完整兼容影响分析应路由到 `main-to-main-upgrade`。

默认不会安装：

- `personal/`
- `in-progress/`
- `deprecated/`

如果你确实想安装 `personal/` 和 `in-progress/`，可以加 `--all`：

```bash
./scripts/link-kilo-skills.sh --all --with-commands
```

不建议新人一开始使用 `--all`，因为其中有些 skill 是 Matt 个人环境专用或还在草稿阶段。

## 6. 查看脚本帮助

```bash
./scripts/link-kilo-skills.sh --help
```

你会看到类似输出：

```text
Link Matt Pocock skills into Kilo Code.

Options:
  --with-commands       Also create slash-command wrappers in command/.
  --project <path>      Install into <path>/.kilo instead of ~/.config/kilo.
  --dest <path>         Custom skills destination directory.
  --command-dest <path> Custom command destination directory.
  --all                 Include personal/ and in-progress/ skills too.
  -h, --help            Show this help.
```

## 7. 验证安装是否成功

### 7.1 验证 skills 目录

全局安装后，检查：

```bash
ls -la ~/.config/kilo/skills
```

你应该能看到类似：

```text
diagnosing-bugs -> <repo>/skills/engineering/diagnosing-bugs
tdd -> <repo>/skills/engineering/tdd
to-spec -> <repo>/skills/engineering/to-spec
to-tickets -> <repo>/skills/engineering/to-tickets
grill-with-docs -> <repo>/skills/engineering/grill-with-docs
```

如果是项目级安装，检查：

```bash
ls -la /path/to/your-project/.kilo/skills
```

### 7.2 验证 SKILL.md 是否存在

以 `diagnosing-bugs` 为例：

```bash
test -f ~/.config/kilo/skills/diagnosing-bugs/SKILL.md && echo "diagnosing-bugs installed"
```

如果安装成功，会输出：

```text
diagnosing-bugs installed
```

也可以直接查看 skill 内容：

```bash
sed -n '1,20p' ~/.config/kilo/skills/diagnosing-bugs/SKILL.md
```

你应该能看到：

```text
---
name: diagnosing-bugs
description: Disciplined diagnosis loop for hard bugs and performance regressions...
---
```

### 7.3 验证 slash commands

如果安装时加了 `--with-commands`，检查：

```bash
ls -la ~/.config/kilo/command
```

你应该能看到：

```text
diagnosing-bugs.md
model-adaptation.md
modelzoo-image-validation.md
main-to-main-upgrade.md
tdd.md
to-spec.md
to-tickets.md
grill-with-docs.md
```

查看某个 command：

```bash
sed -n '1,30p' ~/.config/kilo/command/diagnosing-bugs.md
```

内容应该类似：

```md
---
description: Disciplined diagnosis loop for hard bugs and performance regressions...
---

请使用 `diagnosing-bugs` skill，严格按它的流程处理下面的问题：

$ARGUMENTS
```

### 7.4 在 Kilo Code 里验证

重启 Kilo Code 或打开新 session 后，在聊天框输入：

```text
/diagnosing-bugs 测试一下：请说明 diagnosing-bugs skill 的工作流程，不要改代码。
```

如果 slash command 生效，agent 应该会按 `diagnosing-bugs` 的流程解释：

- 先建立反馈循环
- 再复现问题
- 再提出可证伪假设
- 再插桩验证
- 最后修复、回归测试、清理调试代码

也可以验证自然语言调用：

```text
请使用 tdd skill，简单说明红绿重构流程，不要改代码。
```

也可以验证 vLLM-DLC publication 路由边界：

```text
这个特定新模型在 DLC Platform 上加载失败，请只路由到合适 skill，不要运行命令或修改文件。
/model-adaptation 请只处理参数转发：检查这个模型的 Attention、tokenizer 和部署 profile 兼容边界。
把 vllm-dlc main 对齐到 exact upstream full SHA 1111111111111111111111111111111111111111，并只分析兼容影响。
/main-to-main-upgrade 请只处理参数转发：分析 exact upstream full SHA 的完整 compatibility-impact range。
```

这两个 skills 的 publication 只描述 capability 与 routing boundary。Ticket 06 的 exact v12 profiles 仅完成 operational regression，保持 `authoritativeness: operational_only`、`acceptance_eligible: false`、alignment unchanged、manifest report-only 和 finalization `none`；这不等于 Real DLC Hardware acceptance、Verified vLLM Alignment、DLC Runtime dispatch 或其他更强执行结论。

如果 skill 被正确加载，agent 应该会强调：

- 先写一个失败测试
- 写最小实现让测试通过
- 一次只做一个行为
- 全部通过后再重构
- 测试 public interface，不测试实现细节

## 8. 常见问题

### 8.1 Kilo Code 里输入 `/diagnosing-bugs` 没反应

先确认 command 文件是否存在：

```bash
ls -la ~/.config/kilo/command/diagnosing-bugs.md
```

如果不存在，重新安装并加上 `--with-commands`：

```bash
./scripts/link-kilo-skills.sh --with-commands
```

然后重启 Kilo Code 或打开新 session。

### 8.2 command 存在，但 skill 没有被正确使用

检查 skill 是否存在：

```bash
test -f ~/.config/kilo/skills/diagnosing-bugs/SKILL.md && echo ok
```

如果没有输出 `ok`，说明 skill 链接没有成功。重新执行：

```bash
./scripts/link-kilo-skills.sh --with-commands
```

### 8.3 不想用全局配置怎么办

使用项目级安装：

```bash
./scripts/link-kilo-skills.sh --project /path/to/your-project --with-commands
```

然后在 `/path/to/your-project` 里打开 Kilo Code。

### 8.4 已经有同名 skill，脚本会覆盖吗

如果目标位置是已有真实目录或文件，脚本会跳过，不会删除。

例如：

```text
skip diagnosing-bugs: ~/.config/kilo/skills/diagnosing-bugs already exists and is not a symlink
```

如果目标位置是 symlink，脚本会更新 symlink 指向本仓库里的 skill。

### 8.5 修改了本仓库里的 skill，Kilo 里会同步吗

会。脚本使用的是 symlink，不是复制。

例如：

```text
~/.config/kilo/skills/diagnosing-bugs -> <repo>/skills/engineering/diagnosing-bugs
```

所以你修改 `<repo>/skills/engineering/diagnosing-bugs/SKILL.md` 后，Kilo 读取到的也是同一份文件。

如果 Kilo 当前 session 已经加载过旧内容，建议打开新 session。

## 9. 推荐新人先验证的 5 个 skill

安装完成后，建议先试这 5 个：

```text
/grill-with-docs 我想实现一个课程收藏功能，请先追问需求边界，不要写代码。
```

```text
/diagnosing-bugs 测试一下 diagnosing-bugs 流程：假设登录接口偶尔返回 500，你会怎么排查？不要改代码。
```

```text
/tdd 请说明如何用红绿重构实现课程收藏功能，不要改代码。
```

```text
/to-spec 请把我们刚才关于课程收藏功能的讨论整理成 spec 草稿，不要发布 issue。
```

```text
/to-tickets 请把课程收藏功能拆成 tracer-bullet tickets，只输出拆分方案，不要创建 issue。
```

这些验证命令都要求“不改代码”，适合确认 skill 是否可用。

## 10. 推荐日常使用方式

需求不清时：

```text
/grill-with-docs 我想实现 <功能>，请结合代码库追问我直到需求边界清楚。
```

写新功能时：

```text
/tdd 实现 <功能>。优先测试 <最重要的用户可观察行为>。
```

排查 bug 时：

```text
/diagnosing-bugs <bug 描述>。请先建立可重复的失败信号，不要直接猜原因。
```

沉淀需求时：

```text
/to-spec 请把当前讨论整理成 spec。
```

拆任务时：

```text
/to-tickets 请把这个 spec 拆成多个 tracer-bullet tickets，并注明 blocking edges。
```

## 11. 卸载方式

如果是全局安装，删除：

```bash
rm -rf ~/.config/kilo/skills/diagnosing-bugs \
  ~/.config/kilo/skills/tdd \
  ~/.config/kilo/skills/to-spec \
  ~/.config/kilo/skills/to-tickets \
  ~/.config/kilo/skills/grill-with-docs
```

如果你想删除所有由脚本链接的 skills，可以先查看：

```bash
ls -la ~/.config/kilo/skills
```

确认都是指向本仓库目录的 symlink 后，再批量删除。

如果安装了 commands，也可以删除：

```bash
rm -f ~/.config/kilo/command/diagnosing-bugs.md \
  ~/.config/kilo/command/tdd.md \
  ~/.config/kilo/command/to-spec.md \
  ~/.config/kilo/command/to-tickets.md \
  ~/.config/kilo/command/grill-with-docs.md
```

项目级安装则删除项目里的 `.kilo/skills/` 和 `.kilo/command/` 中对应文件即可。

## 12. 最短路径

如果你只想快速开始，按下面三步走：

1. 安装：

```bash
./scripts/link-kilo-skills.sh --with-commands
```

2. 重启 Kilo Code 或打开新 session。

3. 在 Kilo Code 中输入：

```text
/diagnosing-bugs 测试一下 diagnosing-bugs skill 的流程，不要改代码。
```

如果 agent 能按 diagnosing-bugs 的调试流程回答，就说明安装基本成功。
