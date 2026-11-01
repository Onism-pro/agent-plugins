# agent-plugins

给 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 用的插件与工具合集。
目前收录一套**记忆维护**工具——不替换你的记忆插件，只在它旁边补三件它通常没有的事。

## 目录

| 路径 | 是什么 |
|---|---|
| `plugins/memory_rawlog/` | 原文日志插件 |
| `scripts/` | 对话压缩、证据审计、遗忘体检 |
| `docs/` | 设计说明、部署步骤 |

## 记忆维护三件套

| 层 | 解决什么 | 形态 |
|---|---|---|
| **原文日志** | 想不起「他明明说过」时，没有原始底稿可查 | 插件 `memory_rawlog`，按天写 jsonl，滚动保留 |
| **对话压缩** | 上下文越聊越长，每轮更慢更贵，注意力被稀释 | 脚本，把老对话压成一页摘要笔记再裁掉原文 |
| **审计** | 说不清是「没记住」还是「记住了没用上」 | 两个脚本：证据审计（漏记了哪些）、遗忘体检（哪些该淡出） |

三条原则：**原文先留着**（不归纳、不进 prompt）、**压缩成笔记而不是删掉**、**审计只报告不自动改**。

> 这三件是自用的，抽出来能独立跑；如果你想要完整的记忆架构（事实库 + 打分 + 事实卡 + 工作台），可以看 [DeepSeek-memory-Ido1um](https://github.com/Ido1um/DeepSeek-memory-Ido1um)，本项目的分层思路受它启发。

## 快速开始

### 1. 原文日志（插件）

把 `plugins/memory_rawlog/` 整个目录拷到 AstrBot 的 `data/plugins/` 下，重启。它会在
`data/plugin_data/memory_rawlog/hot/` 里按天写 `YYYY-MM-DD.jsonl`，默认保留 7 天。

插件配置可覆盖：`keep_days`（默认 7）、`dir`（自定义目录）。

### 2. 对话压缩（脚本）

```bash
export MEMORY_KIT_API_KEY=sk-xxx          # 任何 OpenAI 兼容接口
export MEMORY_KIT_API_BASE=https://api.deepseek.com/v1
export MEMORY_KIT_MODEL=deepseek-chat

python3 scripts/compact_history.py \
  --db /path/to/data_v4.db \
  --umo "wechat:FriendMessage:xxxx@im.wechat" \
  --note-dir /path/to/notes \
  --trigger 90 --keep 50            # 先试运行，看清楚摘要再决定
```

确认摘要没问题后加 `--apply`。**写库前要停掉机器人**，否则会被进程里的缓存覆盖。
`scripts/compact_run.sh` 已经把「判断条数 → 停容器 → 压缩 → 起容器」串好了：

```bash
UMO=... DB=... NOTE_DIR=... ./scripts/compact_run.sh
```

### 3. 审计（脚本）

```bash
# 证据审计：这几天说过的话里，有哪些事实没进记忆库
python3 scripts/audit_evidence.py --hot .../hot --db .../simple_memory.db --days 7

# 遗忘体检：按「强度 × 半衰期」找该淡出的记忆（默认只看不写）
python3 scripts/audit_forget.py --db .../simple_memory.db
```

两个脚本都只读；`audit_forget.py --apply` 会把条目搬进 `memory_archive`（不删除，可恢复），并在动作前备份数据库。

## 定时任务

```cron
40 4 * * *  /bin/bash /opt/memory-kit/scripts/compact_run.sh
50 4 * * 1  python3 /opt/memory-kit/scripts/audit_evidence.py --hot ... --db ... --days 7
45 4 * * 0  python3 /opt/memory-kit/scripts/audit_forget.py --db ... --apply
```

建议排在备份之后。压缩和遗忘都会写库，选在机器人空闲的凌晨。

## 依赖

- AstrBot 4.x（插件部分）
- `audit_forget.py` / `audit_evidence.py` 读取 **angel_memory** 插件（`astrbot_plugin_angel_memory`）的
  SQLite 表结构；其他记忆插件需要改 `--table` 或自行调整 SQL
- Python 3.9+，脚本只用标准库

## 已知限制

- **表结构会变**：脚本直接读 SQLite，上游插件改字段就可能失效，升级后请先跑一次试运行。
- **压缩是有损的**：摘要能保住「发生过什么、说了什么」，保不住原话。真要抠细节，靠原文日志。
- **遗忘体检需要时间**：库不满一个月基本挑不出东西，这是设计如此，不是坏了。
- **原文日志含明文对话**：注意磁盘权限和备份策略，别把 `hot/` 提交进仓库。

## 许可

MIT
