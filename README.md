# Stock Ledger

A local Python + SQLite inventory application with a browser UI. Receive and issue whole units, inspect movement history and reconcile balances. Uses only Python's standard library.

## Run
1. Install Python 3.10 or newer.
2. Open a terminal in this folder and run `python server.py` (on Windows, `py -3 server.py` also works when the launcher is installed).
3. Open http://127.0.0.1:8095. Do not open index.html directly.
4. Create BOOK-01, receive 10 units, then issue 3 with a new request ID. The balance should be 7.
5. Retry the same movement with the same ID: no second deduction occurs.
6. Try to issue 8: the change is rejected and the balance stays 7.
7. Stop with Ctrl+C. The database persists next to the application. Use `--db another.sqlite3` to start a separate demo database, or `--port 8096` for another local port.

## Test
`python -m unittest -v test_ledger.py`

## Architecture
Browser forms → JSON HTTP routes → ledger.py domain functions → SQLite.
- POST /api/products accepts sku and name.
- POST /api/movements accepts sku, integer delta, reason and request_id.
- GET /api/state returns products, movements and reconciliation discrepancies.

`BEGIN IMMEDIATE` obtains SQLite's write lock before checking stock. Balance updates and history inserts share a transaction. A unique request ID prevents duplicate retries; a reused ID with different content is rejected. SQL values are parameterized. Database CHECK constraints guard nonnegative balances. Reconciliation compares each balance with the sum of its recorded changes.

## Limits
Local learning prototype; bind is deliberately 127.0.0.1. No user authentication, roles, HTTPS, migrations, pagination, rate limiting or backup process. History is not tamper-proof. It handles whole units only, not valuations, taxes or payments. SQLite serializes writes and this is not a distributed design. API responses currently return all history, with only 50 displayed in the UI. No claim of production readiness.

## Verification scope
Tests exercise the domain and actual SQLite database, including concurrent issues, persistence and forced rollback. Browser UI and end-to-end HTTP behavior require manual review; local networking is restricted in the authoring environment.

## Development
Created with AI coding assistance for Simon Wagathiru. See the portfolio guide for an explanation, demo script and interview questions. Understand the transaction and retry behavior before presenting it as portfolio work.
