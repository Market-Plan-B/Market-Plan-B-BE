from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.db_setting import Notification, Content, User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/")
def get_notifications(user_id: int, db: Session = Depends(get_db)):
    # 유저 확인
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Notification + Contents join
    notifs = (
        db.query(Notification, Content)
        .join(Content, Content.id == Notification.content_id)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc())
        .all()
    )

    result = []
    for notif, content in notifs:
        result.append({
            "notification_id": notif.id,
            "content_id": content.id,
            "title": content.title,
            "url": content.url,
            "score": float(content.source_score) if content.source_score else None,
            "is_read": notif.is_read,
            "created_at": notif.created_at,
            "read_at": notif.read_at
        })

    return result


@router.patch("/{notification_id}/read")
def mark_as_read(notification_id: int, db: Session = Depends(get_db)):
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    notif.is_read = True
    notif.read_at = datetime.utcnow()
    db.commit()

    return {"success": True}


@router.patch("/read-all")
def mark_all_as_read(user_id: int, db: Session = Depends(get_db)):
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == False)
        .update({
            Notification.is_read: True,
            Notification.read_at: datetime.utcnow()
        })
    )

    db.commit()
    return {"success": True, "count": updated}