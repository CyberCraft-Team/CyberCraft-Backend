set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input

python manage.py migrate

# Superuser yaratish (agar mavjud bo'lmasa)
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='lxz_404').exists():
    User.objects.create_superuser('lxz_404', '', 'Pashol_2321235')
    print('Superuser yaratildi!')
else:
    print('Superuser allaqachon mavjud.')
"
