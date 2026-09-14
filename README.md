# TimeMuse Skill

让 AI 在讨论你的经历、项目投入和想法时，自然引用 TimeMuse 的记录，不必每次点名调用。

## 安装

把这句话发给你的 Agent：

> 请帮我安装 TimeMuse Skill：https://github.com/tidepang/timemuse-skill ，按默认设置完成安装。

也可以在终端运行：

```sh
git clone https://github.com/tidepang/timemuse-skill.git
cd timemuse-skill
python3 scripts/install.py
```

目前支持 Codex，需要 macOS 和 Python 3.9+。默认使用本机时区；更新时自动备份旧版，保留已有设置。其他 Agent 客户端尚未验证，不支持时请说明，不要套用 Codex 安装路径。

安装完成即可使用，不需要额外授权或选择配置。默认读取你自己的时间块、备注、想法、已保存日反馈、Todo 和周目标。查询结果交给当前 AI 服务处理；Skill 只读，不修改原始记录，也不读取截图或 OCR。

## 使用

直接问“帮我回想上周做了什么”或“这个想法我以前记过吗”。AI 会按问题查找记录，并附上日期与来源。自然触发取决于客户端；安装后必要时新建一个对话。

想停止读取时，让 Agent 撤销 TimeMuse Skill 的启用，或在已安装目录运行 `python3 scripts/evidence.py revoke`。

自定义范围、数据位置、卸载及技术边界见 [详细说明](references/contract.md)。
