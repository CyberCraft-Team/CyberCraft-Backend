# CyberCraft Backend

CyberCraft Minecraft server management API — Django REST Framework bilan qurilgan.

## Texnologiyalar

- Python 3.12+ (Django 6 talabi)
- Django + Django REST Framework
- Daphne (ASGI)
- Channels (WebSocket)
- SQLite (dev) / PostgreSQL (prod)

## O'rnatish

```bash
# Virtual environment yaratish
python -m venv env
source env/bin/activate  # Linux/Mac
env\Scripts\activate     # Windows

# Paketlarni o'rnatish
pip install -r requirements.txt

# .env faylini yaratish
cp .env.example .env
# .env faylini tahrirlash va SECRET_KEY qiymatini o'zgartirish

# Migratsiya
python manage.py migrate

# Serverni ishga tushirish
python manage.py runserver
```

## Production

Production sozlamalari, xavfsizlik tekshiruvlari va ishga tushirish tartibi uchun
[deploy/README.md](deploy/README.md) ga qarang. Production HTTPS sozlamalari
standart holatda yoqilgan; HTTP smoke-test uchun `USE_SSL=0` aniq berilishi kerak.

## Apps

- `accounts` — Foydalanuvchi akkauntlari va autentifikatsiya
- `launcher` — Launcher autentifikatsiya
- `servers` — Server boshqaruvi
- `news` — Yangiliklar
- `voting` — Ovoz berish tizimi
- `rewards` — Mukofotlar
- `auditlog` — Audit log
- `notifications` — Bildirishnomalar
