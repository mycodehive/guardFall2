from .models import Menu,permitted
def navigation(request):
    if not request.user.is_authenticated:return {'navigation':[]}
    menus=list(Menu.objects.select_related('parent').prefetch_related('groups'))
    def nodes(parent=None):
        return [{'menu':m,'children':nodes(m.pk),'active':bool(m.url and request.path.startswith(m.url))} for m in menus if m.parent_id==parent and permitted(request.user,m)]
    return {'navigation':nodes()}
