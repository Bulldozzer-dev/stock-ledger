"""Loopback-only inventory server. Standard-library only; not an internet service."""
import argparse
import csv
import io
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from ledger import connect, add_product, move, history, inventory

HERE=Path(__file__).resolve().parent
def csv_bytes(rows, fields):
    stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(fields)
    for row in rows:
        # Escape spreadsheet formula prefixes on text cells; numeric deltas remain numeric.
        writer.writerow([("'"+row[k] if isinstance(row[k],str) and row[k].lstrip().startswith(('=','+','-','@','\t','\r','\n')) else row[k]) for k in fields])
    return ('\ufeff'+stream.getvalue()).encode('utf-8')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def send(self,status,content,kind,filename=None):
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(content)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if filename:self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers();self.wfile.write(content)
    def reply(self,status,data):self.send(status,json.dumps(data).encode(),'application/json; charset=utf-8')
    def allowed(self):
        if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':
            self.reply(403,{'error':'Use the printed 127.0.0.1 address.'});return False
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://127.0.0.1:{self.server.server_port}':
            self.reply(403,{'error':'Origin not allowed.'});return False
        return True
    def do_GET(self):
        if not self.allowed():return
        route=urlsplit(self.path);query=parse_qs(route.query,keep_blank_values=True);db=None
        try:
            static={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if route.path in static:
                name,kind=static[route.path];return self.send(200,(HERE/name).read_bytes(),kind)
            if route.path=='/api/health':return self.reply(200,{'status':'ok','version':2})
            if route.path not in ['/api/state','/api/movements','/api/export/products.csv','/api/export/movements.csv']:return self.reply(404,{'error':'Not found.'})
            db=connect(self.server.db_path)
            sku=query.get('sku',[None])[0] or None
            if route.path=='/api/state':return self.reply(200,inventory(db))
            if route.path=='/api/movements':return self.reply(200,history(db,sku,int(query.get('limit',['20'])[0]),int(query.get('offset',['0'])[0])))
            if route.path=='/api/export/products.csv':
                rows=inventory(db)['products'];fields=['sku','name','stock','reorder_level'];name='inventory.csv'
            else:
                params=[];where=''
                if sku:
                    from ledger import text
                    sku=text(sku,'SKU',40);where=' WHERE sku=?';params=[sku]
                rows=db.execute('SELECT * FROM movements'+where+' ORDER BY id DESC',params)
                fields=['id','created_at','sku','delta','reason','request_id'];name='movements.csv'
            self.send(200,csv_bytes(rows,fields),'text/csv; charset=utf-8',name)
        except (ValueError,TypeError) as error:self.reply(400,{'error':str(error)})
        except sqlite3.Error:self.reply(503,{'error':'Database unavailable. Try again.'})
        finally:
            if db is not None:db.close()
    def do_POST(self):
        if not self.allowed():return
        if self.headers.get('Content-Type','').split(';')[0].strip()!='application/json':return self.reply(415,{'error':'Use application/json.'})
        db=None
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=8192:return self.reply(413,{'error':'Request body must be 1–8192 bytes.'})
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError('Body must be a JSON object.')
            db=connect(self.server.db_path);route=urlsplit(self.path).path
            if route=='/api/products':result=add_product(db,data.get('sku'),data.get('name'),data.get('reorder_level',0))
            elif route=='/api/movements':result=move(db,data.get('sku'),data.get('delta'),data.get('reason'),data.get('request_id'))
            else:return self.reply(404,{'error':'Not found.'})
            self.reply(200,result)
        except (ValueError,TypeError,UnicodeError) as error:self.reply(400,{'error':str(error)})
        except sqlite3.Error:self.reply(503,{'error':'Database unavailable. Retry with the same request ID.'})
        finally:
            if db is not None:db.close()

def make_server(path,port=0):
    db=connect(path);db.close();server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.daemon_threads=True;server.db_path=Path(path);return server

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8095);parser.add_argument('--db',type=Path,default=HERE/'inventory.sqlite3');args=parser.parse_args()
    server=make_server(args.db,args.port);print(f'Stock Ledger: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
