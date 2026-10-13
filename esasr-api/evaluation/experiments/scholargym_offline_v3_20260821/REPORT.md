# ESASR 离线检索优化 V3

日期：2026-08-21
状态：实现与评测完成

## 已加入的能力

- **规则查询分解**：不调用 LLM，从查询中生成标题通道和高信息长词聚焦通道。
- **多路召回与 RRF**：原始全文检索、标题检索和聚焦检索可按权重融合，并记录每篇论文的召回来源。
- **本地 Cross Encoder**：使用 `cross-encoder/ms-marco-MiniLM-L6-v2` 对 Top-20 候选精排。
- **双层结果**：Top-100 作为候选池，Top-1 作为当前高精度最终输出。
- **完整成本记录**：API 调用、LLM 调用和 Token 均为 0；单独记录精排延时。

## 默认策略

默认继续采用等权 BM25 单通道召回，并开启可选 Top-20 Cross Encoder 精排。规则分解与 RRF 已实现为实验开关，但不默认启用：冻结验证集显示低权重标题 RRF 将 F1@1 从 0.2310 降至 0.1859；聚焦 AND 通道也未获得稳定收益。保留接口用于以后配合更强精排器做消融，但不能将负向结果包装成主方案。

## 200 条完整样本结果

| 版本 | Precision@1 | Recall@1 | F1@1 | F1 95% CI | MAP@100 | nDCG@100 | API | Token |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V1：标题权重 5 | 0.2250 | 0.1745 | 0.1862 | [0.1377, 0.2371] | 0.2471 | 0.3319 | 0 | 0 |
| V2：标题摘要等权 | 0.3000 | 0.2301 | 0.2466 | [0.1928, 0.3033] | 0.2802 | 0.3598 | 0 | 0 |
| V3：V2 + Cross Encoder | **0.3300** | **0.2454** | **0.2649** | [0.2093, 0.3223] | **0.3007** | **0.3773** | 0 | 0 |

V3 相对 V2 的完整样本 F1 增量为 +0.0183，相对提升 7.4%。冻结验证集 F1 从 0.2310 提升到 0.2395。两者方向一致，但配对 bootstrap 的 95% 区间分别为 [-0.0017, 0.0408] 和 [-0.0221, 0.0408]，均跨 0，因此应将 V3 描述为**有希望但尚未达到统计显著**，不能宣称已稳定优于 V2。

## 使用方法

先安装本地精排依赖：

```bash
cd esasr-api
./venv/bin/pip install -r requirements-reranker.txt
```

稳定默认基线使用单通道召回；加入本地精排时传入：

```bash
./venv/bin/python tools/run_scholargym_offline.py \
  --paper-db evaluation/datasets/scholargym/scholargym_paper_db.json \
  --benchmark evaluation/datasets/scholargym/scholargym_bench.jsonl \
  --index evaluation/datasets/scholargym/scholargym_fts5.db \
  --out-dir evaluation/experiments/scholargym_offline_v3 \
  --limit 200 --seed 2026 --retrieve-k 100 --output-k 1 \
  --retrieval-strategy single \
  --cross-encoder-model cross-encoder/ms-marco-MiniLM-L6-v2 \
  --cross-encoder-device cpu --rerank-top-n 20
```

RRF 消融可将 `--retrieval-strategy` 改为 `rrf`，并通过 `--title-route-weight`、`--focused-route-weight`、`--rrf-k` 和 `--route-k` 控制融合。该模式当前不应作为正式默认配置。
