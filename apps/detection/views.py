import json
from django.contrib import messages
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse,FileResponse,Http404,HttpResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from apps.menus.decorators import feature
from apps.core.models import audit
from .models import Job,TrainedModel,DetectionSettings,MonitoringSession,PoseFrame,FallEvent,NotificationSettings
from .forms import JobForm,SettingsForm,NotificationForm
from .services import ingest_frame

def own(qs,user):return qs.filter(owner=user)
def configuration():return DetectionSettings.objects.get_or_create(pk=1)[0]
@feature('monitor')
def monitor(request):
    return render(request,'detection/monitor.html',{'sessions':own(MonitoringSession.objects.all(),request.user)[:20],'models':TrainedModel.objects.filter(Q(owner=request.user)|Q(allowed_users=request.user),active=True).distinct()})
@feature('monitor')
@require_POST
def start(request):
    model=None
    if request.POST.get('model'):model=get_object_or_404(TrainedModel.objects.filter(Q(owner=request.user)|Q(allowed_users=request.user)).distinct(),pk=request.POST['model'],active=True)
    session=MonitoringSession.objects.create(owner=request.user,model=model,config=configuration().as_config())
    audit(request.user,'session.start',session)
    return JsonResponse({'id':session.pk})
@feature('monitor')
@require_POST
def frame(request,pk):
    get_object_or_404(MonitoringSession,pk=pk,owner=request.user)
    try:
        data=json.loads(request.body)
        if not isinstance(data,dict):raise ValidationError('객체 요청이 필요합니다.')
        pose,event=ingest_frame(request.user,pk,data.get('sequence'),data.get('joints'))
    except (ValueError,ValidationError,KeyError,TypeError) as exc:
        return JsonResponse({'error':str(exc)},status=409 if getattr(exc,'code',None)=='conflict' else 400)
    except RuntimeError:
        return JsonResponse({'error':'모델 실행 오류입니다. 모델 및 ML 설치를 확인하세요.'},status=503)
    return JsonResponse({'prediction':pose.prediction,'probability':pose.probability,'event':event.pk if event else None})
@feature('monitor')
@require_POST
@transaction.atomic
def stop(request,pk):
    obj=get_object_or_404(MonitoringSession.objects.select_for_update(),pk=pk,owner=request.user)
    obj.active=False;obj.ended_at=timezone.now();obj.save(update_fields=['active','ended_at']);audit(request.user,'session.stop',obj)
    if request.POST.get('_redirect'):return redirect('/monitor/')
    return JsonResponse({'stopped':True})
@feature('jobs',staff=True)
def jobs(request):
    kind=request.GET.get('kind','video')
    if kind not in ('video','train'):raise Http404
    form=JobForm(request.POST or None,request.FILES or None,kind=kind)
    if request.method=='POST' and form.is_valid():
        obj=form.save(commit=False);obj.owner=request.user;obj.kind=kind;obj.config=configuration().as_config();obj.config['epochs']=20;obj.save();audit(request.user,'job.create',obj)
        messages.success(request,'작업이 대기열에 등록되었습니다. 작업 처리 명령으로 실행하세요.')
        return redirect('/jobs/?kind='+kind)
    return render(request,'detection/jobs.html',{'form':form,'kind':kind,'jobs':own(Job.objects.filter(kind=kind),request.user)[:100]})
@feature('jobs',staff=True)
@require_POST
def cancel_job(request,pk):
    obj=get_object_or_404(Job,pk=pk,owner=request.user)
    if obj.status=='queued':obj.status='cancelled';obj.save(update_fields=['status']);audit(request.user,'job.cancel',obj)
    else:messages.error(request,'대기 중인 작업만 취소할 수 있습니다.')
    return redirect('/jobs/?kind='+obj.kind)
@feature('jobs',staff=True)
def download(request,pk):
    obj=get_object_or_404(Job,pk=pk,owner=request.user)
    if obj.status!='done' or not obj.result_file:raise Http404
    file=obj.trainedmodel.artifact if obj.kind=='train' else obj.result_file
    return FileResponse(file.open('rb'),as_attachment=True,filename=f'guardfall2-job-{pk}.csv' if obj.kind=='video' else f'guardfall2-model-{pk}.zip')
@feature('models',staff=True)
def models(request):
    from django.contrib.auth import get_user_model
    return render(request,'detection/models.html',{'models':own(TrainedModel.objects.all(),request.user).prefetch_related('allowed_users'),'users':get_user_model().objects.filter(is_active=True)})
@feature('models',staff=True)
@require_POST
@transaction.atomic
def activate(request,pk):
    obj=get_object_or_404(TrainedModel.objects.select_for_update(),pk=pk,owner=request.user)
    from .ml import predict_record
    from .models import default_config
    row={f'{j}_{s}':.5 if s!='vr' else 1 for j in ['left_shoulder','right_shoulder','left_knee','right_knee'] for s in ['x','y','v','vr']}
    try:predict_record(obj,row,default_config())
    except Exception:
        messages.error(request,'모델 검증에 실패했습니다. ML 설치와 모델 파일을 확인하세요.');return redirect('/models/')
    obj.active=True;obj.save(update_fields=['active']);audit(request.user,'model.activate',obj)
    messages.success(request,'모델이 검증되어 실시간 감지에 사용할 수 있습니다.')
    return redirect('/models/')
@feature('events')
def events(request):
    qs=FallEvent.objects.filter(session__owner=request.user).select_related('session','frame')
    status=request.GET.get('status','')
    if status:qs=qs.filter(status=status)
    return render(request,'detection/events.html',{'page':Paginator(qs,30).get_page(request.GET.get('page')),'status':status,'total':qs.count()})
