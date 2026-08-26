<template>
  <div class="about-page">
    <section class="hero-section" aria-labelledby="about-title">
      <div class="hero-copy">
        <p class="competition-label">
          <span class="label-dot" aria-hidden="true"></span>
          第八届中国研究生人工智能创新大赛 · 企业赛题
        </p>
        <h1 id="about-title">科研场景下复杂学术查询的<br><span>智能论文搜索与推荐演示项目</span></h1>
        <p class="hero-description">
          ESASR 面向传统关键词检索难以准确表达的复杂科研需求，借助大模型理解研究意图、
          拆解约束条件并规划检索路径，再融合多个学术数据源完成论文发现、质量评估与个性化推荐。
        </p>
        <div class="hero-tags" aria-label="项目关键能力">
          <span>复杂查询理解</span>
          <span>智能体检索规划</span>
          <span>多源论文融合</span>
          <span>可解释推荐</span>
        </div>
      </div>
      <aside class="hero-panel" aria-label="项目目标">
        <div class="panel-index">AI × Research</div>
        <strong>让科研检索从“关键词匹配”<br>走向“研究意图理解”</strong>
        <p>为研究者提供更准确、更完整、更可追溯的学术发现体验。</p>
        <div class="panel-metrics">
          <div><b>多源</b><span>学术数据接入</span></div>
          <div><b>全链路</b><span>智能检索编排</span></div>
          <div><b>可解释</b><span>推荐依据呈现</span></div>
        </div>
      </aside>
    </section>

    <section class="section project-section" aria-labelledby="project-heading">
      <div class="section-heading">
        <p>PROJECT OVERVIEW</p>
        <h2 id="project-heading">项目要解决什么问题？</h2>
      </div>
      <div class="overview-grid">
        <article class="overview-card problem-card">
          <span class="card-number">01</span>
          <h3>科研查询越来越复杂</h3>
          <p>真实科研问题通常同时包含主题、时间、方法、数据集、开放代码、论文级别等多重条件，单一关键词难以完整表达。</p>
          <ul>
            <li>自然语言问题难以直接转换为检索式</li>
            <li>跨学科概念存在同义词与语义差异</li>
            <li>结果数量庞大，但真正相关的论文有限</li>
          </ul>
        </article>
        <article class="overview-card solution-card">
          <span class="card-number">02</span>
          <h3>用智能体编排检索全过程</h3>
          <p>系统先理解用户真正想解决的研究问题，再自动生成检索策略、并行调用数据源，并依据相关性与学术质量筛选结果。</p>
          <ul>
            <li>大模型提取主题、约束和隐含意图</li>
            <li>多数据源并行检索与结果去重融合</li>
            <li>给出排序理由和可继续探索的方向</li>
          </ul>
        </article>
      </div>
    </section>

    <section class="section workflow-section" aria-labelledby="workflow-heading">
      <div class="section-heading centered">
        <p>RETRIEVAL WORKFLOW</p>
        <h2 id="workflow-heading">从研究问题到可信论文推荐</h2>
        <span>以下流程图完全由 HTML 与 CSS 构建，展示 ESASR 的端到端检索链路。</span>
      </div>

      <div class="workflow" role="img" aria-label="ESASR 智能论文检索流程：用户提出问题，系统理解意图、规划任务、并行检索数据源、融合重排，最终生成可解释推荐。">
        <ol class="flow-track">
          <li class="flow-step input-step">
            <div class="step-head"><span>01</span><small>INPUT</small></div>
            <h3>自然语言查询</h3>
            <p>研究者描述主题、范围、时间与成果要求</p>
            <div class="query-demo">“近三年多模态大模型在医学影像诊断中的应用，要求有公开代码和顶会论文”</div>
          </li>
          <li class="flow-step">
            <div class="step-head"><span>02</span><small>UNDERSTAND</small></div>
            <h3>意图理解</h3>
            <p>识别核心概念并结构化复杂约束</p>
            <div class="mini-tags"><span>主题</span><span>时间</span><span>代码</span><span>级别</span></div>
          </li>
          <li class="flow-step">
            <div class="step-head"><span>03</span><small>PLAN</small></div>
            <h3>智能检索规划</h3>
            <p>生成子问题、扩展同义词并制定检索策略</p>
            <div class="plan-lines"><i></i><i></i><i></i></div>
          </li>
          <li class="flow-step source-step">
            <div class="step-head"><span>04</span><small>RETRIEVE</small></div>
            <h3>多源并行检索</h3>
            <p>向多个学术平台发起查询并收集候选论文</p>
            <div class="source-grid">
              <span>OpenAlex</span><span>Semantic Scholar</span><span>arXiv</span><span>Crossref</span>
            </div>
          </li>
          <li class="flow-step">
            <div class="step-head"><span>05</span><small>RANK</small></div>
            <h3>证据融合与重排</h3>
            <p>去重、过滤并综合评估语义与学术质量</p>
            <div class="rank-bars"><i></i><i></i><i></i></div>
          </li>
          <li class="flow-step output-step">
            <div class="step-head"><span>06</span><small>OUTPUT</small></div>
            <h3>可解释论文推荐</h3>
            <p>输出高相关论文、推荐依据和后续探索方向</p>
            <div class="output-list"><span>精选论文</span><span>相关性说明</span><span>引用与代码</span></div>
          </li>
        </ol>
        <div class="feedback-loop">
          <span>持续反馈</span>
          <i aria-hidden="true"></i>
          <p>用户的收藏、点击和再次检索将帮助系统优化后续推荐</p>
        </div>
      </div>
    </section>

    <section class="section value-section" aria-labelledby="value-heading">
      <div class="section-heading">
        <p>CORE VALUE</p>
        <h2 id="value-heading">项目核心价值</h2>
      </div>
      <div class="value-grid">
        <article><span>01</span><h3>更懂问题</h3><p>保留自然语言中的科研语境，不要求用户掌握复杂数据库检索语法。</p></article>
        <article><span>02</span><h3>检索更全</h3><p>通过查询扩展和多源协同，减少单一数据源与单一关键词造成的遗漏。</p></article>
        <article><span>03</span><h3>结果更准</h3><p>综合语义相关性、发表时间、引用信息与用户约束完成多维排序。</p></article>
        <article><span>04</span><h3>过程可信</h3><p>呈现论文来源、推荐原因及关键证据，让研究者能够判断与复核。</p></article>
      </div>
    </section>

    <footer class="about-footer">
      <div>
        <strong>ESASR</strong>
        <span>面向复杂学术查询的智能论文搜索与推荐系统</span>
      </div>
      <div class="team-credit">
        <span>PROJECT TEAM · 项目团队</span>
        <strong>Justifying</strong>
      </div>
    </footer>
  </div>
