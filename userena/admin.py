from django.contrib import admin
from django.contrib.auth.models import User
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
    admin.site.unregister(User)
    admin.site.register(User, UserenaUserAdmin)

ProfileAdmin = get_class(settings.USERENA_PROFILEADMIN)
if ProfileAdmin:
    profile_model = get_profile_model()
    admin.site.unregister(profile_model)
    admin.site.register(profile_model, ProfileAdmin)
