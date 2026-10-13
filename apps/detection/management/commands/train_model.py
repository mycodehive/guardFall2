from django.core.management.base import BaseCommand, CommandError
from apps.detection.models import Job
from apps.detection.ml import train_record


class Command(BaseCommand):
    help = 'Process a queued classifier training job. Requires optional ML dependencies.'

    def add_arguments(self, parser):
        parser.add_argument('job_id', type=int)

    def handle(self, *args, **options):
        try:
            record = Job.objects.get(pk=options['job_id'], kind='train')
            model = train_record(record)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Model {model.pk} trained: {model.metrics}'))
