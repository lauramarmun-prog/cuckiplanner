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
WEEK_MENU_TABLE = "madriguera_week_menu"
WEIGHT_ENTRIES_TABLE = "madriguera_weight_entries"

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


def _resolve_week_start(week_start: str | None) -> str:
    value = (week_start or "").strip()
    if not value:
        raise RuntimeError("Missing week_start (expected YYYY-MM-DD)")
    return value


def _resolve_day_index(day_index: int) -> int:
    if not isinstance(day_index, int):
        raise RuntimeError("day_index must be an integer")
    if day_index < 1 or day_index > 7:
        raise RuntimeError("day_index must be in range 1..7")
    return day_index


def _resolve_date(value: str | None) -> str:
    resolved = (value or "").strip()
    if not resolved:
        raise RuntimeError("Missing date (expected YYYY-MM-DD)")
    return resolved


def _resolve_weight_kg(value: float) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError):
        raise RuntimeError("weight_kg must be a valid number")
    return resolved


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


@mcp.tool
def planner_week_menu_list(user_id: str | None = None, week_start: str | None = None) -> dict:
    resolved_user_id = _resolve_user_id(user_id)
    resolved_week_start = _resolve_week_start(week_start)
    res = (
        _db()
        .table(WEEK_MENU_TABLE)
        .select("id,user_id,week_start,day_index,breakfast,lunch,dinner,is_done,created_at,updated_at")
        .eq("user_id", resolved_user_id)
        .eq("week_start", resolved_week_start)
        .order("day_index", desc=False)
        .execute()
    )
    return {
        "ok": True,
        "user_id": resolved_user_id,
        "week_start": resolved_week_start,
        "items": res.data or [],
    }


@mcp.tool
def planner_week_menu_add(
    day_index: int,
    breakfast: str = "",
    lunch: str = "",
    dinner: str = "",
    is_done: bool = False,
    user_id: str | None = None,
    week_start: str | None = None,
) -> dict:
    resolved_user_id = _resolve_user_id(user_id)
    resolved_week_start = _resolve_week_start(week_start)
    resolved_day_index = _resolve_day_index(day_index)

    payload = {
        "user_id": resolved_user_id,
        "week_start": resolved_week_start,
        "day_index": resolved_day_index,
        "breakfast": breakfast,
        "lunch": lunch,
        "dinner": dinner,
        "is_done": is_done,
    }
    res = _db().table(WEEK_MENU_TABLE).insert(payload).execute()
    return {"ok": True, "item": (res.data or [{}])[0]}


@mcp.tool
def planner_week_menu_update(
    item_id: str,
    breakfast: str | None = None,
    lunch: str | None = None,
    dinner: str | None = None,
    is_done: bool | None = None,
    day_index: int | None = None,
    user_id: str | None = None,
    week_start: str | None = None,
) -> dict:
    changes: Dict[str, Any] = {}
    if breakfast is not None:
        changes["breakfast"] = breakfast
    if lunch is not None:
        changes["lunch"] = lunch
    if dinner is not None:
        changes["dinner"] = dinner
    if is_done is not None:
        changes["is_done"] = is_done
    if day_index is not None:
        changes["day_index"] = _resolve_day_index(day_index)
    if not changes:
        return {"ok": False, "error": "No fields to update"}

    query = _db().table(WEEK_MENU_TABLE).update(changes).eq("id", item_id)
    if user_id:
        query = query.eq("user_id", user_id)
    if week_start:
        query = query.eq("week_start", week_start)
    res = query.execute()
    return {"ok": True, "updated": res.data or []}


@mcp.tool
def planner_week_menu_delete(item_id: str, user_id: str | None = None, week_start: str | None = None) -> dict:
    query = _db().table(WEEK_MENU_TABLE).delete().eq("id", item_id)
    if user_id:
        query = query.eq("user_id", user_id)
    if week_start:
        query = query.eq("week_start", week_start)
    res = query.execute()
    return {"ok": True, "deleted": res.data or []}


