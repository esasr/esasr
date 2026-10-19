import unittest,json
from types import SimpleNamespace
from unittest.mock import patch
from services.search_pipeline import _same_title_work,select_initial_queries,run_search_pipeline,SearchBudget
from services.relevance_service import _validate_decisions,_verify
from services.reranker_service import CrossEncoderReranker

class QualityV2(unittest.TestCase):
 def test_unicode_hyphenated_author_variants_merge(self):
  a={'title':'Text-only data synthesis for vision language model training','authors':'Xiaomin Yu, Wenjie Zhang','year':2025}
  b={**a,'authors':'Xiao-Min Yu, Wen-Jie Zhang'}
  self.assertTrue(_same_title_work(a,b))
 def test_short_title_needs_author_evidence(self):
  a={'title':'Generative Adversarial Networks','authors':'Zhipeng Cai','year':2021}
  self.assertFalse(_same_title_work(a,{**a,'authors':'Moez Krichen','year':2023}))
 def test_semantic_rank_cannot_be_overridden_by_source_rank(self):
  r=CrossEncoderReranker('test');r._model=SimpleNamespace(predict=lambda *a,**kw:[-1.,2.])
  rows=r.rerank('intent',[{'id':'generic','relevanceScore':1.},{'id':'specific','relevanceScore':.1}],2)
  self.assertEqual(rows[0]['id'],'specific')
 def test_complementary_query_preferred_to_reordering(self):
  q=['neural network integer quantization','integer quantization neural network','low precision inference acceleration']
  self.assertEqual(select_initial_queries(q),[q[0],q[2]])
 def test_decisions_must_cover_every_candidate(self):
  for raw in [{'decisions':[]},{'decisions':[{'index':0,'relevant':True,'confidence':.9}]*2}]:
   with self.assertRaises(ValueError):_validate_decisions(raw,2)
 def test_string_boolean_is_rejected(self):
  with self.assertRaises(ValueError):_validate_decisions({'decisions':[{'index':0,'relevant':'false','confidence':.9}]},1)
 def test_invalid_json_keeps_predictions_and_usage(self):
  settings=SimpleNamespace(base_url='https://example.invalid',api_key='test',get=lambda k,d:d)
  response=SimpleNamespace(usage=SimpleNamespace(prompt_tokens=20,completion_tokens=5,total_tokens=25),choices=[SimpleNamespace(message=SimpleNamespace(content='invalid'))])
  papers=[{'id':'a'}]
  with patch('services.relevance_service._provider_settings',return_value=('deepseek','deepseek-v4-flash',settings)),patch('services.relevance_service.OpenAI') as api:
   api.return_value.chat.completions.create.return_value=response
   result,meta=_verify('query',papers)
  self.assertEqual(result,papers);self.assertEqual(meta['usage']['total_tokens'],25);self.assertEqual(meta['status'],'fallback')

class PipelineVerification(unittest.IsolatedAsyncioTestCase):
 async def test_verified_empty_result_is_not_replaced_by_irrelevant_top1(self):
  async def retrieve(q,n):return [{'id':'a','title':'Unrelated title','abstract':'different subject'}]
  async def verify(*a,**kw):return [],{'status':'completed','llmCalls':1,'usage':{'total_tokens':50,'prompt_tokens':40,'completion_tokens':10},'evaluated':1,'selected':0}
  from config import cfg
  old=cfg._ranking_raw.get('relevance_verifier');cfg._ranking_raw['relevance_verifier']={'enabled':True}
  try:
   with patch('services.search_pipeline.verify_relevance',verify),patch('services.search_pipeline.cache_set'):
    r=await run_search_pipeline('query',plan_override={'decomposed_queries':['query'],'constraints':{},'usage':{'total_tokens':20}},retrievers={'test':retrieve},budget=SearchBudget(1,15,1,'none'),reranker_metadata={'status':'disabled'})
   self.assertEqual(r['papers'],[]);self.assertEqual(r['metrics']['llmTokens'],70)
  finally:
   if old is None:cfg._ranking_raw.pop('relevance_verifier',None)
   else:cfg._ranking_raw['relevance_verifier']=old
