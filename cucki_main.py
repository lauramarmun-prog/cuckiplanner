import os
from typing import Dict, Any, Optional

from fastapi import FastAPI
from fastmcp import FastMCP
from supabase import create_client, Client


url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # esta, no anon
supabase = create_client(url, key)

print("has_service_role:", "SUPABASE_SERVICE_ROLE_KEY" in os.environ)
print("service_role_len:", len(os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")))
print("anon_len:", len(os.environ.get("SUPABASE_ANON_KEY","")))

DEFAULT_CUCKI_USER_ID = os.getenv("CUCKI_DEFAULT_USER_ID", "faf1e3b1-1bca-44b6-a36d-8f4f18138f56")
SHOPPING_TABLE = "madriguera_shopping_list"

sb: Optional[Client] = supabase


def _db() -> Client:
    if sb is None:
        raise RuntimeError("Supabase not configured (missing SUPABASE_URL / SUPABASE_*_KEY)")
    return sb


def _resolve_user_id(user_id: str | None) -> str:
    resolved = (user_id or DEFAULT_CUCKI_USER_ID or "").strip()
    if not resolved:
        raise RuntimeError("Missing user_id and CUCKI_DEFAULT_USER_ID")
    return resolved


def _shopping_select_query(user_id: str):
    return (
        _db()
        .table(SHOPPING_TABLE)
        .select("id,user_id,name,category,qty,done,created_at")
        .eq("user_id", user_id)
    )


def _shopping_insert(user_id: str, name: str, category: str, qty: str, done: bool = False) -> Dict[str, Any]:
    payload = {
        "user_id": user_id,
        "name": name,
        "category": category,
        "qty": qty,
        "done": done,
    }
    res = _db().table(SHOPPING_TABLE).insert(payload).execute()
    return (res.data or [{}])[0]


mcp = FastMCP("Cucki Planner MCP")


@mcp.tool
def planner_default_user_id() -> dict:
    return {"ok": True, "user_id": DEFAULT_CUCKI_USER_ID}


@mcp.tool
def planner_shopping_list(user_id: str | None = None, include_done: bool = True) -> dict:
    resolved_user_id = _resolve_user_id(user_id)
    query = _shopping_select_query(resolved_user_id)
    if not include_done:
        query = query.eq("done", False)
    res = query.order("created_at", desc=True).execute()
    return {"ok": True, "user_id": resolved_user_id, "items": res.data or []}


@mcp.tool
def planner_shopping_add(
    name: str,
    user_id: str | None = None,
    category: str = "Otros",
    qty: str = "1",
    done: bool = False,
) -> dict:
    resolved_user_id = _resolve_user_id(user_id)
    row = _shopping_insert(user_id=resolved_user_id, name=name, category=category, qty=qty, done=done)
    return {"ok": True, "user_id": resolved_user_id, "item": row}


@mcp.tool
def planner_shopping_update(
    item_id: str,
    name: str | None = None,
    category: str | None = None,
    qty: str | None = None,
    done: bool | None = None,
    user_id: str | None = None,
) -> dict:
    changes: Dict[str, Any] = {}
    if name is not None:
        changes["name"] = name
    if category is not None:
        changes["category"] = category
    if qty is not None:
        changes["qty"] = qty
    if done is not None:
        changes["done"] = done
    if not changes:
        return {"ok": False, "error": "No fields to update"}

    query = _db().table(SHOPPING_TABLE).update(changes).eq("id", item_id)
    if user_id:
        query = query.eq("user_id", user_id)
    res = query.execute()
    return {"ok": True, "updated": res.data or []}


@mcp.tool
def planner_shopping_set_done(item_id: str, done: bool = True, user_id: str | None = None) -> dict:
    query = _db().table(SHOPPING_TABLE).update({"done": done}).eq("id", item_id)
    if user_id:
        query = query.eq("user_id", user_id)
    res = query.execute()
    return {"ok": True, "updated": res.data or []}


@mcp.tool
def planner_shopping_delete(item_id: str, user_id: str | None = None) -> dict:
    query = _db().table(SHOPPING_TABLE).delete().eq("id", item_id)
    if user_id:
        query = query.eq("user_id", user_id)
    res = query.execute()
    return {"ok": True, "deleted": res.data or []}


mcp_app = mcp.http_app(path="/")
app = FastAPI(lifespan=mcp_app.lifespan)


@app.get("/")
def root():
    return {"ok": True, "msg": "Cucki Planner MCP online"}


app.mount("/mcp", mcp_app)