</template>

<style scoped lang="scss">
.about-page {
  --about-blue: #3f51b5;
  --about-indigo: #263889;
  --about-cyan: #39a5db;
  --about-soft: rgba(63, 81, 181, 0.08);
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  color: var(--text-primary);
}

.hero-section {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.75fr);
  gap: 56px;
  align-items: center;
  min-height: 520px;
  padding: 64px 4px 72px;
}

.hero-section::before {
  position: absolute;
  z-index: 0;
  top: 26px;
  right: -8%;
  width: 430px;
  height: 430px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(63, 81, 181, 0.13), transparent 68%);
  content: '';
  pointer-events: none;
}

.hero-copy, .hero-panel { position: relative; z-index: 1; }

.competition-label {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 24px;
  color: var(--about-blue);
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.label-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--about-cyan); box-shadow: 0 0 0 5px rgba(57, 165, 219, 0.12); }

h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(36px, 4.2vw, 58px);
  line-height: 1.18;
  letter-spacing: -0.035em;
}

h1 span { color: var(--about-blue); }

.hero-description {
  max-width: 760px;
  margin: 28px 0 0;
  color: var(--text-secondary);
  font-size: 17px;
  line-height: 1.9;
}

.hero-tags { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 30px; }
.hero-tags span { padding: 8px 14px; border: 1px solid rgba(63, 81, 181, 0.18); border-radius: 999px; background: var(--bg-surface); color: var(--about-blue); font-size: 13px; font-weight: 600; }

