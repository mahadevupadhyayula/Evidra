from django.core.management.base import BaseCommand, CommandError

from apps.generations.models import GenerationOperation
from apps.generations.services import GenerationRunService


class Command(BaseCommand):
    help = "Process pending database-backed generation runs."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10, help="Maximum runs to process.")
        parser.add_argument(
            "--operation",
            choices=[choice.value for choice in GenerationOperation],
            help="Optionally process only one known operation.",
        )
        parser.add_argument(
            "--abandoned-after-minutes",
            type=int,
            default=GenerationRunService.ABANDONED_AFTER_MINUTES,
            help="Recover running jobs older than this threshold before processing.",
        )
        parser.add_argument(
            "--skip-abandoned-recovery",
            action="store_true",
            help="Do not recover abandoned running jobs before processing.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be at least 1.")

        recovered = 0
        if not options["skip_abandoned_recovery"]:
            recovered = GenerationRunService.recover_abandoned(
                abandoned_after_minutes=options["abandoned_after_minutes"]
            )
        processed = GenerationRunService.process_batch(
            limit=limit,
            operation=options.get("operation"),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {processed} generation run(s); recovered {recovered} abandoned run(s)."
            )
        )
