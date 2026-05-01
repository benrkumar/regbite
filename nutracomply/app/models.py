from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    Float, ForeignKey, JSON, Enum as _SAEnumType, Index, LargeBinary
)
from sqlalchemy.orm import relationship
import enum

from app.database import Base


# SQLite-compatible SAEnum: stores values as VARCHAR, not DB-native enum.
# Explicitly sets values_callable so SQLAlchemy always uses enum.value (lowercase)
# for storage — Python 3.11+ changed str(StrEnum.MEMBER) to return the NAME,
# which caused SQLAlchemy to build its lookup from names (uppercase) instead.
def SAEnum(*args, **kwargs):
    kwargs.setdefault("native_enum", False)
    # Force value-based storage so lookup keys match the lowercase values in the DB
    if args and isinstance(args[0], type) and issubclass(args[0], enum.Enum):
        kwargs.setdefault("values_callable", lambda x: [e.value for e in x])
    return _SAEnumType(*args, **kwargs)


# ─── Enums ───────────────────────────────────────────────────────────────────

class RuleCategory(str, enum.Enum):
    MANDATORY_FIELD = "MANDATORY_FIELD"
    PROHIBITED_CLAIM = "PROHIBITED_CLAIM"
    INGREDIENT_RESTRICTION = "INGREDIENT_RESTRICTION"
    FORMAT_REQUIREMENT = "FORMAT_REQUIREMENT"
    QUANTITY_REQUIREMENT = "QUANTITY_REQUIREMENT"
    ALLERGEN_REQUIREMENT = "ALLERGEN_REQUIREMENT"
    CLAIM_SUBSTANTIATION = "CLAIM_SUBSTANTIATION"
    WARNING = "WARNING"
    ADDITIVE_LIMIT = "ADDITIVE_LIMIT"
    LICENSING = "LICENSING"


class RuleFramework(str, enum.Enum):
    FSSAI = "FSSAI"
    LEGAL_METROLOGY = "LEGAL_METROLOGY"
    AYUSH = "AYUSH"
    BIS = "BIS"
    DGFT = "DGFT"


class RegulationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"
    EFFECTIVE = "EFFECTIVE"
    SUPERSEDED = "SUPERSEDED"


class CheckType(str, enum.Enum):
    PRESENCE = "PRESENCE"
    ABSENCE = "ABSENCE"
    PATTERN_MATCH = "PATTERN_MATCH"
    VALUE_IN_LIST = "VALUE_IN_LIST"
    NOT_IN_LIST = "NOT_IN_LIST"
    FORMAT = "FORMAT"
    # Backwards-compatibility for older seeded / production rows.
    FORMAT_LLM = "FORMAT_LLM"


