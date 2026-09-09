# -*- coding: utf-8 -*-
"""Customer feedback & feature requests. v1 = capture to the admin inbox; a public
upvote board / roadmap builds on this same table later."""
from fastapi import APIRouter, Depends
from .. import db
from ..models import FeedbackCreate
from ..deps import current_user

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("")
def submit(body: FeedbackCreate, user: str = Depends(current_user)):
    fid = db.new_id("fb")
    db.insert("feedback", {
        "id": fid, "user_id": user, "kind": body.kind,
        "message": body.message, "email": body.email, "page": body.page,
        "created_at": db.now(),
    })
    return {"id": fid, "thanks": "Got it — thank you. We read every request."}


@router.get("")
def list_feedback(user: str = Depends(current_user)):
    """Admin inbox (scaffold: returns all). Later: gate to admins + add upvotes/status."""
    return db.fetchall("feedback")
