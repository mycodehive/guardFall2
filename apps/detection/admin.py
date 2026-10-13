# Sensitive domain data is intentionally managed through owner-scoped application views.
from django.contrib import admin
from .models import DetectionSettings
@admin.register(DetectionSettings)
class DetectionSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self,request):return not DetectionSettings.objects.exists() and request.user.is_superuser
    def has_change_permission(self,request,obj=None):return request.user.is_superuser
    def has_delete_permission(self,request,obj=None):return False
