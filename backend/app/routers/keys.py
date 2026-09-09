# -*- coding: utf-8 -*-
"""BYOK provider-key management. Keys are encrypted at rest; only a masked hint is
ever returned. The plaintext is decrypted in-memory only when a job needs it."""
from fastapi import APIRouter, Depends, HTTPException
from .. import db, security
from ..models import KeyCreate
from ..deps import current_user

router = APIRouter(prefix="/keys", tags=["byok"])


@router.post("")
def save_key(body: KeyCreate, user: str = Depends(current_user)):
    existing = db.fetchone("provider_keys", user_id=user, provider=body.provider)
    row = {
        "ciphertext": security.encrypt(body.api_key),
        "hint": security.hint(body.api_key),
        "created_at": db.now(),
    }
    if existing:
        db.update("provider_keys", existing["id"], row)
    else:
        row.update(id=db.new_id("key"), user_id=user, provider=body.provider)
        db.insert("provider_keys", row)
    return {"provider": body.provider, "hint": row["hint"], "saved": True}


@router.get("")
def list_keys(user: str = Depends(current_user)):
    return [{"provider": k["provider"], "hint": k["hint"]}
            for k in db.fetchall("provider_keys", user_id=user)]


@router.delete("/{provider}")
def delete_key(provider: str, user: str = Depends(current_user)):
    k = db.fetchone("provider_keys", user_id=user, provider=provider)
    if not k:
        raise HTTPException(404, "no key for that provider")
    import sqlite3
    from ..config import settings
    with sqlite3.connect(settings.DB_PATH) as c:
        c.execute("DELETE FROM provider_keys WHERE id=?", [k["id"]])
    return {"deleted": provider}
