# Render 接入部署说明

本配置部署一个带密钥的文本关键词检索基线，用于准备公网接入。它不代表通过官方 Smoke 或具备正式 Full 评测容量、效果和参赛资格。

## 费用与配置

2026 年 10 月 31 日查询 Render 官网：`0.5c-512mb` 实例价格为每月 7 美元，持久盘为每 GB 每月 0.25 美元。这里配置 5GB，固定部分按整月估算为 8.25 美元；流量超额、税费等另计，以创建时账单预览为准。

使用 Hobby 工作区即可，不需要为本配置升级 Pro 工作区。选择的是付费计算实例，不是会空闲休眠的 Free 实例。初始规格只用于接入和小规模验证，Full 前需要根据实际数据与并发做容量测试。

## 创建服务

1. 将 `render.yaml`、`.python-version`、更新后的 `competition_app_secure.py` 和项目说明提交到 GitHub。
2. 在 https://dashboard.render.com 注册或登录，可使用 GitHub 登录。
3. 创建 Hobby 工作区；如果引导页询问付费工作区升级，当前配置无需升级。
4. 通过 New → Blueprint 选择 `a1750235782-a11y/chronomem`。授权 Render GitHub App 读取该仓库即可。
5. 检查识别到的单个 Web Service：`chronomem-api`、Python、Singapore、`0.5c-512mb`、5GB 持久盘。确认页面费用和本说明一致后，按页面流程完成部署所需支付设置及创建。
6. 等待构建和启动日志，直到服务 Live。Render 会分配 HTTPS 的 `onrender.com` 地址，无需为初次接入购买域名。

`render.yaml` 会自动生成服务端密钥，不需要把电脑上的 `.env` 上传。生成的密钥在服务的 Environment 页面查看或复制。该值是 Memory System Key，不是赛事 Eval Key。

自动部署已关闭。评测期间不要修改并重新部署受评版本。Render Blueprint 的自动同步是独立设置；创建后在 Blueprint Settings 中将 Auto Sync 设为 No，后续配置变更改为手动同步。

## 验证

1. 打开实际服务地址后的 `/health`，应返回 `status: ok`、`version: 0.3.0-bm25`、`storage: sqlite`。
2. 在 `/docs` 测试没有密钥时 Add/Search 返回 401，使用 Render 生成的密钥授权后返回 200。
3. 使用合成练习数据验证 Add、Search、不同 user_id 隔离、重复 request_id 不重复写入、top_k 限制。
4. 在练习数据阶段重启服务，确认已添加记录仍能检索。不要在正式评测运行中做重启测试。

本地测试数据不会自动上传到 Render。云端数据库保存在 `/var/data/chronomem_contract.db`，由持久盘保留。

## 提交与后续工作

- 正式申请地址填写实际分配的 HTTPS URL：Add 为 `/add`，Search 为 `/search`，Health 为 `/health`。鉴权选择 X-Api-Key。
- 填写真实方法说明、当前 Commit 和经过测试的容量与并发，不声明未验证的能力或成绩。
- 本版本使用 BM25 词法检索，面对自然语言问题可能无法召回。正式 Full 前需改进并验证检索方法，同时核对组别、模型规则、公开仓库、署名及许可证要求。
- 评测数据仅用于本次评测；按赛事规则在任务完成后 30 天内删除，除非另获书面允许。本版本未自动执行定时删除。
- 费用会持续产生。评测及必要复核结束后，根据官方要求导出需要保留的非敏感材料，删除服务和持久盘等付费资源，并检查 Render Billing。

## 官方参考

- https://render.com/pricing
- https://render.com/docs/disks
- https://render.com/docs/blueprint-spec
- https://render.com/docs/python-version
- https://render.com/docs/infrastructure-as-code
- https://agentmemoryleaderboard.ai/rules
- https://agentmemoryleaderboard.ai/api-guide
