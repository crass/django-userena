from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.admin.sites import NotRegistered
from django.utils.importlib import import_module
from userena.utils import get_profile_model
from . import settings

def get_class(path):
    if path:
        module_name, attr_name = path.rsplit('.', 1)
        module = import_module(module_name)
        return getattr(module, attr_name)
    else:
        return None

UserenaUserAdmin = get_class(settings.USERENA_USERADMIN)
if UserenaUserAdmin:
    try:
        admin.site.unregister(User)
    except NotRegistered:
        pass
    admin.site.register(User, UserenaUserAdmin)

ProfileAdmin = get_class(settings.USERENA_PROFILEADMIN)
if ProfileAdmin:
    profile_model = get_profile_model()
    try:
        admin.site.unregister(profile_model)
    except NotRegistered:
        pass
    admin.site.register(profile_model, ProfileAdmin)
