from .permissions import is_editor


def permissions(request):
    return {"can_edit": is_editor(request.user)}
