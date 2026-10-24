"""Create one real officer account without ever putting its password in a command."""
import getpass
import re
import sys

from database import Base, SessionLocal, engine
import models
from models import OfficerAccount
from services.auth_security import hash_password

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def main() -> None:
    email = (sys.argv[1] if len(sys.argv) > 1 else input("Officer Gmail/email: ")).strip().lower()
    if not EMAIL_RE.fullmatch(email):
        raise SystemExit("Enter a valid officer email address.")
    password = getpass.getpass("Create password (8+ characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 8:
        raise SystemExit("Password must contain at least 8 characters.")
    if password != confirmation:
        raise SystemExit("Passwords did not match; no account was created.")

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(OfficerAccount).filter_by(email=email).first():
            raise SystemExit("That officer account already exists.")
        db.add(OfficerAccount(email=email, password_hash=hash_password(password)))
        db.commit()
    print(f"Officer account created for {email}. Password is stored as a one-way hash.")


if __name__ == "__main__":
    main()
