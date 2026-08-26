#!/usr/bin/env python3
"""Generate the original, publication-style figure set for the competition report."""

from pathlib import Path
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "images"
OUT.mkdir(exist_ok=True)

BLUE = "#173F5F"
BLUE2 = "#20639B"
ORANGE = "#ED553B"
GOLD = "#F6A623"
GRAY = "#6B7280"
LIGHT = "#F3F4F6"
MID = "#D1D5DB"
WHITE = "#FFFFFF"
INK = "#1F2937"
GREEN = "#3A7D44"

mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial Unicode MS", "PingFang SC", "Songti SC", "Arial", "DejaVu Sans"],
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    # Figures are reduced to A4 text width in the report.  These source sizes
    # keep the final rendered glyphs comfortably above the 5 pt floor.
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "xtick.labelsize": 9.5,
    "ytick.labelsize": 9.5,
    "axes.spines.right": False,
    "axes.spines.top": False,
    "axes.linewidth": 0.8,
    "legend.frameon": False,
})


def canvas(width=10.8, height=5.6):
    fig, ax = plt.subplots(figsize=(width, height), constrained_layout=True)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor(WHITE)
    ax.set_facecolor(WHITE)
    return fig, ax


def box(ax, xy, wh, title, detail="", color=BLUE, fill=WHITE, lw=1.6, title_size=10.5, detail_size=10.0):
    x, y = xy
    w, h = wh
    p = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.009,rounding_size=0.012",
                       ec=color, fc=fill, lw=lw)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h * 0.66, title, ha="center", va="center",
            color=color, fontsize=title_size, fontweight="bold")
    if detail:
        ax.text(x + w / 2, y + h * 0.32, detail, ha="center", va="center",
                color=INK, fontsize=detail_size, linespacing=1.25)
    return p


def arrow(ax, start, end, color=GRAY, text=None, rad=0.0, lw=1.2):
    a = FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=10, lw=lw,
                        color=color, connectionstyle=f"arc3,rad={rad}")
    ax.add_patch(a)
    if text:
        mx, my = (start[0] + end[0]) / 2, (start[1] + end[1]) / 2
        ax.text(mx, my + 0.025, text, ha="center", va="bottom", fontsize=9.5, color=color)
    return a


def tag(ax, x, y, text, color=ORANGE):
    ax.text(x, y, text, ha="center", va="center", color=WHITE, fontsize=10,
            fontweight="bold", bbox=dict(boxstyle="round,pad=0.28", fc=color, ec=color))


def save(fig, stem):
    fig.savefig(OUT / f"{stem}.png", dpi=300, bbox_inches="tight", facecolor=WHITE)
    fig.savefig(OUT / f"{stem}.svg", bbox_inches="tight", facecolor=WHITE)
    fig.savefig(OUT / f"{stem}.pdf", bbox_inches="tight", facecolor=WHITE)
    plt.close(fig)


def fig1_overall():
    fig, ax = canvas(11.4, 5.9)
    ax.text(0.5, 0.96, "证据状态驱动的自适应学术检索框架", ha="center", va="top",
            fontsize=16, fontweight="bold", color=BLUE)
    ax.text(0.5, 0.905, "Evidence-State Adaptive Scholarly Retrieval (ESASR)", ha="center",
            va="top", fontsize=9.5, color=GRAY)
    xs = [0.035, 0.205, 0.375, 0.545, 0.715, 0.865]
    widths = [0.125, 0.125, 0.125, 0.125, 0.125, 0.105]
    titles = ["复杂科研问题", "约束感知\n查询编译", "证据缺口\n检索路由", "多源证据\n融合排序", "局部语义精排", "自适应\n结果集"]
    details = ["主题·方法·数据集\n年份·Venue·排除项", "结构化槽位\n预算化子查询", "并行首轮召回\n按缺口触发补检", "去重·RRF·覆盖\n来源一致性·权威性", "Cross Encoder\n仅重排 Top-20", "置信度门控\n输出 1 或 2 篇"]
    colors = [GRAY, BLUE, BLUE2, BLUE, ORANGE, ORANGE]
    for i, (x, w) in enumerate(zip(xs, widths)):
        box(ax, (x, 0.54), (w, 0.24), titles[i], details[i], colors[i], LIGHT if i in (0, 5) else WHITE)
        if i < len(xs) - 1:
            arrow(ax, (x + w + 0.008, 0.66), (xs[i + 1] - 0.008, 0.66), color=GRAY)
    box(ax, (0.19, 0.15), (0.56, 0.18), "证据状态控制器", "覆盖率 c · 约束缺口 G · 排名分数 s · 任务预算 B", BLUE, "#EAF2F8", title_size=11.5)
    arrow(ax, (0.47, 0.33), (0.47, 0.53), color=BLUE, text="状态驱动决策")
    box(ax, (0.79, 0.15), (0.16, 0.18), "可审计输出", "来源证据·检索轨迹\n缺失字段·关系分型", GREEN, "#EFF7F0")
    arrow(ax, (0.81, 0.54), (0.87, 0.34), color=GREEN)
    tag(ax, 0.095, 0.845, "输入")
    tag(ax, 0.92, 0.845, "输出")
    save(fig, "Fig1_ESASR_OverallFramework")


