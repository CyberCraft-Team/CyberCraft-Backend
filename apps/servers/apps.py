from django.apps import AppConfig


class ServersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.servers"

    _atexit_registered = False

    def ready(self):
        import os
        import sys

        # Django dev server (runserver) ishlatilganda, u 2 ta jarayon ochadi.
        # Bizga faqat asosiy ishchi jarayon (RUN_MAIN=true) kerak.
        # Agar runserver bo'lmasa (masalan: shell, migrate yoki production), odatdagidek ishlayveradi.
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true':
            return

        if not ServersConfig._atexit_registered:
            import atexit
            from .server_manager import MinecraftServerManager

            # Backend o'chirilishidan oldin barcha serverlarni to'xtatish
            atexit.register(MinecraftServerManager.stop_all_servers)
            ServersConfig._atexit_registered = True