@feature('events')
@require_POST
def review_event(request,pk):
    obj=get_object_or_404(FallEvent,pk=pk,session__owner=request.user)
    status=request.POST.get('status')
    if status not in ['confirmed','false_alarm']:return HttpResponse('잘못된 상태',status=400)
    obj.status=status;obj.note=request.POST.get('note','')[:2000];obj.reviewed_at=timezone.now();obj.save();audit(request.user,'event.review',obj)
    return redirect('/events/')
@feature('events')
def export_events(request):
    from openpyxl import Workbook
    from io import BytesIO
    wb=Workbook();ws=wb.active;ws.title='낙상 기록';ws.append(['번호','세션','발생시간','상태','메모'])
    for e in FallEvent.objects.filter(session__owner=request.user).select_related('session'):
        values=[e.pk,e.session.name,timezone.localtime(e.created_at).isoformat(),e.get_status_display(),e.note]
        for i,v in enumerate(values):
            if isinstance(v,str) and v.startswith(('=','+','-','@')):values[i]="'"+v
        ws.append(values)
    b=BytesIO();wb.save(b)
    response=HttpResponse(b.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');response['Content-Disposition']='attachment; filename="guardfall2-events.xlsx"';return response
@feature('settings',staff=True)
def settings_view(request):
    form=SettingsForm(request.POST or None,instance=configuration())
    if request.method=='POST' and form.is_valid():
        obj=form.save();audit(request.user,'settings.update',obj);messages.success(request,'설정이 저장되었습니다. 새 감지 세션부터 적용됩니다.');return redirect('/settings/')
    return render(request,'detection/settings.html',{'form':form})
@feature('notifications')
def notifications(request):
    cfg,_=NotificationSettings.objects.get_or_create(owner=request.user)
    form=NotificationForm(request.POST or None,initial={'enabled':cfg.enabled})
    if request.method=='POST' and form.is_valid():
        from .notifications import encrypt
        try:
            if form.cleaned_data['token']:cfg.token_ciphertext=encrypt(form.cleaned_data['token'])
            if form.cleaned_data['chat_id']:cfg.chat_id_ciphertext=encrypt(form.cleaned_data['chat_id'])
            if form.cleaned_data['enabled'] and not(cfg.token_ciphertext and cfg.chat_id_ciphertext):raise ValueError('봇 토큰과 Chat ID가 필요합니다.')
            cfg.enabled=form.cleaned_data['enabled'];cfg.save();audit(request.user,'notifications.update',cfg);messages.success(request,'알림 설정이 저장되었습니다.');return redirect('/notifications/')
        except ValueError as exc:form.add_error(None,str(exc))
    return render(request,'detection/notifications.html',{'form':form,'configured':bool(cfg.token_ciphertext and cfg.chat_id_ciphertext)})

@feature('monitor')
@require_POST
def image_frame(request,pk):
    import base64,binascii
    session=get_object_or_404(MonitoringSession,pk=pk,owner=request.user)
    if not session.active:return JsonResponse({'error':'종료된 감지 세션입니다.'},status=409)
    try:
        data=json.loads(request.body)
        if not isinstance(data,dict) or not isinstance(data.get('image'),str):raise ValueError('이미지 요청이 필요합니다.')
        sequence=data.get('sequence')
        from datetime import timedelta
        if isinstance(sequence,bool) or not isinstance(sequence,int) or not 0<=sequence<=2147483647:raise ValueError('유효한 프레임 번호가 필요합니다.')
        if sequence<=session.last_sequence:raise ValidationError('중복 또는 역순 프레임입니다.',code='conflict')
        if timezone.now()-session.started_at>timedelta(hours=8):raise ValidationError('감지 세션이 만료되었습니다.',code='conflict')
        if len(data['image'])>2*1024*1024:raise ValueError('이미지 요청이 너무 큽니다.')
        raw=base64.b64decode(data['image'],validate=True)
        from .ml import extract_image
        joints=extract_image(raw,session.config)
        pose,event=ingest_frame(request.user,pk,data.get('sequence'),joints)
    except (ValueError,ValidationError,binascii.Error,KeyError,TypeError) as exc:
        return JsonResponse({'error':str(exc)},status=409 if getattr(exc,'code',None)=='conflict' else 400)
    except RuntimeError as exc:
        return JsonResponse({'error':str(exc)},status=503)
    return JsonResponse({'prediction':pose.prediction,'probability':pose.probability,'event':event.pk if event else None})

@feature('models',staff=True)
@require_POST
def assign_model(request,pk):
    from django.contrib.auth import get_user_model
    obj=get_object_or_404(TrainedModel,pk=pk,owner=request.user)
    users=get_user_model().objects.filter(pk__in=request.POST.getlist('users'),is_active=True)
    obj.allowed_users.set(users)
    audit(request.user,'model.assign',obj)
    messages.success(request,'모델 사용자를 지정했습니다.')
    return redirect('/models/')

@feature('models',staff=True)
@require_POST
def deactivate_model(request,pk):
    obj=get_object_or_404(TrainedModel,pk=pk,owner=request.user)
    obj.active=False;obj.save(update_fields=['active']);audit(request.user,'model.deactivate',obj)
    messages.success(request,'모델을 비활성화했습니다. 해당 모델의 감지 세션은 새 프레임을 받지 않습니다.')
    return redirect('/models/')
