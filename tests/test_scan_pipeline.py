import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "nutracomply"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


from app.models import LabelVersion  # noqa: E402
from app.routes.auth import _build_demo_label_artifacts  # noqa: E402
from app.routes.labels import _SCAN_JOBS, _local_fast_path_ok, _prime_label_processing, _scan_source_available  # noqa: E402
from app.services.dashboard_service import build_product_risk_matrix  # noqa: E402
from app.services.ocr_service import extract_text_from_file  # noqa: E402
from app.services.scan_eta_service import format_eta_window  # noqa: E402


class ScanPipelineTests(unittest.TestCase):
    def test_local_fast_path_requires_confidence_and_critical_fields(self):
        strong_extraction = {
            "product_name": "Omega Plus",
            "product_type_declaration": "HEALTH SUPPLEMENT",
            "fssai_license_number": "12345678901234",
            "net_quantity": "60 capsules",
            "expiry_date": "12/2027",
            "manufacturer_details": "Acme Wellness, India",
            "ingredient_list": ["Omega 3", "Vitamin E"],
            "warnings": ["Keep away from children"],
        }
        weak_extraction = {
            "product_name": "Omega Plus",
            "ingredient_list": ["Omega 3"],
        }

        self.assertTrue(_local_fast_path_ok(strong_extraction, 0.86))
        self.assertFalse(_local_fast_path_ok(strong_extraction, 0.40))
        self.assertFalse(_local_fast_path_ok(weak_extraction, 0.86))

    def test_prime_label_processing_clears_stale_scan_job(self):
        label = LabelVersion(id=42, processing_status="failed", processing_step="timeout", processing_error="old error")
        _SCAN_JOBS[42] = {"status": "failed", "error": "old error", "done": True}

        class DummySession:
            def commit(self):
                return None

        _prime_label_processing(label, DummySession())

        self.assertNotIn(42, _SCAN_JOBS)
        self.assertEqual(label.processing_status, "queued")
        self.assertEqual(label.processing_step, "queued")
        self.assertIsNone(label.processing_error)
        self.assertFalse(label.needs_review)

    def test_pdf_fast_path_skips_ocr_fallback_when_disabled(self):
        class FakePage:
            def extract_text(self):
                return ""

        class FakePdf:
            def __enter__(self):
                self.pages = [FakePage()]
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: FakePdf())

        class ExplodingFitz:
            def open(self, _path):
                raise AssertionError("OCR fallback should not run")

        with patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber, "fitz": ExplodingFitz()}):
            text, confidence = extract_text_from_file("label.pdf", allow_ocr_fallback=False)

        self.assertEqual(text, "")
        self.assertEqual(confidence, 0.0)

    def test_scan_source_available_for_stored_ocr_text(self):
        label = LabelVersion(file_path="missing/demo.jpg", file_data=None, ocr_raw_text="FSSAI Lic No: 12345678901234")
        self.assertTrue(_scan_source_available(label))

    def test_demo_label_artifacts_include_reusable_text(self):
        demo = {
            "name": "Omega-3 Fish Oil 1000mg",
            "category": "Health Supplement",
            "extraction": {
                "product_name": "Omega-3 Fish Oil 1000mg",
                "product_type_declaration": "HEALTH SUPPLEMENT",
                "fssai_license_number": "12345678901234",
                "net_quantity": "60 Softgel Capsules",
                "serving_size": "1 Softgel Capsule daily",
                "manufacturing_date": "01/2025",
                "expiry_date": "12/2027",
                "batch_number": "OFO-B250110",
                "manufacturer_details": "HealthFirst Labs Pvt. Ltd., Baddi, HP - 173205",
                "country_of_origin": "India",
                "ingredient_list": ["Fish Oil", "Gelatin"],
                "allergen_declarations": ["Contains: Fish"],
                "warnings": ["NOT FOR MEDICINAL USE", "Keep out of reach of children"],
            },
        }

        label_text, label_bytes = _build_demo_label_artifacts(demo)

        self.assertIn("FSSAI Lic No:", label_text)
        self.assertIn("NOT FOR MEDICINAL USE", label_text)
        self.assertTrue(label_bytes is None or label_bytes[:2] == b"\xff\xd8")

    def test_format_eta_window_reflects_file_mix(self):
        self.assertEqual(format_eta_window(["image"]), "about 2-3 min")
        self.assertEqual(format_eta_window(["image", "pdf"]), "about 4-6 min")

    def test_build_product_risk_matrix_prioritizes_critical_products(self):
        risky_product = types.SimpleNamespace(id=1, name="Omega Burn")
        risky_label = types.SimpleNamespace(id=11, extraction_confidence=0.95, file_name="omega-burn.png")
        missing_product = types.SimpleNamespace(id=2, name="Mystery Herbal")
        healthy_product = types.SimpleNamespace(id=3, name="Daily Fiber")
        healthy_label = types.SimpleNamespace(id=12, extraction_confidence=0.97, file_name="daily-fiber.pdf")

        cards = [
            {
                "product": risky_product,
                "label": risky_label,
                "label_state": "ready",
                "summary": {
                    "score": 63,
                    "critical_failures": 2,
                    "failed_count": 11,
                    "warning_count": 1,
                    "verdict": "NON_COMPLIANT",
                    "label": "Non-Compliant",
                },
                "needs_review": False,
                "tone": "bad",
            },
            {
                "product": missing_product,
                "label": None,
                "label_state": "missing",
                "summary": {
                    "score": None,
                    "critical_failures": 0,
                    "failed_count": 0,
                    "warning_count": 0,
                    "verdict": None,
                    "label": "No label",
                },
                "needs_review": False,
                "tone": "none",
            },
            {
                "product": healthy_product,
                "label": healthy_label,
                "label_state": "ready",
                "summary": {
                    "score": 96,
                    "critical_failures": 0,
                    "failed_count": 0,
                    "warning_count": 0,
                    "verdict": "COMPLIANT",
                    "label": "Compliant",
                },
                "needs_review": False,
                "tone": "good",
            },
        ]

        matrix = build_product_risk_matrix(cards)

        self.assertEqual(matrix["focus"]["product_name"], "Omega Burn")
        self.assertEqual(matrix["breakdown"]["critical"], 1)
        self.assertEqual(matrix["breakdown"]["blind_spots"], 1)
        self.assertEqual(matrix["breakdown"]["healthy"], 1)
        self.assertGreaterEqual(matrix["hotspot_count"], 1)
        self.assertEqual(matrix["items"][0]["detail_href"], "/labels/11")


if __name__ == "__main__":
    unittest.main()