def fig2_compiler():
    fig, ax = canvas(10.8, 5.2)
    ax.text(0.5, 0.95, "约束感知查询编译器（CQC）", ha="center", va="top", fontsize=16, fontweight="bold", color=BLUE)
    box(ax, (0.03, 0.39), (0.18, 0.24), "自然语言查询", "中英文复合条件\n允许自由表达", GRAY, LIGHT)
    box(ax, (0.29, 0.62), (0.18, 0.19), "语义规划器", "LLM JSON 规划\n单次调用、可缓存", BLUE, WHITE)
    box(ax, (0.29, 0.25), (0.18, 0.19), "规则规划器", "无密钥或异常时\n确定性降级", BLUE2, WHITE)
    box(ax, (0.55, 0.35), (0.2, 0.3), "统一约束模式", "topic · methods · datasets\nyear · venue · open access\ninclude / exclude", ORANGE, "#FFF4F1", title_size=11.5)
    box(ax, (0.82, 0.58), (0.15, 0.18), "硬约束", "年份·排除词\n强制 Venue", BLUE, WHITE)
    box(ax, (0.82, 0.23), (0.15, 0.18), "软证据", "主题·方法·数据集\n开放获取", ORANGE, WHITE)
    arrow(ax, (0.21, 0.51), (0.29, 0.71), color=BLUE)
    arrow(ax, (0.21, 0.49), (0.29, 0.34), color=BLUE2)
    arrow(ax, (0.47, 0.71), (0.55, 0.55), color=BLUE)
    arrow(ax, (0.47, 0.34), (0.55, 0.45), color=BLUE2)
    arrow(ax, (0.75, 0.53), (0.82, 0.67), color=BLUE)
    arrow(ax, (0.75, 0.47), (0.82, 0.32), color=ORANGE)
    ax.text(0.5, 0.09, "设计目标：完整保留用户意图，同时把不可执行的自然语言转化为可验证检索约束", ha="center", color=INK, fontsize=9.5)
    save(fig, "Fig2_CQC_QueryCompiler")


