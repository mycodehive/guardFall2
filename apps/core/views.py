from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Q
from apps.menus.models import Menu,permitted
from apps.detection.models import Job,MonitoringSession,FallEvent,TrainedModel
@login_required
def dashboard(request):
    u=request.user
    def access(code):
        menu=Menu.objects.filter(code=code).first()
        return bool(menu and permitted(u,menu))
    context={'session_count':MonitoringSession.objects.filter(owner=u,active=True).count() if access('monitor') else 0,'event_count':FallEvent.objects.filter(session__owner=u,status='new').count() if access('events') else 0,'model_count':TrainedModel.objects.filter(Q(owner=u)|Q(allowed_users=u),active=True).distinct().count() if access('monitor') else 0,'job_count':Job.objects.filter(owner=u,status__in=['queued','running']).count() if access('jobs') and u.is_staff else 0,'recent_events':FallEvent.objects.filter(session__owner=u).select_related('session')[:5] if access('events') else [],'can_monitor':access('monitor'),'can_events':access('events'),'can_jobs':access('jobs') and u.is_staff}
    return render(request,'core/dashboard.html',context)
