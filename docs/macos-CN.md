[English](../README.md) | [简体中文](../README-CN.md)

# Codex 回复完成提示音

Codex 每轮回复结束后，在 macOS 本地播放提示音。

这个 Skill 使用 Codex 官方的用户级 `notify` 配置。完成一次配置后，新建任务和已有任务只要加载同一份 `~/.codex/config.toml`，都可以触发提示音。仓库同时提供内置音效、交互式切换、更新工具、隐私友好的日志和回归测试。

> 本仓库基于 [zty42/codex-sound-notifications](https://github.com/zty42/codex-sound-notifications) 修改。原项目由 zty42 创建，并采用 MIT License。本分支保留原作者署名，主要修复实际使用中发现的 Codex Desktop 兼容问题。

## 这个版本修复了什么

- 正确解析 Codex 追加在 `notify` 命令末尾的 JSON payload
- 默认使用直接通知模式，避免多层包装、递归包装和辅助进程卡住
- 支持按需转发原有通知命令，并设置 5 秒超时
- 兼容部分 Codex Desktop 集成产生的空回调
- 对短时间内的重复调用做跨进程去重
- 兼容部分 macOS 自带的 Python 3.9
- 默认不把提示词或回复正文写入日志
- 当前包含 39 项本地回归测试

## 运行条件

- macOS
- 支持 `notify` 的 Codex Desktop 或 Codex CLI
- Python 3.9 或更高版本
- macOS 自带的 `afplay`
- `~/.codex/config.toml` 可写

## 安装

把仓库克隆到 Codex 的用户级 Skill 目录：

```bash
mkdir -p ~/.codex/skills
git clone https://github.com/Qin-jiahao/codex-sound-notifications.git \
  ~/.codex/skills/codex-sound-notifications
cd ~/.codex/skills/codex-sound-notifications
python3 scripts/setup_sound_notifications.py --sound-file celebration.wav
```

配置完成后，请彻底退出 Codex 再重新打开。已经运行的 App 进程可能仍然使用旧配置。

你也可以在 Codex 对话中调用 `$skill-installer`：

```text
$skill-installer install https://github.com/Qin-jiahao/codex-sound-notifications
```

`$skill-installer` 只负责复制 Skill 文件，不会自动写入完成回调。安装后仍需执行一次上面的配置命令。

## 验证是否生效

先预览音效：

```bash
python3 scripts/manage_sound_notifications.py --preview celebration.wav
```

再确认用户级配置里存在顶层 `notify`：

```bash
grep '^notify =' ~/.codex/config.toml
```

重启 Codex 后发送一条普通消息。回复结束时应播放提示音。

## 管理提示音

打开交互式选择器：

```bash
python3 scripts/manage_sound_notifications.py
```

常用的非交互命令如下：

```bash
python3 scripts/manage_sound_notifications.py --list
python3 scripts/manage_sound_notifications.py --preview button.wav
python3 scripts/manage_sound_notifications.py --apply button.wav --yes
python3 scripts/manage_sound_notifications.py --check-update
python3 scripts/manage_sound_notifications.py --update
```

你也可以直接在 Codex 对话里调用：

```text
$codex-sound-notifications 列出声音
$codex-sound-notifications 预览 celebration.wav
$codex-sound-notifications 切换到 button.wav
$codex-sound-notifications 检查更新
```

## 已有 `notify` 配置时怎么处理

安装器默认替换当前顶层 `notify`。实际测试表明，这个模式在 Codex Desktop 中更稳定，也是本仓库重点验证的模式。

如果已有其他程序依赖 `notify`，可以显式保留，并在播放声音后继续调用它：

```bash
python3 scripts/setup_sound_notifications.py \
  --sound-file celebration.wav \
  --preserve-existing-notify
```

保留模式会把旧命令序列化成 JSON，再把 Codex payload 作为最后一个命令行参数传给旧程序。等待时间上限为 5 秒。旧程序需要支持从命令行参数读取 payload。如果旧程序只读取标准输入，或者它会再次改写 `notify`，仍可能发生兼容问题。

## 导入本地音效

安装器可以从本地 zip 中提取一个 WAV 文件，并保存到 `assets/sounds/`：

```bash
python3 scripts/setup_sound_notifications.py \
  --zip-path /path/to/sounds.zip \
  --sound-file custom.wav
```

脚本只读取本地文件，同时会忽略 zip 中常见的 macOS 元数据条目。

## 日志与隐私

运行时诊断日志位于 `/tmp/codex-sound-notify.log`。

日志默认记录时间、事件匹配、播放状态和退出码，不记录提示词或回复正文。运行时参数 `--log-payload-preview` 可以额外记录 payload 的前 200 个字符，仅建议临时排障时使用，因为其中可能包含对话内容。

```bash
tail -n 20 /tmp/codex-sound-notify.log
```

## 常见问题

### 预览能响，回复结束不响

1. 彻底退出所有 Codex 窗口，然后重新打开 App。
2. 确认 `notify` 位于 `~/.codex/config.toml` 顶层，并且出现在第一个 `[配置段]` 之前。
3. 不带 `--preserve-existing-notify` 重新运行安装器。
4. 完成一轮回复后，检查 `/tmp/codex-sound-notify.log` 是否新增记录。

### 只响一次，后续不再响

请更新到当前版本，再运行一次安装器。早期实现用进程相对的单调时钟做跨进程去重。在部分 macOS 系统 Python 中，不同进程的时间值不可直接比较。当前版本改用可比较的系统时间戳。

### 一轮回复响两次

请检查是否还有其他通知层同时播放声音。Codex `notify`、终端通知和 `[tui].notifications` 属于不同机制。这个 Skill 只配置 `notify`，并会抑制 250 毫秒内收到的重复调用。

### 安装时报 `tomllib` 导入错误

这个错误来自旧版本。当前分支只使用 Python 3.9 已有的标准库能力。

### 更新失败

如果安装目录是 Git 仓库，更新命令只做快进拉取，并在存在本地修改时拒绝覆盖。归档方式安装的副本通过 GitHub 仓库接口更新，同时保留额外添加的本地音效。

## 测试

```bash
python3 scripts/test_sound_notifications.py
```

测试覆盖配置替换和保留、payload 解析、完成事件筛选、重复调用抑制、音效导入、交互式管理和更新流程。

## 目录结构

```text
codex-sound-notifications/
├── SKILL.md
├── agents/openai.yaml
├── assets/sounds/*.wav
└── scripts/
    ├── codex_sound_notify.py
    ├── manage_sound_notifications.py
    ├── setup_sound_notifications.py
    └── test_sound_notifications.py
```

## 使用范围与限制

- 当前使用 `afplay`，所以播放功能只支持 macOS。
- 每台本地电脑或远程 Codex 主机都需要单独配置。
- 配置后需要让 Codex 重新加载 `~/.codex/config.toml`，彻底重启最稳妥。
- 这个项目是 Skill 和本地脚本，不是 Codex 原生设置面板或斜杠命令。
- 任意第三方通知包装器的兼容性无法完全保证。

## 署名与许可证

原项目和原始代码作者为 [zty42](https://github.com/zty42)。本仓库保留上游 MIT License，具体修改记录见 [CHANGELOG.md](../CHANGELOG.md)。

仓库中的 WAV 文件从上游项目原样继承。上游 README 将音效来源标为 [SND](https://snd.dev/)。更具体的来源说明见 [ASSETS.md](../ASSETS.md)。本分支不对第三方音效主张额外权利。

## 参考资料

- [Codex 配置参考](https://developers.openai.com/codex/config-reference)
- [Codex Hooks](https://developers.openai.com/codex/hooks)
- [原始仓库](https://github.com/zty42/codex-sound-notifications)