def fig3_routing():
    fig, ax = canvas(11.0, 5.5)
    ax.text(0.5, 0.96, "证据缺口驱动检索路由（EGRR）", ha="center", va="top", fontsize=16, fontweight="bold", color=BLUE)
    box(ax, (0.03, 0.58), (0.15, 0.18), "首轮子查询", "最多 4 个", BLUE, WHITE)
    box(ax, (0.25, 0.68), (0.17, 0.17), "OpenAlex", "并行召回", BLUE2, WHITE)
    box(ax, (0.25, 0.42), (0.17, 0.17), "Semantic Scholar", "并行召回", BLUE2, WHITE)
    box(ax, (0.49, 0.56), (0.18, 0.22), "候选证据状态", "覆盖率 c\n未覆盖约束 G\n剩余预算 B", ORANGE, "#FFF4F1")
    diamond = FancyBboxPatch((0.73, 0.56), 0.12, 0.22, boxstyle="round,pad=0.01", ec=BLUE, fc="#EAF2F8", lw=1.3)
    ax.add_patch(diamond)
    ax.text(0.79, 0.67, "G≠∅ 且 B>0?", ha="center", va="center", color=BLUE, fontweight="bold", fontsize=9.5)
    box(ax, (0.88, 0.69), (0.1, 0.15), "定向补检", "缺口词组", ORANGE, WHITE)
    box(ax, (0.88, 0.42), (0.1, 0.15), "进入排序", "冻结候选", GREEN, WHITE)
    for y in (0.765, 0.505):
        arrow(ax, (0.18, 0.67), (0.25, y), color=GRAY)
    arrow(ax, (0.42, 0.765), (0.49, 0.68), color=GRAY)
    arrow(ax, (0.42, 0.505), (0.49, 0.64), color=GRAY)
    arrow(ax, (0.67, 0.67), (0.73, 0.67), color=GRAY)
    arrow(ax, (0.85, 0.71), (0.88, 0.76), color=ORANGE, text="是")
    arrow(ax, (0.85, 0.62), (0.88, 0.50), color=GREEN, text="否")
    arrow(ax, (0.93, 0.69), (0.58, 0.79), color=ORANGE, rad=0.32, text="更新证据状态")
    ax.text(0.5, 0.18, "共享预算：子查询 ≤ 4，数据源任务 ≤ 8；补检由缺口确定性生成，不新增 LLM 调用", ha="center", color=INK, fontsize=9.5,
            bbox=dict(boxstyle="round,pad=0.5", fc=LIGHT, ec=MID))
    save(fig, "Fig3_EGRR_RetrievalRouting")


def fig4_ranking():
    fig, ax = canvas(11.2, 5.6)
    ax.text(0.5, 0.96, "多源证据融合与局部语义精排", ha="center", va="top", fontsize=16, fontweight="bold", color=BLUE)
    labels = [("词法相关性", "标题 + 摘要等权", BLUE2), ("RRF 排名证据", "跨来源/子查询", BLUE),
              ("查询覆盖", "主题·方法·数据集", ORANGE), ("来源一致性", "多源共同命中", GOLD),
              ("权威性证据", "Venue·引用·OA", GRAY)]
    for i, (t, d, c) in enumerate(labels):
        y = 0.76 - i * 0.135
        box(ax, (0.03, y), (0.2, 0.105), t, d, c, WHITE, title_size=9.5, detail_size=9.5)
        arrow(ax, (0.23, y + 0.048), (0.33, 0.52), color=c)
    box(ax, (0.33, 0.39), (0.2, 0.25), "多源证据融合排序\n（MEFR）", "统一归一化\n硬约束先过滤\n保留证据分解", BLUE, "#EAF2F8", title_size=11.5)
    box(ax, (0.61, 0.53), (0.16, 0.2), "Top-20", "受控候选池\n避免全量推理", GRAY, LIGHT)
    box(ax, (0.61, 0.22), (0.16, 0.2), "其余候选", "保留基础排序\n支持降级", GRAY, WHITE)
    box(ax, (0.84, 0.53), (0.14, 0.2), "局部语义精排\n（LCER）", "Cross Encoder\n0.65语义+0.35基础", ORANGE, "#FFF4F1", title_size=10)
    arrow(ax, (0.53, 0.55), (0.61, 0.63), color=ORANGE)
    arrow(ax, (0.53, 0.47), (0.61, 0.32), color=GRAY)
    arrow(ax, (0.77, 0.63), (0.84, 0.63), color=ORANGE)
    ax.text(0.9, 0.38, "最终排序分数", ha="center", va="center", color=ORANGE, fontweight="bold", fontsize=9.5)
    arrow(ax, (0.91, 0.53), (0.91, 0.42), color=ORANGE)
    ax.text(0.5, 0.08, "可解释性：每个候选同时保留召回来源、命中约束、融合分量和精排分数", ha="center", fontsize=9.5, color=INK)
    save(fig, "Fig4_MEFR_LCER_RankingPipeline")


