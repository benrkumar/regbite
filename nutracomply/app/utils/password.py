"""
Shared password-strength validation.

Single source of truth for password complexity rules — imported by all
auth flows (registration, password change, invite acceptance) so that
the policy is consistent across every entry point.
"""


def validate_password(password: str) -> str | None:
    """Return an error message string if the password is too weak, else None.

    Policy (must ALL be satisfied):
    - At least 10 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    """
    if len(password) < 10:
        return "Password must be at least 10 characters."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one digit."
    return None
