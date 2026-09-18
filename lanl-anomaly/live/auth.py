"""Authentication: password + TOTP for demo users."""
import pyotp
import hashlib
import hmac
import os
import json

_SECRETS_PATH = os.path.join(os.path.dirname(__file__), '.totp_secrets.json')

USERS = {
    'luffy': {
        'name': 'Luffy',
        'user_id': 'U2899@DOM1',
        'password': 'mugiwara',
        'role': 'employee',
    },
    'ace': {
        'name': 'Ace',
        'user_id': 'U293@DOM1',
        'password': 'salvatore',
        'role': 'employee',
    },
    'igris': {
        'name': 'Igris',
        'user_id': 'U2097@DOM1',
        'password': 'shadow01',
        'role': 'employee',
    },
    'ashborn': {
        'name': 'Ashborn',
        'user_id': 'U66@DOM1',
        'password': 'monarch99',
        'role': 'employee',
    },
    'soc_admin': {
        'name': 'SOC Analyst',
        'user_id': None,
        'password': 'defender',
        'role': 'analyst',
    },
}


def _load_secrets():
    """Load or generate TOTP secrets."""
    if os.path.exists(_SECRETS_PATH):
        with open(_SECRETS_PATH) as f:
            return json.load(f)
    secrets = {}
    for username in USERS:
        secrets[username] = pyotp.random_base32()
    with open(_SECRETS_PATH, 'w') as f:
        json.dump(secrets, f, indent=2)
    return secrets


_secrets = None


def _get_secrets():
    global _secrets
    if _secrets is None:
        _secrets = _load_secrets()
    return _secrets


def get_totp_secret(username):
    """Return TOTP secret for a user."""
    return _get_secrets().get(username)


def get_totp_uri(username):
    """Return otpauth URI for QR code generation."""
    secret = get_totp_secret(username)
    if not secret:
        return None
    user = USERS[username]
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name='LANL SOC')


def get_current_code(username):
    """Get current TOTP code for a user (for demo display)."""
    secret = get_totp_secret(username)
    if not secret:
        return None
    return pyotp.TOTP(secret).now()


def verify_password(username, password):
    """Verify password. Returns user dict or None."""
    user = USERS.get(username)
    if not user:
        return None
    if not hmac.compare_digest(user['password'], password):
        return None
    return user


def verify_totp(username, code):
    """Verify TOTP code. Returns True/False."""
    secret = get_totp_secret(username)
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def authenticate(username, password, totp_code):
    """Full auth: password + TOTP. Returns user dict or None."""
    user = verify_password(username, password)
    if not user:
        return None
    if not verify_totp(username, totp_code):
        return None
    return user
