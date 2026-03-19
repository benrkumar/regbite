from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    Float, ForeignKey, JSON, Enum as _SAEnumType
)
from sqlalchemy.orm import relationship
import enum

from app.database import Base


# SQLite-compatible SAEnum: stores values as VARCHAR, not DB-native enum
def SAEnum(*args, **kwargs):
    kwargs.setdefault("native_enum", False)
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


class CheckType(str, enum.Enum):
    PRESENCE = "PRESENCE"
    ABSENCE = "ABSENCE"
    PATTERN_MATCH = "PATTERN_MATCH"
    VALUE_IN_LIST = "VALUE_IN_LIST"
    NOT_IN_LIST = "NOT_IN_LIST"
    FORMAT = "FORMAT"


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


# ─── Models ──────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    onboarding_complete = Column(Boolean, nullable=True)
    company_name = Column(String(255), nullable=True)
    company_gstin = Column(String(20), nullable=True)
    is_admin = Column(Boolean, default=False)
    role = Column(SAEnum(UserRole), default=UserRole.ACCOUNT_ADMIN)
    notification_emails = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    team_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # who invited/owns this sub-user

    products = relationship("Product", back_populates="owner")
    licenses = relationship("LicenseRenewal", back_populates="owner")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    sku = Column(String(100), index=True)
    brand = Column(String(255), nullable=True)
    category = Column(String(100))
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
        if not self.label_versions:
            return None
        latest = self.label_versions[0]
        if not latest.checks:
            return None
        total = len(latest.checks)
        passed = sum(1 for c in latest.checks if c.result == CheckResult.PASS)
        return round((passed / total) * 100) if total else 0


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
    is_current = Column(Boolean, default=True)

    product = relationship("Product", back_populates="label_versions")
    checks = relationship(
        "ComplianceCheck", back_populates="label_version",
        cascade="all, delete-orphan"
    )
    alerts = relationship("Alert", back_populates="label_version")


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

    label_version = relationship("LabelVersion", back_populates="checks")
    rule = relationship("ComplianceRule", back_populates="checks")


class RegulationChange(Base):
    __tablename__ = "regulation_changes"

    id = Column(Integer, primary_key=True, index=True)
    source_url = Column(String(1000))
    document_name = Column(String(500))
    detected_at = Column(DateTime, default=datetime.utcnow)
    change_type = Column(SAEnum(ChangeType), default=ChangeType.UNKNOWN)
    affected_rule_codes = Column(JSON, default=list)
    summary_text = Column(Text)
    diff_text = Column(Text)
    effective_date = Column(DateTime, nullable=True)
    severity = Column(SAEnum(Severity), default=Severity.MEDIUM)
    status = Column(String(20), default="NEW")
    document_hash = Column(String(64))

    alerts = relationship("Alert", back_populates="regulation_change")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
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

    product = relationship("Product")
    label_version = relationship("LabelVersion", back_populates="alerts")
    regulation_change = relationship("RegulationChange", back_populates="alerts")


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

    id          = Column(Integer, primary_key=True, index=True)
    kb_type     = Column(SAEnum(KBType), nullable=False, index=True)
    title       = Column(String(500), nullable=False)
    source      = Column(String(500))           # e.g. "db:rule:42", "upload:file.pdf"
    content     = Column(Text, nullable=False)
    chunk_count = Column(Integer, default=0)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    is_active   = Column(Boolean, default=True)

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
    FSSAI = "FSSAI"
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    license_name = Column(String(255), nullable=False)
    license_type = Column(SAEnum(LicenseType), nullable=False)
    license_number = Column(String(100))
    expiry_date = Column(DateTime, nullable=False)
    issued_date = Column(DateTime, nullable=True)
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="licenses")

    @property
    def days_until_expiry(self):
        delta = self.expiry_date - datetime.utcnow()
        return delta.days

    @property
    def status(self):
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
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    label_version_id = Column(Integer, ForeignKey("label_versions.id"), nullable=True)
    score = Column(Integer, nullable=True)  # 0-100
    verdict = Column(String(30), nullable=True)  # COMPLIANT / PARTIAL / NON_COMPLIANT
    check_results = Column(JSON, default=list)  # full per-rule results
    pdf_path = Column(String(500), nullable=True)
    share_token = Column(String(64), unique=True, nullable=True, index=True)
    share_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User")
    product = relationship("Product", back_populates="reports", foreign_keys=[product_id])
    label_version = relationship("LabelVersion")


# ─── Team Invites ─────────────────────────────────────────────────────────────

class TeamInvite(Base):
    __tablename__ = "team_invites"

    id          = Column(Integer, primary_key=True, index=True)
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
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable for system events
    action        = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=True)   # "product", "label", "report", "rule", etc.
    resource_id   = Column(Integer, nullable=True)
    detail        = Column(String(500), nullable=True)  # human-readable description
    ip_address    = Column(String(45), nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow, index=True)
    user          = relationship("User", foreign_keys=[user_id])


# ─── API Keys ─────────────────────────────────────────────────────────────────

class APIKey(Base):
    __tablename__ = "api_keys"
    id           = Column(Integer, primary_key=True, index=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False)
    name         = Column(String(100), nullable=False)          # e.g. "Production", "Dev laptop"
    key_prefix   = Column(String(10), nullable=False)           # first 8 chars, shown in UI
    key_hash     = Column(String(200), nullable=False)          # bcrypt hash of full key
    last_used_at = Column(DateTime, nullable=True)
    is_active    = Column(Boolean, default=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    user         = relationship("User", foreign_keys=[user_id])
