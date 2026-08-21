# ScholarSeeker

> 面向复杂学术查询的智能论文搜索与推荐系统  
> Intelligent Academic Paper Search and Recommendation System for Complex Research Queries

## 使用 npm 从 GitHub 安装

前置条件：Node.js 20.11 或更高版本，以及正在运行的 Docker Desktop / Docker
Engine。项目不要求用户预先安装 Python、PostgreSQL、Redis 或 Neo4j。

仓库发布到 GitHub 后，可以直接从 GitHub 地址全局安装 CLI：

```bash
npm install -g git+https://github.com/wanglei1123/ScholarSeeker.git
scholarseeker init my-scholarseeker
cd my-scholarseeker
scholarseeker start
```

`scholarseeker init` 会启动交互式配置向导：

1. 使用 ↑/↓ 选择 DeepSeek、Qwen、OpenAI、Kimi 或自定义兼容平台，按空格确认；
2. 隐藏输入 API Key；
3. 可选配置 Semantic Scholar 和 OpenAlex；
4. 自动生成本地 `.env`、`config.yaml` 和随机 JWT 密钥；
5. API Key 仅保存在本机 `.env`，不会进入前端构建或 Git。

初始化和启动时会展示“第八届中国研究生人工智能创新大赛企业赛题-科研场景下复杂学术查询的智能论文搜索与推荐演示项目”标识。

随时可以重新配置或检查环境：

```bash
scholarseeker setup
scholarseeker config
scholarseeker doctor
scholarseeker status
scholarseeker logs api web
scholarseeker stop
```

### 常用终端命令

| 命令 | 作用 |
| --- | --- |
| `scholarseeker start` / `scholarseeker up` | 启动服务 |
| `scholarseeker stop` / `scholarseeker down` | 终止服务 |
| `scholarseeker restart --no-build` | 不重新构建镜像并重启服务 |
| `scholarseeker status` | 查看容器运行状态 |
| `scholarseeker logs api web` | 查看 API 和 Web 日志 |
| `scholarseeker config` | 安全显示当前配置，不输出 Key 内容 |
| `scholarseeker key list` | 查看各平台 API Key 配置状态 |
| `scholarseeker key add deepseek` | 添加 DeepSeek API Key |
| `scholarseeker key update deepseek` | 修改 DeepSeek API Key |
| `scholarseeker key set openai` | 添加或覆盖 OpenAI API Key |
| `scholarseeker key remove openai` | 删除 OpenAI API Key（会确认） |
| `scholarseeker provider list` | 列出平台、Key 状态和默认平台 |
| `scholarseeker provider current` | 查看当前默认平台 |
| `scholarseeker provider use qwen` | 将 Qwen 设为默认平台 |

支持的平台名称为 `deepseek`、`qwen`、`openai`、`kimi` 和 `custom`。API Key
使用隐藏输入并仅写入当前项目的 `.env`。修改 Key 或默认平台后，运行
`scholarseeker restart --no-build` 使配置生效。

在 macOS 上，如果执行 `scholarseeker start` 时 Docker Desktop 尚未运行，CLI
会询问是否自动启动它，并等待 Docker daemon 就绪后继续部署。

启动时终端会显示 Codex 风格的 `ScholarSeeker` 品牌卡片与动态扫光状态。若 8080、8000、5432、6379、7474
或 7687 已被其他程序占用，CLI 会自动寻找相邻空闲端口、保存到 `.env`，再继续
启动，避免 Docker 因 `port is already allocated` 中断。

也可以不全局安装，直接运行 GitHub 包：

```bash
npm exec --yes \
  --package=git+https://github.com/wanglei1123/ScholarSeeker.git \
  -- scholarseeker init my-scholarseeker
```

## 项目简介

ScholarSeeker 是面向科研场景设计的智能学术搜索系统，旨在解决传统关键词检索在复杂科研问题下召回率不足、语义理解能力有限以及结果组织能力弱的问题。

