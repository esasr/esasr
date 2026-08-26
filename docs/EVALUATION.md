# ESASR 实验与评测协议

本文档定义一套可复现、可审计的论文检索实验流程。主指标遵循赛题对 F1 Score 的要求，同时使用排名质量、查询理解、结构化输出与运行成本指标定位系统改进来自哪里。

## 当前可复现证据（2026-08-26）

- ScholarGym 本地镜像：570,206 篇论文；从 2,536 条查询中按来源分层固定抽取 200 条，随机种子为 2026。
- 当前最佳已归档配置为 V3：Top-100 FTS5 候选、Top-20 本地 Cross Encoder、Top-1 输出；Macro F1@1 为 0.2649，bootstrap 95% CI 为 [0.2093, 0.3223]。
- V3 相对 V2 的配对 F1 差值为 0.0183，95% CI 为 [-0.0017, 0.0408]，区间跨 0，因此仅视为正向趋势。
- V4 的 Macro F1@1 为 0.2562，低于 V3；不得以版本号替代模型选择证据，正式文档继续以 V3 为当前最佳配置。
- V5 不重新检索，而是在 V3 冻结候选上验证“置信度校准自适应结果集（CARS）”：按来源分层、按查询 ID 稳定哈希拆分开发/测试各 100 条；只在开发集选择阈值。测试集固定 Top-1 的 F1 为 0.2475，CARS 为 0.2571，配对差值 0.0097、95% CI [0.0000, 0.0267]，平均返回 1.07 篇。该区间包含 0，只能视为初步正向结果。
- 以上均为固定本地样本结果，不是赛事隐藏测试集或 ScholarGym 官方榜单成绩。

归档目录：`esasr-api/evaluation/experiments/scholargym_offline_v3_20260821/`、`scholargym_offline_v4_20260821/` 与 `scholargym_offline_v5_adaptive_20260826/`。正式复跑需核对各目录的 `manifest.json`、数据哈希、模型名称、逐查询预测与比较报告。

V5 复跑命令：

```bash
cd esasr-api
./venv/bin/python tools/calibrate_adaptive_selector.py \
  --gold evaluation/experiments/scholargym_offline_v3_20260821/gold.jsonl \
  --predictions evaluation/experiments/scholargym_offline_v3_20260821/predictions.jsonl \
  --out-dir evaluation/experiments/scholargym_offline_v5_adaptive_20260826 \
  --bootstrap-samples 5000
```

该实验必须从完整 V3 候选文件读取数据，不能使用已经截断的 `selected_predictions.jsonl`。阈值搜索只接触 `dev_gold.jsonl`；最终表只读取 `test_gold.jsonl`。固定 Top-2/3/5 是必要负面对照，用于排除“单纯增加返回数量”带来的伪提升。

## 1. 指标体系

| 评测目标 | 主指标 | 补充指标 | 回答的问题 |
|---|---|---|---|
| 检索集合质量 | Macro/Micro F1@K | Precision@K、Recall@K | 返回集合是否同时兼顾准确率与覆盖率？ |
| 排名质量 | nDCG@K | MAP@K、MRR@K | 相关论文是否尽早出现，高相关论文是否排在前面？ |
| 查询理解 | 约束槽位 F1 | 按约束类型分组 | 主题、方法、数据集、年份、Venue 等是否被正确解析？ |
| 运行效率 | 平均/中位/P95 延时 | API 调用、HTTP 尝试、Token、每个 TP 的成本 | 同等质量下，哪种配置更省？ |
| 结构化输出 | 字段与证据覆盖率 | 轨迹/关系图可用率 | 结果是否便于核验与整理？ |
| 稳定性 | 95% bootstrap CI | 逐查询分布、失败率 | 指标差异是否稳定，是否只由少数查询驱动？ |

推荐以 **F1@20** 作为竞赛主表，另外报告 K=5、10、20 的变化。若 Gold Set 使用分级相关性（例如 0/1/2），nDCG 可区分“部分相关”和“高度相关”；若只做二值标注，F1、Recall 和 MAP 更直观。

参考实现与基准：

