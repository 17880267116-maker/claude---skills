# claude---skills

Claude Code 技能集合，让 AI 助手获得专业领域能力。

---

## 已收录技能

### social-crawler — 小红书博主数据爬取

定向爬取小红书博主数据，支持多维度筛选，输出 CSV 可直接用 Excel 打开。

**触发方式**：

```
/crawl 博主名
爬取 XXX 最近一个月的数据
帮我抓 XXX 的笔记，只要点赞超过 100 的
```

**筛选参数**：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `blogger` | 小红书博主昵称 | 必填 |
| `--days` | 最近 N 天 | 30 |
| `--max` | 最多取 N 条 | 0（不限） |
| `--min-likes` | 最低点赞数 | 0（不限） |
| `--type` | video / normal / all | video |
| `--token` | TikHub API Token | 自动读取 |
| `--output` | 输出目录 | ./data |

**返回数据**：

CSV 文件，包含：标题、文案、点赞、评论、收藏、转发、发布时间、笔记链接

**使用示例**：

```bash
# 首次使用需指定 token
python crawl.py 好运聊AI --token 你的tikhub_token

# 配置好环境变量后可省略
python crawl.py 好运聊AI --days 14 --max 10 --min-likes 50 --type video
```

**API Token 配置（首次使用必读）**：

三种方式任选其一：

1. 命令行参数：`python crawl.py 博主名 --token 你的token`
2. 环境变量（推荐）：`export TIKHUB_API_TOKEN=你的token`
3. 配置文件：`~/.xiaohongshu/tikhub_config.json` 写入 `{"api_token": "你的token"}`

Token 获取：联系 TikHub 官方获取 API Key。

**支持平台**：

| 平台 | 状态 | 说明 |
|------|------|------|
| 小红书 | 支持 | 基于 TikHub API |
| 抖音 | 不支持 | TikHub 暂不支持 |
| 视频号 | 不支持 | 无可用 API |

**依赖**：

- `blogger-distiller` 项目中的 `TikHubClient`
- Python 3.8+

---

## 安装

将 `SKILL.md` 和 `crawl.py` 放入 `~/.claude/skills/social-crawler/` 目录即可被 Claude Code 识别。
