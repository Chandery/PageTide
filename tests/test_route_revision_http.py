"""Actual isolated HTTP preview/confirm/409 contracts, no model calls."""
import copy
import json
import http.client
import unittest
from app import server
from tests import test_app_server
from tests.test_route_store import PLAN


class RevisionHTTPTests(unittest.TestCase):
    setUp=test_app_server.ServerSmokeTests.setUp
    _post=test_app_server.ServerSmokeTests._post
    _get=test_app_server.ServerSmokeTests._get

    def seed(self):
        app=server.make_app(str(self.root))
        try:
            pid=app.create_project('Route patch','manual',['epitaxy'])['project_id']
            app.route_save(pid,plan=PLAN)
            return pid
        finally:app.store.close()

    def preview(self,pid,**extra):
        body={'action':'revision-preview','project_id':pid,'brief':{'goal':'读懂新方向'},'patch':{'operations':[]},**extra}
        return self._post('/api/route',body)

    def test_http_preview_confirm_repeat_and_restart(self):
        pid=self.seed(); status,draft=self.preview(pid)
        self.assertEqual(status,200)
        status,saved=self._post('/api/route',{'action':'revision-confirm','project_id':pid,'draft_id':draft['draft_id']})
        self.assertEqual(status,200);self.assertEqual(saved['brief']['goal'],'读懂新方向')
        status,repeated=self._post('/api/route',{'action':'revision-confirm','project_id':pid,'draft_id':draft['draft_id']})
        self.assertEqual(status,200);self.assertTrue(repeated['duplicate'])
        app=server.make_app(str(self.root))
        try:self.assertEqual(app.route_get(pid)['brief']['goal'],'读懂新方向')
        finally:app.store.close()

    def test_http_graph_conflict_preserves_draft(self):
        pid=self.seed();_,draft=self.preview(pid)
        app=server.make_app(str(self.root))
        try:app.route_mode(pid,'off')
        finally:app.store.close()
        status,out=self._post('/api/route',{'action':'revision-confirm','project_id':pid,'draft_id':draft['draft_id']})
        self.assertEqual(status,409)
        status,out=self._post('/api/route',{'action':'revision-draft','project_id':pid})
        self.assertEqual(status,200);self.assertEqual(out['draft']['draft_id'],draft['draft_id']);self.assertTrue(out['draft']['stale'])

    def test_http_confirmation_rejects_whole_graph_and_client_cutoff(self):
        pid=self.seed();_,draft=self.preview(pid)
        status,_=self._post('/api/route',{'action':'revision-confirm','project_id':pid,'draft_id':draft['draft_id'],'graph':{}})
        self.assertEqual(status,400)
        status,_=self.preview(pid,patch={'operations':[{'op':'update_node','ref':'c1','changes':{'progress_since_feedback_id':0}}]})
        self.assertEqual(status,400)
        status,out=self._post('/api/route',{'action':'revision-draft','project_id':pid})
        self.assertEqual(out['draft']['draft_id'],draft['draft_id'])

    def test_http_invalid_brief_and_stale_revision_do_not_make_drafts(self):
        pid=self.seed()
        for brief in [{},{'goal':'中'*251},{'goal':'g','known':None}]:
            self.assertEqual(self.preview(pid,brief=brief)[0],400)
        self.assertEqual(self.preview(pid,revision=0)[0],409)
        _,out=self._post('/api/route',{'action':'revision-draft','project_id':pid})
        self.assertIsNone(out['draft'])

    def test_raw_duplicate_fields_and_nonfinite_json_are_refused(self):
        pid=self.seed()
        base='{"action":"revision-preview","project_id":'+json.dumps(pid)+',"brief":{"goal":"g"},"patch":{"operations":'
        payloads=[base+'[{"op":"update_node","ref":"c1","changes":{"name":"First","name":"Last"}}]}}',
                  base+'[{"op":"update_node","ref":"c1","changes":{"hint":NaN}}]}}',
                  '{"action":"revision-draft","action":"revision-confirm","project_id":'+json.dumps(pid)+'}']
        for payload in payloads:
            connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=5)
            try:
                connection.request('POST','/api/route',payload,{'Content-Type':'application/json'})
                response=connection.getresponse();response.read();self.assertEqual(response.status,400)
            finally:connection.close()
        _,out=self._post('/api/route',{'action':'revision-draft','project_id':pid})
        self.assertIsNone(out['draft'])

    def test_revision_requires_explicit_project_id(self):
        pid=self.seed()
        for project in [None,'',[],{}]:
            self.assertEqual(self.preview(project)[0],400)
            self.assertEqual(self._post('/api/route',{'action':'revision-draft','project_id':project})[0],400)

    def test_http_unknown_project_and_wrong_draft_identity_are_refused(self):
        self.assertEqual(self.preview('unknown')[0],400)
        pid=self.seed();_,draft=self.preview(pid)
        self.assertEqual(self._post('/api/route',{'action':'revision-confirm','project_id':pid,'draft_id':'0'*32})[0],409)
        self.assertEqual(self._post('/api/route',{'action':'revision-confirm','project_id':pid,'draft_id':[]})[0],400)


if __name__=='__main__':unittest.main()
