import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "nutracomply"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


from app.models import ComplianceRule, RuleFramework, User, UserRole  # noqa: E402
from app.services.access_control import sync_user_role_flags  # noqa: E402
from app.services.compliance_engine import _rule_applies  # noqa: E402
from app.services.onboarding_service import should_force_onboarding  # noqa: E402
from app.services.report_service import _build_verdict  # noqa: E402


class AuditRemediationTests(unittest.TestCase):
    def test_sync_user_role_flags_uses_role_as_source_of_truth(self):
        super_admin = User(
            name="Admin",
            email="admin@example.com",
            hashed_password="x",
            role=UserRole.SUPER_ADMIN,
            is_admin=False,
        )
        account_admin = User(
            name="Owner",
            email="owner@example.com",
            hashed_password="x",
            role=UserRole.ACCOUNT_ADMIN,
            is_admin=True,
        )

        sync_user_role_flags(super_admin)
        sync_user_role_flags(account_admin)

        self.assertTrue(super_admin.is_admin)
        self.assertFalse(account_admin.is_admin)

    def test_build_verdict_requires_zero_critical_failures(self):
        self.assertEqual(_build_verdict(95, 0), "COMPLIANT")
        self.assertEqual(_build_verdict(72, 0), "PARTIAL")
        self.assertEqual(_build_verdict(95, 1), "NON_COMPLIANT")
        self.assertEqual(_build_verdict(72, 2), "NON_COMPLIANT")

    def test_rule_applies_uses_structured_product_and_import_scope(self):
        rule = ComplianceRule(
            rule_code="FSSAI-001",
            description="Imported herbal products need importer details",
            framework=RuleFramework.FSSAI,
            applicable_product_classes=["herbal"],
            applicable_import_scope="imported",
        )

        imported_extraction = {
            "country_of_origin": "United States",
            "health_claims": ["supports wellness"],
        }
        domestic_extraction = {
            "country_of_origin": "India",
            "health_claims": ["supports wellness"],
        }

        self.assertTrue(_rule_applies(rule, imported_extraction, "Herbal/Ayurvedic"))
        self.assertFalse(_rule_applies(rule, domestic_extraction, "Herbal/Ayurvedic"))
        self.assertFalse(_rule_applies(rule, imported_extraction, "Sports Nutrition"))

    def test_should_force_onboarding_only_for_protected_app_routes(self):
        incomplete_user = User(
            name="Owner",
            email="owner@example.com",
            hashed_password="x",
            role=UserRole.ACCOUNT_ADMIN,
            onboarding_complete=False,
        )
        viewer_demo = User(
            name="Viewer",
            email="viewer@example.com",
            hashed_password="x",
            role=UserRole.VIEWER,
            onboarding_complete=False,
        )
        super_admin = User(
            name="Admin",
            email="admin@example.com",
            hashed_password="x",
            role=UserRole.SUPER_ADMIN,
            onboarding_complete=False,
        )

        self.assertTrue(should_force_onboarding(incomplete_user, "/products", False))
        self.assertTrue(should_force_onboarding(incomplete_user, "/checker/run", False))
        self.assertFalse(should_force_onboarding(incomplete_user, "/help", False))
        self.assertFalse(should_force_onboarding(viewer_demo, "/products", True))
        self.assertFalse(should_force_onboarding(super_admin, "/products", False))


if __name__ == "__main__":
    unittest.main()