系统基于大语言模型（LLM）构建多阶段 Academic Search Agent，能够自动完成：

- 查询理解与意图解析
- 查询分解与扩展
- 多源学术搜索
- 引文网络扩展
- 智能论文排序
- 搜索结果归纳总结
- 论文推荐与知识发现

用户仅需输入自然语言描述的研究问题，即可获得高质量论文推荐及结构化研究分析结果。

---

## Docker 快速启动

需要 Docker Desktop 或 Docker Engine，并支持 `docker compose`。

```bash
./run.sh
```

首次运行会自动：

1. 从 `.env.example` 创建本地 `.env`；
2. 构建 Vue/Nginx 与 FastAPI 镜像；
3. 启动 PostgreSQL、Redis、Neo4j、API 和 Web；
4. 等待健康检查通过并打印访问地址。

默认地址：

- Web：`http://127.0.0.1:8080`
- API 文档：`http://127.0.0.1:8000/docs`
- Neo4j Browser：`http://127.0.0.1:7474`

建议首次启动前在 `.env` 中填写 LLM 和学术 API 密钥。没有 LLM 密钥时项目
仍可启动，查询规划会自动使用规则回退。

使用 Kimi 时，在 `.env` 中填写：

```dotenv
LLM_ACTIVE_PROVIDER=kimi
KIMI_API_KEY=你的_Moonshot_API_Key
```

修改后重新运行 `./run.sh --no-build`，Docker 会将密钥安全地传给后端；
密钥不会打包进前端代码。

常用命令：

```bash
./scripts/status.sh                 # 查看状态
./scripts/logs.sh api web           # 查看指定服务日志
./scripts/stop.sh                   # 停止并保留数据
./scripts/stop.sh --volumes         # 停止并删除所有本地数据
./run.sh --no-build                 # 不重新构建镜像
./run.sh --pull                     # 拉取最新基础镜像后启动
./run.sh --with-reranker            # 构建并启用 Cross Encoder
```

端口、密码、模型和 API 密钥均可通过 `.env` 修改。Cross Encoder 模式会安装
额外的 PyTorch/Transformers 依赖，并在首次检索时下载模型，因此首次启动明显
更慢、镜像也更大。

---

## 系统架构
graph TD
    subgraph 用户交互层 (Vue3)
        A[查询输入界面] --> B[检索看板/可视化图谱]
        B --> C[报告预览与导出]
    end

    subgraph 业务逻辑与调度层 (Python)
        D[Agent 调度引擎] <--> E[任务队列/异步处理]
        E <--> F[数据清洗与格式统一]
        F --> G[报告生成引擎]
    end

    subgraph 智能决策层 (LLM APIs)
        H[Qwen API]
        I[DeepSeek API]
        J[GPT API]
    end

    subgraph 外部数据接入层 (Academic APIs)
        K[OpenAlex API]
        L[Semantic Scholar API]
        M[arXiv API]
    end

    A <--> D
    D <--> H
    D <--> I
    D <--> J
    D <--> K
    D <--> L
    D <--> M
    G --> C
---

## 核心功能

### 查询理解

自动识别：

- 研究主题
- 方法约束
- 数据集约束
- 时间范围
- 发表 Venue
- 开源代码要求

示例：

输入：

```text
近三年多模态大模型在医学影像诊断中的应用，
要求公开代码和顶会论文
```

解析结果：

```json
{
  "topic": "Multimodal LLM",
  "domain": "Medical Imaging",
  "year": "2022-2025",
  "open_source": true,
  "venue": "Top Conference"
}
```

---

### 查询分解

复杂问题自动拆解为多个子查询：

```text
Multimodal Medical LLM

Medical Vision Language Model

Medical Diagnosis Foundation Model
```

---

### 多源检索

支持：

- OpenAlex
- Semantic Scholar
- arXiv

复杂检索统一通过 `POST /api/search/run` 执行。接口会将查询规划产生的
子查询真正用于 OpenAlex 与 Semantic Scholar 的并行召回，并在调用预算内完成：

