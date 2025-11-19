import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import LinkCreate

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Utilities
# -----------------------------
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

def serialize_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    # Convert datetime to isoformat if present
    for k in ["created_at", "updated_at"]:
        if k in doc and hasattr(doc[k], "isoformat"):
            doc[k] = doc[k].isoformat()
    return doc

# -----------------------------
# Health
# -----------------------------
@app.get("/")
def read_root():
    return {"message": "Links Dashboard API"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# -----------------------------
# Users API (simple accounts)
# -----------------------------
class UserIn(BaseModel):
    name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None

@app.post("/users")
def create_user(user: UserIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    data = user.model_dump()
    # Ensure unique by email if provided
    if data.get("email"):
        exists = db["user"].find_one({"email": data["email"]})
        if exists:
            return serialize_doc(exists)
    try:
        user_id = create_document("user", data)
        doc = db["user"].find_one({"_id": ObjectId(user_id)})
        return serialize_doc(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users")
def list_users(limit: int = Query(100, ge=1, le=500)):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    cursor = db["user"].find({}).sort([("created_at", -1)]).limit(limit)
    return [serialize_doc(d) for d in cursor]

# -----------------------------
# Links API
# -----------------------------
@app.post("/links")
def create_link(payload: LinkCreate):
    data = payload.model_dump()
    data["clicks"] = 0
    # Normalize labels: strip spaces
    labels = [l.strip() for l in (data.get("labels") or []) if l.strip()]
    data["labels"] = labels
    try:
        link_id = create_document("link", data)
        doc = db["link"].find_one({"_id": ObjectId(link_id)})
        return serialize_doc(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/links")
def list_links(
    label: Optional[str] = Query(None, description="Filter by label"),
    search: Optional[str] = Query(None, description="Search in title or description"),
    sort: str = Query("popular", pattern="^(popular|new)$", description="Sort order: popular or new"),
    limit: int = Query(100, ge=1, le=500)
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    filter_q: Dict[str, Any] = {}
    if label:
        filter_q["labels"] = {"$in": [label]}
    if search:
        filter_q["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
        ]
    sort_spec = [("clicks", -1)] if sort == "popular" else [("created_at", -1)]
    cursor = db["link"].find(filter_q).sort(sort_spec).limit(limit)
    return [serialize_doc(doc) for doc in cursor]

@app.post("/links/{link_id}/click")
def increment_click(link_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    if not ObjectId.is_valid(link_id):
        raise HTTPException(status_code=400, detail="Invalid link id")
    res = db["link"].find_one_and_update(
        {"_id": ObjectId(link_id)},
        {"$inc": {"clicks": 1}, "$set": {"updated_at": db.command("serverStatus")["localTime"]}},
        return_document=True
    )
    if not res:
        raise HTTPException(status_code=404, detail="Link not found")
    return serialize_doc(res)

class LinkUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    labels: Optional[List[str]] = None
    description: Optional[str] = None

@app.put("/links/{link_id}")
def update_link(link_id: str, payload: LinkUpdate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    if not ObjectId.is_valid(link_id):
        raise HTTPException(status_code=400, detail="Invalid link id")
    update_data = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if "labels" in update_data and update_data["labels"] is not None:
        update_data["labels"] = [l.strip() for l in update_data["labels"] if l and l.strip()]
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = db["link"].find_one_and_update(
        {"_id": ObjectId(link_id)},
        {"$set": {**update_data, "updated_at": db.command("serverStatus")["localTime"]}},
        return_document=True
    )
    if not res:
        raise HTTPException(status_code=404, detail="Link not found")
    return serialize_doc(res)

@app.delete("/links/{link_id}")
def delete_link(link_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    if not ObjectId.is_valid(link_id):
        raise HTTPException(status_code=400, detail="Invalid link id")
    res = db["link"].delete_one({"_id": ObjectId(link_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Link not found")
    return {"ok": True}

@app.get("/labels")
def list_labels():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    pipeline = [
        {"$unwind": "$labels"},
        {"$group": {"_id": "$labels", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": 1}}
    ]
    agg = db["link"].aggregate(pipeline)
    return [{"label": d["_id"], "count": d["count"]} for d in agg]

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
