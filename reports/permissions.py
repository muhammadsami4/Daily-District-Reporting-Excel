"""Role-based access: superusers (admins) and members of the 'Editors' group may create or
revise reports; every other logged-in user is read-only."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

EDITOR_GROUP = "Editors"


def is_editor(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.groups.filter(name=EDITOR_GROUP).exists()))


def editor_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_editor(request.user):
            raise PermissionDenied("Your account is read-only. Ask an administrator for the Editors role.")
        return view(request, *args, **kwargs)
    return login_required(wrapper)


def superuser_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Administrators only.")
        return view(request, *args, **kwargs)
    return login_required(wrapper)
