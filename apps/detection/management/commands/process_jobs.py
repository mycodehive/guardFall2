import time
from django.core.management.base import BaseCommand
from apps.detection.models import Job
from apps.detection.ml import process_record,train_record
class Command(BaseCommand):
    help='등록된 영상/학습 대기열을 순서대로 처리합니다. 단일 worker로 운영하세요.'
    def add_arguments(self,parser):
        parser.add_argument('--once',action='store_true')
    def handle(self,*args,**options):
        while True:
            ids=list(Job.objects.filter(status='queued').order_by('created_at').values_list('pk',flat=True)[:100])
            for pk in ids:
                job=Job.objects.get(pk=pk)
                try:
                    result=train_record(job) if job.kind=='train' else process_record(job)
                    self.stdout.write(f'Job {pk} complete')
                except Exception as exc:self.stderr.write(f'Job {pk} failed: {exc}')
            if options['once']:break
            time.sleep(5)
