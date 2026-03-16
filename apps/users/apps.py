# apps/users/apps.py
from django.apps import AppConfig

class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.users'  # Path must match your folder structure
    label = 'users'       # This is the nickname Django uses for AUTH_USER_MODEL
    
  