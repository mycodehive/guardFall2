from django.core.management.base import BaseCommand, CommandError
from apps.detection.models import Job
from apps.detection.ml import process_record


class Command(BaseCommand):
    help = 'Process a queued video extraction job. Requires optional vision dependencies.'

    def add_arguments(self, parser):
        parser.add_argument('job_id', type=int)

    def handle(self, *args, **options):
        try:
            record = Job.objects.get(pk=options['job_id'], kind='video')
            result = process_record(record)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Video processed: {result}'))