class Severity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class CheckResult(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    SKIPPED = "SKIPPED"


class AlertType(str, enum.Enum):
    REGULATION_CHANGE = "REGULATION_CHANGE"
    LABEL_VIOLATION = "LABEL_VIOLATION"
    INGREDIENT_BANNED = "INGREDIENT_BANNED"
    CLAIM_PROHIBITED = "CLAIM_PROHIBITED"


class AlertStatus(str, enum.Enum):
    UNREAD = "UNREAD"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class ChangeType(str, enum.Enum):
    INGREDIENT_BAN = "INGREDIENT_BAN"
    INGREDIENT_RESTRICTION = "INGREDIENT_RESTRICTION"
    LABEL_REQUIREMENT = "LABEL_REQUIREMENT"
    HEALTH_CLAIM = "HEALTH_CLAIM"
    FORMAT_CHANGE = "FORMAT_CHANGE"
    NEW_REGULATION = "NEW_REGULATION"
    AMENDMENT = "AMENDMENT"
    UNKNOWN = "UNKNOWN"


class IngredientStatus(str, enum.Enum):
    APPROVED = "APPROVED"
    BANNED = "BANNED"
    RESTRICTED = "RESTRICTED"
    REQUIRES_SUBSTANTIATION = "REQUIRES_SUBSTANTIATION"


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ACCOUNT_ADMIN = "account_admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    CONSULTANT = "consultant"


class PlanType(str, enum.Enum):
    FREE       = "free"
    GROWTH     = "growth"
    ENTERPRISE = "enterprise"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE    = "active"
    CANCELLED = "cancelled"
    PAST_DUE  = "past_due"
    TRIALING  = "trialing"


# ─── Models ──────────────────────────────────────────────────────────────────

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    owner_email = Column(String(255), nullable=True)
    company_name = Column(String(255), nullable=True)
    company_gstin = Column(String(20), nullable=True)
    report_brand_name = Column(String(255), nullable=True)
    report_brand_color = Column(String(10), nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    onboarding_complete = Column(Boolean, nullable=True)
    company_name = Column(String(255), nullable=True)
    company_gstin = Column(String(20), nullable=True)
    report_brand_name = Column(String(255), nullable=True)   # overrides "RegBite" in reports
    report_brand_color = Column(String(10), nullable=True)   # hex color e.g. "#6366f1"
    is_admin = Column(Boolean, default=False)
    role = Column(SAEnum(UserRole), default=UserRole.ACCOUNT_ADMIN)
    plan = Column(SAEnum(PlanType), nullable=True)   # denormalized for fast checks
    notification_emails = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    team_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # who invited/owns this sub-user

    account = relationship("Account", foreign_keys=[account_id])
    products = relationship("Product", back_populates="owner")
    licenses = relationship("LicenseRenewal", back_populates="owner")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    sku = Column(String(100), index=True)
    brand = Column(String(255), nullable=True)
    category = Column(String(100))
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    is_temporary = Column(Boolean, default=False)
    is_sample = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_products_user_active", "user_id", "is_active"),
        Index("ix_products_account_active", "account_id", "is_active"),
    )

    account = relationship("Account", foreign_keys=[account_id])
    owner = relationship("User", back_populates="products")
    label_versions = relationship(
        "LabelVersion", back_populates="product",
        order_by="LabelVersion.uploaded_at.desc()"
    )
    reports = relationship(
        "ComplianceReport", back_populates="product",
        foreign_keys="ComplianceReport.product_id"
    )

    @property
    def latest_label(self):
        return self.label_versions[0] if self.label_versions else None

    @property
    def compliance_score(self):
        return self.compliance_summary["score"]

    @property
    def compliance_summary(self):
        latest = self.latest_label
        if not latest or not latest.checks:
            return {
                "score": None,
                "critical_failures": 0,
                "verdict": None,
                "tone": "none",
                "label": "No label",
                "passed_count": 0,
                "failed_count": 0,
                "warning_count": 0,
                "total_checks": 0,
            }
        from app.services.verdict_service import summarize_checks
        return summarize_checks(latest.checks)

    @property
    def compliance_verdict(self):
        return self.compliance_summary["verdict"]

    @property
    def critical_failures(self):
        return self.compliance_summary["critical_failures"]


class LabelVersion(Base):
    __tablename__ = "label_versions"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255))
    file_type = Column(String(50))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    ocr_raw_text = Column(Text)
    extraction_json = Column(JSON)
    extraction_confidence = Column(Float)
    extraction_source = Column(String(20), nullable=True)   # "claude", "gemma", "gemini", "local", "fallback"
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    processing_status = Column(String(20), nullable=True)
    processing_step = Column(String(50), nullable=True)
    processing_error = Column(Text, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_finished_at = Column(DateTime, nullable=True)
    needs_review = Column(Boolean, default=False)
    is_current = Column(Boolean, default=True)
    file_data = Column(LargeBinary, nullable=True)

    __table_args__ = (
        Index("ix_labels_product_current", "product_id", "is_current"),
    )

    product = relationship("Product", back_populates="label_versions")
    checks = relationship(
        "ComplianceCheck", back_populates="label_version",
        cascade="all, delete-orphan"
    )
    alerts = relationship("Alert", back_populates="label_version")

    @property
    def scan_ready(self):
        return self.processing_status == "ready"

    @property
    def scan_failed(self):
        return self.processing_status == "failed"


class ComplianceRule(Base):
    __tablename__ = "compliance_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_code = Column(String(50), unique=True, index=True, nullable=False)
    category = Column(SAEnum(RuleCategory), nullable=False)
    regulation_source = Column(String(500))
    description = Column(Text, nullable=False)
    check_type = Column(SAEnum(CheckType), nullable=False)
    check_config = Column(JSON, nullable=False)
    severity = Column(SAEnum(Severity), nullable=False)
    remediation_template = Column(Text)
    effective_from = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)
    # Rule versioning (Item 5) — tracks which version of the regulation this rule reflects
    version = Column(String(50), nullable=True)          # e.g. "VIII", "2022-v2", "2025-Amendment-1"
    framework = Column(SAEnum(RuleFramework), nullable=True)  # FSSAI, LEGAL_METROLOGY, AYUSH, BIS, DGFT
    regulation_status = Column(SAEnum(RegulationStatus), default=RegulationStatus.EFFECTIVE)
    applicable_product_classes = Column(JSON, default=list)
    applicable_claim_classes = Column(JSON, default=list)
    applicable_import_scope = Column(String(30), nullable=True)
    applicable_dosage_forms = Column(JSON, default=list)
    applicable_target_groups = Column(JSON, default=list)
    exception_flags = Column(JSON, default=list)

    checks = relationship("ComplianceCheck", back_populates="rule")


