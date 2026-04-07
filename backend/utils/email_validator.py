"""
Phase 3: Email Validator + Disposable Domain Blocklist
Prevents spam, ensures legitimate referrals, enforces legal consent
"""

import re
from typing import Tuple

# Disposable/Temporary email domains (prevent spam referrals)
DISPOSABLE_DOMAINS = {
    # Temporary email services
    'tempmail.com', 'temp-mail.org', 'throwaway.email',
    'mailinator.com', 'maildrop.cc', 'temp.email',
    '10minutemail.com', 'guerrillamail.com', 'yopmail.com',
    'sharklasers.com', 'spam4.me', '10minutemail.de',
    'throwawaymail.com', 'privacy.com', 'protonmail.com',
    
    # Catch-all/sybil attack vectors
    'test.com', 'example.com', 'temp.com', 'fake.com',
    'xxx.com', '123.com', 'admin.com',
}

EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"
)


class EmailValidationError(Exception):
    """Raised when email fails validation"""
    pass


def validate_email_format(email: str) -> bool:
    """
    Validate email format (RFC 5322 simplified)
    Returns: True if valid format, raises EmailValidationError otherwise
    """
    email = email.strip().lower()
    
    if not email or len(email) > 254:
        raise EmailValidationError("Email is empty or too long (max 254 chars)")
    
    if not EMAIL_REGEX.match(email):
        raise EmailValidationError("Email format invalid (not RFC 5322 compliant)")
    
    return True


def validate_email_domain(email: str) -> bool:
    """
    Check if email domain is legitimate (not disposable/temporary)
    Returns: True if legit, raises EmailValidationError if disposable
    """
    email = email.strip().lower()
    domain = email.split('@')[1] if '@' in email else ''
    
    if not domain:
        raise EmailValidationError("Invalid email format")
    
    # Check exact domain match
    if domain in DISPOSABLE_DOMAINS:
        raise EmailValidationError(
            f"Email domain '{domain}' is temporary/disposable. "
            "Use your work or personal email."
        )
    
    # Check common subdomains of disposable services
    for disposable in DISPOSABLE_DOMAINS:
        if domain.endswith(disposable):
            raise EmailValidationError(
                f"Email domain '{domain}' appears to be temporary. "
                "Use a legitimate email address."
            )
    
    return True


def validate_email(email: str) -> Tuple[bool, str]:
    """
    Full email validation pipeline
    
    Args:
        email: Email address to validate
    
    Returns:
        Tuple of (is_valid: bool, error_message: str or '')
    
    Example:
        is_valid, error_msg = validate_email('user@gmail.com')
        if not is_valid:
            print(f"Invalid: {error_msg}")
    """
    try:
        validate_email_format(email)
        validate_email_domain(email)
        return True, ""
    except EmailValidationError as e:
        return False, str(e)


def get_email_domain(email: str) -> str:
    """Extract domain from email safely"""
    try:
        return email.split('@')[1].lower()
    except IndexError:
        return ""


def is_corporate_email(email: str) -> bool:
    """Detect corporate domains (for analytics)"""
    domain = get_email_domain(email)
    common_corporate = {
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'protonmail.com', 'icloud.com', 'aol.com', 'mail.com'
    }
    return domain not in common_corporate
