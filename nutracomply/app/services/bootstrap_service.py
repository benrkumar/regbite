from __future__ import annotations

from app.models import (
    Alert,
    APIKey,
    CheckerSession,
    ComplianceReport,
    KBDocument,
    KBType,
    LabelVersion,
    LicenseRenewal,
    PaymentRecord,
    Product,
    RegulationChange,
    RegulationSource,
    Subscription,
    TeamInvite,
    User,
)
from app.services.access_control import ensure_account_for_user, sync_user_role_flags


DEFAULT_REGULATION_SOURCES = [
    {
        "name": "FSSAI Regulations",
        "slug": "fssai-regulations",
        "base_url": "https://fssai.gov.in/cms/food-safety-and-standards-regulations.php",
        "doc_type": "regulation_page",
    },
    {
        "name": "FSSAI Gazette Notifications",
        "slug": "fssai-gazette",
        "base_url": "https://fssai.gov.in/notifications.php?notification=gazette-notification",
        "doc_type": "gazette",
    },
    {
        "name": "AYUSH Advisories",
        "slug": "ayush-advisories",
        "base_url": "https://ayush.gov.in/advisories",
        "doc_type": "advisory",
    },
    {
        "name": "AYUSH Regulations",
        "slug": "ayush-regulations",
        "base_url": "https://ayush.gov.in/regulation-rules-and-acts",
        "doc_type": "regulation_page",
    },
    {
        "name": "Legal Metrology Rules",
        "slug": "legal-metrology-rules",
        "base_url": "https://consumeraffairs.nic.in/policies-rules/legal-metrology-packaged-commodities-rules-2011",
        "doc_type": "rules",
    },
    {
        "name": "Legal Metrology Act",
        "slug": "legal-metrology-act",
        "base_url": "https://consumeraffairs.gov.in/pages/legal-metrology-act",
        "doc_type": "act",
    },
]


def seed_regulation_sources(db) -> None:
    existing = {
        source.slug: source
        for source in db.query(RegulationSource).all()
    }
    for source_data in DEFAULT_REGULATION_SOURCES:
        if source_data["slug"] in existing:
            continue
        db.add(RegulationSource(**source_data))
    db.flush()

    all_sources = db.query(RegulationSource).all()
    for change in db.query(RegulationChange).filter(RegulationChange.source_id.is_(None)).all():
        url = (change.source_url or "").lower()
        matched = None
        for source in all_sources:
            if source.base_url.lower() in url or source.slug.split("-")[0] in url:
                matched = source
                break
        if not matched:
            continue
        change.source_id = matched.id
        if not change.document_type:
            change.document_type = matched.doc_type


def backfill_account_ownership(db) -> None:
    users = db.query(User).order_by(User.id.asc()).all()
    user_by_id = {user.id: user for user in users}

    for user in users:
        sync_user_role_flags(user)
        owner = user_by_id.get(user.team_id) if user.team_id else user
        account = ensure_account_for_user(db, owner or user)
        if not user.account_id:
            user.account_id = account.id
        if owner and owner.id != user.id:
            user.account_id = owner.account_id or account.id
        if owner and owner.id == user.id:
            account.company_name = account.company_name or user.company_name
            account.company_gstin = account.company_gstin or user.company_gstin
            account.report_brand_name = account.report_brand_name or user.report_brand_name
            account.report_brand_color = account.report_brand_color or user.report_brand_color
            account.owner_email = account.owner_email or user.email

    db.flush()
    account_ids = {user.id: user.account_id for user in users}

    for product in db.query(Product).all():
        if not product.account_id:
            product.account_id = account_ids.get(product.user_id)

    for renewal in db.query(LicenseRenewal).all():
        if not renewal.account_id:
            renewal.account_id = account_ids.get(renewal.user_id)

    for report in db.query(ComplianceReport).all():
        if not report.account_id:
            report.account_id = (
                getattr(report.product, "account_id", None)
                or account_ids.get(report.user_id)
            )

    for api_key in db.query(APIKey).all():
        if not api_key.account_id:
            api_key.account_id = account_ids.get(api_key.user_id)

    for subscription in db.query(Subscription).all():
        if not subscription.account_id:
            subscription.account_id = account_ids.get(subscription.user_id)

    for payment in db.query(PaymentRecord).all():
        if not payment.account_id:
            payment.account_id = account_ids.get(payment.user_id)

    for invite in db.query(TeamInvite).all():
        if not invite.account_id:
            invite.account_id = account_ids.get(invite.invited_by)

    for session in db.query(CheckerSession).all():
        if not session.account_id:
            session.account_id = account_ids.get(session.user_id)

    for kb_doc in db.query(KBDocument).filter(KBDocument.kb_type == KBType.PRODUCTS).all():
        if kb_doc.account_id:
            continue
        source = kb_doc.source or ""
        if source.startswith("db:product:"):
            try:
                product_id = int(source.rsplit(":", 1)[-1])
            except ValueError:
                product_id = None
            if product_id:
                product = db.query(Product).filter(Product.id == product_id).first()
                if product:
                    kb_doc.account_id = product.account_id

    for alert in db.query(Alert).all():
        if alert.account_id:
            continue
        if alert.product_id:
            product = db.query(Product).filter(Product.id == alert.product_id).first()
            alert.account_id = getattr(product, "account_id", None)
            continue
        if alert.label_version_id:
            label = (
                db.query(LabelVersion)
                .filter(LabelVersion.id == alert.label_version_id)
                .first()
            )
            if label and label.product:
                alert.account_id = getattr(label.product, "account_id", None)
                continue
        if alert.regulation_change_id:
            account_owner = next(
                (
                    user.account_id
                    for user in users
                    if user.role and user.role.value == "super_admin"
                ),
                None,
            )
            alert.account_id = account_owner

    db.flush()