.hero-panel {
  overflow: hidden;
  padding: 34px;
  border: 1px solid rgba(63, 81, 181, 0.18);
  border-radius: 24px;
  background: linear-gradient(145deg, var(--about-indigo), #5264c4);
  box-shadow: 0 24px 60px rgba(39, 53, 131, 0.22);
  color: #fff;
}
.hero-panel::after { position: absolute; right: -80px; bottom: -90px; width: 240px; height: 240px; border: 1px solid rgba(255,255,255,.16); border-radius: 50%; content: ''; }
.panel-index { margin-bottom: 38px; color: rgba(255,255,255,.68); font-size: 12px; font-weight: 700; letter-spacing: .16em; text-transform: uppercase; }
.hero-panel strong { position: relative; z-index: 1; font-size: 25px; line-height: 1.5; }
.hero-panel > p { position: relative; z-index: 1; margin: 18px 0 30px; color: rgba(255,255,255,.75); font-size: 14px; line-height: 1.75; }
.panel-metrics { position: relative; z-index: 1; display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding-top: 22px; border-top: 1px solid rgba(255,255,255,.18); }
.panel-metrics div { display: flex; flex-direction: column; gap: 7px; }
.panel-metrics b { font-size: 17px; }
.panel-metrics span { color: rgba(255,255,255,.62); font-size: 11px; line-height: 1.4; }

.section { padding: 88px 0; }
.section-heading { margin-bottom: 36px; }
.section-heading > p { margin: 0 0 10px; color: var(--about-blue); font-size: 12px; font-weight: 800; letter-spacing: .16em; }
.section-heading h2 { margin: 0; font-size: clamp(28px, 3vw, 40px); letter-spacing: -.02em; }
.section-heading > span { display: block; margin-top: 14px; color: var(--text-secondary); font-size: 14px; }
.section-heading.centered { text-align: center; }

.project-section { border-top: 1px solid var(--border-color); }
.overview-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 22px; }
.overview-card { position: relative; min-height: 330px; padding: 38px; overflow: hidden; border: 1px solid var(--border-color); border-radius: 20px; background: var(--bg-surface); }
.overview-card::after { position: absolute; right: -40px; bottom: -58px; color: rgba(63,81,181,.04); content: attr(data-number); font-size: 180px; font-weight: 900; }
.overview-card .card-number { display: inline-flex; width: 42px; height: 42px; align-items: center; justify-content: center; margin-bottom: 42px; border-radius: 12px; background: var(--about-soft); color: var(--about-blue); font-size: 13px; font-weight: 800; }
.overview-card h3 { margin: 0 0 14px; font-size: 24px; }
.overview-card p { color: var(--text-secondary); font-size: 15px; line-height: 1.8; }
.overview-card ul { display: grid; gap: 10px; margin: 24px 0 0; padding: 0; list-style: none; }
.overview-card li { position: relative; padding-left: 20px; color: var(--text-secondary); font-size: 14px; }
.overview-card li::before { position: absolute; left: 0; color: var(--about-cyan); content: '✓'; font-weight: 800; }
.solution-card { border-color: rgba(63,81,181,.22); background: linear-gradient(145deg, var(--bg-surface), var(--about-soft)); }

