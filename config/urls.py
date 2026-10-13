from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import path
from apps.core.views import dashboard
from apps.detection import views as v
urlpatterns=[path('',dashboard,name='home'),path('accounts/login/',auth.LoginView.as_view(),name='login'),path('accounts/logout/',auth.LogoutView.as_view(),name='logout'),path('accounts/password/',auth.PasswordChangeView.as_view(template_name='registration/password_change.html',success_url='/'),name='password_change'),path('admin/',admin.site.urls),path('monitor/',v.monitor),path('monitor/start/',v.start),path('monitor/<int:pk>/image/',v.image_frame),path('monitor/<int:pk>/frame/',v.frame),path('monitor/<int:pk>/stop/',v.stop),path('jobs/',v.jobs),path('jobs/<int:pk>/cancel/',v.cancel_job),path('jobs/<int:pk>/download/',v.download),path('models/',v.models),path('models/<int:pk>/activate/',v.activate),path('models/<int:pk>/assign/',v.assign_model),path('models/<int:pk>/deactivate/',v.deactivate_model),path('events/',v.events),path('events/export/',v.export_events),path('events/<int:pk>/review/',v.review_event),path('settings/',v.settings_view),path('notifications/',v.notifications)]
