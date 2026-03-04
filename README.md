# CyberCraft Backend

CyberCraft Minecraft server management API — Django REST Framework bilan qurilgan.

## Texnologiyalar

- Python 3.10+
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

## Apps

- `accounts` — Foydalanuvchi akkauntlari va autentifikatsiya
- `launcher` — Launcher autentifikatsiya
- `servers` — Server boshqaruvi
- `news` — Yangiliklar
- `voting` — Ovoz berish tizimi
- `rewards` — Mukofotlar
- `auditlog` — Audit log
- `notifications` — Bildirishnomalar
