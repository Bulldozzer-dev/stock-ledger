# Stock Ledger — backend correctness and persistence

### The problem and a short explanation

A small stock system must do more than display a quantity. It must record why stock changed, reject an issue when there is not enough stock, and avoid processing the same request twice after a retry.

Practice explanation: “Stock Ledger is a local inventory prototype. Products start with zero stock, and every receipt or issue creates a movement. The balance update and movement entry happen in one transaction. I also use a unique request ID so retrying a request does not change the stock again.”

### Run it

Extract `stock-ledger-source.zip` and open a terminal in the extracted folder. Python 3.10 or newer is required. Use the command supported by your installation:

```text
python server.py
```

On Windows with the Python launcher installed:

```text
py -3 server.py
```

Open `http://127.0.0.1:8095` in your browser. Opening `index.html` directly does not start the server. Stop the server with Ctrl+C. By default, `inventory.sqlite3` is stored next to the program and survives a restart. For a separate sample database or occupied port:

```text
python server.py --db practice.sqlite3 --port 8096
```

### Architecture and files

```text
Browser form
    → JSON HTTP request
    → server.py route and input handling
    → ledger.py inventory function
    → SQLite transaction
    → JSON response
    → browser refresh
```

- `index.html`: forms, fetch calls and safe text rendering. It includes its styles and JavaScript so the server serves one UI file.
- `server.py`: starts a loopback-only HTTP server, handles routes, limits request bodies and returns JSON responses.
- `ledger.py`: schema, connection setup, input validation, product creation, stock movements, snapshots and reconciliation.
- `test_ledger.py`: temporary-database tests, including a concurrent withdrawal test and an intentionally failed insert.
- `.github/workflows/tests.yml`: configuration to run tests on a future GitHub push. It has not run on GitHub yet.

### Data model

`products` has a text `sku` primary key, a product `name` and a nonnegative integer `stock`. `movements` has an auto-incremented `id`, unique `request_id`, product `sku`, signed integer `delta`, `reason` and a UTC creation timestamp. A foreign key ties each movement to its product.

A receipt has a positive delta; an issue has a negative delta. The system handles whole units, not prices or financial valuation. Product stock starts at zero, so the sum of all its recorded deltas should equal its current stock.

The balance is stored separately for simple reads. That introduces a consistency obligation: updates to stock and history must always commit together. `reconcile()` checks that obligation by comparing each stored balance to `SUM(delta)`.

### Follow the important functions

`connect(path)` opens SQLite, enables foreign keys and creates tables if needed. `text()` trims and validates bounded, nonempty text. `add_product()` uses parameterized SQL to insert a product at zero stock. Duplicate SKUs produce a readable error.

`move()` is the key function:

1. Validate the SKU, reason, request ID and quantity. Booleans are rejected even though Python treats bool as a subclass of int.
2. Start `BEGIN IMMEDIATE` to reserve SQLite's writer lock before checking the balance.
3. Look up the request ID. If the same ID already exists with the same SKU, delta and reason, return the original movement with `replayed: true`.
4. If that ID was used with different content, reject it. A request ID identifies one operation, not a session.
5. Confirm that the product exists and that the resulting stock will not be negative.
6. Update stock and insert the movement inside the same transaction.
7. Commit only after both succeed. On an exception, roll back the entire transaction.

`snapshot()` reads products and history. `reconcile()` returns only discrepancies; an empty list means the recorded totals match the stored balances.

### API contract

- `POST /api/products`: JSON with `sku` and `name`.
- `POST /api/movements`: JSON with `sku`, integer `delta`, `reason` and `request_id`.
- `GET /api/state`: products, movement history and reconciliation errors.

The current implementation returns HTTP 200 for a successful creation or movement, 400 for invalid domain input, 404 for unknown routes, 413 for an invalid body size, 415 for an unsupported content type and 503 for a database error. A production API could refine these distinctions, including 201 for creation and 409 for conflicts.

### A five-minute demonstration

1. Create product `BOOK-01`, named `Exercise book`.
2. Receive 10 units using request ID `receive-001` and reason `Opening stock`.
3. Generate a new request ID or enter `issue-001`. Issue 3 units by entering `-3`. The balance should be 7.
4. Submit the same issue again without changing its ID or content. The response should say it was already recorded. The balance should remain 7.
5. Use a new ID and try to issue 8 units. It should fail without a new movement or changed balance.
6. Refresh and restart the server to demonstrate persistence. Show the history and reconciliation message.

These are expected browser results to verify, not a claim that the browser demonstration was executed in the authoring environment.

### Tests and why they matter

Run `python -m unittest -v test_ledger.py`. All 12 tests passed locally. They cover receipts/issues, overselling rollback, retry idempotency, conflicting request IDs, invalid quantities, unknown SKUs, duplicate products, SQL-like text, persistence, forced history-insert failure, reconciliation and concurrent withdrawals.

The forced-failure test creates a database trigger that aborts the movement insert. It then checks that the earlier balance update was rolled back. The concurrency test gives a product one unit and uses two database connections to issue one unit each. Exactly one succeeds. This verifies a real race condition at the database layer; it does not prove performance at large scale.

### Interview questions

**Why use a transaction?** Without it, the stock could change while its history insert failed. A transaction makes those related changes all-or-nothing.

**What does idempotency solve?** A client may retry because it did not receive the response. Reusing the same request ID returns the original movement rather than applying the quantity again. Clicking “New request ID” creates a different operation.

**Why acquire the lock before reading stock?** Otherwise two writers could both read the same available balance and decide it is safe to issue. SQLite serializes writers; the second transaction must see the updated state after the first completes.

**Is the history immutable?** The application offers no edit/delete route for it, but anyone with database-file access can change it. It is not tamper-proof or a compliance-grade audit log.

**How would you scale it?** First add authentication, authorization, pagination, migrations, operational logging and backups. For heavier concurrent workloads, assess a database such as PostgreSQL and design transaction isolation deliberately. Those are future changes, not implemented capabilities.

### Your own extension exercise

Add a reorder threshold per product and a low-stock filter. Decide whether equality counts as low stock, write tests for that boundary, update the schema through a migration rather than deleting existing data, and explain the UI change in a small commit. This gives you a concrete contribution to discuss.



Created with AI coding assistance. Local tests passed. Browser verification remains pending. Source and automated test workflow are available in this repository.
