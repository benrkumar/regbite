import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "nutracomply"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


from app.database import Base  # noqa: E402
from app.models import (  # noqa: E402
    APIKey,
    Account,
    ActivityLog,
    ComplianceReport,
    LabelVersion,
    Notification,
    NotificationType,
    Product,
    TeamInvite,
    User,
    UserRole,
)
from app.services.activity_service import build_user_audit_snapshot, present_action, resource_link  # noqa: E402


class ActivityAuditTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_build_user_audit_snapshot_aggregates_user_footprint(self):
        db = self.Session()

        account = Account(name="Acme Workspace", owner_email="owner@example.com")
        db.add(account)
        db.commit()
        db.refresh(account)

        user = User(
            account_id=account.id,
            email="owner@example.com",
            name="Owner",
            hashed_password="x",
            role=UserRole.ACCOUNT_ADMIN,
            is_active=True,
        )
        teammate = User(
            account_id=account.id,
            email="editor@example.com",
            name="Editor",
            hashed_password="x",
            role=UserRole.EDITOR,
            is_active=True,
        )
        db.add_all([user, teammate])
        db.commit()
        db.refresh(user)

        product = Product(account_id=account.id, user_id=user.id, name="Omega Plus")
        db.add(product)
        db.commit()
        db.refresh(product)

        label = LabelVersion(
            product_id=product.id,
            file_path="uploads/demo.pdf",
            file_name="demo.pdf",
            file_type="pdf",
            processing_status="ready",
        )
        report = ComplianceReport(
            report_ref="RB-20260501-0001",
            account_id=account.id,
            user_id=user.id,
            product_id=product.id,
            score=93,
            verdict="COMPLIANT",
        )
        notification = Notification(
            user_id=user.id,
            title="Label analysis finished",
            ntype=NotificationType.INFO,
            is_read=False,
        )
        api_key = APIKey(
            account_id=account.id,
            user_id=user.id,
            name="Primary",
            key_prefix="rb_live_1",
            key_hash="hash",
            is_active=True,
        )
        invite = TeamInvite(
            account_id=account.id,
            email="viewer@example.com",
            role=UserRole.VIEWER,
            invited_by=user.id,
            token="invite-token",
            is_accepted=False,
            expires_at=datetime.utcnow() + timedelta(days=3),
        )
        logs = [
            ActivityLog(account_id=account.id, user_id=user.id, action="login", detail="Signed in"),
            ActivityLog(account_id=account.id, user_id=user.id, action="label_uploaded", resource_type="label", resource_id=1, detail="Queued label scan"),
            ActivityLog(account_id=account.id, user_id=user.id, action="password_changed", detail="Changed account password"),
        ]
        db.add_all([label, report, notification, api_key, invite, *logs])
        db.commit()

        snapshot = build_user_audit_snapshot(db, user, limit=10)

        self.assertEqual(snapshot["counts"]["products"], 1)
        self.assertEqual(snapshot["counts"]["labels"], 1)
        self.assertEqual(snapshot["counts"]["reports"], 1)
        self.assertEqual(snapshot["counts"]["notifications_unread"], 1)
        self.assertEqual(snapshot["counts"]["active_api_keys"], 1)
        self.assertEqual(snapshot["counts"]["team_members"], 2)
        self.assertEqual(snapshot["counts"]["pending_invites"], 1)
        self.assertEqual(snapshot["counts"]["notification_recipients"], 0)
        self.assertEqual(snapshot["counts"]["access_events_30d"], 1)
        self.assertEqual(snapshot["counts"]["scan_events_30d"], 1)
        self.assertEqual(snapshot["counts"]["security_events_30d"], 1)
        self.assertEqual(snapshot["counts"]["activity_total"], 3)
        self.assertEqual(snapshot["workspace"]["name"], "Acme Workspace")
        self.assertEqual(snapshot["last_login"].action, "login")
        self.assertEqual(snapshot["last_scan"].action, "label_uploaded")
        self.assertIsNotNone(snapshot["last_scan_at"])
        self.assertEqual(snapshot["last_report_at"], report.created_at)
        self.assertEqual(snapshot["last_security"].action, "password_changed")
        self.assertEqual(snapshot["recent_activity_display"][0]["group"], "Security")
        self.assertEqual(snapshot["access_activity"][0]["entry"].action, "password_changed")
        self.assertEqual(snapshot["scan_activity"][0]["entry"].action, "label_uploaded")
        self.assertEqual(snapshot["recent_api_keys"][0].name, "Primary")
        self.assertEqual(snapshot["recent_team_invites"][0].email, "viewer@example.com")
        self.assertEqual(snapshot["activity_mix"][0]["count"], 1)

        db.close()

    def test_action_presentation_and_links_are_stable(self):
        self.assertEqual(present_action("label_scan_failed")["tone"], "bad")
        self.assertEqual(present_action("label_scan_failed")["group"], "Scans")
        self.assertEqual(resource_link("report", 42), "/reports/42")
        self.assertEqual(resource_link("api_key", 99), "/settings/api-keys")


if __name__ == "__main__":
    unittest.main()
