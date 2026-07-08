import base64
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, Optional

from fastapi import FastAPI, Body, Header, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# ----------------------------
# CORS
# ----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 56
RATE_LIMIT = 18
WINDOW = 10  # seconds

# ----------------------------
# Fixed catalog (IDs 1..56)
# ----------------------------
orders_catalog = [
    {"id": i, "item": f"Order {i}"}
    for i in range(1, TOTAL_ORDERS + 1)
]

# ----------------------------
# In-memory stores
# ----------------------------
idempotency_store = {}
client_requests = defaultdict(list)

# ----------------------------
# Rate limiting middleware
# ----------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    # Allow browser preflight
    if request.method == "OPTIONS":
        return await call_next(request)

    client = request.headers.get("X-Client-Id", "anonymous")
    now = time.time()

    # Remove expired timestamps
    client_requests[client] = [
        t for t in client_requests[client]
        if now - t < WINDOW
    ]

    if len(client_requests[client]) >= RATE_LIMIT:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too Many Requests"},
            headers={"Retry-After": "10"},
        )

    client_requests[client].append(now)
    return await call_next(request)

# ----------------------------
# Root
# ----------------------------
@app.get("/")
def root():
    return {"message": "Orders API Running"}

# ----------------------------
# POST /orders
# ----------------------------
@app.post("/orders", status_code=201)
def create_order(
    response: Response,
    body: Dict[str, Any] = Body(default={}),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    # Existing idempotency key
    if idempotency_key in idempotency_store:
        response.status_code = 200
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        **body,
    }

    idempotency_store[idempotency_key] = order
    return order

# ----------------------------
# GET /orders
# ----------------------------
@app.get("/orders")
def list_orders(
    limit: int = Query(default=10, ge=1),
    cursor: Optional[str] = Query(default=None),
):
    start = 0

    if cursor:
        try:
            start = int(base64.b64decode(cursor).decode())
        except Exception:
            start = 0

    end = min(start + limit, TOTAL_ORDERS)

    items = orders_catalog[start:end]

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