def fig5_cars():
    fig, ax = canvas(10.8, 5.4)
    ax.text(0.5, 0.96, "置信度门控自适应结果集（CARS）", ha="center", va="top", fontsize=16, fontweight="bold", color=BLUE)
    box(ax, (0.04, 0.55), (0.18, 0.2), "排序候选", "s₁ ≥ s₂ ≥ …\n默认保留第 1 篇", BLUE, WHITE)
    box(ax, (0.31, 0.55), (0.22, 0.2), "第二候选三重门控", "s₂ ≥ 0.60\ns₂/s₁ ≥ 0.85\ns₁-s₂ ≤ 0.10", ORANGE, "#FFF4F1", title_size=10.5)
    box(ax, (0.64, 0.67), (0.16, 0.16), "全部满足", "返回 2 篇", ORANGE, WHITE)
    box(ax, (0.64, 0.39), (0.16, 0.16), "任一不满足", "返回 1 篇", BLUE, WHITE)
    box(ax, (0.87, 0.53), (0.1, 0.2), "输出", "平均 1.07 篇\n测试集 F1 0.2571", GREEN, "#EFF7F0")
    arrow(ax, (0.22, 0.65), (0.31, 0.65), color=GRAY)
    arrow(ax, (0.53, 0.67), (0.64, 0.75), color=ORANGE)
    arrow(ax, (0.53, 0.62), (0.64, 0.47), color=BLUE)
    arrow(ax, (0.80, 0.75), (0.87, 0.66), color=ORANGE)
    arrow(ax, (0.80, 0.47), (0.87, 0.60), color=BLUE)
    ax.text(0.5, 0.18, "开发集：100 条，搜索 8,064 组规则  →  独立测试集：100 条，仅评估一次", ha="center", fontsize=9.5, color=INK,
            bbox=dict(boxstyle="round,pad=0.45", fc=LIGHT, ec=MID))
    ax.text(0.5, 0.10, "规则不新增检索或模型调用；现有配对区间包含 0，因此只报告初步正向趋势", ha="center", fontsize=9.5, color=GRAY)
    save(fig, "Fig5_CARS_AdaptiveSelection")


def fig6_dataflow():
    fig, ax = canvas(11.2, 5.7)
    ax.text(0.5, 0.96, "端到端系统数据流与可信边界", ha="center", va="top", fontsize=16, fontweight="bold", color=BLUE)
    layers = [(0.76, "交互层", ["自然语言输入", "结果证据", "轨迹与关系图"]),
              (0.55, "编排层", ["查询规划", "预算控制", "融合与精排"]),
              (0.34, "数据服务层", ["OpenAlex", "Semantic Scholar", "本地 Cross Encoder"]),
              (0.13, "状态层", ["PostgreSQL", "Redis", "Neo4j"])]
    colors = [BLUE, BLUE2, ORANGE, GRAY]
    for (y, name, items), c in zip(layers, colors):
        ax.text(0.04, y + 0.07, name, ha="left", va="center", color=c, fontweight="bold", fontsize=10.5)
        ax.plot([0.13, 0.97], [y, y], color=MID, lw=0.8)
        for j, item in enumerate(items):
            x = 0.2 + j * 0.27
            box(ax, (x, y + 0.015), (0.2, 0.12), item, "", c, WHITE, title_size=9.5)
    for x in (0.30, 0.57, 0.84):
        arrow(ax, (x, 0.77), (x, 0.70), color=GRAY)
        arrow(ax, (x, 0.56), (x, 0.49), color=GRAY)
        arrow(ax, (x, 0.35), (x, 0.28), color=GRAY)
    ax.text(0.98, 0.50, "错误可见\n来源可追\n缺失不补造", ha="right", va="center", fontsize=9.5, color=ORANGE, fontweight="bold")
    save(fig, "Fig6_System_EndToEndDataFlow")


