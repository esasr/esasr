import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from services.llm_service import _normalize_plan, _heuristic_plan, analyze_search_query
from services.reranker_service import _probability, CrossEncoderReranker, confidence_mass_select, _configured_model
from services.search_pipeline import rank_and_merge, run_search_pipeline, SearchBudget, _rerank_query


def plan():
 return {'research_question':'LLM agents for schedule planning', 'decomposed_queries':['LLM agents schedule planning'], 'constraints':{'topics':['schedule planning'],'methods':['LLM'],'datasets':[],'venues':[],'exclude':[]}}

class QualityRegressions(unittest.TestCase):
 def test_deepseek_planning_uses_configured_mode_and_output_budget(self):
  options={'max_output_tokens':4096,'thinking':'disabled','timeout':30}
  settings=SimpleNamespace(base_url='https://example.invalid',api_key='test-key',get=lambda k,d=None:options.get(k,d))
  response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'constraints':{},'decomposed_queries':['paper search agents']})))],usage=SimpleNamespace(prompt_tokens=1,completion_tokens=1,total_tokens=2),model='deepseek-v4-flash',system_fingerprint=None)
  with patch('services.llm_service._provider_settings',return_value=('deepseek','deepseek-v4-flash',settings)),patch('services.llm_service.OpenAI') as api:
   api.return_value.chat.completions.create.return_value=response
   analyze_search_query('paper search agents','deepseek','deepseek-v4-flash')
  request=api.return_value.chat.completions.create.call_args.kwargs
  self.assertEqual(request['max_tokens'],4096)
  self.assertEqual(request['extra_body'],{'thinking':{'type':'disabled'}})

 def test_local_model_instance_reused_across_requests(self):
  first=_configured_model('test-model',8,512,'cpu')
  self.assertIs(first,_configured_model('test-model',8,512,'cpu'))
  self.assertIsNot(first,_configured_model('different-model',8,512,'cpu'))

 def test_chinese_intent_uses_compiled_english_for_english_model(self):
  p={'research_question':'寻找图像匹配论文','decomposed_queries':['Transformer image matching','image matching ScanNet']}
  q=_rerank_query(p,'寻找图像匹配论文','cross-encoder/ms-marco-MiniLM-L6-v2')
  self.assertEqual(q,'Transformer image matching ; image matching ScanNet')

 def test_multilingual_model_keeps_original_intent(self):
  p={'research_question':'寻找图像匹配论文','decomposed_queries':['Transformer image matching']}
  self.assertEqual(_rerank_query(p,'query','BAAI/bge-reranker-base'),'寻找图像匹配论文')

 def test_missing_english_compilation_does_not_feed_chinese_to_english_model(self):
  self.assertIsNone(_rerank_query({'research_question':'复杂中文需求'},'复杂中文需求','cross-encoder/ms-marco-MiniLM-L6-v2'))

 def test_partial_method_does_not_replace_research_intent(self):
  p=_normalize_plan({'constraints':{'topics':['schedule planning'],'methods':['LLM']},'decomposed_queries':['LLM','LLM agents schedule planning']},'Give me some papers showing that LLM agents can do schedule planning.')
  self.assertEqual(p['decomposed_queries'][0],'LLM agents schedule planning')
  self.assertNotIn('LLM',p['decomposed_queries'])

 def test_command_sentence_needs_semantic_planning(self):
  self.assertIsNone(_heuristic_plan('Show me all research papers on machine translation agents.'))
  self.assertIsNotNone(_heuristic_plan('LLM agents schedule planning'))

 def test_logit_conversion_is_monotonic_at_one(self):
  self.assertLess(_probability(.9),_probability(1.1))
  self.assertAlmostEqual(_probability(0),.5)

 def test_reranker_requests_logits_and_preserves_order(self):
  class Fake:
   def predict(self,pairs,**kwargs):
    self.activation=kwargs['activation_fn']
    return [.9,1.1]
  model=Fake();r=CrossEncoderReranker('test');r._model=model
  rows=[{'id':'a','title':'A','relevanceScore':.5},{'id':'b','title':'B','relevanceScore':.5}]
  self.assertEqual([p['id'] for p in r.rerank('query',rows,2)],['b','a'])
  self.assertEqual(model.activation.__class__.__name__,'Identity')

 def test_near_tie_extension_does_not_walk_an_entire_score_chain(self):
  rows=[{'id':str(i),'relevanceScore':x} for i,x in enumerate([.9,.8,.7,.6,.5])]
  selected,_=confidence_mass_select(rows,breadth_level=3)
  self.assertEqual(len(selected),4)

 def test_merges_preprint_and_published_record_without_losing_provenance(self):
  title='Learning Reliable Schedule Planning with Language Model Agents'
  a={'id':'oa','doi':'10.1234/published','title':title,'authors':'Alice Smith','year':2024,'abstract':'short'}
  b={'id':'s2_x','doi':'10.48550/arXiv.2401.12345','title':title,'authors':'Alice Smith','year':2024,'abstract':'a longer abstract','arxivId':'2401.12345v2'}
  rows=rank_and_merge([('OpenAlex','LLM agents schedule planning',[a]),('Semantic Scholar','LLM agents schedule planning',[b])],plan(),20)
  self.assertEqual(len(rows),1)
  self.assertEqual(set(rows[0]['recordIds']),{'oa','s2_x'})
  self.assertEqual(len(rows[0]['sources']),2)

 def test_same_title_different_authors_not_merged(self):
  title='Learning Reliable Schedule Planning with Language Model Agents'
  a={'id':'a','doi':'10.123/a','title':title,'authors':'Alice Smith','year':2024}
  b={'id':'b','doi':'10.123/b','title':title,'authors':'Bob Jones','year':2024}
  self.assertEqual(len(rank_and_merge([('OpenAlex','query',[a,b])],plan(),20)),2)

class RoutingRegressions(unittest.IsolatedAsyncioTestCase):
 async def test_missing_dataset_triggers_budgeted_search_even_if_lexical_gate_stops(self):
  p=plan();p['constraints']['datasets']=['BenchmarkX'];p['decomposed_queries']+=['LLM agents BenchmarkX']
  calls=[]
  async def retrieve(q,n):
   calls.append(q)
   return [{'id':q,'title':'LLM schedule planning agents','abstract':'schedule planning with LLM agents','year':2024}]
  with patch('services.search_pipeline.egrr_decision',return_value={'route':False}),patch('services.search_pipeline.cache_set'):
   r=await run_search_pipeline('query',limit=20,plan_override=p,budget=SearchBudget(4,15,4,'coverage'),retrievers={'test':retrieve},reranker_metadata={'status':'disabled'})
  self.assertTrue(r['coverage']['secondRoundTriggered'])
  self.assertLessEqual(r['metrics']['apiCalls'],4)
