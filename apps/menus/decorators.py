from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from .models import Menu,permitted
def feature(code,staff=False):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            if staff and not request.user.is_staff:raise PermissionDenied
            menu=Menu.objects.filter(code=code).first()
            if not menu or not permitted(request.user,menu):raise PermissionDenied
            return view(request,*args,**kwargs)
        return wrapped
    return decorator
