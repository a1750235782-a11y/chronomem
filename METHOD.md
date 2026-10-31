# ChronoMem 0.3.0-bm25 方法说明

维护者署名：a1750235782-a11y。许可证：MIT。代码与部署说明在 Codex 辅助下完成。项目实现了标准 BM25 的词法检索基线，不声称提出新的检索算法。

## 写入与存储

Add 接收并保存原始消息顺序、role、content、user_id、session_id、request_id 和可选 Unix 毫秒 timestamp。消息按最多 1600 个字符切块，相邻块重叠 200 个字符。保存原消息，并为块创建 SQLite 倒排索引、词频、每用户文档频率和长度统计。

每个 user_id 的词项、文档频率、长度统计和检索候选独立。所有写入、索引更新及请求完成标记在一个 SQLite 事务内提交；提交后才返回成功。重试使用相同 user_id、request_id 和内容时不重复写入，改变内容的重复请求返回 400。

## 分词与检索

文本先做 Unicode NFKC 与大小写归一化。英文使用字母数字词项并移除一小组常用停用词；中文使用单字和相邻双字词项。其他语言和混合文本的效果没有系统验证。

Search 仅使用 query 的词项，在相同 user_id 的索引中查询。长查询最多使用当前用户语料中最稀有的 32 个已知词项。options 被接口接受，但本版本不用于扩展检索。

排序使用标准词频饱和与文档长度归一化：k1=1.2，b=0.75，IDF=log(1+(N-df+0.5)/(df+0.5))。同分按稳定块 ID 顺序处理。返回最多 top_k 条证据，包含稳定字符串 id、原文片段及源角色；有可用源时间时附上 UTC 时间和 created_at。score 是词法相关性分数，不是概率。

该系统不在 Search 中生成最终答案，不读取金标，不跨样本共享记忆或统计量。索引、检索和分词均为本项目编写的 Python/SQLite 实现，没有复制 Lucene 代码。

## 模型与费用

本版本没有 LLM、Embedding 或 Reranker 组件，不调用模型 API。申请时应如实填报“无模型的 BM25 词法基线”；是否符合所选组别的当前模型要求，仍以官方审核为准。

## 运行配置和验证范围

- 当前接入服务器：中国香港，Ubuntu 24.04，2 vCPU、2GiB 内存、40GiB 系统盘。
- HTTPS 经 Nginx 转发至单进程 Uvicorn；持久化为 SQLite。
- 建议初始申请并发：Add=1、Search=1；这不是正式 Full 容量保证。
- 本地合成样例已验证英文/中文非整句检索、长消息分块、原数据迁移、用户隔离、重复与并发重试、时间保留、重启一致性。公开基准成绩和官方 Smoke/Full 结果尚无。
- 正式 Full 的全套容量、运行时间和效果尚未完成验证。关键词无重叠的同义表达、多跳组合、跨语言、冲突消解及删除/遗忘未得到可靠解决。

## 数据处理

评测记忆仅用于本次评测，不用于训练、微调、产品分析或对外传播。程序不记录请求正文、API key 或候选内容到访问日志。数据库及其备份应按赛事规则在任务完成后 30 天内删除，除非另获书面允许；本版本没有自动删除计时器。

## 参考与来源

- Robertson 等人的 Okapi/BM25 经典检索方法。参数与 IDF 形式可参考 Apache Lucene 官方 BM25 说明：https://github.com/apache/lucene/blob/main/lucene/core/src/java/org/apache/lucene/search/similarities/BM25Similarity.java
- 接口约定：https://agentmemoryleaderboard.ai/api-guide
- 参赛规则：https://agentmemoryleaderboard.ai/rules
- FastAPI、Pydantic、Uvicorn、python-dotenv 为运行依赖，各自许可证适用于相应第三方软件。
- MIT 许可模板参考：https://choosealicense.com/licenses/mit/ 。维护者已确认采用 MIT，并以 GitHub 账号 a1750235782-a11y 署名。
