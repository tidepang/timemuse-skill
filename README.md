# TimeMuse Skill

让外部 AI 在讨论你的经历、项目投入和想法时，按需查询 TimeMuse 的本地记录。不必每次说“查询 TimeMuse”；是否自然触发仍取决于 AI 客户端及当次对话。

这是独立分发的只读 Skill，不是 TimeMuse App，也不是云同步或 MCP 服务。没有登录、API Key、第三方 Python 包或后台进程，不要求 App 正在运行；需要本机已有 TimeMuse 数据库和 Python 3.9+（含系统 IANA 时区数据）。数据库结构变化时需要更新适配。

## 安装

先下载并检查代码，再运行本地安装脚本，不使用远程脚本管道。可以下载本仓库 ZIP 并解压，或在终端执行：

```sh
git clone https://github.com/tidepang/timemuse-skill.git
cd timemuse-skill
```

阅读 `scripts/install.py` 和 `scripts/evidence.py` 后，在你自己的终端运行：

```sh
python3 scripts/install.py --timezone Asia/Shanghai
```

将 `Asia/Shanghai` 换成 TimeMuse 使用的本地 IANA 时区，例如 `America/Los_Angeles`。第一版安装到 Codex 的 `${CODEX_HOME:-$HOME/.codex}/skills/timemuse-skill`。其他客户端的兼容性与自然发现行为尚未验证。

安装流程会接着列出数据库位置、时区、读取范围和外部 AI 提示。确认后输入 `ALLOW TIMEMUSE EVIDENCE` 才启用读取；输入其他内容则保留安装但取消本次授权。这不是 macOS 系统权限。AI 助手不得代替用户自行同意。

默认范围是时间块、时间块备注、随手想法、已保存日反馈、Todo 和 Project 周目标，覆盖这些类型的历史记录；每次查询最多 93 天，不等于一次导出全部历史。可用 `--types blocks,block_notes` 等参数缩小范围。应用活动 `activity` 需显式加入，不默认包含。

暂不启用读取：

```sh
python3 scripts/install.py --install-only
```

此选项不会撤销已有授权。首次安装后，必要时新建 AI 对话，让客户端重新发现 Skill。

## 隐私与读取范围

- 选出的记录会返回 AI 对话，可能由该客户端的外部 AI 服务处理；不是全程本地推理。
- 查询工具不修改数据库，不上传文件、不缓存内容、不自动发布，不返回截图、原始 OCR、Muse 对话、窗口标题或原始 URL 列。
- 用户自己写的备注、Todo 等仍可能含私人内容和 URL，不会自动匿名化。只启用你愿意交给该 AI 的类型。
- 时间投入不等于成果，Todo 和目标是意图；当前可修改文字不代表当时的历史快照。回答应保留日期与来源，并区分记录和推测。
- 只读及范围限制由此查询工具执行，不是对其他本机程序的系统级隔离。授权读取不等于授权向他人发送。

完整字段、日期边界、限制和错误语义见 [Evidence Contract](references/contract.md)。

## 检查、修改与撤销

在已安装的 Skill 目录运行以下命令（Codex 默认目录可用 `cd "${CODEX_HOME:-$HOME/.codex}/skills/timemuse-skill"` 进入）：

```sh
python3 scripts/evidence.py status
python3 scripts/evidence.py setup --timezone Asia/Shanghai --types blocks,block_notes
python3 scripts/evidence.py revoke
```

`status` 和 `setup` 不读取数据库。授权仅保存在本机 `~/Library/Application Support/TimeMuseSkill/consent.json`。重新 setup 会替换范围，revoke 对之后的查询生效，不会收回已进入对话的内容或正在执行的读取。

非标准数据位置可在 setup 时指定 `--database /absolute/path/to/timemuse.sqlite` 和 `--profile`；默认 profile 为 `local-profile`。不要把数据库或授权文件提交到 GitHub。

## 更新与卸载

下载新版本、检查改动后，运行：

```sh
python3 scripts/install.py --update --install-only
```

已有安装默认不会被覆盖；`--update` 仅接受识别为 TimeMuse Skill 的目录，并将原目录完整保留在客户端根目录下的 `skill-backups/`，不放进 Skill 发现目录。符号链接安装需要手动管理。更新保留已有授权，不自动扩大读取范围。

卸载时先运行 `revoke`，再删除客户端里的 `timemuse-skill` 目录；备份可自行清理。不会删除 TimeMuse 的记录。

## 验证

```sh
python3 -m unittest discover -s tests
```

测试只使用临时目录和模拟数据，不读取真实数据库。自然触发可试问“帮我回想上周做了什么”或“这个想法我以前记过吗”；一般知识问题不应读取个人记录。
