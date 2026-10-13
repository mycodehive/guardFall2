import math
from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import MonitoringSession,PoseFrame,FallEvent,NotificationSettings,NotificationDelivery
from .ml import rule_predict
JOINTS=['left_shoulder','right_shoulder','left_knee','right_knee']
def validate_joints(data,config):
    if not isinstance(data,dict):raise ValidationError('관절 객체가 필요합니다.')
    clean={}
    for joint in JOINTS:
        for suffix in ['x','y','v']:
            key=f'{joint}_{suffix}'; value=data.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValidationError('유효한 관절 좌표가 필요합니다.')
            if suffix=='v' and not 0<=value<=1:raise ValidationError('신뢰도는 0~1입니다.')
            if suffix in ('x','y') and not -2<=value<=3:raise ValidationError('좌표 범위 초과입니다.')
            clean[key]=float(value)
        clean[f'{joint}_vr']=int(clean[f'{joint}_v']>=config.get('VISIBILITY',.7))
    return clean
@transaction.atomic
def ingest_frame(user,session_id,sequence,joints):
    session=MonitoringSession.objects.select_for_update().get(pk=session_id,owner=user)
    now=timezone.now()
    if session.model_id and (not session.model.active or (session.model.owner_id!=user.pk and not session.model.allowed_users.filter(pk=user.pk).exists())):
        raise ValidationError('모델 사용 권한이 변경되었습니다. 새 세션을 시작하세요.',code='conflict')
    if not session.active:raise ValidationError('종료된 감지 세션입니다.',code='conflict')
    if now-session.started_at>timedelta(hours=8):raise ValidationError('감지 세션이 만료되었습니다. 다시 시작하세요.',code='conflict')
    if isinstance(sequence,bool) or not isinstance(sequence,int) or not 0<=sequence<=2147483647:raise ValidationError('프레임 번호가 필요합니다.')
    if sequence<=session.last_sequence:raise ValidationError('중복 또는 역순 프레임입니다.',code='conflict')
    clean=validate_joints(joints,session.config)
    probability=None
    if session.model_id:
        from .ml import predict_record
        prediction,probability=predict_record(session.model,clean,session.config)
    else: prediction=rule_predict(clean,session.config)
    frame=PoseFrame.objects.create(session=session,sequence=sequence,joints=clean,prediction=prediction,probability=probability)
    session.fall_streak=session.fall_streak+1 if prediction==1 else 0
    session.last_sequence=sequence
    event=None
    if session.fall_streak>=session.config.get('consecutive_frames',10) and (not session.last_event_at or (now-session.last_event_at).total_seconds()>=session.config.get('cooldown_seconds',30)):
        event=FallEvent.objects.create(session=session,frame=frame)
        session.last_event_at=now
        if NotificationSettings.objects.filter(owner=user,enabled=True).exists():NotificationDelivery.objects.create(event=event)
    session.save(update_fields=['fall_streak','last_sequence','last_event_at'])
    return frame,event
