"""Inventory domain logic. Standard-library only; quantities are whole units."""
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(name) > 0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0)
);
CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL UNIQUE,
    sku TEXT NOT NULL REFERENCES products(sku),
    delta INTEGER NOT NULL CHECK(delta != 0),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
"""
def connect(path):
    db=sqlite3.connect(str(path), timeout=5)
    db.row_factory=sqlite3.Row
    db.executescript(SCHEMA)
    return db

def text(value, label, maximum):
    if not isinstance(value,str) or not value.strip() or len(value.strip())>maximum:
        raise ValueError(f'{label} must contain 1–{maximum} characters.')
    return value.strip()

def add_product(db, sku, name):
    sku=text(sku,'SKU',40); name=text(name,'Name',120)
    try:
        with db: db.execute('INSERT INTO products(sku,name) VALUES (?,?)',(sku,name))
    except sqlite3.IntegrityError as error:
        raise ValueError('That SKU already exists.') from error
    return {'sku':sku,'name':name,'stock':0}

def move(db, sku, delta, reason, request_id):
    sku=text(sku,'SKU',40);reason=text(reason,'Reason',200);request_id=text(request_id,'Request ID',100)
    if type(delta) is not int or delta==0 or abs(delta)>1000000:
        raise ValueError('Quantity change must be a non-zero integer between -1000000 and 1000000.')
    # Acquire the write lock before reading stock: another writer cannot interleave.
    try:
        db.execute('BEGIN IMMEDIATE')
        existing=db.execute('SELECT * FROM movements WHERE request_id=?',(request_id,)).fetchone()
        if existing:
            if (existing['sku'],existing['delta'],existing['reason'])!=(sku,delta,reason):
                raise ValueError('Request ID was already used for a different movement.')
            db.commit()
            return {'movement':dict(existing),'replayed':True}
        product=db.execute('SELECT stock FROM products WHERE sku=?',(sku,)).fetchone()
        if product is None: raise ValueError('Unknown SKU.')
        if product['stock']+delta<0: raise ValueError('Not enough stock. Nothing was changed.')
        db.execute('UPDATE products SET stock=stock+? WHERE sku=?',(delta,sku))
        cursor=db.execute('INSERT INTO movements(request_id,sku,delta,reason) VALUES (?,?,?,?)',(request_id,sku,delta,reason))
        row=db.execute('SELECT * FROM movements WHERE id=?',(cursor.lastrowid,)).fetchone()
        db.commit()
        return {'movement':dict(row),'replayed':False}
    except Exception:
        db.rollback()
        raise

def snapshot(db):
    return {'products':[dict(r) for r in db.execute('SELECT * FROM products ORDER BY sku')],
            'movements':[dict(r) for r in db.execute('SELECT * FROM movements ORDER BY id DESC')]}

def reconcile(db):
    rows=db.execute('SELECT p.sku,p.stock,COALESCE(SUM(m.delta),0) AS recorded FROM products p LEFT JOIN movements m ON m.sku=p.sku GROUP BY p.sku ORDER BY p.sku')
    return [dict(r) for r in rows if r['stock']!=r['recorded']]
