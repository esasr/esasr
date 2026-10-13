/** Local UI fixtures only: no credentials, real API calls or evaluation data. */
import { createServer } from 'vite'

const papers = Array.from({ length: 14 }, (_, index) => ({
  id: `ui-fixture-${index + 1}`,
  title: `[UI 测试样例 ${index + 1}] Evidence-aware local feature matching with adaptive attention and long-form research metadata`,
  authors: 'Demo Author A, Demo Author B, Demo Author C',
  venue: index % 2 ? 'International Conference on Computer Vision and Pattern Recognition — Long Venue Layout Test' : 'UI Fixture Conference',
  year: 2024,
  citationCount: 24 + index,
  abstract: 'This is synthetic layout-test content, not an actual paper or experimental result. We examine how long titles, multiple constraints, provenance and missing metadata are presented in a research interface. '.repeat(7),
  relevanceScore: 1 - index / 20,
  relevanceLevel: '布局测试',
  isOpenAccess: index % 2 === 0,
  sources: ['UI fixture'],
  matchedTerms: ['matching', 'attention', 'evidence'],
  recommendReason: '仅用于界面测试：验证长文本换行、同列对齐与滚动行为。',
  evidenceCoverage: .75,
  criterionEvidence: [{ criterion: 'UI 测试', value: 'long-form evidence', source: 'abstract', snippet: 'Synthetic evidence for expandable layout testing only.' }],
  concepts: ['Interface testing', 'Long metadata', 'Reading workflow'],
  doi: 'UI-TEST-NOT-A-REAL-DOI',
}))

const server = await createServer({
  define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('') },
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  plugins: [{
    name: 'local-ui-fixtures',
    configureServer(vite) {
      vite.middlewares.use(async (req, res, next) => {
        if (!req.url?.startsWith('/api/')) return next()
        const path = req.url.split('?')[0]
        let body
        if (path === '/api/search/providers') body = { providers: [{ id: 'fixture', label: 'UI 测试（无外部调用）', models: ['layout-fixture'] }], default: { provider: 'fixture', model: 'layout-fixture' } }
        else if (path === '/api/search/run') {
          // A visible wait exercises the loading illustration without paid model calls.
          await new Promise(resolve => setTimeout(resolve, 1600))
          body = {
            papers,
            plan: { intentions: [{ label: 'Topic', value: 'Evidence-aware image matching with exceptionally long compound constraints' }, { label: 'Year', value: '2020–2026' }], decomposed_queries: ['image matching attention large viewpoint changes', 'long query layout demonstration without remote access'] },
            trace: ['查询规划', '首轮多源召回', '覆盖诊断', '缺口补检', '局部语义精排', '结果输出'].map(stage => ({ stage, status: 'completed', detail: '仅用于 UI 演示，不代表真实检索或实验数据', durationMs: 0 })),
            metrics: { rawCandidates: 14, returnedPapers: 14, apiCalls: 0, llmTokens: 0, totalDurationMs: 0, plannerMode: 'heuristic', failures: [], resultSelector: { selected: 14, breadthLabel: '测试' } },
            coverage: { firstRound: { score: .5, gaps: [] }, final: { score: .75, gaps: [{ dimension: 'dataset', value: 'Long missing dataset label for wrapping', hits: 0 }] }, secondRoundTriggered: false },
          }
        } else if (path?.endsWith('/related')) body = { data: papers.slice(1, 6) }
        else if (path?.endsWith('/graph')) body = { data: {
          nodes: papers.slice(0, 4).map(p => ({ id: p.id, style: { labelText: p.title } })),
          edges: papers.slice(1, 4).map(p => ({ source: p.id, target: papers[0].id, type: 'CITES' })),
        } }
        else if (path?.startsWith('/api/papers/')) body = { data: papers.find(p => path.endsWith(p.id)) || papers[0] }
        else { res.statusCode = 404; body = { error: 'Not implemented in UI fixtures' } }
        res.setHeader('Content-Type', 'application/json; charset=utf-8')
        res.end(JSON.stringify(body))
      })
    },
  }],
})
await server.listen()
console.log('UI FIXTURES ONLY — http://127.0.0.1:5173/search?q=UI-layout-test (no external APIs)')