class ComplianceCheck(Base):
    __tablename__ = "compliance_checks"

    id = Column(Integer, primary_key=True, index=True)
    label_version_id = Column(Integer, ForeignKey("label_versions.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("compliance_rules.id"), nullable=False)
    result = Column(SAEnum(CheckResult), nullable=False)
    actual_value = Column(Text)
    message = Column(Text)
    remediation = Column(Text)
    checked_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_checks_label_version", "label_version_id"),
    )

    label_version = relationship("LabelVersion", back_populates="checks")
    rule = relationship("ComplianceRule", back_populates="checks")


class RegulationChange(Base):
    __tablename__ = "regulation_changes"
    __table_args__ = (
        Index("ix_regulation_changes_source_document", "source_id", "source_document_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("regulation_sources.id"), nullable=True)
    source_url = Column(String(1000))
    source_document_key = Column(String(255), nullable=True)
    document_name = Column(String(500))
    detected_at = Column(DateTime, default=datetime.utcnow)
    change_type = Column(SAEnum(ChangeType), default=ChangeType.UNKNOWN)
    affected_rule_codes = Column(JSON, default=list)
    summary_text = Column(Text)
    diff_text = Column(Text)
    effective_date = Column(DateTime, nullable=True)
    severity = Column(SAEnum(Severity), default=Severity.MEDIUM)
    status = Column(String(20), default="NEW")
    regulation_status = Column(SAEnum(RegulationStatus), default=RegulationStatus.EFFECTIVE)
    document_hash = Column(String(64))
    document_type = Column(String(100), nullable=True)
    crawl_status = Column(String(50), nullable=True)
    reject_reason = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    review_state = Column(String(50), nullable=True)
    extracted_page_count = Column(Integer, nullable=True)
    total_page_count = Column(Integer, nullable=True)
    supersedes_change_id = Column(Integer, ForeignKey("regulation_changes.id"), nullable=True)
    superseded_by_change_id = Column(Integer, ForeignKey("regulation_changes.id"), nullable=True)

    alerts = relationship("Alert", back_populates="regulation_change")
    source = relationship("RegulationSource", foreign_keys=[source_id], back_populates="changes")


class RegulationSource(Base):
    __tablename__ = "regulation_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(120), nullable=False, unique=True, index=True)
    base_url = Column(String(1000), nullable=False)
    doc_type = Column(String(100), nullable=True)
    parser_kind = Column(String(100), nullable=True)
    cadence = Column(String(30), nullable=True)
    is_active = Column(Boolean, default=True)
    freshness_state = Column(String(30), nullable=True)
    discovery_config = Column(JSON, default=dict)
    last_checked_at = Column(DateTime, nullable=True)
    last_success_at = Column(DateTime, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    last_error_message = Column(Text, nullable=True)
    last_crawled_at = Column(DateTime, nullable=True)
    last_status = Column(String(50), nullable=True)
    last_discovery_count = Column(Integer, nullable=True)
    last_reject_count = Column(Integer, nullable=True)
    last_reject_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    changes = relationship("RegulationChange", back_populates="source")
    crawl_runs = relationship(
        "RegulationCrawlRun",
        back_populates="source",
        order_by="RegulationCrawlRun.started_at.desc()",
    )


class RegulationCrawlRun(Base):
    __tablename__ = "regulation_crawl_runs"
    __table_args__ = (
        Index("ix_regulation_crawl_runs_source_started", "source_id", "started_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("regulation_sources.id"), nullable=False, index=True)
    initiated_by = Column(String(30), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(30), nullable=False, default="running")
    discovery_count = Column(Integer, default=0)
    accepted_count = Column(Integer, default=0)
    reject_count = Column(Integer, default=0)
    unchanged_count = Column(Integer, default=0)
    error_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("RegulationSource", back_populates="crawl_runs")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    label_version_id = Column(Integer, ForeignKey("label_versions.id"), nullable=True)
    regulation_change_id = Column(Integer, ForeignKey("regulation_changes.id"), nullable=True)
    alert_type = Column(SAEnum(AlertType), nullable=False)
    severity = Column(SAEnum(Severity), nullable=False)
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    rule_violations = Column(JSON, default=list)
    status = Column(SAEnum(AlertStatus), default=AlertStatus.UNREAD)
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    account = relationship("Account", foreign_keys=[account_id])
    product = relationship("Product")
    label_version = relationship("LabelVersion", back_populates="alerts")
    regulation_change = relationship("RegulationChange", back_populates="alerts")


class AlertReadState(Base):
    __tablename__ = "alert_read_states"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_alert_read_states_alert_user", "alert_id", "user_id", unique=True),
    )

    alert = relationship("Alert", foreign_keys=[alert_id])
    user = relationship("User", foreign_keys=[user_id])


class Ingredient(Base):
    __tablename__ = "ingredients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    aliases = Column(JSON, default=list)
    status = Column(SAEnum(IngredientStatus), nullable=False)
    max_daily_dose = Column(String(100))
    source_restriction = Column(Text)
    ban_reason = Column(Text)
    regulation_reference = Column(String(500))
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── LLM Studio ──────────────────────────────────────────────────────────────

class KBType(str, enum.Enum):
    REGULATIONS = "regulations"
    PRODUCTS    = "products"


class KBDocument(Base):
    """A source document ingested into a knowledge base."""
    __tablename__ = "kb_documents"

    id           = Column(Integer, primary_key=True, index=True)
    kb_type      = Column(SAEnum(KBType), nullable=False, index=True)
    account_id   = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    title        = Column(String(500), nullable=False)
    source       = Column(String(500))           # e.g. "db:rule:42", "upload:file.pdf"
    content      = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=True, index=True)  # SHA-256 of raw bytes — dedup
    chunk_count  = Column(Integer, default=0)
    uploaded_by  = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at  = Column(DateTime, default=datetime.utcnow)
    is_active    = Column(Boolean, default=True)

    chunks = relationship("KBChunk", back_populates="document",
                          cascade="all, delete-orphan")


class KBChunk(Base):
    """A text chunk from a KBDocument used for retrieval."""
    __tablename__ = "kb_chunks"

    id          = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=False)
    kb_type     = Column(SAEnum(KBType), nullable=False, index=True)  # denormalized — avoids JOIN in retrieval
    chunk_index = Column(Integer, nullable=False)
    content     = Column(Text, nullable=False)

    document = relationship("KBDocument", back_populates="chunks")


class LLMConversation(Base):
    """Stores admin chat history per KB type (persisted across browser sessions)."""
    __tablename__ = "llm_conversations"

    id         = Column(Integer, primary_key=True, index=True)
    kb_type    = Column(SAEnum(KBType), nullable=False)
    admin_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    messages   = Column(JSON, default=list)     # [{"role":"user"|"model","content":"..."}]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── License Renewal Tracker ─────────────────────────────────────────────────

class LicenseType(str, enum.Enum):
    FSSAI_REGISTRATION = "FSSAI Registration"    # up to ₹1.5 Cr turnover
    FSSAI_STATE = "FSSAI State License"           # up to ₹50 Cr turnover
    FSSAI_CENTRAL = "FSSAI Central License"       # above ₹50 Cr turnover
    FSSAI = "FSSAI"                                # legacy — existing rows
    AYUSH = "AYUSH"
    IEC = "IEC"
    BIS = "BIS"
    STATE = "State License"
    OTHER = "Other"


class LicenseStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"
    RENEWED = "RENEWED"


class LicenseRenewal(Base):
    __tablename__ = "license_renewals"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    license_name = Column(String(255), nullable=False)
    license_type = Column(SAEnum(LicenseType), nullable=False)
    license_number = Column(String(100))
    expiry_date = Column(DateTime, nullable=False)
    issued_date = Column(DateTime, nullable=True)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    is_perpetual = Column(Boolean, default=False)  # March 2026 FSSAI amendment: perpetual license validity
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="licenses")

    @property
    def days_until_expiry(self):
        if self.is_perpetual:
            return 9999  # perpetual licenses never expire
        delta = self.expiry_date - datetime.utcnow()
        return delta.days

    @property
    def status(self):
        if self.is_perpetual:
            return LicenseStatus.ACTIVE
        days = self.days_until_expiry
        if days < 0:
            return LicenseStatus.EXPIRED
        elif days <= 30:
            return LicenseStatus.EXPIRING_SOON
        else:
            return LicenseStatus.ACTIVE

    @property
    def status_color(self):
        days = self.days_until_expiry
        if days < 0:
            return "danger"
        elif days <= 30:
            return "danger"
        elif days <= 60:
            return "warning"
        else:
            return "success"


# ─── Published Alerts (Admin-composed regulation alerts) ──────────────────────

class PublishedAlertSeverity(str, enum.Enum):
    INFORMATIONAL = "Informational"
    IMPORTANT = "Important"
    URGENT = "Urgent"


class PublishedAlertStatus(str, enum.Enum):
    DRAFT = "Draft"
    PUBLISHED = "Published"
    ARCHIVED = "Archived"


class PublishedAlert(Base):
    __tablename__ = "published_alerts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    summary = Column(Text, nullable=False)
    source_url = Column(String(1000))
    source_title = Column(String(500))
    affected_categories = Column(JSON, default=list)
    severity = Column(SAEnum(PublishedAlertSeverity), nullable=False, default=PublishedAlertSeverity.INFORMATIONAL)
    status = Column(SAEnum(PublishedAlertStatus), default=PublishedAlertStatus.DRAFT)
    published_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ─── Compliance Reports ───────────────────────────────────────────────────────

class ComplianceReport(Base):
    __tablename__ = "compliance_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_ref = Column(String(30), unique=True, index=True, nullable=False)  # RB-YYYYMMDD-NNNN
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    label_version_id = Column(Integer, ForeignKey("label_versions.id"), nullable=True)
    checker_session_id = Column(Integer, ForeignKey("checker_sessions.id"), nullable=True)
    score = Column(Integer, nullable=True)  # 0-100
    verdict = Column(String(30), nullable=True)  # COMPLIANT / PARTIAL / NON_COMPLIANT
    check_results = Column(JSON, default=list)  # full per-rule results
    pdf_path = Column(String(500), nullable=True)
    share_token = Column(String(64), unique=True, nullable=True, index=True)
    share_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    product = relationship("Product", back_populates="reports", foreign_keys=[product_id])
    label_version = relationship("LabelVersion")
    checker_session = relationship("CheckerSession", foreign_keys=[checker_session_id])


class CheckerSession(Base):
    __tablename__ = "checker_sessions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    label_version_id = Column(Integer, ForeignKey("label_versions.id"), nullable=True)
    source_type = Column(String(20), nullable=False, default="manual")
    input_payload = Column(JSON, default=dict)
    promoted_product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    promoted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", foreign_keys=[account_id])
    user = relationship("User", foreign_keys=[user_id])
    product = relationship("Product", foreign_keys=[product_id])
    label_version = relationship("LabelVersion", foreign_keys=[label_version_id])
    promoted_product = relationship("Product", foreign_keys=[promoted_product_id])


# ─── Team Invites ─────────────────────────────────────────────────────────────

class TeamInvite(Base):
    __tablename__ = "team_invites"

    id          = Column(Integer, primary_key=True, index=True)
    account_id  = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    email       = Column(String(255), nullable=False, index=True)
    role        = Column(SAEnum(UserRole), nullable=False, default=UserRole.VIEWER)
    invited_by  = Column(Integer, ForeignKey("users.id"), nullable=False)
    token       = Column(String(100), unique=True, nullable=False)
    is_accepted = Column(Boolean, default=False)
    created_at  = Column(DateTime, default=datetime.utcnow)
    expires_at  = Column(DateTime, nullable=False)

    inviter = relationship("User", foreign_keys=[invited_by])


# ─── Activity Log ─────────────────────────────────────────────────────────────

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id            = Column(Integer, primary_key=True, index=True)
    account_id    = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable for system events
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    action        = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True)   # "product", "label", "report", "rule", etc.
    resource_id   = Column(Integer, nullable=True)
    detail        = Column(String(500), nullable=True)  # human-readable description
    status        = Column(String(20), nullable=True, default="success")
    ip_address    = Column(String(45), nullable=True)
    user_agent    = Column(String(300), nullable=True)
    context_json  = Column(JSON, default=dict)
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)
    account       = relationship("Account", foreign_keys=[account_id])
    user          = relationship("User", foreign_keys=[user_id])
    target_user   = relationship("User", foreign_keys=[target_user_id])


