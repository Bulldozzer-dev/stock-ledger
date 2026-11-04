# Local HTTP API / v2

Base URL: `http://127.0.0.1:8095` (or the printed port). Requests must use that exact host. JSON mutations require `Content-Type: application/json`, with an object body of at most 8192 bytes. Cross-origin browser requests are rejected. No CORS access is granted.

| Method | Route | Behavior |
|---|---|---|
| GET | /api/health | status and API version |
| GET | /api/state | products and reconciliation_errors, read in one snapshot |
| GET | /api/movements?sku=BOOK-01&limit=20&offset=0 | newest-first movements, total, limit, offset; sku optional |
| POST | /api/products | create product |
| POST | /api/movements | record or replay movement |
| GET | /api/export/products.csv | catalogue CSV attachment |
| GET | /api/export/movements.csv?sku=BOOK-01 | history CSV attachment; sku optional |

## Product request
```json
{"sku":"BOOK-01","name":"Exercise book","reorder_level":5}
```
SKU: 1–40 characters, case sensitive. Name: 1–120. Reorder level: integer 0–1000000, defaults to zero. New products start with zero stock. Duplicate SKU returns HTTP 400.

## Movement request
```json
{"sku":"BOOK-01","delta":10,"reason":"Opening stock","request_id":"opening-001"}
```
Delta is a nonzero integer from -1000000 to 1000000. Reason: 1–200 characters. Request ID: 1–100. Whitespace at the edges of strings is trimmed. Unknown SKU, insufficient stock or conflicting retry returns HTTP 400. An identical retry returns the original movement and `replayed: true`, without changing stock.

Successful JSON writes return 200. Validation errors return 400 with `{"error":"..."}`. Disallowed host/origin: 403. Unknown route: 404. Unsupported content type: 415. Invalid body size: 413. SQLite errors: 503. A malformed Content-Length returns 400. This is a local application, with no authentication or public service guarantee.

If a movement request times out, retry the identical payload with the same request ID. For a new movement, use a fresh ID. A database failure returns a retry instruction and rolls back the transaction. Product creation does not provide request-ID replay; after an ambiguous response, inspect state before retrying.

History limit is 1–100; offset is 0–10000000. Offset paging is not a frozen snapshot: new movements may shift later pages. Export the CSV to inspect one complete query result. CSVs use UTF-8 with BOM and escape formula-like text with a leading apostrophe for spreadsheet safety. No destructive API is exposed.
