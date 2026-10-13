import math
from pathlib import Path
from django import forms
from .models import Job,DetectionSettings
class JobForm(forms.ModelForm):
    class Meta:
        model=Job
        fields=['name','input_file','algorithm']
        labels={'name':'작업명','input_file':'입력 파일','algorithm':'학습 모델'}
    def __init__(self,*args,kind='video',**kwargs):
        self.kind=kind
        super().__init__(*args,**kwargs)
        if kind=='video':self.fields.pop('algorithm')
    def clean_input_file(self):
        f=self.cleaned_data['input_file']
        allowed={'.csv'} if self.kind=='train' else {'.mp4','.avi','.mov','.webm'}
        limit=10*1024*1024 if self.kind=='train' else 200*1024*1024
        if Path(f.name).suffix.lower() not in allowed:raise forms.ValidationError('지원하지 않는 파일 형식입니다.')
        if f.size>limit or f.size==0:raise forms.ValidationError('파일 용량 범위를 확인하세요.')
        return f
class SettingsForm(forms.ModelForm):
    class Meta:
        model=DetectionSettings
        exclude=['id']
        labels={'min_ok_parts':'최소 유효 관절 수','ls_y':'왼쪽 어깨 Y 기준','rs_y':'오른쪽 어깨 Y 기준','lk_y':'왼쪽 무릎 Y 기준','rk_y':'오른쪽 무릎 Y 기준','fall_count':'낙상 조건 충족 관절 수','visibility':'관절 신뢰도 기준','fall_probability':'모델 확률 기준','consecutive_frames':'연속 낙상 프레임 수','cooldown_seconds':'중복 알림 방지 시간(초)'}
    def clean(self):
        data=super().clean()
        for key,val in data.items():
            if isinstance(val,float) and not math.isfinite(val):self.add_error(key,'유한한 숫자를 입력하세요.')
        return data
class NotificationForm(forms.Form):
    enabled=forms.BooleanField(label='텔레그램 알림 사용',required=False)
    token=forms.CharField(label='봇 토큰 (변경할 때만 입력)',required=False,widget=forms.PasswordInput)
    chat_id=forms.CharField(label='수신 Chat ID (변경할 때만 입력)',required=False,widget=forms.PasswordInput)