# ─── API Keys ─────────────────────────────────────────────────────────────────

class APIKey(Base):
    __tablename__ = "api_keys"
    id           = Column(Integer, primary_key=True, index=True)
    account_id   = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    name         = Column(String(100), nullable=False)          # e.g. "Production", "Dev laptop"
    key_prefix   = Column(String(10), nullable=False)           # first 8 chars, shown in UI
    key_hash     = Column(String(200), nullable=False)          # bcrypt hash of full key
    last_used_at = Column(DateTime, nullable=True)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    user         = relationship("User", foreign_keys=[user_id])


# ─── Billing / Subscriptions ──────────────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"
    id                   = Column(Integer, primary_key=True, index=True)
    account_id           = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id              = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    plan                 = Column(SAEnum(PlanType), nullable=False, default=PlanType.FREE)
    status               = Column(SAEnum(SubscriptionStatus), nullable=False, default=SubscriptionStatus.ACTIVE)
    razorpay_order_id    = Column(String(100), nullable=True)
    razorpay_payment_id  = Column(String(100), nullable=True)
    razorpay_sub_id      = Column(String(100), nullable=True)
    current_period_start = Column(DateTime, nullable=True)
    current_period_end   = Column(DateTime, nullable=True)
    trial_ends_at        = Column(DateTime, nullable=True)
    cancelled_at         = Column(DateTime, nullable=True)
    created_at           = Column(DateTime, default=datetime.utcnow)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user                 = relationship("User", foreign_keys=[user_id])


