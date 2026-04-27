from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Alert, AlertReadState, AlertStatus
from app.services.access_control import get_account_id


def account_alert_query(db: Session, user):
    account_id = get_account_id(user)
    return db.query(Alert).filter(Alert.account_id == account_id)


def mark_alert_read(db: Session, user, alert: Alert) -> None:
    state = (
        db.query(AlertReadState)
        .filter(
            AlertReadState.alert_id == alert.id,
            AlertReadState.user_id == user.id,
        )
        .first()
    )
    if not state:
        state = AlertReadState(
            alert_id=alert.id,
            user_id=user.id,
            read_at=datetime.utcnow(),
        )
        db.add(state)
    else:
        state.read_at = datetime.utcnow()


def mark_all_alerts_read(db: Session, user) -> int:
    alerts = (
        account_alert_query(db, user)
        .filter(Alert.status != AlertStatus.RESOLVED)
        .all()
    )
    for alert in alerts:
        mark_alert_read(db, user, alert)
    return len(alerts)


def attach_read_state(db: Session, user, alerts: list[Alert]) -> list[Alert]:
    if not alerts:
        return alerts
    states = {
        state.alert_id
        for state in db.query(AlertReadState)
        .filter(
            AlertReadState.user_id == user.id,
            AlertReadState.alert_id.in_([a.id for a in alerts]),
            AlertReadState.read_at.isnot(None),
        )
        .all()
    }
    for alert in alerts:
        alert.is_unread = (
            alert.status != AlertStatus.RESOLVED and alert.id not in states
        )
    return alerts


def count_unread_alerts(db: Session, user) -> int:
    alerts = account_alert_query(db, user).filter(Alert.status != AlertStatus.RESOLVED).all()
    attach_read_state(db, user, alerts)
    return sum(1 for alert in alerts if getattr(alert, "is_unread", False))