.workflow-section { margin: 0 -40px; padding: 88px 40px; border-radius: 32px; background: linear-gradient(180deg, rgba(63,81,181,.07), rgba(57,165,219,.03)); }
.workflow { position: relative; }
.flow-track { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 48px 24px; margin: 0; padding: 12px 0 0; list-style: none; counter-reset: flow; }
.flow-step { position: relative; min-height: 260px; padding: 26px; border: 1px solid rgba(63,81,181,.16); border-radius: 18px; background: var(--bg-surface); box-shadow: 0 10px 32px rgba(38,56,137,.07); }
.flow-step:not(:nth-child(3)):not(:last-child)::after { position: absolute; z-index: 2; top: 50%; right: -33px; width: 40px; height: 2px; background: linear-gradient(90deg, var(--about-blue), var(--about-cyan)); content: ''; }
.flow-step:not(:nth-child(3)):not(:last-child)::before { position: absolute; z-index: 3; top: calc(50% - 4px); right: -34px; width: 8px; height: 8px; border-top: 2px solid var(--about-cyan); border-right: 2px solid var(--about-cyan); content: ''; transform: rotate(45deg); }
.step-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 34px; }
.step-head span { display: inline-flex; width: 40px; height: 40px; align-items: center; justify-content: center; border-radius: 11px; background: var(--about-blue); color: #fff; font-size: 13px; font-weight: 800; }
.step-head small { color: var(--about-blue); font-size: 10px; font-weight: 800; letter-spacing: .13em; }
.flow-step h3 { margin: 0 0 10px; font-size: 20px; }
.flow-step > p { min-height: 48px; margin: 0; color: var(--text-secondary); font-size: 13px; line-height: 1.7; }
.query-demo { margin-top: 16px; padding: 12px; border-radius: 10px; background: var(--about-soft); color: var(--text-secondary); font-size: 11px; line-height: 1.55; }
.mini-tags, .source-grid, .output-list { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 16px; }
.mini-tags span, .source-grid span, .output-list span { padding: 6px 9px; border-radius: 7px; background: var(--about-soft); color: var(--about-blue); font-size: 10px; font-weight: 700; }
.source-grid { display: grid; grid-template-columns: repeat(2, 1fr); }
.source-grid span { text-align: center; }
.plan-lines, .rank-bars { display: grid; gap: 7px; margin-top: 18px; }
.plan-lines i { height: 7px; border-radius: 99px; background: rgba(63,81,181,.12); }
.plan-lines i:nth-child(2) { width: 76%; }
.plan-lines i:nth-child(3) { width: 58%; }
.rank-bars i { height: 8px; border-radius: 99px; background: linear-gradient(90deg, var(--about-blue), var(--about-cyan)); opacity: .82; }
.rank-bars i:nth-child(2) { width: 82%; opacity: .55; }
.rank-bars i:nth-child(3) { width: 64%; opacity: .32; }
.output-step { border-color: rgba(57,165,219,.35); }
.output-step .step-head span { background: var(--about-cyan); }
.feedback-loop { display: flex; align-items: center; gap: 18px; margin: 32px auto 0; padding: 14px 20px; max-width: 690px; border: 1px dashed rgba(63,81,181,.25); border-radius: 999px; background: var(--bg-surface); }
.feedback-loop span { flex: 0 0 auto; color: var(--about-blue); font-size: 12px; font-weight: 800; }
.feedback-loop i { width: 50px; height: 1px; background: rgba(63,81,181,.28); }
.feedback-loop p { margin: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.5; }

.value-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }
.value-grid article { padding: 30px 24px; border-top: 3px solid var(--about-blue); background: var(--bg-surface); box-shadow: 0 8px 28px rgba(30,42,98,.06); }
.value-grid span { color: var(--about-cyan); font-size: 11px; font-weight: 800; }
.value-grid h3 { margin: 18px 0 10px; font-size: 20px; }
.value-grid p { margin: 0; color: var(--text-secondary); font-size: 13px; line-height: 1.75; }

.about-footer { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-top: 20px; padding: 34px 0 48px; border-top: 1px solid var(--border-color); }
.about-footer div { display: flex; flex-direction: column; gap: 7px; }
.about-footer .team-credit { align-items: flex-end; text-align: right; }
.about-footer strong { color: var(--about-blue); font-size: 20px; }
.about-footer span, .about-footer p { margin: 0; color: var(--text-secondary); font-size: 12px; }

:global(html.dark) .about-page { --about-blue: #8c9eff; --about-indigo: #252f70; --about-soft: rgba(140,158,255,.12); }

@media (max-width: 980px) {
  .hero-section { grid-template-columns: 1fr; gap: 34px; padding-top: 52px; }
  .hero-panel { max-width: 640px; }
  .flow-track { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .flow-step:not(:nth-child(3)):not(:last-child)::after, .flow-step:not(:nth-child(3)):not(:last-child)::before { display: none; }
  .value-grid { grid-template-columns: repeat(2, 1fr); }
}

@media (max-width: 680px) {
  .hero-section { min-height: auto; padding: 40px 0 60px; }
  .competition-label { align-items: flex-start; font-size: 12px; line-height: 1.6; }
  h1 { font-size: 34px; line-height: 1.25; }
  h1 br { display: none; }
  .hero-description { font-size: 15px; }
  .hero-panel { padding: 26px; border-radius: 18px; }
  .panel-metrics { grid-template-columns: 1fr; }
  .panel-metrics div { flex-direction: row; align-items: center; gap: 12px; }
  .section { padding: 64px 0; }
  .overview-grid, .flow-track, .value-grid { grid-template-columns: 1fr; }
  .overview-card { min-height: auto; padding: 28px; }
  .overview-card .card-number { margin-bottom: 28px; }
  .workflow-section { margin: 0 -24px; padding: 64px 24px; border-radius: 22px; }
  .flow-track { gap: 18px; }
  .flow-step { min-height: auto; }
  .feedback-loop { align-items: flex-start; border-radius: 16px; }
  .feedback-loop i { display: none; }
  .about-footer { align-items: flex-start; flex-direction: column; }
  .about-footer .team-credit { align-items: flex-start; text-align: left; }
}
</style>