def fig7_evidence():
    fig, ax = canvas(11.2, 5.5)
    ax.text(0.5, 0.96, "分层实验协议：模块收益与输出策略分开验证", ha="center", va="top", fontsize=16, fontweight="bold", color=BLUE)
    box(ax, (0.04, 0.65), (0.18, 0.18), "数据母集", "2,536 条查询\n570,206 篇论文", BLUE, WHITE)
    box(ax, (0.30, 0.65), (0.2, 0.18), "排序模块实验", "分层固定 200 条\n同语料·同 Top-100", BLUE2, "#EAF2F8")
    box(ax, (0.58, 0.65), (0.18, 0.18), "核心比较", "词法权重\nCross Encoder\nRRF 路由", ORANGE, "#FFF4F1")
    box(ax, (0.82, 0.65), (0.14, 0.18), "证据", "F1@1 0.2649\n95% CI", GREEN, "#EFF7F0")
    arrow(ax, (0.22, 0.74), (0.30, 0.74)); arrow(ax, (0.50, 0.74), (0.58, 0.74)); arrow(ax, (0.76, 0.74), (0.82, 0.74))
    box(ax, (0.30, 0.28), (0.2, 0.18), "输出策略实验", "按来源分层拆分\n100 开发 + 100 测试", BLUE2, "#EAF2F8")
    box(ax, (0.58, 0.28), (0.18, 0.18), "公平对照", "冻结相同候选\n固定 Top-K vs CARS", ORANGE, "#FFF4F1")
    box(ax, (0.82, 0.28), (0.14, 0.18), "证据", "F1 0.2571\n平均 1.07 篇", GREEN, "#EFF7F0")
    arrow(ax, (0.22, 0.69), (0.30, 0.37), color=GRAY, rad=0.08)
    arrow(ax, (0.50, 0.37), (0.58, 0.37)); arrow(ax, (0.76, 0.37), (0.82, 0.37))
    ax.text(0.5, 0.10, "不将两个口径合并为单一总分；所有结论均限定到对应样本、候选池与预算条件", ha="center", fontsize=9.5, color=INK)
    save(fig, "Fig7_Experiment_EvidenceProtocol")


def fig8_ablation():
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.7), constrained_layout=True)
    fig.patch.set_facecolor(WHITE)
    methods = ["标题偏置\n词法召回", "等权\n词法召回", "等权词法\n+局部精排", "多路 RRF\n+局部精排"]
    vals = [0.1862, 0.2466, 0.2649, 0.2562]
    colors = [MID, BLUE2, ORANGE, GRAY]
    ax = axes[0]
    bars = ax.bar(np.arange(4), vals, color=colors, width=0.68)
    ax.set_ylim(0, 0.31); ax.set_ylabel("Macro F1@1")
    ax.set_xticks(np.arange(4), methods)
    ax.set_title("a  排序模块消融（n=200）", loc="left", fontweight="bold", color=BLUE)
    ax.grid(axis="y", color=LIGHT, lw=0.8); ax.set_axisbelow(True)
    for b, v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v+0.008, f"{v:.4f}", ha="center", fontsize=9.5, color=INK)
    klabels = ["Top-1", "Top-2", "Top-3", "Top-5", "CARS"]
    kvals = [0.2475, 0.1986, 0.1665, 0.1304, 0.2571]
    ax = axes[1]
    bars = ax.bar(np.arange(5), kvals, color=[BLUE2, MID, MID, MID, ORANGE], width=0.68)
    ax.set_ylim(0, 0.30); ax.set_ylabel("Macro F1")
    ax.set_xticks(np.arange(5), klabels)
    ax.set_title("b  输出策略对比（独立测试 n=100）", loc="left", fontweight="bold", color=BLUE)
    ax.grid(axis="y", color=LIGHT, lw=0.8); ax.set_axisbelow(True)
    for b, v in zip(bars, kvals):
        ax.text(b.get_x()+b.get_width()/2, v+0.007, f"{v:.4f}", ha="center", fontsize=9.5, color=INK)
    fig.suptitle("模块消融与自适应输出策略的实测表现", fontsize=15, fontweight="bold", color=BLUE)
    save(fig, "Fig8_Ablation_Performance")


