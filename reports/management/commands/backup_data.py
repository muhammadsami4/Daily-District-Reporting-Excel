import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = ("Write a timestamped backup: a JSON dump of all reports/users (works for every database) and, for "
            "SQLite, a consistent copy of the database file. Old backups beyond --keep are removed.")

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", default=str(settings.BASE_DIR / "backups"))
        parser.add_argument("--keep", type=int, default=30, help="How many backups of each kind to keep.")

    def handle(self, *args, **opts):
        out = Path(opts["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        json_path = out / f"backup_{stamp}.json"
        with open(json_path, "w", encoding="utf-8") as fh:
            call_command("dumpdata", "reports", "auth.user", "auth.group", indent=1,
                         use_natural_foreign_keys=True, stdout=fh)
        self.stdout.write(self.style.SUCCESS(f"JSON backup: {json_path}"))

        db = settings.DATABASES["default"]
        if db["ENGINE"].endswith("sqlite3"):
            db_path = out / f"db_{stamp}.sqlite3"
            src, dst = sqlite3.connect(str(db["NAME"])), sqlite3.connect(str(db_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
            self.stdout.write(self.style.SUCCESS(f"SQLite copy: {db_path}"))
        else:
            self.stdout.write("PostgreSQL: also run  pg_dump -U <user> <dbname> > backup.sql  (see README).")

        for pattern in ("backup_*.json", "db_*.sqlite3"):
            for old in sorted(out.glob(pattern))[:-opts["keep"]]:
                old.unlink()
