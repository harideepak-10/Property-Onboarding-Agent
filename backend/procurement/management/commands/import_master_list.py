from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from procurement.importer import import_csv

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "master_list_sample.csv"


class Command(BaseCommand):
    help = "Import the master supply list from a CSV file (defaults to the bundled sample list)."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(SAMPLE))
        parser.add_argument("--deactivate-missing", action="store_true",
                            help="Deactivate items that are not in this file.")

    def handle(self, path, deactivate_missing, **opts):
        with open(path, newline="", encoding="utf-8-sig") as f:
            result = import_csv(f, deactivate_missing=deactivate_missing)
        if result["errors"]:
            raise CommandError("Nothing imported:\n" + "\n".join(result["errors"]))
        if opts.get("verbosity", 1):
            self.stdout.write(self.style.SUCCESS(f"Imported: {result['created']} new, {result['updated']} updated."))
