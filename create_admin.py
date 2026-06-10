import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import User

username = 'admin'
password = 'adminpassword123'

user = User.objects.filter(username=username).first()
if user:
    user.set_password(password)
    user.is_staff = True
    user.is_superuser = True
    user.is_active = True
    user.save()
    print(f"User '{username}' paroli yangilandi.")
else:
    User.objects.create_superuser(username=username, password=password, email='admin@cybercraft.uz')
    print(f"Yangi superuser '{username}' yaratildi. Parol: {password}")
