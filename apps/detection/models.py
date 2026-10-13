import uuid
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator,MaxValueValidator

def private_upload(instance,filename):
    from pathlib import Path
    return f'private/{instance.owner_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}'
def default_config():
    return {'MIN_OK_PARTS':3,'LS_Y':0.55,'RS_Y':0.55,'LK_Y':0.65,'RK_Y':0.65,'FALL_COUNT':3,'VISIBILITY':0.7,'FALL_PROBABILITY':0.5}
class DetectionSettings(models.Model):
    id=models.PositiveSmallIntegerField(primary_key=True,default=1,editable=False)
    min_ok_parts=models.PositiveSmallIntegerField(default=3,validators=[MinValueValidator(1),MaxValueValidator(4)])
    ls_y=models.FloatField(default=.55,validators=[MinValueValidator(0),MaxValueValidator(1)])
    rs_y=models.FloatField(default=.55,validators=[MinValueValidator(0),MaxValueValidator(1)])
    lk_y=models.FloatField(default=.65,validators=[MinValueValidator(0),MaxValueValidator(1)])
    rk_y=models.FloatField(default=.65,validators=[MinValueValidator(0),MaxValueValidator(1)])
    fall_count=models.PositiveSmallIntegerField(default=3,validators=[MinValueValidator(1),MaxValueValidator(4)])
    visibility=models.FloatField(default=.7,validators=[MinValueValidator(0),MaxValueValidator(1)])
    fall_probability=models.FloatField(default=.5,validators=[MinValueValidator(0),MaxValueValidator(1)])
    consecutive_frames=models.PositiveSmallIntegerField(default=10,validators=[MinValueValidator(1),MaxValueValidator(300)])
    cooldown_seconds=models.PositiveIntegerField(default=30,validators=[MaxValueValidator(86400)])
    def as_config(self):
        return {'MIN_OK_PARTS':self.min_ok_parts,'LS_Y':self.ls_y,'RS_Y':self.rs_y,'LK_Y':self.lk_y,'RK_Y':self.rk_y,'FALL_COUNT':self.fall_count,'VISIBILITY':self.visibility,'FALL_PROBABILITY':self.fall_probability,'consecutive_frames':self.consecutive_frames,'cooldown_seconds':self.cooldown_seconds}
class Job(models.Model):
    KIND=[('video','영상 분석'),('train','모델 학습')]
    STATUS=[('queued','대기'),('running','처리 중'),('done','완료'),('failed','실패'),('cancelled','취소')]
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    name=models.CharField(max_length=120)
    kind=models.CharField(max_length=12,choices=KIND)
    algorithm=models.CharField(max_length=12,choices=[('dense','Dense'),('lstm','LSTM'),('ensemble','앙상블')],default='dense')
    status=models.CharField(max_length=12,choices=STATUS,default='queued')
    input_file=models.FileField(upload_to=private_upload)
    result_file=models.FileField(upload_to=private_upload,blank=True)
    config=models.JSONField(default=default_config)
    error=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    class Meta: ordering=['-created_at']
class TrainedModel(models.Model):
    allowed_users=models.ManyToManyField(settings.AUTH_USER_MODEL,blank=True,related_name='assigned_fall_models')
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    job=models.OneToOneField(Job,on_delete=models.SET_NULL,null=True,blank=True)
    name=models.CharField(max_length=120)
    algorithm=models.CharField(max_length=12)
    artifact=models.FileField(upload_to=private_upload)
    metrics=models.JSONField(default=dict)
    features=models.JSONField(default=list)
    active=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=['-created_at']
class MonitoringSession(models.Model):
    owner=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    name=models.CharField(max_length=120,default='실시간 감지')
    model=models.ForeignKey(TrainedModel,on_delete=models.PROTECT,null=True,blank=True)
    config=models.JSONField(default=default_config)
    active=models.BooleanField(default=True)
    fall_streak=models.PositiveIntegerField(default=0)
    last_sequence=models.IntegerField(default=-1)
    last_event_at=models.DateTimeField(null=True,blank=True)
    started_at=models.DateTimeField(auto_now_add=True)
    ended_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=['-started_at']
class PoseFrame(models.Model):
    session=models.ForeignKey(MonitoringSession,on_delete=models.CASCADE,related_name='frames')
    sequence=models.PositiveIntegerField()
    joints=models.JSONField()
    prediction=models.SmallIntegerField(default=-1)
    probability=models.FloatField(null=True,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['session','sequence'],name='unique_session_frame')]
        ordering=['sequence']
class FallEvent(models.Model):
    session=models.ForeignKey(MonitoringSession,on_delete=models.CASCADE,related_name='events')
    frame=models.OneToOneField(PoseFrame,on_delete=models.CASCADE)
    status=models.CharField(max_length=12,choices=[('new','미확인'),('confirmed','확인'),('false_alarm','오탐')],default='new')
    note=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    reviewed_at=models.DateTimeField(null=True,blank=True)
    class Meta: ordering=['-created_at']
class NotificationSettings(models.Model):
    owner=models.OneToOneField(settings.AUTH_USER_MODEL,on_delete=models.CASCADE)
    enabled=models.BooleanField(default=False)
    token_ciphertext=models.TextField(blank=True)
    chat_id_ciphertext=models.TextField(blank=True)
class NotificationDelivery(models.Model):
    event=models.OneToOneField(FallEvent,on_delete=models.CASCADE)
    status=models.CharField(max_length=12,default='queued',choices=[('queued','대기'),('sent','발송'),('failed','실패')])
    attempts=models.PositiveSmallIntegerField(default=0)
    error=models.CharField(max_length=200,blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