def fig9_deploy():
    fig, ax = canvas(11.2, 5.4)
    ax.text(0.5, 0.96, "容器化部署拓扑与密钥隔离", ha="center", va="top", fontsize=16, fontweight="bold", color=BLUE)
    box(ax, (0.03, 0.55), (0.13, 0.18), "用户浏览器", "HTTPS", GRAY, LIGHT)
    box(ax, (0.23, 0.55), (0.15, 0.18), "Web 容器", "Vue 3 静态资源\n反向代理", BLUE2, WHITE)
    box(ax, (0.46, 0.55), (0.17, 0.18), "API 容器", "FastAPI 编排\n模型与密钥边界", BLUE, "#EAF2F8")
    box(ax, (0.72, 0.68), (0.12, 0.15), "OpenAlex", "远端 API", ORANGE, WHITE)
    box(ax, (0.86, 0.68), (0.12, 0.15), "Semantic\nScholar", "远端 API", ORANGE, WHITE, title_size=9.5)
    box(ax, (0.70, 0.29), (0.09, 0.15), "PostgreSQL", "业务数据", GRAY, WHITE, title_size=9.5)
    box(ax, (0.81, 0.29), (0.07, 0.15), "Redis", "缓存", GRAY, WHITE)
    box(ax, (0.90, 0.29), (0.07, 0.15), "Neo4j", "关系", GRAY, WHITE)
    arrow(ax, (0.16, 0.64), (0.23, 0.64), color=GRAY)
    arrow(ax, (0.38, 0.64), (0.46, 0.64), color=BLUE)
    arrow(ax, (0.63, 0.66), (0.72, 0.75), color=ORANGE)
    arrow(ax, (0.63, 0.65), (0.86, 0.75), color=ORANGE, rad=-0.08)
    for x in (0.745, 0.845, 0.935):
        arrow(ax, (0.58, 0.55), (x, 0.44), color=GRAY)
    ax.text(0.50, 0.22, "密钥仅注入 API 容器 · 配置只读挂载 · 组件异常返回 503/degraded", ha="center", fontsize=9.5, color=INK,
            bbox=dict(boxstyle="round,pad=0.45", fc=LIGHT, ec=MID))
    save(fig, "Fig9_Deployment_Topology")


def fig10_iteration():
    fig, ax = canvas(11.2, 5.2)
    ax.text(0.5, 0.96, "技术迭代：以可证伪实验收敛到最终方案", ha="center", va="top", fontsize=16, fontweight="bold", color=BLUE)
    points = [0.08, 0.27, 0.46, 0.65, 0.84]
    titles = ["标题偏置暴露", "等权词法修正", "局部语义精排", "多路融合负结果", "自适应结果集"]
    details = ["F1 0.1862", "F1 0.2466", "F1 0.2649", "F1 0.2562\n未进入主线", "测试 F1 0.2571\n平均 1.07篇"]
    for i, (x, t, d) in enumerate(zip(points, titles, details)):
        c = ORANGE if i in (2, 4) else (GRAY if i == 3 else BLUE2)
        ax.add_patch(Circle((x, 0.56), 0.027, fc=c, ec=WHITE, lw=1.5, zorder=3))
        if i < len(points)-1:
            arrow(ax, (x+0.03, 0.56), (points[i+1]-0.03, 0.56), color=MID, lw=2)
        ax.text(x, 0.70 if i%2==0 else 0.42, t, ha="center", va="center", fontsize=9.5, fontweight="bold", color=c)
        ax.text(x, 0.79 if i%2==0 else 0.31, d, ha="center", va="center", fontsize=9.5, color=INK)
    ax.text(0.5, 0.12, "选择准则：同数据、同候选预算、同指标；正向结果进入最终主线，负结果保留为消融证据", ha="center", fontsize=9.5, color=INK,
            bbox=dict(boxstyle="round,pad=0.45", fc=LIGHT, ec=MID))
    save(fig, "Fig10_Iteration_Roadmap")


if __name__ == "__main__":
    fig1_overall(); fig2_compiler(); fig3_routing(); fig4_ranking(); fig5_cars()
    fig6_dataflow(); fig7_evidence(); fig8_ablation(); fig9_deploy(); fig10_iteration()
    print(f"Generated 10 figure sets in {OUT}")
