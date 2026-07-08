import base64
import time
import uuid
from collections import defaultdict
from typing import Optional

from fastapi import FastAPI, Header, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

# -----------------------------
# CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 56
RATE_LIMIT = 18
WINDOW = 10

# -----------------------------
# Fixed catalog of orders
# -----------------------------
orders_catalog = [
    {
        "id": i,
        "item": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -----------------------------
# Stores
# -----------------------------
idempotency_store = {}
client_requests = defaultdict(list)

# -----------------------------
# Request model
# -----------------------------
class OrderCreate(BaseModel):
    item: Optional[str] = None


# -----------------------------
# Rate Limiter Middleware
# -----------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    # Always allow browser preflight
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
            headers={"Retry-After": "10"},
            content={"detail": "Too Many Requests"},
        )

    client_requests[client].append(now)

    return await call_next(request)


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders")
def create_order(
    order: OrderCreate,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):

    # Same key -> same response
    if idempotency_key in idempotency_store:
        response.status_code = 200
        return idempotency_store[idempotency_key]

    created = {
        "id": str(uuid.uuid4()),
        "item": order.item
    }

    idempotency_store[idempotency_key] = created

    response.status_code = 201
    return created


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def list_orders(
    limit: int = Query(10, ge=1),
    cursor: Optional[str] = None
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
        next_cursor = base64.b64encode(
            str(end).encode()
        ).decode()

    return {
        "items": items,
        "next_cursor": next_cursor
    }


# -----------------------------
# Root endpoint
# -----------------------------
@app.get("/")
def root():
    return {
        "message": "Orders API Running"
    }