```text
结构化查询规划
      ↓
多子查询 × 多数据源召回
      ↓
DOI / 规范化标题去重
      ↓
RRF + 约束匹配 + 查询覆盖度融合排序
      ↓
结果证据、检索轨迹与成本指标
```

默认预算为最多 4 个子查询、8 次数据源调用，每个数据源每次返回 15 条候选。
调用方可以在请求中下调预算，以控制 API 消耗与端到端延迟。

首轮检索后，系统会对主题、方法、数据集、领域、Venue 和开放获取约束逐项
计算覆盖度。只有存在覆盖缺口或候选数量不足时，才会生成针对性查询并执行
第二轮检索；第二轮仍受同一 API 调用预算限制。

---

### 引文网络扩展

通过：

- References
- Citations
- Co-Citations

发现潜在高价值论文。

---

### 智能排序

采用多阶段排序策略：

```text
BM25 Recall
      ↓
Embedding Retrieval
      ↓
Cross Encoder Rerank
      ↓
LLM Relevance Judge
```

当前实现支持可选的本地 Cross Encoder。默认关闭以避免首次启动时自动下载
大模型；启用方式：

```bash
cd scholarseeker-api
./venv/bin/pip install -r requirements-reranker.txt
```

然后在 `config.yaml` 中设置：

```yaml
ranking:
  cross_encoder:
    enabled: true
    model: BAAI/bge-reranker-base
    top_n: 40
```

模型不可用或推理失败时，系统会自动回退到 RRF 融合排序，并在接口的
`metrics.reranker` 和检索轨迹中记录原因。

### 离线 F1 评测

Gold 与预测文件均采用 JSONL 格式，可使用 DOI、论文 ID 或标题匹配：

```json
{"id":"q1","query":"检索问题","relevant":[{"doi":"10.xxxx/xxx"},{"title":"Paper title"}]}
{"id":"q1","predicted":[{"doi":"10.xxxx/xxx"},{"title":"Another title"}]}
```

执行评测：

```bash
cd scholarseeker-api
./venv/bin/python tools/evaluate_retrieval.py \
  --gold evaluation/sample_gold.jsonl \
  --predictions evaluation/sample_predictions.jsonl \
  --k 20 \
  --out evaluation/report.json
```

报告同时包含 Macro/Micro Precision@K、Recall@K、F1@K、TP/FP/FN 和逐查询结果。

---

### 结构化结果输出

输出内容包括：

- 推荐论文列表
- 推荐理由
- 研究热点分析
- 技术路线总结
- 引文关系图谱

---

## 技术栈

### Frontend

- Vue3
- TypeScript
- Vite
- Pinia
- Vue Router
- Element Plus
- ECharts
- AntV G6

### Backend

- Python
- FastAPI

### LLM

- Qwen
- DeepSeek
- OpenAI GPT

### Retrieval

- OpenAlex API
- Semantic Scholar API
- arXiv API

### Ranking

- BM25
- BGE-M3
- BGE-Reranker-v2

### Database

- PostgreSQL
- Redis

### Graph

- NetworkX
- Neo4j（Optional）

---

## 项目结构

```text
ScholarSeeker/

├── scholarseeker-web/      # Vue3 Frontend
├── scholarseeker-api/         # FastAPI Backend
└── README.md
```

---


## 创新点

- 基于 LLM 的复杂学术查询理解
- Query Decomposition 查询分解机制
- 多源学术检索融合
- Citation Expansion 引文扩展搜索
- 多阶段智能排序
- 科研知识图谱可视化
- 面向科研场景的结构化结果生成

---

## 应用场景

- 文献调研
- 开题报告准备
- Related Work 搜集
- 研究热点分析
- 研究方向发现
- 学术知识探索

---

## 团队信息

第八届中国研究生人工智能创新大赛

企业赛题：

科研场景下复杂学术查询的智能论文搜索与推荐

ScholarSeeker Team © 2026
```
