"""Real HTTP integration tests against an ephemeral loopback server and temporary DB."""
import csv
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
import urllib.error
import urllib.request
from pathlib import Path
from server import make_server
from ledger import connect, add_product, move, inventory
from backup import backup

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3'
        self.server=make_server(self.path);self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def request(self,path,body=None,headers=None,raw=False):
        data=None if body is None else body if isinstance(body,bytes) else json.dumps(body).encode()
        h={'Content-Type':'application/json'} if body is not None else {}
        h.update(headers or {});req=urllib.request.Request(self.base+path,data=data,headers=h)
        try:r=urllib.request.urlopen(req,timeout=5)
        except urllib.error.HTTPError as e:r=e
        with r:
            content=r.read();return r.status,content if raw else json.loads(content),r.headers
    def product(self):
        status,p,_=self.request('/api/products',{'sku':'BOOK-01','name':'Notebook','reorder_level':5});self.assertEqual(status,200);return p
    def movement(self,delta=10,key='r1',reason='Opening stock'):
        return self.request('/api/movements',{'sku':'BOOK-01','delta':delta,'request_id':key,'reason':reason})
    def test_receive_issue_retry_conflict_and_oversell(self):
        self.product();self.assertEqual(self.movement()[0],200)
        self.assertFalse(self.movement(-3,'r2')[1]['replayed']);self.assertTrue(self.movement(-3,'r2')[1]['replayed'])
        self.assertEqual(self.movement(-4,'r2')[0],400);self.assertEqual(self.movement(-8,'r3')[0],400)
        state=self.request('/api/state')[1];self.assertEqual(state['products'][0]['stock'],7);self.assertEqual(state['reconciliation_errors'],[])
    def test_reorder_validation_and_duplicate_product(self):
        self.assertEqual(self.product()['reorder_level'],5)
        self.assertEqual(self.request('/api/products',{'sku':'BOOK-01','name':'Duplicate'})[0],400)
        for invalid in [-1,True,1.5,'5']:
            self.assertEqual(self.request('/api/products',{'sku':'X','name':'X','reorder_level':invalid})[0],400)
    def test_history_pagination_and_filter(self):
        self.product()
        for n in range(23):self.movement(1,f'r{n}')
        self.request('/api/products',{'sku':'OTHER','name':'Other'})
        self.request('/api/movements',{'sku':'OTHER','delta':1,'reason':'Other','request_id':'other'})
        a=self.request('/api/movements?sku=BOOK-01&limit=20&offset=0')[1];b=self.request('/api/movements?sku=BOOK-01&limit=20&offset=20')[1]
        self.assertEqual(a['total'],23);self.assertEqual(len(a['movements']),20);self.assertEqual(len(b['movements']),3)
        self.assertFalse(set(x['id'] for x in a['movements'])&set(x['id'] for x in b['movements']))
        self.assertEqual(self.request('/api/movements?limit=101')[0],400);self.assertEqual(self.request('/api/movements?offset=-1')[0],400)
    def test_csv_roundtrip_and_formula_neutralization(self):
        self.request('/api/products',{'sku':'=CMD','name':'Comma, "quoted"\nline','reorder_level':2})
        status,body,headers=self.request('/api/export/products.csv',raw=True);self.assertEqual(status,200)
        rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))));self.assertEqual(rows[0]['sku'],"'=CMD");self.assertEqual(rows[0]['name'],'Comma, "quoted"\nline')
        self.assertIn('attachment',headers['Content-Disposition'])
        self.product();self.movement(reason='=SUM(1,2)')
        rows=list(csv.DictReader(io.StringIO(self.request('/api/export/movements.csv?sku=BOOK-01',raw=True)[1].decode('utf-8-sig'))))
        self.assertEqual(rows[0]['reason'],"'=SUM(1,2)");self.assertEqual(len(rows),1)
    def test_bad_requests_and_cross_origin_are_rejected(self):
        self.assertEqual(self.request('/api/products',b'{')[0],400)
        self.assertEqual(self.request('/api/products',[])[0],400)
        self.assertEqual(self.request('/api/products',{},headers={'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('/api/products',{},headers={'Origin':'https://example.com'})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'attacker.example'})[0],403)
        self.assertEqual(self.request('/api/products',b'x'*8193)[0],413)
    def test_static_health_and_not_found(self):
        for path in ['/','/app.js','/style.css']:self.assertEqual(self.request(path,raw=True)[0],200)
        self.assertEqual(self.request('/api/health')[1]['version'],2)
        self.assertEqual(self.request('/../ledger.py')[0],404)
    def test_backup_is_consistent_and_refuses_overwrite(self):
        self.product();self.movement();dest=Path(self.temp.name)/'backup.sqlite3';backup(self.path,dest)
        with closing(connect(dest)) as db:self.assertEqual(inventory(db)['products'][0]['stock'],10)
        self.assertEqual(self.request('/api/state')[1]['products'][0]['stock'],10)
        with self.assertRaises(FileExistsError):backup(self.path,dest)
    def test_migration_preserves_old_data(self):
        old=Path(self.temp.name)/'old.sqlite3'
        with closing(sqlite3.connect(old)) as db:
            with db:
                db.execute('CREATE TABLE products (sku TEXT PRIMARY KEY,name TEXT NOT NULL,stock INTEGER NOT NULL DEFAULT 0)')
                db.execute("INSERT INTO products VALUES ('OLD','Old product',0)")
        db=connect(old)
        try:
            p=inventory(db)['products'][0];self.assertEqual(p['sku'],'OLD');self.assertEqual(p['reorder_level'],0)
        finally:db.close()

if __name__=='__main__':unittest.main()
