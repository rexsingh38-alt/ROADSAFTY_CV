"""Password sign-in and account setup for the SafeRoad local dashboard."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hmac
import logging
import re
import secrets
import smtplib
import ssl
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import AUTH_SECRET, GMAIL_APP_PASSWORD, GMAIL_USER, LOGIN_ALERT_TO, LOGIN_DEV_OTP, LOCAL_LOGIN_ORIGINS
from database import get_db
from models import LoginAudit, OfficerAccount, OtpChallenge
from services.auth_security import hash_otp, hash_password, issue_session, verify_password

router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger("saferoad.auth")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", re.IGNORECASE)
GMAIL_RE = re.compile(r"^[^\s@]+@gmail\.com$", re.IGNORECASE)
DUMMY_HASH = hash_password("not-a-real-account-password")
OTP_LIFETIME = timedelta(minutes=5)


class EmailRequest(BaseModel):
    email: str = Field(min_length=7, max_length=254)


class OtpVerifyRequest(EmailRequest):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=1024)


def _send_mail(recipient: str, subject: str, body: str) -> bool:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = GMAIL_USER
    message["To"] = recipient
    message.set_content(body)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
            server.starttls(context=context)
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD.replace(" ", ""))
            server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException) as exc:
        logger.warning("Could not send sign-in email: %s", type(exc).__name__)
        return False


def _send_login_alert(email: str, source_ip: str | None, user_agent: str | None) -> bool:
    recipient = LOGIN_ALERT_TO or email
    body = (
        "A successful sign-in to the SafeRoad AI Traffic Office Portal was recorded.\n\n"
        f"Account: {email}\nSource IP: {source_ip or 'Unavailable'}\n"
        f"Browser/device: {(user_agent or 'Unavailable')[:300]}\n\n"
        "If this was not you, contact your traffic office administrator."
    )
    return _send_mail(recipient, "SafeRoad AI sign-in alert", body)


def _request_context(request: Request) -> tuple[str | None, str | None]:
    source_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500] or None
    return source_ip, user_agent


def _local_dev_login_allowed(request: Request, source_ip: str | None) -> bool:
    # Never expose the development OTP outside the local dashboard origin.
    return bool(LOGIN_DEV_OTP and source_ip in {"127.0.0.1", "::1"}
                and request.headers.get("origin", "") in LOCAL_LOGIN_ORIGINS)


@router.post("/request-otp")
def request_otp(payload: EmailRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if not GMAIL_RE.fullmatch(email):
        return JSONResponse(status_code=422, content={"detail": "Use a valid @gmail.com address."})

    now = datetime.now(timezone.utc)
    source_ip, _ = _request_context(request)
    hour_ago = now - timedelta(hours=1)
    sent_for_email = db.query(func.count(OtpChallenge.id)).filter(
        OtpChallenge.email == email, OtpChallenge.created_at >= hour_ago
    ).scalar() or 0
    sent_for_ip = db.query(func.count(OtpChallenge.id)).filter(
        OtpChallenge.source_ip == source_ip, OtpChallenge.created_at >= hour_ago
    ).scalar() or 0
    recent = db.query(OtpChallenge.id).filter(
        OtpChallenge.email == email, OtpChallenge.created_at >= now - timedelta(seconds=60)
    ).first()
    if recent or sent_for_email >= 5 or sent_for_ip >= 12:
        return JSONResponse(status_code=429, content={"detail": "Please wait before requesting another code."})

    local_dev_login = _local_dev_login_allowed(request, source_ip)
    if (not GMAIL_USER or not GMAIL_APP_PASSWORD) and not local_dev_login:
        return JSONResponse(status_code=503, content={"detail": "Gmail OTP is not configured. Add GMAIL_USER and GMAIL_APP_PASSWORD to backend/.env."})

    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge_id = str(uuid4())
    body = (
        f"Your SafeRoad AI sign-in code is: {code}\n\n"
        "It expires in 5 minutes and can be used only once. Do not share this code. "
        "If you did not request it, you can ignore this email."
    )
    email_sent = True if local_dev_login and (not GMAIL_USER or not GMAIL_APP_PASSWORD) else _send_mail(email, "Your SafeRoad AI verification code", body)
    if not email_sent:
        return JSONResponse(status_code=503, content={"detail": "Gmail could not send the code. Check the App Password in backend/.env."})

    db.add(OtpChallenge(id=challenge_id, email=email,
                        code_digest=hash_otp(challenge_id, email, code),
                        created_at=now, expires_at=now + OTP_LIFETIME, source_ip=source_ip))
    db.commit()

    result = {"message": "Verification code sent to your Gmail inbox.", "email": email, "expires_in_seconds": 300}
    if local_dev_login and (not GMAIL_USER or not GMAIL_APP_PASSWORD):
        result["dev_code"] = code
        result["local_only"] = True
    return result


@router.post("/verify-otp")
def verify_otp(payload: OtpVerifyRequest, request: Request, db: Session = Depends(get_db)):
    source_ip, user_agent = _request_context(request)
    local_dev_login = _local_dev_login_allowed(request, source_ip)
    if (not GMAIL_USER or not GMAIL_APP_PASSWORD) and not local_dev_login:
        return JSONResponse(status_code=503, content={"detail": "Gmail OTP is not configured on the server."})
    email = payload.email.strip().lower()
    now = datetime.now(timezone.utc)
    challenge = None
    if EMAIL_RE.fullmatch(email):
        challenge = db.query(OtpChallenge).filter(
            OtpChallenge.email == email,
            OtpChallenge.consumed_at.is_(None),
            OtpChallenge.attempts < 5,
            OtpChallenge.expires_at > now,
        ).order_by(OtpChallenge.created_at.desc()).first()

    valid_code = bool(challenge and hmac.compare_digest(
        challenge.code_digest, hash_otp(challenge.id, email, payload.code)))
    if not valid_code:
        if challenge:
            challenge.attempts += 1
        db.add(LoginAudit(email=email[:254], attempted_at=now, success=False,
                          source_ip=source_ip, user_agent=user_agent, notification_sent=False))
        db.commit()
        return JSONResponse(status_code=401, content={"detail": "The code is invalid or expired. Request a new code."})

    challenge.consumed_at = now
    account = db.query(OfficerAccount).filter(OfficerAccount.email == email).first()
    if account is None:
        # OTP ownership is the credential for passwordless accounts; this random hash is not usable as a password.
        account = OfficerAccount(email=email, password_hash=hash_password(secrets.token_urlsafe(48)))
        db.add(account)
    elif not account.is_active:
        db.add(LoginAudit(email=email, attempted_at=now, success=False, source_ip=source_ip,
                          user_agent=user_agent, notification_sent=False))
        db.commit()
        return JSONResponse(status_code=403, content={"detail": "This officer account is disabled."})

    audit = LoginAudit(email=email, attempted_at=now, success=True, source_ip=source_ip,
                       user_agent=user_agent, notification_sent=False)
    db.add(audit)
    db.commit()
    notification_sent = _send_login_alert(email, source_ip, user_agent)
    audit.notification_sent = notification_sent
    db.commit()
    return {"access_token": issue_session(email), "token_type": "bearer",
            "officer": {"email": email}, "notification_sent": notification_sent}


@router.post("/register")
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """Create or set a local dashboard password without an email verification step."""
    email = payload.email.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        return JSONResponse(status_code=422, content={"detail": "Enter a valid email address."})

    account = db.query(OfficerAccount).filter(OfficerAccount.email == email).first()
    if account is None:
        account = OfficerAccount(email=email, password_hash=hash_password(payload.password))
        db.add(account)
    else:
        # Existing local OTP accounts had random, unusable passwords; allow them to set one here.
        account.password_hash = hash_password(payload.password)
        account.is_active = True

    source_ip, user_agent = _request_context(request)
    audit = LoginAudit(email=email, attempted_at=datetime.now(timezone.utc), success=True,
                       source_ip=source_ip, user_agent=user_agent, notification_sent=False)
    db.add(audit)
    db.commit()
    return {"access_token": issue_session(email), "token_type": "bearer",
            "officer": {"email": email}, "notification_sent": False}


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Legacy password login for accounts provisioned by the local administrator."""
    email = payload.email.strip().lower()
    account = db.query(OfficerAccount).filter(OfficerAccount.email == email).first() if EMAIL_RE.fullmatch(email) else None
    password_ok = verify_password(payload.password, account.password_hash if account else DUMMY_HASH)
    success = bool(account and account.is_active and password_ok)
    source_ip, user_agent = _request_context(request)
    notification_sent = _send_login_alert(email, source_ip, user_agent) if success else False
    db.add(LoginAudit(email=email[:254], attempted_at=datetime.now(timezone.utc), success=success,
                      source_ip=source_ip, user_agent=user_agent, notification_sent=notification_sent))
    db.commit()
    if not success:
        return JSONResponse(status_code=401, content={"detail": "Email or password is incorrect."})
    return {"access_token": issue_session(email), "token_type": "bearer",
            "officer": {"email": email}, "notification_sent": notification_sent}
