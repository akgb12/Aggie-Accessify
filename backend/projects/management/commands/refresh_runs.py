from django.core.management.base import BaseCommand

from a11y_pipeline.runs.outputs import OUTPUTS_VERSION
from projects.models import Run
from projects.tasks import refresh_run_outputs_now


class Command(BaseCommand):
    help = "Bring every finished run's downloads up to date now, without the model"

    def handle(self, *args, **options) -> None:
        outdated = Run.objects.filter(
            status=Run.Status.SUCCEEDED, outputs_version__lt=OUTPUTS_VERSION
        )
        updated = 0
        total = outdated.count()
        for run in outdated:
            Run.objects.filter(id=run.id).update(refreshing=True)
            if refresh_run_outputs_now(run):
                updated += 1
        self.stdout.write(f"Checked {total} older run(s); {updated} gained new downloads.")
