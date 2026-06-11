#!/bin/bash
# CyberCraft — Build/Deploy Script
# Production da ishga tushirilganda collectstatic, migrate, va superuser yaratadi.
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate

# Superuser yaratish — env dan olinadi (hardcoded emas!)
python manage.py shell -c "
from django.contrib.auth import get_user_model
import os

User = get_user_model()
username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

if not username or not password:
    print('DJANGO_SUPERUSER_USERNAME va DJANGO_SUPERUSER_PASSWORD env da topilmadi. Superuser yaratilmadi.')
elif User.objects.filter(username=username).exists():
    print(f'Superuser \"{username}\" allaqachon mavjud.')
else:
    User.objects.create_superuser(username, '', password)
    print(f'Superuser \"{username}\" yaratildi!')
"
