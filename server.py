"""Local-only demo server. Do not expose it to a network without hardening."""
import json, sqlite3, argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from ledger import connect, add_product, move, snapshot, reconcile

HERE=Path(__file__).resolve().parent
class Handler(BaseHTTPRequestHandler):
    def reply(self,status,data):
        content=json.dumps(data).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(content)));self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(content)
    def do_GET(self):
        route=urlsplit(self.path).path
        if route=='/':
            data=(HERE/'index.html').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        elif route=='/api/state':
            db=connect(self.server.db_path)
            try: self.reply(200,{**snapshot(db),'reconciliation_errors':reconcile(db)})
            finally: db.close()
        else: self.reply(404,{'error':'Not found.'})
    def do_POST(self):
        # Reject cross-origin browser requests and require non-simple JSON requests.
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':
            return self.reply(403,{'error':'Origin not allowed.'})
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.reply(415,{'error':'Use application/json.'})
        db=None
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192: return self.reply(413,{'error':'Request body must be 1–8192 bytes.'})
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict): raise ValueError('Body must be a JSON object.')
            db=connect(self.server.db_path)
            route=urlsplit(self.path).path
            if route=='/api/products': result=add_product(db,data.get('sku'),data.get('name'))
            elif route=='/api/movements': result=move(db,data.get('sku'),data.get('delta'),data.get('reason'),data.get('request_id'))
            else: return self.reply(404,{'error':'Not found.'})
            self.reply(200,result)
        except (ValueError,TypeError,UnicodeError) as error: self.reply(400,{'error':str(error)})
        except sqlite3.Error: self.reply(503,{'error':'Database unavailable. Retry with the same request ID.'})
        finally:
            if db is not None: db.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8095)
    parser.add_argument('--db',type=Path,default=HERE/'inventory.sqlite3');args=parser.parse_args()
    db=connect(args.db);db.close()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler);server.db_path=args.db
    print(f'Stock Ledger: http://127.0.0.1:{args.port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
