from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction

from reports.core.constants import CATEGORIES, DISTRICTS
from reports.models import District, ReportCategory
from reports.permissions import EDITOR_GROUP


class Command(BaseCommand):
    help = ("Create the 38 reference districts (in reference-workbook order), the 6 report categories "
            "and the 'Editors' group. Safe to run repeatedly: existing rows are never overwritten.")

    @transaction.atomic
    def handle(self, *args, **options):
        new_d = new_c = 0
        for order, (name, aliases) in enumerate(DISTRICTS, 1):
            _, created = District.objects.get_or_create(
                name=name, defaults={"sort_order": order, "aliases": ", ".join(aliases)})
            new_d += created
        for order, spec in enumerate(CATEGORIES, 1):
            _, created = ReportCategory.objects.get_or_create(code=spec["code"], defaults={
                "label": spec["label"], "excel_header": spec["excel_header"], "sort_order": order,
                "aliases": ", ".join(spec["aliases"]), "mapping_confirmed": spec["mapping_confirmed"]})
            new_c += created
        Group.objects.get_or_create(name=EDITOR_GROUP)
        self.stdout.write(self.style.SUCCESS(
            f"Master data ready: {new_d} districts and {new_c} categories created "
            f"({District.objects.count()} / {ReportCategory.objects.count()} in total)."))
        unconfirmed = ReportCategory.objects.filter(mapping_confirmed=False)
        for c in unconfirmed:
            self.stdout.write(self.style.WARNING(
                f"Mapping '{c.label}' -> '{c.excel_header}' is NOT confirmed yet: confirm it under Settings."))
