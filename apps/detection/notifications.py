import json
import urllib.request
from cryptography.fernet import Fernet,InvalidToken
from django.conf import settings

def cipher():
    if not settings.GUARDFALL_ENCRYPTION_KEY:raise ValueError('GUARDFALL_ENCRYPTION_KEY가 필요합니다.')
    return Fernet(settings.GUARDFALL_ENCRYPTION_KEY.encode())
def encrypt(value):return cipher().encrypt(value.encode()).decode()
def decrypt(value):return cipher().decrypt(value.encode()).decode()
def deliver(item):
    from .models import NotificationSettings
    cfg=NotificationSettings.objects.get(owner=item.event.session.owner)
    if not cfg.enabled:raise ValueError('알림이 비활성화되었습니다.')
    token=decrypt(cfg.token_ciphertext); chat_id=decrypt(cfg.chat_id_ciphertext)
    import re
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+',token):raise ValueError('봇 토큰 형식 오류')
    body=json.dumps({'chat_id':chat_id,'text':f'GuardFall2: 낙상 의심 감지 #{item.event_id}. 감지 화면에서 확인해 주세요.'}).encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',data=body,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as response:
        result=json.load(response)
    if not result.get('ok'):raise ValueError('알림 서비스 응답 실패')
