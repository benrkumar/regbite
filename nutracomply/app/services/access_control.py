from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Account, User, UserRole


READ_ONLY_ROLES = {
    UserRole.VIEWER,
    UserRole.CONSULTANT,
}

EDIT_ROLES = {
    UserRole.ACCOUNT_ADMIN,
    UserRole.EDITOR,
}


def sync_user_role_flags(user: User | None) -> None:
    if not user:
        return
    user.is_admin = user.role == UserRole.SUPER_ADMIN


def is_platform_admin(user: User | None) -> bool:
    return bool(user and user.role == UserRole.SUPER_ADMIN)


def is_account_admin(user: User | None) -> bool:
    return bool(user and user.role == UserRole.ACCOUNT_ADMIN)


def can_read_account_data(user: User | None) -> bool:
    return bool(user and user.role in {
        UserRole.SUPER_ADMIN,
        UserRole.ACCOUNT_ADMIN,
        UserRole.EDITOR,
        UserRole.VIEWER,
        UserRole.CONSULTANT,
    })


def can_edit_account_data(user: User | None) -> bool:
    return bool(user and (user.role in EDIT_ROLES or is_platform_admin(user)))


def can_manage_billing(user: User | None) -> bool:
    return bool(user and (is_platform_admin(user) or is_account_admin(user)))


def can_manage_team(user: User | None) -> bool:
    return can_manage_billing(user)


def can_manage_api_keys(user: User | None) -> bool:
    return can_manage_billing(user)


def can_manage_branding(user: User | None) -> bool:
    return can_manage_billing(user)


def can_share_reports(user: User | None) -> bool:
    return can_edit_account_data(user)


def can_run_checker(user: User | None) -> bool:
    return can_edit_account_data(user)


def can_upload_labels(user: User | None) -> bool:
    return can_edit_account_data(user)


def can_mutate_products(user: User | None) -> bool:
    return can_edit_account_data(user)


def get_account_id(user: User | None) -> Optional[int]:
    if not user:
        return None
    return getattr(user, "account_id", None)


def get_workspace_owner(db: Session, user: User | None) -> User | None:
    if not user:
        return None
    if user.team_id:
        owner = db.query(User).filter(User.id == user.team_id).first()
        if owner:
            return owner
    return user


def build_account_name(user: User) -> str:
    if user.company_name:
        return user.company_name.strip()[:255]
    if user.name:
        return f"{user.name.strip()[:200]}'s Workspace"
    return f"{user.email}'s Workspace"


def ensure_account_for_user(db: Session, user: User) -> Account:
    if getattr(user, "account_id", None):
        account = db.query(Account).filter(Account.id == user.account_id).first()
        if account:
            return account

    account = Account(
        name=build_account_name(user),
        owner_email=user.email,
        company_name=user.company_name,
        company_gstin=user.company_gstin,
        report_brand_name=user.report_brand_name,
        report_brand_color=user.report_brand_color,
        created_by_user_id=user.id,
    )
    db.add(account)
    db.flush()
    user.account_id = account.id
    sync_user_role_flags(user)
    db.flush()
    return account


def ensure_workspace_for_user(db: Session, user: User | None) -> Account | None:
    if not user:
        return None
    sync_user_role_flags(user)
    owner = get_workspace_owner(db, user) or user
    account = ensure_account_for_user(db, owner)
    expected_account_id = owner.account_id or account.id
    changed = False
    if user.account_id != expected_account_id:
        user.account_id = expected_account_id
        changed = True
    if owner.company_name and not account.company_name:
        account.company_name = owner.company_name
        changed = True
    if owner.company_gstin and not account.company_gstin:
        account.company_gstin = owner.company_gstin
        changed = True
    if owner.report_brand_name and not account.report_brand_name:
        account.report_brand_name = owner.report_brand_name
        changed = True
    if owner.report_brand_color and not account.report_brand_color:
        account.report_brand_color = owner.report_brand_color
        changed = True
    if changed:
        db.flush()
    return account


def account_users_query(db: Session, user: User | None):
    account_id = get_account_id(user)
    return db.query(User).filter(User.account_id == account_id)


def get_account_contact_user(db: Session, account_id: int | None) -> User | None:
    if account_id is None:
        return None

    primary = (
        db.query(User)
        .filter(
            User.account_id == account_id,
            User.role.in_([UserRole.ACCOUNT_ADMIN, UserRole.SUPER_ADMIN]),
        )
        .order_by(User.created_at.asc(), User.id.asc())
        .first()
    )
    if primary:
        return primary

    return (
        db.query(User)
        .filter(User.account_id == account_id)
        .order_by(User.created_at.asc(), User.id.asc())
        .first()
    )


def require_account_membership(user: User | None, account_id: int | None) -> bool:
    if not user or account_id is None:
        return False
    if is_platform_admin(user):
        return True
    return get_account_id(user) == account_id