- [PaSa](https://github.com/bytedance/pasa)：复杂学术查询与 Recall@20/50/100。
- [LitSearch](https://aclanthology.org/2024.emnlp-main.840/)：597 个经人工检查或编辑的真实文献检索问题，并使用 Recall@K 评估。
- [AstaBench](https://github.com/allenai/asta-bench)：将任务得分与模型/工具成本共同记录，强调冻结配置和可复现日志。
- [NIST trec_eval](https://github.com/usnistgov/trec_eval)：TREC 社区标准检索评测工具，可交叉校验 MAP、nDCG、MRR 等指标。

## 2. Gold Set 构建

1. 按学科、语言、约束类型和难度分层抽样复杂查询。
2. 对每个查询建立候选池：合并 ESASR 各消融配置、OpenAlex、Semantic Scholar 和人工补检结果，去重后再标注。
3. 两名标注者独立判断相关性，建议使用三级标签：0=不相关、1=部分相关、2=高度相关。
4. 对分歧样本进行裁决，并报告一致率或 Cohen's kappa。
5. 冻结开发集与测试集。开发集用于阈值和权重选择，测试集只运行一次最终配置。
6. 论文身份优先按 DOI 匹配，其次按 OpenAlex/Semantic Scholar ID，最后使用规范化标题；无法稳定识别的记录进入人工核验队列。

Gold JSONL 的推荐字段：

```json
{
  "id": "q001",
  "query": "自然语言复杂查询",
  "split": "test",
  "domain": "medicine",
  "language": "zh",
  "difficulty": "hard",
  "constraint_type": "method+year+venue",
  "constraints": {"methods": ["cross encoder"], "year_from": 2022},
  "relevant": [
    {"doi": "10.xxxx/example", "title": "Paper title", "relevance": 2}
  ]
}
```

## 3. 预测与成本日志

预测文件必须保存完整排序结果。为评测运行效率和结构化输出，建议同时保存查询计划、运行轨迹、图数据和服务端 `metrics`：

```json
{
  "id": "q001",
  "constraints": {"methods": ["cross encoder"], "year_from": 2022},
  "predicted": [{"id": "...", "title": "...", "authors": [], "year": 2025, "venue": "...", "source": "openalex", "evidence": []}],
  "trace": [{"stage": "planning"}, {"stage": "retrieval"}],
  "graph": {"nodes": [], "edges": []},
  "metrics": {"apiCalls": 4, "httpAttempts": 5, "llmTokens": 180, "totalDurationMs": 1250}
}
```

不要把底层重试隐藏在一次“逻辑 API 调用”中：`apiCalls` 记录检索任务，`httpAttempts` 记录包含重试的真实 HTTP 请求。Token 至少记录 prompt、completion 和 total；模型提供 reasoning tokens 时单独保存。

## 4. 等预算消融

| 编号 | 配置 | 验证目的 |
|---|---|---|
| A | 单查询 + OpenAlex + 基础排序 | 最低成本基线 |
| B | 多查询 + 单数据源 | 查询分解贡献 |
| C0 | 多查询 + 多数据源，不补检 | 多源召回与融合贡献 |
| C1 | C0 + 固定第二轮 | 控制“多检索一次”的影响 |
| C2 | C0 + 随机/非缺口第二轮 | 检验补检方向是否重要 |
| D | C0 + 覆盖缺口驱动第二轮 | 核心策略贡献 |
| E | D + Cross Encoder | 精排对 Precision/F1 和延时的影响 |

所有配置必须固定查询集合、时间窗、候选上限、最大子查询数和最大数据源任务数。D 与 C1/C2 的比较使用逐查询 paired bootstrap：只有当 F1/Recall 的差值置信区间支持改善，或质量不下降但单位 TP 成本降低时，才能主张覆盖补检有效。

在线 API 会变化。正式实验应保存代码提交、配置哈希、模型名称与 revision、运行时间、原始响应和失败日志；关键消融尽量在同一时间窗执行，必要时使用冻结响应重放排序实验。

## 5. 运行单配置评测

```bash
cd esasr-api
python tools/evaluate_retrieval.py \
  --gold evaluation/sample_gold.jsonl \
  --predictions evaluation/sample_predictions.jsonl \
  --k 5 --k 10 --k 20 \
  --bootstrap-samples 5000 \
  --out evaluation/report.json
```

输出包含：

- Macro/Micro Precision、Recall、F1；
- MAP、MRR、nDCG；
- Macro 指标的 bootstrap 置信区间；
- 约束槽位 F1；
- 论文字段、证据、轨迹与关系图覆盖率；
- API/HTTP/Token/延时的总量、均值、中位数、P95 和单位 TP 成本；
- 每个查询的 TP/FP/FN、排名指标、成本和分组标签。
- 按学科、语言、约束类型、难度和数据划分聚合的分层指标；
- 缺失预测、重复查询 ID 和不属于 Gold Set 的额外预测 ID。

## 6. 比较多个实验配置

```bash
cd esasr-api
python tools/compare_experiments.py \
  --gold evaluation/gold_test.jsonl \
  --run A=evaluation/predictions_A.jsonl \
  --run C1=evaluation/predictions_C1.jsonl \
  --run D=evaluation/predictions_D.jsonl \
  --run E=evaluation/predictions_E.jsonl \
  --k 5 --k 10 --k 20 \
  --primary-k 20 \
  --bootstrap-samples 5000 \
  --out-json evaluation/experiments.json \
  --out-csv evaluation/leaderboard.csv \
  --out-md evaluation/leaderboard.md
```

第一个 `--run` 被视为基线。工具输出逐查询 paired bootstrap 的 F1/Recall 差值、胜率，以及候选配置相对基线的实际 Token/API 预算比。默认允许 5% 的观察预算波动；缺少成本字段时不会自动宣称“等预算”。

## 7. 结果报告最低要求

- 查询数、数据分层和 K；
- Macro/Micro F1，Precision，Recall，MAP，nDCG 和 95% CI；
- 平均/P95 延时、Token、逻辑 API 调用、HTTP 尝试、失败率；
- 约束槽位 F1、结构化字段/证据覆盖率；
- A-E 消融和逐查询负例；
- 代码提交、配置哈希、模型 revision、硬件、时间窗与原始日志路径。

F1 不能替代错误分析：相同 F1 可能来自不同的 Precision/Recall 权衡。nDCG 不能替代召回率：前几篇排得好并不代表相关论文找得全。成本指标也不能脱离质量单独比较；应优先呈现质量-成本 Pareto 前沿。

## 8. API 限流下的测评协议

质量评测与在线服务评测必须分开：

1. **质量主实验使用冻结语料。** 优先使用 ScholarGym 静态论文库、Semantic Scholar 数据集或 OpenAlex snapshot，在本地运行检索并计算 F1、Recall、MAP 与 nDCG。这样不同配置面对完全相同的候选语料。
2. **在线 API 只评测运行行为。** 记录逻辑 API 任务数、真实 HTTP 尝试、429/5xx/传输失败率、重试等待和端到端延时。
3. **每个数据源使用独立串行队列。** Semantic Scholar 认证 Key 默认按不高于 1 RPS 调度，建议保留安全余量；收到 `Retry-After` 时必须服从，否则使用带抖动的指数退避。
4. **逐查询原子落盘并断点续跑。** 已成功查询不重复运行；失败查询在冷却窗口后原位重跑。任何配置只要存在未恢复的数据源失败，就标记为 incomplete，不进入主 F1 对比。
5. **不以空列表或演示数据掩盖失败。** API 异常必须传播到实验 `failures` 字段；评测报告同时给出 `failedQueries/queries`。
6. **缓存不冒充调用节省。** 冻结响应重放适合算法消融，但需把 `logicalApiCalls` 与 `httpAttempts` 分开报告，并注明 latency 来自在线调用还是本地 replay。

[Semantic Scholar 官方说明](https://www.semanticscholar.org/product/api)认证 Key 的入门限额为全端点 1 RPS，并建议大规模任务使用可下载数据集；[OpenAlex 官方文档](https://developers.openalex.org/api-reference/authentication)提供 `/rate-limit` 查询剩余额度，并建议使用大页、批量 ID 与指数退避。正式测评前应保存两者的额度状态与实验时间窗。
