from django.contrib import admin
from .models import AuditLog
@admin.register(AuditLog)
class AuditAdmin(admin.ModelAdmin):
    list_display=['actor','action','object_type','object_id','created_at']
    readonly_fields=['actor','action','object_type','object_id','created_at']
    def has_add_permission(self,request):return False
    def has_change_permission(self,request,obj=None):return False
    def has_delete_permission(self,request,obj=None):return False
