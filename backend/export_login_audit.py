"""Export the password-free sign-in dataset to CSV for authorized local review."""
import csv
from pathlib import Path

from database import SessionLocal
from models import LoginAudit

OUTPUT = Path(__file__).resolve().parent / "login-audit.csv"


def main() -> None:
    with SessionLocal() as db, OUTPUT.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "email", "attempted_at", "success", "source_ip", "user_agent", "notification_sent"])
        for row in db.query(LoginAudit).order_by(LoginAudit.attempted_at.desc(), LoginAudit.id.desc()):
            writer.writerow([row.id, row.email, row.attempted_at.isoformat() if row.attempted_at else "",
                             row.success, row.source_ip or "", row.user_agent or "", row.notification_sent])
    print(f"Exported sign-in audit rows to {OUTPUT}")


if __name__ == "__main__":
    main()