@mcp.tool
def planner_week_menu_upsert_day(
    day_index: int,
    breakfast: str = "",
    lunch: str = "",
    dinner: str = "",
    is_done: bool = False,
    user_id: str | None = None,
    week_start: str | None = None,
) -> dict:
    resolved_user_id = _resolve_user_id(user_id)
    resolved_week_start = _resolve_week_start(week_start)
    resolved_day_index = _resolve_day_index(day_index)

    existing = (
        _db()
        .table(WEEK_MENU_TABLE)
        .select("id,user_id,week_start,day_index,breakfast,lunch,dinner,is_done,created_at,updated_at")
        .eq("user_id", resolved_user_id)
        .eq("week_start", resolved_week_start)
        .eq("day_index", resolved_day_index)
        .limit(1)
        .execute()
    )

    if existing.data:
        row_id = existing.data[0]["id"]
        changes = {
            "breakfast": breakfast,
            "lunch": lunch,
            "dinner": dinner,
            "is_done": is_done,
        }
        updated = (
            _db()
            .table(WEEK_MENU_TABLE)
            .update(changes)
            .eq("id", row_id)
            .eq("user_id", resolved_user_id)
            .eq("week_start", resolved_week_start)
            .execute()
        )
        return {"ok": True, "mode": "updated", "item": (updated.data or [{}])[0]}

    payload = {
        "user_id": resolved_user_id,
        "week_start": resolved_week_start,
        "day_index": resolved_day_index,
        "breakfast": breakfast,
        "lunch": lunch,
        "dinner": dinner,
        "is_done": is_done,
    }
    inserted = _db().table(WEEK_MENU_TABLE).insert(payload).execute()
    return {"ok": True, "mode": "inserted", "item": (inserted.data or [{}])[0]}


@mcp.tool
def planner_weight_list(user_id: str | None = None) -> dict:
    resolved_user_id = _resolve_user_id(user_id)
    res = (
        _db()
        .table(WEIGHT_ENTRIES_TABLE)
        .select("id,user_id,date,weight_kg,notes,created_at,updated_at")
        .eq("user_id", resolved_user_id)
        .order("date", desc=False)
        .execute()
    )
    return {"ok": True, "user_id": resolved_user_id, "items": res.data or []}


@mcp.tool
def planner_weight_add(
    date: str,
    weight_kg: float,
    notes: str | None = None,
    user_id: str | None = None,
) -> dict:
    resolved_user_id = _resolve_user_id(user_id)
    resolved_date = _resolve_date(date)
    resolved_weight_kg = _resolve_weight_kg(weight_kg)
    payload = {
        "user_id": resolved_user_id,
        "date": resolved_date,
        "weight_kg": resolved_weight_kg,
        "notes": notes,
    }
    res = _db().table(WEIGHT_ENTRIES_TABLE).insert(payload).execute()
    return {"ok": True, "item": (res.data or [{}])[0]}


@mcp.tool
def planner_weight_update(
    item_id: str,
    date: str | None = None,
    weight_kg: float | None = None,
    notes: str | None = None,
    user_id: str | None = None,
) -> dict:
    changes: Dict[str, Any] = {}
    if date is not None:
        changes["date"] = _resolve_date(date)
    if weight_kg is not None:
        changes["weight_kg"] = _resolve_weight_kg(weight_kg)
    if notes is not None:
        changes["notes"] = notes
    if not changes:
        return {"ok": False, "error": "No fields to update"}

    query = _db().table(WEIGHT_ENTRIES_TABLE).update(changes).eq("id", item_id)
    if user_id:
        query = query.eq("user_id", user_id)
    res = query.execute()
    return {"ok": True, "updated": res.data or []}


@mcp.tool
def planner_weight_delete(item_id: str, user_id: str | None = None) -> dict:
    query = _db().table(WEIGHT_ENTRIES_TABLE).delete().eq("id", item_id)
    if user_id:
        query = query.eq("user_id", user_id)
    res = query.execute()
    return {"ok": True, "deleted": res.data or []}


@mcp.tool
def planner_weight_upsert_by_date(
    date: str,
    weight_kg: float,
    notes: str | None = None,
    user_id: str | None = None,
) -> dict:
    resolved_user_id = _resolve_user_id(user_id)
    resolved_date = _resolve_date(date)
    resolved_weight_kg = _resolve_weight_kg(weight_kg)

    existing = (
        _db()
        .table(WEIGHT_ENTRIES_TABLE)
        .select("id,user_id,date,weight_kg,notes,created_at,updated_at")
        .eq("user_id", resolved_user_id)
        .eq("date", resolved_date)
        .limit(1)
        .execute()
    )

    if existing.data:
        row_id = existing.data[0]["id"]
        changes = {"weight_kg": resolved_weight_kg, "notes": notes}
        updated = (
            _db()
            .table(WEIGHT_ENTRIES_TABLE)
            .update(changes)
            .eq("id", row_id)
            .eq("user_id", resolved_user_id)
            .execute()
        )
        return {"ok": True, "mode": "updated", "item": (updated.data or [{}])[0]}

    payload = {
        "user_id": resolved_user_id,
        "date": resolved_date,
        "weight_kg": resolved_weight_kg,
        "notes": notes,
    }
    inserted = _db().table(WEIGHT_ENTRIES_TABLE).insert(payload).execute()
    return {"ok": True, "mode": "inserted", "item": (inserted.data or [{}])[0]}


mcp_app = mcp.http_app(path="/")
app = FastAPI(lifespan=mcp_app.lifespan)


@app.get("/")
def root():
    return {"ok": True, "msg": "Cucki Planner MCP online"}


app.mount("/mcp", mcp_app)



