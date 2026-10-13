from django.core.management.base import BaseCommand
from apps.detection.models import NotificationDelivery
from apps.detection.notifications import deliver
class Command(BaseCommand):
    help='대기/실패 알림 전송 (최대 3회 시도). 명시적 운영 실행 시 실제 메시지를 발송합니다.'
    def handle(self,*args,**options):
        # Run one notification worker only to prevent concurrent duplicate sends.
        for item in NotificationDelivery.objects.filter(status__in=['queued','failed'],attempts__lt=3).select_related('event__session')[:100]:
            item.attempts+=1
            try:deliver(item);item.status='sent';item.error=''
            except Exception:item.status='failed';item.error='전송 실패: 네트워크 및 알림 설정을 확인하세요.'
            item.save(update_fields=['attempts','status','error'])
            self.stdout.write(f'{item.pk}: {item.status}')