class PaymentRecord(Base):
    __tablename__ = "payment_records"
    id                  = Column(Integer, primary_key=True, index=True)
    account_id          = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    user_id             = Column(Integer, ForeignKey("users.id"), nullable=False)
    razorpay_payment_id = Column(String(100), nullable=True)
    razorpay_order_id   = Column(String(100), nullable=True)
    amount_paise        = Column(Integer, nullable=False)   # amount in paise (₹1 = 100 paise)
    currency            = Column(String(5), default="INR")
    plan                = Column(SAEnum(PlanType), nullable=False)
    status              = Column(String(50), nullable=False, default="created")  # created/paid/failed
    created_at          = Column(DateTime, default=datetime.utcnow)
    user                = relationship("User", foreign_keys=[user_id])


# ─── In-App Notifications ─────────────────────────────────────────────────────

# ─── Blog ────────────────────────────────────────────────────────────────────

class BlogPostStatus(str, enum.Enum):
    DRAFT     = "draft"
    PUBLISHED = "published"
    ARCHIVED  = "archived"


class NotificationType(str, enum.Enum):
    INFO    = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ALERT   = "alert"


class Notification(Base):
    __tablename__ = "notifications"
    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title      = Column(String(200), nullable=False)
    message    = Column(String(500), nullable=True)
    ntype      = Column(SAEnum(NotificationType), default=NotificationType.INFO)
    is_read    = Column(Boolean, default=False, index=True)
    link       = Column(String(300), nullable=True)   # optional deep link
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    user       = relationship("User", foreign_keys=[user_id])


