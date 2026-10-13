from django.db import models
from django.core.exceptions import ValidationError
class Menu(models.Model):
    code=models.SlugField(unique=True)
    title=models.CharField(max_length=80)
    url=models.CharField(max_length=200,blank=True)
    parent=models.ForeignKey('self',on_delete=models.CASCADE,null=True,blank=True,related_name='children')
    order=models.PositiveIntegerField(default=0)
    active=models.BooleanField(default=True)
    staff_only=models.BooleanField(default=False)
    groups=models.ManyToManyField('auth.Group',blank=True)
    class Meta:
        ordering=['order','pk']
    def __str__(self): return self.title
    def clean(self):
        seen={self.pk} if self.pk else set()
        parent=self.parent if self.parent_id else None
        depth=1
        while parent:
            if parent.pk in seen: raise ValidationError('메뉴 순환 참조는 허용되지 않습니다.')
            seen.add(parent.pk); depth+=1
            if depth>3: raise ValidationError('메뉴는 3단계까지만 구성할 수 있습니다.')
            parent=parent.parent
        if self.url and (not self.url.startswith('/') or self.url.startswith('//')):
            raise ValidationError('메뉴 URL은 내부 경로여야 합니다.')
        if self.pk:
            def height(node):
                return 1+max((height(c) for c in node.children.all()),default=0)
            if depth+height(self)-1>3: raise ValidationError('하위 메뉴 포함 3단계를 초과합니다.')
def permitted(user,menu):
    if not user.is_authenticated:return False
    seen=set()
    while menu:
        if menu.pk in seen:return False
        seen.add(menu.pk)
        if not menu.active or (menu.staff_only and not user.is_staff):return False
        if not user.is_superuser and menu.groups.exists() and not menu.groups.filter(pk__in=user.groups.values('pk')).exists():return False
        menu=menu.parent
    return True
