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

        # Schema-level commands run before the tables are guaranteed to be
        # there, and none of them serve traffic, so there is nothing to
        # reconcile or monitor for them.
        offline_commands = {
            "migrate",
            "makemigrations",
            "collectstatic",
            "test",
            "showmigrations",
            "loaddata",
            "dumpdata",
        }
        if len(sys.argv) > 1 and sys.argv[1] in offline_commands:
            return

        if not ServersConfig._atexit_registered:
            import atexit
            from .server_manager import MinecraftServerManager

            # Backend o'chirilishidan oldin barcha serverlarni to'xtatish
            atexit.register(MinecraftServerManager.stop_all_servers)

            # Starts the monitor, whose first job is to reconcile the
            # statuses a killed or crashed backend left behind. That query
            # deliberately runs on the monitor thread rather than here:
            # Django warns about touching the database from ready().
            MinecraftServerManager.start_monitoring()
            
            ServersConfig._atexit_registered = True
