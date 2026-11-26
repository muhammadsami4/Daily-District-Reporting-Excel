from datetime import datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from reports import services
from reports.core.validator import has_errors
from reports.models import DailyReport


class Command(BaseCommand):
    help = ("Import one or more daily-report text files with exactly the same parsing and validation as the "
            "web form. Files with errors are skipped, never partially saved. Existing dates are not overwritten.")

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="+")
        parser.add_argument("--user", help="Username recorded as the author (default: first superuser).")
        parser.add_argument("--date", help="Fallback date DD-MM-YYYY when the file has none.")
        parser.add_argument("--dry-run", action="store_true", help="Parse and validate only.")

    def handle(self, *args, **opts):
        User = get_user_model()
        user = (User.objects.filter(username=opts["user"]).first() if opts["user"]
                else User.objects.filter(is_superuser=True).first())
        if user is None:
            raise CommandError("No such user. Create one with 'python manage.py createsuperuser' first.")
        form_date = None
        if opts["date"]:
            try:
                form_date = datetime.strptime(opts["date"], "%d-%m-%Y").date()
            except ValueError:
                raise CommandError("--date must look like 24-11-2026")

        saved = skipped = 0
        for name in opts["files"]:
            text = Path(name).read_text(encoding="utf-8-sig")
            draft = services.parse_text(text, form_date)
            issues = services.validate_draft(draft)
            self.stdout.write(f"\n{name}")
            for issue in issues:
                self.stdout.write(f"  [{issue.level.upper()}] {issue.message}")
            report_date = services.draft_date(draft)
            if has_errors(issues):
                self.stdout.write(self.style.ERROR("  skipped: validation errors"))
                skipped += 1
            elif DailyReport.objects.filter(report_date=report_date).exists():
                self.stdout.write(self.style.WARNING(f"  skipped: a report for {report_date:%d-%m-%Y} already exists"))
                skipped += 1
            elif opts["dry_run"]:
                self.stdout.write(self.style.SUCCESS(f"  OK (dry run) for {report_date:%d-%m-%Y}"))
            else:
                services.save_report(draft, user, reason=f"Imported from {Path(name).name}")
                self.stdout.write(self.style.SUCCESS(f"  saved report for {report_date:%d-%m-%Y}"))
                saved += 1
        self.stdout.write(f"\nDone: {saved} saved, {skipped} skipped.")
