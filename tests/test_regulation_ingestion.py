import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = PROJECT_ROOT / "nutracomply"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


from app.database import Base  # noqa: E402
from app.models import ChangeType, KBDocument, KBType, RegulationChange, RegulationSource, Severity  # noqa: E402
from app.services.bootstrap_service import seed_regulation_sources  # noqa: E402
from app.services.llm_service import seed_regulations_kb  # noqa: E402
from app.services.regulation_ingestion import derive_source_freshness, process_source_discovery  # noqa: E402
from app.services.scraper import DownloadedDocument, SourceDiscovery  # noqa: E402


def make_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


class RegulationIngestionTests(unittest.TestCase):
    def test_seed_regulation_sources_backfills_legacy_change_defaults(self):
        db = make_session()
        self.addCleanup(db.close)
        legacy_change = RegulationChange(
            source_url="https://fssai.gov.in/notifications/gazette-notification-update.pdf",
            document_name="Gazette Notification Update",
            detected_at=datetime(2026, 4, 1, 8, 30),
            change_type=ChangeType.NEW_REGULATION,
            severity=Severity.HIGH,
            status="NEW",
        )
        db.add(legacy_change)
        db.commit()

        seed_regulation_sources(db)
        db.commit()
        db.refresh(legacy_change)

        self.assertIsNotNone(legacy_change.source_id)
        self.assertEqual(legacy_change.crawl_status, "accepted")
        self.assertEqual(legacy_change.review_state, "legacy")
        self.assertEqual(legacy_change.published_at, legacy_change.detected_at)
        self.assertTrue(legacy_change.source_document_key.startswith("fssai-"))

    def test_process_source_discovery_versions_changed_document_and_skips_same_hash(self):
        db = make_session()
        self.addCleanup(db.close)
        seed_regulation_sources(db)
        db.commit()

        source = db.query(RegulationSource).filter(RegulationSource.slug == "fssai-regulations").first()
        discovery = SourceDiscovery(
            source_url="https://fssai.gov.in/cms/2026-amendment.pdf",
            document_name="2026 Amendment",
            source_document_key="fssai-regulations:2026-amendment",
            document_type="regulation_page",
            section="regulations",
        )

        classification = {
            "change_type": "AMENDMENT",
            "severity": "HIGH",
            "summary_text": "Updated labelling requirement",
            "effective_date": "2026-05-01",
        }

        with patch("app.services.regulation_ingestion.download_document", return_value=DownloadedDocument(
            text="first version text",
            sha256="hash-a",
            total_pages=8,
            extracted_pages=8,
            content_type="application/pdf",
        )), patch("app.services.regulation_ingestion.classify_regulation_change", return_value=classification), patch(
            "app.services.regulation_ingestion._publish_regulation_change"
        ):
            first = process_source_discovery(db, source, discovery)

        self.assertEqual(first["action"], "accepted")
        first_change = first["change"]
        self.assertEqual(first_change.review_state, "auto_published")
        self.assertEqual(first_change.total_page_count, 8)

        with patch("app.services.regulation_ingestion.download_document", return_value=DownloadedDocument(
            text="same version text",
            sha256="hash-a",
            total_pages=8,
            extracted_pages=8,
            content_type="application/pdf",
        )), patch("app.services.regulation_ingestion.classify_regulation_change", return_value=classification), patch(
            "app.services.regulation_ingestion._publish_regulation_change"
        ):
            unchanged = process_source_discovery(db, source, discovery)

        self.assertEqual(unchanged["action"], "unchanged")

        with patch("app.services.regulation_ingestion.download_document", return_value=DownloadedDocument(
            text="second version text",
            sha256="hash-b",
            total_pages=9,
            extracted_pages=9,
            content_type="application/pdf",
        )), patch("app.services.regulation_ingestion.classify_regulation_change", return_value=classification), patch(
            "app.services.regulation_ingestion._publish_regulation_change"
        ):
            second = process_source_discovery(db, source, discovery)

        self.assertEqual(second["action"], "accepted")
        second_change = second["change"]
        db.refresh(first_change)
        db.refresh(second_change)
        self.assertEqual(second_change.supersedes_change_id, first_change.id)
        self.assertEqual(first_change.superseded_by_change_id, second_change.id)

    def test_derive_source_freshness_states(self):
        now = datetime.utcnow()
        fresh = RegulationSource(
            name="Fresh",
            slug="fresh-source",
            base_url="https://example.com/fresh",
            last_success_at=now - timedelta(hours=2),
        )
        stale = RegulationSource(
            name="Stale",
            slug="stale-source",
            base_url="https://example.com/stale",
            last_success_at=now - timedelta(hours=72),
        )
        degraded = RegulationSource(
            name="Degraded",
            slug="degraded-source",
            base_url="https://example.com/degraded",
            last_success_at=now - timedelta(hours=2),
            last_error_at=now - timedelta(hours=1),
        )
        never = RegulationSource(
            name="Never",
            slug="never-source",
            base_url="https://example.com/never",
        )

        self.assertEqual(derive_source_freshness(fresh, now), "fresh")
        self.assertEqual(derive_source_freshness(stale, now), "stale")
        self.assertEqual(derive_source_freshness(degraded, now), "degraded")
        self.assertEqual(derive_source_freshness(never, now), "never")

    def test_seed_regulations_kb_skips_rejected_regulation_changes(self):
        db = make_session()
        self.addCleanup(db.close)
        accepted_change = RegulationChange(
            source_url="https://fssai.gov.in/cms/accepted.pdf",
            document_name="Accepted Update",
            detected_at=datetime.utcnow(),
            change_type=ChangeType.AMENDMENT,
            severity=Severity.MEDIUM,
            crawl_status="accepted",
            review_state="auto_published",
        )
        rejected_change = RegulationChange(
            source_url="https://fssai.gov.in/cms/rejected.pdf",
            document_name="Rejected Update",
            detected_at=datetime.utcnow(),
            change_type=ChangeType.UNKNOWN,
            severity=Severity.LOW,
            crawl_status="rejected",
            review_state="rejected",
        )
        db.add_all([accepted_change, rejected_change])
        db.commit()

        seed_regulations_kb(db)

        kb_sources = [
            row.source
            for row in db.query(KBDocument)
            .filter(KBDocument.kb_type == KBType.REGULATIONS)
            .all()
        ]
        self.assertIn(f"db:regulation_change:{accepted_change.id}", kb_sources)
        self.assertNotIn(f"db:regulation_change:{rejected_change.id}", kb_sources)


if __name__ == "__main__":
    unittest.main()
