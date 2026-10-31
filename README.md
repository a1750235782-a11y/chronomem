# ChronoMem：文本 BM25 记忆检索基线

维护者：a1750235782-a11y。MIT 许可证。项目在 Codex 辅助下编写，使用标准 BM25 思路，不声称提出新算法或取得官方评测成绩。

当前版本：`0.3.0-bm25`。本项目面向 Agent Memory Leaderboard 文本 Add/Search 接口。正式参赛受理与模型规则适用性仍需主办方审核；尚未通过官方 Smoke 或 Full。

## 方法

Add 保留原始消息及来源标识，按 1600 字符分块、200 字符重叠，建立 SQLite 倒排索引。英文使用字母数字词项，中文使用单字和相邻双字。每个 user_id 的索引、词频和语料统计相互隔离。

Search 使用 BM25（k1=1.2，b=0.75）排序，长查询最多使用最稀有的 32 个已知词项。返回带原文、角色及可用源时间的证据片段，不生成最终答案。没有 LLM、Embedding 或 Reranker 组件，也不调用模型 API。

完整处理细节、来源引用和能力限制见 [METHOD.md](METHOD.md)。

## Windows 本地运行

已使用 Windows/Python 3.14.6 验证。Ubuntu/Python 3.12.3 的部署需要在目标服务器完成安装与接口检查。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\setup_local_key.py
.\.venv\Scripts\python.exe -m uvicorn competition_app_secure:app --host 127.0.0.1 --port 8000 --reload
```

打开 `http://127.0.0.1:8000/docs`。本地密钥由脚本生成并保存到 `.env`，不应提交仓库。系统环境变量优先于 `.env`。

## Ubuntu 部署

本项目使用 Nginx、单进程 Uvicorn、systemd 和 SQLite。API 监听本机端口，Nginx 提供 HTTPS。`CHRONOMEM_DB_PATH` 指定数据库文件，`CHRONOMEM_VERSION` 指定申报版本标签。

基础安装参考 [SERVER_INSTALL.md](SERVER_INSTALL.md)，HTTPS 配置脚本为 `configure_https.py`。IP 证书由 Let's Encrypt 提供，续期任务由 systemd 管理。现有 0.2 服务器的升级脚本为 `upgrade_bm25.py`，它备份数据库、原程序与服务配置；健康检查或自检失败时恢复旧程序和服务配置。

`render.yaml` 与 [DEPLOY_RENDER.md](DEPLOY_RENDER.md) 是可选托管模板，不是当前阿里云服务器的运行配置。

## 接口示例

Add 和 Search 需要 `X-Api-Key` 请求头。`GET /health` 不需要密钥。

`POST /add`：

```json
{
  "request_id": "local-add-001",
  "messages": [{"role": "user", "content": "Alice prefers Colombian coffee."}],
  "user_id": "demo-user-a",
  "session_id": "demo-session-1"
}
```

成功后返回 HTTP 200，JSON 包含 `success: true` 及原样返回的 request_id、user_id、session_id。相同逻辑请求的重试不会重复写入。

`POST /search`：

```json
{"query": "Which coffee does Alice prefer?", "user_id": "demo-user-a", "top_k": 100}
```

返回 `{"data": [...]}`，每项包含稳定字符串 id、非空 content 和数值 score；有可用源时间时附 created_at。没有结果时返回 `{"data": []}`。返回数量不超过 top_k。不同 user_id 的请求不能检索其他用户的记忆。

## 接入自检与限制

`check_server.py` 使用合成的独立用户记录检查接口、密钥、用户隔离、幂等重试、top_k、非整句检索，以及当前服务器的启动/证书续期任务。它不是官方 Smoke，也不是效果基准或 Full 容量验证。

本版本仍是词法基线，无法可靠解决无词项重叠的同义表达、多跳问题、跨语言、冲突消解与遗忘。正式 Full 前需确认实际数据规模、存储、耗时及并发容量。

评测数据及其备份仅用于当前任务，按官方要求在任务结束后 30 天内删除；本项目没有自动删除计时器。

## 官方资料

- https://agentmemoryleaderboard.ai/competition/
- https://agentmemoryleaderboard.ai/rules
- https://agentmemoryleaderboard.ai/api-guide

依赖各自遵循其第三方许可证；本项目代码的 MIT 授权见 [LICENSE](LICENSE)。
