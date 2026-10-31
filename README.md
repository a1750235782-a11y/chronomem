# ChronoMem 文本记忆基线

这是一个在 Codex 辅助下编写的入门教学项目，用于学习 FastAPI、SQLite，以及 Agent Memory Leaderboard 的文本 Add/Search 请求格式。当前搜索使用字符串包含匹配；仓库提供 Render 部署配置，但尚未进行官方 Smoke 或 Full 评测，也没有竞赛成绩或新算法声明。

## 已完成的功能

- 按原顺序保存消息的角色、内容、来源时间和会话信息。
- 按 `user_id` 隔离检索范围；Search 不按 `session_id` 限制结果。
- SQLite 持久化，重启后保留记录与稳定的字符串记忆 ID。
- Add 同步提交事务后返回 HTTP 200，并原样返回请求标识。
- 相同用户、相同 `request_id` 和相同内容的重试不会重复写入。复用标识但改变内容时返回 HTTP 400。
- Add/Search 使用 `X-Api-Key`；未提供或错误密钥返回 HTTP 401。
- `/health` 无需鉴权，`/docs` 提供交互测试。

## Windows 本地运行

已经在 Windows、Python 3.14.6 环境验证。其他环境尚未验证。

首次安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\setup_local_key.py
```

已有虚拟环境和密钥时，直接启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn competition_app_secure:app --host 127.0.0.1 --port 8000 --reload
```

打开 `http://127.0.0.1:8000/docs`。服务从程序文件所在目录读取 `.env`；默认数据库名为 `chronomem_contract.db`。可以通过 `CHRONOMEM_DB_PATH` 设置持久盘上的数据库路径。

## Render 公网接入准备

仓库中的 `render.yaml` 配置了单个付费实例、5GB 持久盘、公开健康检查，以及自动生成的接口密钥。具体创建步骤、费用组成和接入验证见 [DEPLOY_RENDER.md](DEPLOY_RENDER.md)。

该配置是接入起点，正式 Full 前还需验证检索效果和容量。自动部署已关闭；评测期间需固定代码与配置版本。

## 密钥配置

`setup_local_key.py` 会在项目目录的 `.env` 中生成 `CHRONOMEM_API_KEY`，并补充 `.gitignore` 规则。它不会显示密钥，也不会替换已经存在的非空密钥。

`.env.example` 仅列出配置项；本地初始化请直接运行脚本，不必复制该文件。系统环境变量优先于 `.env`。接口密钥与主办方签发的 Eval Key 是两种凭证。

在第二个 PowerShell 窗口中，可将本地密钥复制到剪贴板：

```powershell
.\.venv\Scripts\python.exe -c "from dotenv import dotenv_values; print(dotenv_values('.env')['CHRONOMEM_API_KEY'])" | Set-Clipboard
```

随后在 `/docs` 的 Authorize 输入框中粘贴密钥。授权后的 Curl 示例会包含密钥，不应公开。

## 请求示例

所有 Add/Search 请求都需带 `X-Api-Key` 请求头。

`POST /add`：

```json
{
  "request_id": "local-add-001",
  "messages": [{"role": "user", "content": "我喜欢喝咖啡"}],
  "user_id": "demo-user-a",
  "session_id": "demo-session-1"
}
```

成功时返回 HTTP 200，JSON 包含 `success: true` 以及原请求中的 `request_id`、`user_id`、`session_id`。

`POST /search`：

```json
{
  "query": "咖啡",
  "user_id": "demo-user-a",
  "top_k": 100
}
```

返回示例：

```json
{"data": [{"id": "mem_1", "content": "我喜欢喝咖啡"}]}
```

没有匹配时返回 `{"data": []}`。结果不超过 `top_k`。本原型中所有包含查询字符串的匹配项视为同分，按写入顺序打破平局。

## 当前限制与部署前工作

当前版本仅支持文本，使用大小写不敏感的字面字符串匹配，未实现语义检索、自然语言问题分解或时序记忆推理。数据量、并发、延迟、恢复流程及正式评测效果尚未验证。

公开部署前仍需准备稳定的公网 HTTPS 地址、持久化存储、容量说明、日志与数据清理策略，以及公开发布时的维护者署名和许可证。开发用 `--reload` 不作为正式部署方式。

密钥、数据库、虚拟环境和本地备份不应提交仓库。`.gitignore` 可防止新文件被误加入，但不能移除已提交过的敏感文件。

## 官方资料

- 比赛主页：https://agentmemoryleaderboard.ai/competition/
- 参赛说明：https://agentmemoryleaderboard.ai/rules
- API 指南：https://agentmemoryleaderboard.ai/api-guide

该项目名称不表示官方认可；是否符合参赛要求以及评测受理结果，以官方当期规则与审核为准。
