import unittest, tempfile, sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from ledger import connect, add_product, move, snapshot, reconcile
class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';self.db=connect(self.path);add_product(self.db,'BOOK','Book')
    def tearDown(self): self.db.close();self.temp.cleanup()
    def test_receive_and_issue(self):
        move(self.db,'BOOK',10,'Receive','1');move(self.db,'BOOK',-3,'Issue','2');self.assertEqual(snapshot(self.db)['products'][0]['stock'],7);self.assertEqual(reconcile(self.db),[])
    def test_insufficient_stock_rolls_back(self):
        with self.assertRaises(ValueError): move(self.db,'BOOK',-1,'Issue','1')
        self.assertEqual(snapshot(self.db)['movements'],[]);self.assertEqual(snapshot(self.db)['products'][0]['stock'],0)
    def test_retry_is_idempotent(self):
        move(self.db,'BOOK',10,'Receive','same');r=move(self.db,'BOOK',10,'Receive','same');self.assertTrue(r['replayed']);self.assertEqual(snapshot(self.db)['products'][0]['stock'],10)
    def test_reused_id_different_payload_rejected(self):
        move(self.db,'BOOK',10,'Receive','same')
        with self.assertRaises(ValueError): move(self.db,'BOOK',11,'Receive','same')
        self.assertEqual(len(snapshot(self.db)['movements']),1)
    def test_invalid_quantities(self):
        for delta in [0,True,1.5,'2',1000001]:
            with self.assertRaises(ValueError): move(self.db,'BOOK',delta,'Reason','id')
    def test_unknown_sku(self):
        with self.assertRaises(ValueError): move(self.db,'NO',1,'Reason','id')
    def test_duplicate_product(self):
        with self.assertRaises(ValueError): add_product(self.db,'BOOK','Again')
    def test_sql_text_remains_data(self):
        add_product(self.db,"x'; DROP TABLE products;--",'Unusual SKU');self.assertEqual(len(snapshot(self.db)['products']),2)
    def test_persistence(self):
        move(self.db,'BOOK',4,'Receive','1');other=connect(self.path)
        try:self.assertEqual(snapshot(other)['products'][0]['stock'],4)
        finally:other.close()
    def test_failed_history_insert_rolls_back_balance(self):
        self.db.execute("CREATE TRIGGER fail_insert BEFORE INSERT ON movements BEGIN SELECT RAISE(ABORT,'test failure'); END;")
        with self.assertRaises(sqlite3.IntegrityError): move(self.db,'BOOK',5,'Receive','1')
        self.assertEqual(snapshot(self.db)['products'][0]['stock'],0)
    def test_reconciliation_detects_manual_corruption(self):
        with self.db:self.db.execute('UPDATE products SET stock=8')
        self.assertEqual(reconcile(self.db)[0]['recorded'],0)
    def test_concurrent_issues_cannot_oversell(self):
        move(self.db,'BOOK',1,'Receive','initial')
        def issue(i):
            db=connect(self.path)
            try:move(db,'BOOK',-1,'Issue',str(i));return True
            except ValueError:return False
            finally:db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(issue,[1,2]))
        self.assertEqual(sum(results),1);self.assertEqual(snapshot(self.db)['products'][0]['stock'],0);self.assertEqual(reconcile(self.db),[])
if __name__=='__main__':unittest.main(verbosity=2)
