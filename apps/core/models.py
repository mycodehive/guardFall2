from django.db import models
from django.conf import settings
class AuditLog(models.Model):
    actor=models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True)
    action=models.CharField(max_length=100)
    object_type=models.CharField(max_length=100)
    object_id=models.CharField(max_length=100)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering=['-created_at']
def audit(user,action,obj):
    AuditLog.objects.create(actor=user,action=action,object_type=obj.__class__.__name__,object_id=str(obj.pk))