# ─── Blog ────────────────────────────────────────────────────────────────────

class BlogCategory(Base):
    __tablename__ = "blog_categories"
    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False, unique=True)
    slug       = Column(String(120), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    posts      = relationship("BlogPost", back_populates="category")


class BlogPost(Base):
    __tablename__ = "blog_posts"
    id               = Column(Integer, primary_key=True, index=True)
    title            = Column(String(300), nullable=False)
    slug             = Column(String(350), nullable=False, unique=True, index=True)
    excerpt          = Column(Text, nullable=True)
    content          = Column(Text, nullable=False)
    featured_image   = Column(String(500), nullable=True)
    status           = Column(SAEnum(BlogPostStatus), default=BlogPostStatus.DRAFT)
    is_featured      = Column(Boolean, default=False)
    category_id      = Column(Integer, ForeignKey("blog_categories.id"), nullable=True)
    author_id        = Column(Integer, ForeignKey("users.id"), nullable=False)
    tags             = Column(String(500), nullable=True)  # comma-separated
    meta_title       = Column(String(300), nullable=True)
    meta_description = Column(String(500), nullable=True)
    views            = Column(Integer, default=0)
    published_at     = Column(DateTime, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("BlogCategory", back_populates="posts")
    author   = relationship("User", foreign_keys=[author_id])


# ─── Local Extraction Pattern Library ────────────────────────────────────────

class ExtractionPattern(Base):
    """Stores field-level extraction patterns learned from successful Claude extractions."""
    __tablename__ = "extraction_patterns"

    id              = Column(Integer, primary_key=True, index=True)
    field_name      = Column(String(64), nullable=False, index=True)
    field_value     = Column(Text, nullable=False)
    ocr_context     = Column(Text, nullable=False)   # surrounding OCR text for TF-IDF matching
    source_label_id = Column(Integer, ForeignKey("label_versions.id"), nullable=True)
    confidence      = Column(Float, default=0.0)
    created_at      = Column(DateTime, default=datetime.utcnow)


# ─── API Call Log ─────────────────────────────────────────────────────────────

class APICallLog(Base):
    """Tracks every LLM API call beyond label extraction (kb_chat, compliance_format, etc.)"""
    __tablename__ = "api_call_logs"

    id            = Column(Integer, primary_key=True, index=True)
    call_type     = Column(String(30), nullable=False, index=True)  # "kb_chat","compliance_format","query_expansion"
    provider      = Column(String(20), nullable=False)               # "gemma","gemini","claude"
    model         = Column(String(100), nullable=True)
    tokens_input  = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    cost_usd      = Column(Float, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)
