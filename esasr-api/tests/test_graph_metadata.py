import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from services.scholar_service import get_citation_graph

class GraphMetadataTests(unittest.IsolatedAsyncioTestCase):
 async def run_graph(self, details):
  response=MagicMock();response.json.return_value={'title':'Center','referenced_works':['https://openalex.org/W2'],'related_works':['https://openalex.org/W3']}
  client=AsyncMock();client.get.return_value=response
  context=MagicMock();context.__aenter__=AsyncMock(return_value=client);context.__aexit__=AsyncMock(return_value=None)
  with patch('services.scholar_service.httpx.AsyncClient',return_value=context),patch('services.scholar_service.get_paper_details',new=AsyncMock(side_effect=details)),patch('services.scholar_service.run_query',new=AsyncMock()):
   return await get_citation_graph('W1')
 async def test_resolves_titles_and_preserves_relation_types(self):
  g=await self.run_graph([{'title':'A real reference','year':2020,'venue':'CVPR'},{'title':'A related study','year':2021}]);nodes={n['id']:n for n in g['nodes']}
  self.assertEqual(nodes['W2']['data']['title'],'A real reference');self.assertEqual(nodes['W2']['data']['year'],2020)
  self.assertEqual(nodes['W3']['style']['labelText'],'A related study')
  self.assertEqual([e['type'] for e in g['edges']],['CITES','RELATED'])
 async def test_missing_metadata_does_not_fabricate_titles_or_drop_graph(self):
  g=await self.run_graph([RuntimeError('timeout'),{'title':'[Mock] API Error'}]);self.assertEqual(len(g['edges']),2)
  self.assertEqual(g['nodes'][1]['style']['labelText'],'W2');self.assertEqual(g['nodes'][2]['style']['labelText'],'W3')
if __name__=='__main__':unittest.main()
