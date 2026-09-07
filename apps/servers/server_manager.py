import os
import subprocess
import threading
import re
import shutil
import zipfile
import glob as glob_module
import platform
import json
import time
from datetime import datetime

from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def ensure_backend_authlib_injector(dest_path):
    """Ensure authlib-injector jar exists on the backend filesystem, downloading it if missing."""
    if os.path.exists(dest_path):
        return
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    import requests
    url = "https://github.com/yushijinhun/authlib-injector/releases/download/v1.2.7/authlib-injector-1.2.7.jar"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            with open(dest_path, "wb") as f:
                f.write(response.content)
    except Exception as e:
        print(f"Failed to download authlib-injector on backend: {e}")


class MinecraftServerManager:
    _processes = {}
    _log_threads = {}
    _is_shutting_down = False
    _online_players = {}
    _monitor_thread = None
    # Servers whose JVM outlived the backend that started it. There is no
    # Popen handle for these -- no stdin, no log pipe -- but the pid is still
    # ours to watch and to stop.
    _adopted = {}

    # The statuses that claim a server is alive. Only these can go stale when
    # the backend dies; "stopped" and "error" are already terminal. Kept as
    # literals because the model cannot be imported at class-definition time.
    ACTIVE_STATUSES = ("starting", "running", "stopping")

    @classmethod
    def _pid_alive_for(cls, server_id, pid):
        """True when `pid` is up and really is this server's process."""
        if not pid:
            return False
        try:
            import psutil

            proc = psutil.Process(int(pid))
            if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE:
                return False
            # Pids get recycled, so liveness on its own would happily adopt
            # whatever unrelated program inherited the number.
            return cls._is_server_process(str(server_id), int(pid), proc)
        except Exception:
            return False

    @classmethod
    def _terminate_pid_tree(cls, pid, timeout=15):
        """
        Stop a process this backend holds no Popen handle for.

        Servers launched through run.bat/run.sh sit under a shell, so the
        recorded pid is the shell's; killing only that would orphan the JVM
        beneath it, which keeps the port bound and makes the next start fail.
        """
        try:
            import psutil

            proc = psutil.Process(int(pid))
        except Exception:
            return False

        try:
            victims = proc.children(recursive=True)
        except Exception:
            victims = []
        victims.append(proc)

        for victim in victims:
            try:
                victim.terminate()
            except Exception:
                pass

        try:
            _, alive = psutil.wait_procs(victims, timeout=timeout)
        except Exception:
            alive = []
        for victim in alive:
            try:
                victim.kill()
            except Exception:
                pass
        return True

    @classmethod
    def _collect_stats(cls, root, cache):
        """
        CPU and memory for the whole process tree under `root`.

        The recorded pid is usually the shell running run.bat, and the JVM
        doing all the work is its child -- measuring only the root reported
        a busy server as 0% CPU and a couple of megabytes.

        `cache` maps pid -> psutil.Process and is carried between cycles on
        purpose: cpu_percent(interval=None) reports the change since the
        previous call *on the same object*, so building fresh ones every
        time would always read zero.
        """
        try:
            members = [root] + root.children(recursive=True)
        except Exception:
            members = [root]

        live = {}
        cpu = 0.0
        memory_bytes = 0
        for member in members:
            tracked = cache.get(member.pid, member)
            try:
                cpu += tracked.cpu_percent(interval=None)
                memory_bytes += tracked.memory_info().rss
            except Exception:
                # Gone or unreadable between listing and measuring; it just
                # drops out of the cache.
                continue
            live[member.pid] = tracked

        cache.clear()
        cache.update(live)
        return cpu, memory_bytes / (1024 * 1024)

    @classmethod
    def _mark_stopped(cls, server, reason):
        """Record that a server the backend was tracking is no longer up."""
        from .models import MinecraftServer, ServerLog

        server_id = str(server.id)
        # Conditional update: if the log reader already finalised this server
        # we neither race it nor write a second log line about it.
        updated = (
            MinecraftServer.objects.filter(pk=server.pk)
            .exclude(status=MinecraftServer.Status.STOPPED)
            .update(
                status=MinecraftServer.Status.STOPPED,
                pid=None,
                current_players=0,
            )
        )
        if not updated:
            return False

        cls._processes.pop(server_id, None)
        cls._adopted.pop(server_id, None)
        cls._online_players.pop(server_id, None)

        try:
            ServerLog.objects.create(
                server=server,
                level="warn",
                message=f"Server to'xtagan deb belgilandi: {reason}",
            )
        except Exception:
            pass

        channel_layer = get_channel_layer()
        if channel_layer:
            try:
                async_to_sync(channel_layer.group_send)(
                    f"server_{server_id}",
                    {"type": "server_status", "status": "stopped"},
                )
                cls.broadcast_status_update()
            except Exception:
                pass
        return True

    @classmethod
    def reconcile_statuses(cls):
        """
        Line the stored statuses back up with what is actually on the machine.

        A server's status is only ever written from inside this process:
        start_server sets "starting", the log reader flips it to "running"
        and, in its finally block, to "stopped". None of that survives the
        backend being killed, crashing, or reloaded -- whatever the row said
        at that moment stays frozen there, so the panel goes on reporting a
        server as starting or running with no JVM behind it. Run at startup
        so a fresh boot never inherits a stale claim.
        """
        from .models import MinecraftServer, ServerLog

        repaired = []

        # An interrupted install has no pid of its own to check, so it can
        # neither be resumed nor verified -- only reported.
        for server in MinecraftServer.objects.filter(
            status=MinecraftServer.Status.INSTALLING
        ):
            MinecraftServer.objects.filter(pk=server.pk).update(
                status=MinecraftServer.Status.ERROR, pid=None, current_players=0
            )
            repaired.append((server, "install yarim yo'lda uzilib qolgan"))

        for server in MinecraftServer.objects.filter(
            status__in=cls.ACTIVE_STATUSES
        ):
            server_id = str(server.id)
            previous = server.status

            if cls._pid_alive_for(server_id, server.pid):
                # It outlived the restart. Its console is out of reach now,
                # so adopt the pid: stop_server can still reach it and the
                # monitor keeps watching it.
                cls._adopted[server_id] = server.pid
                # Joins and leaves were counted off the console this backend
                # no longer has, so the old figure can never be corrected.
                # Reset it rather than freeze a number that stopped meaning
                # anything the moment the previous backend died.
                cls._online_players[server_id] = set()
                MinecraftServer.objects.filter(pk=server.pk).update(
                    status=MinecraftServer.Status.RUNNING, current_players=0
                )
                continue

            MinecraftServer.objects.filter(pk=server.pk).update(
                status=MinecraftServer.Status.STOPPED, pid=None, current_players=0
            )
            cls._online_players.pop(server_id, None)
            cls._adopted.pop(server_id, None)
            repaired.append(
                (server, f"'{previous}' holatida qolib ketgan, jarayoni topilmadi")
            )

        for server, reason in repaired:
            try:
                ServerLog.objects.create(
                    server=server,
                    level="warn",
                    message=f"Backend qayta ishga tushdi: {reason}. Holat tiklandi.",
                )
            except Exception:
                pass

        if repaired:
            try:
                cls.broadcast_status_update()
            except Exception:
                pass

        return len(repaired)

    @classmethod
    def get_servers_root(cls):
        servers_root = getattr(settings, "SERVERS_ROOT", None)
        if not servers_root:
            servers_root = os.path.join(settings.BASE_DIR, "servers")
        os.makedirs(servers_root, exist_ok=True)
        return servers_root

    @classmethod
    def get_server_path(cls, server):
        return os.path.join(cls.get_servers_root(), str(server.id))

    @classmethod
    def get_available_versions(cls):
        from .models import ServerJar

        versions = (
            ServerJar.objects.filter(is_active=True)
            .values_list("minecraft_version", flat=True)
            .distinct()
            .order_by("-minecraft_version")
        )

        return [{"id": v, "type": "release"} for v in versions]

    @classmethod
    def setup_server_from_jar(cls, server):

        from .models import MinecraftServer

        if not server.server_jar:
            raise Exception("Server JAR tanlanmagan")

        server_path = cls.get_server_path(server)
        os.makedirs(server_path, exist_ok=True)

        server_type_config = server.server_type
        jar_file_name = (
            server_type_config.jar_file_name if server_type_config else "server.jar"
        )
        jar_path = os.path.join(server_path, jar_file_name)

        try:
            source_jar_path = server.server_jar.jar_file.path

            if not os.path.exists(source_jar_path):
                raise Exception(f"JAR fayl topilmadi: {source_jar_path}")

            shutil.copy2(source_jar_path, jar_path)

            eula_path = os.path.join(server_path, "eula.txt")
            with open(eula_path, "w") as f:
                f.write("eula=true\n")

            server.jar_file = jar_file_name
            server.server_path = server_path

            if server_type_config and not server_type_config.is_installer:
                server.is_installed = True

            server.save()

            cls.create_server_properties(server)

            return True

        except Exception as e:
            print(f"Error setting up server from JAR: {e}")
            raise e

    @classmethod
    def _hoist_single_root_directory(cls, server_path, max_depth=6):
        """ZIP bitta tashqi papkada bo'lsa (masalan CyberCraft/), ichkariga ko'chiradi."""
        for _ in range(max_depth):
            entries = [
                e
                for e in os.listdir(server_path)
                if e != "__MACOSX"
                and not e.startswith(".")
                and e != "Thumbs.db"
            ]
            if len(entries) != 1:
                return
            only = os.path.join(server_path, entries[0])
            if not os.path.isdir(only):
                return
            for name in os.listdir(only):
                dest = os.path.join(server_path, name)
                if os.path.exists(dest):
                    return
            for name in os.listdir(only):
                if name == "__MACOSX":
                    continue
                shutil.move(os.path.join(only, name), os.path.join(server_path, name))
            try:
                os.rmdir(only)
            except OSError:
                return

    @classmethod
    def _detect_primary_jar(cls, server_path):
        if not os.path.isdir(server_path):
            return ""
        jars = [f for f in os.listdir(server_path) if f.lower().endswith(".jar")]
        if not jars:
            return ""
        priority = [
            "fabric-server-launch.jar",
            "server.jar",
            "paper.jar",
            "purpur.jar",
            "spigot.jar",
        ]
        lower = {j.lower(): j for j in jars}
        for p in priority:
            if p in lower:
                return lower[p]
        non_install = [j for j in jars if "installer" not in j.lower()]
        if len(non_install) == 1:
            return non_install[0]
        if len(jars) == 1:
            return jars[0]
        return ""

    @classmethod
    def _merge_server_properties_file(cls, properties_path, updates):
        """Mavjud server.properties qatorlarini yangilaydi, yo'q bo'lsa qo'shadi."""
        lines = []
        if os.path.exists(properties_path):
            with open(properties_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

        present = set()
        out = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    out.append(f"{key}={updates[key]}\n")
                    present.add(key)
                    continue
            out.append(line)
        for key, value in updates.items():
            if key not in present:
                out.append(f"{key}={value}\n")

        with open(properties_path, "w", encoding="utf-8") as f:
            f.writelines(out)

    @classmethod
    def _is_managed_jvm_arg(cls, arg):
        """True for the JVM arguments this panel owns and rewrites each start."""
        if arg.startswith("-javaagent:") and "authlib-injector" in arg:
            return True
        return arg.startswith("-Dcybercraft.")

    @classmethod
    def _patch_script_content(cls, content, jvm_args):
        if isinstance(jvm_args, str):
            jvm_args = [jvm_args]
        injected = " ".join(jvm_args)
        cleaned_content = re.sub(r"-javaagent:[^\s]*authlib-injector[^\s]*", "", content)
        cleaned_content = re.sub(r"-Dcybercraft\.[^\s]*", "", cleaned_content)
        lines = cleaned_content.splitlines()
        new_lines = []
        for line in lines:
            stripped = line.strip().lower()

            # Forge's run.bat ends in "pause" so a human who double-clicked it
            # can read the output. Under the panel nobody ever presses a key:
            # the shell sat there for ever after the JVM died, still holding a
            # live pid in the server directory, so the server went on being
            # reported as running long after it had crashed.
            if stripped == "pause" or stripped.startswith("pause "):
                new_lines.append("rem pause  (panel tomonidan olib tashlandi)")
                continue

            if (
                not stripped 
                or stripped.startswith("#") 
                or stripped.startswith("rem") 
                or stripped.startswith("echo")
                or stripped.startswith("set ")
                or ("=" in stripped.split()[0] if stripped.split() else False)
            ):
                new_lines.append(line)
                continue
            
            match = re.search(r"^(\s*(?:exec\s+|start\s+|@\s*)?)(\bjava\b)", line, flags=re.IGNORECASE)
            if match:
                prefix = match.group(1)
                line = line[:match.start()] + prefix + f"java {injected}" + line[match.end():]
            new_lines.append(line)
        return "\n".join(new_lines)

    @classmethod
    def setup_server_from_zip(cls, server, zip_file):
        if not zip_file:
            raise Exception("ZIP fayl topilmadi")

        server_path = cls.get_server_path(server)
        os.makedirs(server_path, exist_ok=True)

        try:
            if hasattr(zip_file, "seek"):
                try:
                    zip_file.seek(0)
                except (AttributeError, OSError):
                    pass

            with zipfile.ZipFile(zip_file, "r") as archive:
                corrupt = archive.testzip()
                if corrupt:
                    raise Exception(
                        f"ZIP buzilgan yoki noto'g'ri (fayl: {corrupt}). Qayta yuklang."
                    )
                server_path_abs = os.path.abspath(server_path)
                for member in archive.infolist():
                    member_path = os.path.abspath(
                        os.path.normpath(os.path.join(server_path_abs, member.filename))
                    )
                    if os.path.commonpath([server_path_abs, member_path]) != server_path_abs:
                        raise Exception("ZIP ichida xavfli fayl yo'li aniqlandi")

                archive.extractall(server_path)

            cls._hoist_single_root_directory(server_path)

            eula_path = os.path.join(server_path, "eula.txt")
            if not os.path.exists(eula_path):
                with open(eula_path, "w", encoding="utf-8") as f:
                    f.write("eula=true\n")

            jar_name = cls._detect_primary_jar(server_path)

            server.server_path = server_path
            server.jar_file = jar_name
            server.is_installed = True
            server.save()

            cls.create_server_properties(server)
            cls.sync_mods_from_disk(server)
            return True
        except zipfile.BadZipFile as e:
            print(f"Error setting up server from ZIP: {e}")
            raise Exception("ZIP fayl ochilmadi — haqiqiy .zip ekanini tekshiring") from e
        except Exception as e:
            print(f"Error setting up server from ZIP: {e}")
            raise e

    @classmethod
    def sync_mods_from_disk(cls, server):
        """Bring the ServerMod rows in line with the jars in <server>/mods.

        The panel's mod list reads the database, but a server uploaded as a
        ZIP arrives with its jars already on disk and no rows to describe
        them -- so the list showed nothing while 70-odd mods sat in the
        folder. Nothing is copied into MEDIA_ROOT: the server directory is
        the one copy that matters, and duplicating a modpack there would
        both waste the space and let the two copies drift apart.
        """
        import hashlib

        from .models import ServerMod

        def sha256_of(path):
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()

        server_path = cls.get_server_path(server)
        mods_dir = os.path.join(server_path, "mods")
        if not os.path.isdir(mods_dir):
            return 0

        on_disk = {}
        for file_name in os.listdir(mods_dir):
            if not file_name.lower().endswith(".jar"):
                continue
            full_path = os.path.join(mods_dir, file_name)
            if os.path.isfile(full_path):
                on_disk[file_name] = os.path.getsize(full_path)

        existing = {mod.file_name: mod for mod in server.mods.all()}

        # A jar that is gone from the folder is gone from the server. Rows
        # carrying an uploaded file are left alone -- those were added
        # through the panel and own their copy in MEDIA_ROOT.
        for file_name, mod in existing.items():
            if file_name not in on_disk and not mod.file:
                mod.delete()

        # Hashing is what makes this loop cost anything, so it only runs for
        # a jar the database has not seen at this size: the launcher checks
        # the hash before re-downloading a mod it already has.
        changed = 0
        for file_name, size in sorted(on_disk.items()):
            mod = existing.get(file_name)
            full_path = os.path.join(mods_dir, file_name)

            if mod is None:
                ServerMod.objects.create(
                    server=server,
                    name=os.path.splitext(file_name)[0],
                    file_name=file_name,
                    file_size=size,
                    sha256_hash=sha256_of(full_path),
                    status=ServerMod.ModStatus.ENABLED,
                )
                changed += 1
            elif not mod.file and (mod.file_size != size or not mod.sha256_hash):
                mod.file_size = size
                mod.sha256_hash = sha256_of(full_path)
                mod.save(update_fields=["file_size", "sha256_hash"])
                changed += 1

        return changed

    @classmethod
    def create_server_properties(cls, server):
        server_path = cls.get_server_path(server)
        properties_path = os.path.join(server_path, "server.properties")

        updates = {
            "server-port": str(server.port),
            "max-players": str(server.max_players),
            "motd": server.motd,
            "gamemode": server.gamemode,
            "difficulty": server.difficulty,
            "pvp": str(server.pvp).lower(),
            "online-mode": str(server.online_mode).lower(),
            "white-list": str(server.white_list).lower(),
            "spawn-protection": str(server.spawn_protection),
            "view-distance": str(server.view_distance),
            "enable-command-block": "true",
        }

        if os.path.exists(properties_path):
            cls._merge_server_properties_file(properties_path, updates)
            return

        properties = f"""#Minecraft server properties
#Generated by CyberCraft
server-port={server.port}
max-players={server.max_players}
motd={server.motd}
gamemode={server.gamemode}
difficulty={server.difficulty}
pvp={str(server.pvp).lower()}
online-mode={str(server.online_mode).lower()}
white-list={str(server.white_list).lower()}
spawn-protection={server.spawn_protection}
view-distance={server.view_distance}
enable-command-block=true
"""

        with open(properties_path, "w", encoding="utf-8") as f:
            f.write(properties)

    @classmethod
    def install_server(cls, server):
        """Installer turdagi serverlarni install qiladi (Forge, NeoForge va h.k.)"""
        from .models import MinecraftServer, ServerLog

        server_type_config = server.server_type
        if not server_type_config or not server_type_config.is_installer:
            raise Exception("Bu server turi install talab qilmaydi")

        if server.is_installed:
            raise Exception("Server allaqachon install qilingan")

        server_path = cls.get_server_path(server)

        install_cmd_str = server_type_config.get_install_command(server)
        if not install_cmd_str:
            raise Exception("Install command topilmadi")

        server.status = MinecraftServer.Status.INSTALLING
        server.save()

        def run_installation():
            try:
                ServerLog.objects.create(
                    server=server,
                    level="info",
                    message=f"Server install boshlanmoqda: {install_cmd_str}",
                )

                import shlex
                install_cmd = shlex.split(install_cmd_str)

                process = subprocess.Popen(
                    install_cmd,
                    cwd=server_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                for line in iter(process.stdout.readline, ""):
                    if not line:
                        break
                    line = line.strip()
                    if line:
                        ServerLog.objects.create(
                            server=server, level="info", message=f"[INSTALL] {line}"
                        )

                process.wait()

                server.refresh_from_db()
                if process.returncode == 0:
                    server.is_installed = True
                    server.status = MinecraftServer.Status.STOPPED
                    server.save()

                    ServerLog.objects.create(
                        server=server,
                        level="info",
                        message="Server muvaffaqiyatli install qilindi",
                    )
                else:
                    server.status = MinecraftServer.Status.ERROR
                    server.save()
                    ServerLog.objects.create(
                        server=server,
                        level="error",
                        message=f"Install jarayoni xato bilan tugadi (code: {process.returncode})",
                    )
            except Exception as e:
                try:
                    server.refresh_from_db()
                    server.status = MinecraftServer.Status.ERROR
                    server.save()
                    ServerLog.objects.create(
                        server=server, level="error", message=f"Install xatosi: {str(e)}"
                    )
                except Exception:
                    pass

        threading.Thread(target=run_installation, daemon=True).start()
        return True

    @classmethod
    def start_server(cls, server):
        from .models import MinecraftServer, ServerLog

        if str(server.id) in cls._processes:
            raise Exception("Server allaqachon ishlayapti")

        server_path = cls.get_server_path(server)

        server_type_config = None
        if server.server_jar and server.server_jar.server_type:
            server_type_config = server.server_jar.server_type
        elif server.server_type:
            server_type_config = server.server_type

        if (
            server_type_config
            and server_type_config.is_installer
            and not server.is_installed
        ):
            raise Exception("Server hali install qilinmagan. Avval install qiling.")

        # Drop the previous run's pid before announcing "starting". It is
        # dead by now, and leaving it in place would let the monitor test a
        # stale number and declare this start-up already stopped.
        server.status = MinecraftServer.Status.STARTING
        server.pid = None
        server.save()
        cls._adopted.pop(str(server.id), None)

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"server_{str(server.id)}",
                {"type": "server_status", "status": "starting"},
            )
            cls.broadcast_status_update()

        # A server that arrived as a ZIP is already built, and the run script
        # it shipped with is the authoritative way to launch it: that script
        # names the exact loader version, module path and args file the
        # archive was assembled around. The per-type run_command is a
        # fallback for servers the panel installed itself -- applied to an
        # uploaded archive it produced "java -jar server.jar", and an archive
        # of a modded server has no such jar. server_jar is null exactly for
        # the archive case, so installed servers keep their existing path.
        run_script_cmd = (
            cls._run_script_command(server_path) if not server.server_jar else None
        )

        if run_script_cmd:
            java_cmd = run_script_cmd
        elif server_type_config:
            if server_type_config.requires_args_file:
                java_cmd = cls._build_forge_command(
                    server_path, server_type_config, server
                )
            else:
                run_cmd_str = server_type_config.get_run_command(server)
                import shlex

                java_cmd = shlex.split(run_cmd_str)
        else:
            jar_name = (server.jar_file or "").strip() or "server.jar"
            jar_path = os.path.join(server_path, jar_name)

            if not os.path.exists(jar_path):
                jar_candidates = sorted(
                    [
                        file_name
                        for file_name in os.listdir(server_path)
                        if file_name.lower().endswith(".jar")
                    ]
                )
                if "server.jar" in jar_candidates:
                    jar_name = "server.jar"
                elif len(jar_candidates) == 1:
                    jar_name = jar_candidates[0]
                else:
                    raise Exception(
                        "Ishga tushirish uchun JAR fayl topilmadi. "
                        "Zip ichida server.jar yoki bitta .jar fayl bo'lishi kerak."
                    )

                server.jar_file = jar_name
                server.save(update_fields=["jar_file", "updated_at"])

            java_cmd = [
                "java",
                f"-Xms{server.min_ram}M",
                f"-Xmx{server.max_ram}M",
                "-jar",
                jar_name,
                "nogui",
            ]

        server.online_mode = True
        server.save(update_fields=["online_mode"])
        cls.create_server_properties(server)

        authlib_path = os.path.join(settings.BASE_DIR, "config", "authlib-injector.jar").replace("\\", "/")
        ensure_backend_authlib_injector(authlib_path)
        
        backend_url = getattr(settings, "BACKEND_URL", "http://127.0.0.1:8000")
        backend_url = backend_url.rstrip("/")
        yggdrasil_url = f"{backend_url}/api/v1/yggdrasil/"
        agent_arg = f"-javaagent:{authlib_path}={yggdrasil_url}"

        # The in-game mod reads these two. Without the key a backend that has
        # MOD_API_KEY set answers 403 to every rank lookup, and the failure is
        # invisible from outside: panel fine, server fine, ranks never appear.
        jvm_args = [agent_arg, f"-Dcybercraft.api={backend_url}"]
        mod_api_key = getattr(settings, "MOD_API_KEY", "")
        if mod_api_key:
            jvm_args.append(f"-Dcybercraft.key={mod_api_key}")

        if java_cmd and (java_cmd[0] == "java" or java_cmd[0].endswith("/java") or java_cmd[0].endswith("\\java") or java_cmd[0].endswith("java.exe")):
            java_cmd = [arg for arg in java_cmd if not cls._is_managed_jvm_arg(arg)]
            for offset, arg in enumerate(jvm_args):
                java_cmd.insert(1 + offset, arg)

        user_args_path = os.path.join(server_path, "user_jvm_args.txt")
        if os.path.exists(user_args_path):
            try:
                with open(user_args_path, "r", encoding="utf-8") as f:
                    content = f.read()
                lines = content.splitlines()
                cleaned_lines = [
                    l for l in lines if not cls._is_managed_jvm_arg(l.strip())
                ]
                cleaned_lines.extend(jvm_args)
                with open(user_args_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(cleaned_lines) + "\n")
            except Exception as e:
                print(f"[DEBUG] Failed to write to user_jvm_args.txt: {e}")

        run_bat_path = os.path.join(server_path, "run.bat")
        if os.path.exists(run_bat_path):
            try:
                with open(run_bat_path, "r", encoding="utf-8") as f:
                    content = f.read()
                new_content = cls._patch_script_content(content, jvm_args)
                if new_content != content:
                    with open(run_bat_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
            except Exception as e:
                print(f"[DEBUG] Failed to patch run.bat: {e}")

        run_sh_path = os.path.join(server_path, "run.sh")
        if os.path.exists(run_sh_path):
            try:
                with open(run_sh_path, "r", encoding="utf-8") as f:
                    content = f.read()
                new_content = cls._patch_script_content(content, jvm_args)
                if new_content != content:
                    with open(run_sh_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
            except Exception as e:
                print(f"[DEBUG] Failed to patch run.sh: {e}")

        try:
            process = subprocess.Popen(
                java_cmd,
                cwd=server_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            cls._processes[str(server.id)] = process
            server.pid = process.pid
            server.last_started = datetime.now()
            server.save()

            cls._online_players[str(server.id)] = set()

            log_thread = threading.Thread(
                target=cls._read_server_logs, args=(server, process), daemon=True
            )
            cls._log_threads[str(server.id)] = log_thread
            log_thread.start()

            ServerLog.objects.create(
                server=server,
                level="info",
                message=f"Server ishga tushirilmoqda PID: {process.pid}",
            )

            cls.start_monitoring()
            return True

        except Exception as e:
            server.status = MinecraftServer.Status.ERROR
            server.save()
            ServerLog.objects.create(
                server=server, level="error", message=f"Serverni ishga tushirishda xato: {str(e)}",
            )
            raise e

    @classmethod
    def _run_script_command(cls, server_path):
        """The launcher script an uploaded archive or an installer left behind.

        Both scripts are named by absolute path. Passing the bare name relied
        on the shell searching its working directory, which Windows switches
        off whenever NoDefaultCurrentDirectoryInExePath is set in the
        environment -- and then cmd answers "'run.bat' is not recognized"
        even though the file is sitting right there.
        """
        if platform.system() == "Windows":
            run_script = os.path.join(server_path, "run.bat")
            if os.path.exists(run_script):
                return ["cmd", "/c", run_script, "nogui"]
            return None

        run_script = os.path.join(server_path, "run.sh")
        if os.path.exists(run_script):
            return ["bash", run_script, "nogui"]
        return None

    @classmethod
    def _build_forge_command(cls, server_path, server_type_config, server):
        """Forge/NeoForge uchun args file'dan command yaratadi"""

        is_windows = platform.system() == "Windows"

        run_script_cmd = cls._run_script_command(server_path)
        if run_script_cmd:
            return run_script_cmd

        java_cmd = ["java", f"-Xms{server.min_ram}M", f"-Xmx{server.max_ram}M"]

        user_args_path = os.path.join(server_path, "user_jvm_args.txt")
        if os.path.exists(user_args_path):
            with open(user_args_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        java_cmd.append(line)

        if server_type_config.args_file_pattern:
            if is_windows:
                win_pattern = server_type_config.args_file_pattern.replace(
                    "unix_args.txt", "win_args.txt"
                )
                pattern = os.path.join(server_path, win_pattern)
            else:
                pattern = os.path.join(
                    server_path, server_type_config.args_file_pattern
                )

            matching_files = glob_module.glob(pattern)

            if matching_files:
                args_file_path = matching_files[0]
                with open(args_file_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            if is_windows:
                                line = (
                                    line.replace(":", ";")
                                    if " -p " in " " + line
                                    or line.startswith("-p ")
                                    or "classpath" in line.lower()
                                    else line
                                )
                            java_cmd.append(line)
            else:
                raise Exception(f"Args fayl topilmadi: {pattern}")

        java_cmd.append("nogui")
        return java_cmd

    @classmethod
    def _read_server_logs(cls, server, process):
        from .models import MinecraftServer, ServerLog

        channel_layer = get_channel_layer()
        server_id = str(server.id)

        try:
            for line in iter(process.stdout.readline, ""):
                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                level = "info"
                if "WARN" in line:
                    level = "warn"
                elif "ERROR" in line or "Exception" in line:
                    level = "error"

                if "Done" in line and "For help" in line:
                    server.status = MinecraftServer.Status.RUNNING
                    server.save()

                    if channel_layer:
                        try:
                            async_to_sync(channel_layer.group_send)(
                                f"server_{server_id}",
                                {"type": "server_status", "status": "running"},
                            )
                        except Exception:
                            pass

                player_match = re.search(
                    r"There are (\d+) of a max of (\d+) players", line
                )
                if player_match:
                    server.current_players = int(player_match.group(1))
                    server.save()

                join_match = re.search(r"\]: ([a-zA-Z0-9_]+) joined the game", line)
                if join_match:
                    player_name = join_match.group(1)
                    if server_id not in cls._online_players:
                        cls._online_players[server_id] = set()
                    cls._online_players[server_id].add(player_name)
                    server.current_players = len(cls._online_players[server_id])
                    server.save(update_fields=["current_players"])
                    cls.broadcast_status_update()

                leave_match = re.search(r"\]: ([a-zA-Z0-9_]+) left the game", line)
                if leave_match:
                    player_name = leave_match.group(1)
                    if server_id in cls._online_players:
                        cls._online_players[server_id].discard(player_name)
                    server.current_players = len(cls._online_players.get(server_id, []))
                    server.save(update_fields=["current_players"])
                    cls.broadcast_status_update()

                log_entry = ServerLog.objects.create(
                    server=server, level=level, message=line
                )

                if channel_layer:
                    try:
                        async_to_sync(channel_layer.group_send)(
                            f"server_{server_id}",
                            {
                                "type": "server_log",
                                "log": {
                                    "id": log_entry.id,
                                    "level": level,
                                    "message": line,
                                    "timestamp": log_entry.timestamp.isoformat(),
                                },
                            },
                        )
                        async_to_sync(channel_layer.group_send)(
                            f"server_console_{server_id}",
                            {
                                "type": "console_log",
                                "line": line,
                                "timestamp": log_entry.timestamp.isoformat(),
                            },
                        )
                    except Exception:
                        pass

        except Exception as e:
            if not cls._is_shutting_down:
                print(f"Log reader error: {e}")

        finally:
            try:
                process.wait()
                server.status = MinecraftServer.Status.STOPPED
                server.pid = None
                server.current_players = 0
                if server_id in cls._online_players:
                    cls._online_players[server_id].clear()
                server.save()

                if server_id in cls._processes:
                    del cls._processes[server_id]

                if channel_layer:
                    async_to_sync(channel_layer.group_send)(
                        f"server_{server_id}",
                        {"type": "server_status", "status": "stopped"},
                    )
                    cls.broadcast_status_update()
            except Exception:
                pass

    @classmethod
    def stop_server(cls, server, force=False, skip_log=False):
        from .models import MinecraftServer, ServerLog

        server_id = str(server.id)

        if server_id not in cls._processes:
            # No pipe to this server: either it is genuinely down, or its JVM
            # was inherited from an earlier backend run. Relabelling the row
            # and walking away used to leave that JVM up, still holding the
            # port, so the next start failed on an address already in use.
            orphan_pid = cls._adopted.pop(server_id, None) or server.pid
            if cls._pid_alive_for(server_id, orphan_pid):
                cls._terminate_pid_tree(orphan_pid)
                if not skip_log:
                    try:
                        ServerLog.objects.create(
                            server=server,
                            level="warn",
                            message=(
                                "Oldingi ishga tushirishdan qolgan jarayon "
                                f"to'xtatildi (PID: {orphan_pid})"
                            ),
                        )
                    except Exception:
                        pass

            server.status = MinecraftServer.Status.STOPPED
            server.pid = None
            server.current_players = 0
            server.save()
            cls._online_players.pop(server_id, None)
            try:
                cls.broadcast_status_update()
            except Exception:
                pass
            return True

        process = cls._processes[server_id]
        server.status = MinecraftServer.Status.STOPPING
        server.save()

        try:
            if force:
                process.kill()
            else:
                process.stdin.write("stop\n")
                process.stdin.flush()

                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()

            if not skip_log:
                ServerLog.objects.create(
                    server=server, level="info", message="Server to'xtatildi"
                )

            return True

        except Exception as e:
            if not skip_log:
                try:
                    ServerLog.objects.create(
                        server=server,
                        level="error",
                        message=f"Serverni to'xtatishda xato: {str(e)}",
                    )
                except Exception:
                    pass
            raise e

    @classmethod
    def stop_all_servers(cls):
        """Backend o'chirilishidan oldin barcha serverlarni to'xtatish."""
        if cls._is_shutting_down:
            return
        cls._is_shutting_down = True
        
        tracked = list(cls._processes.items())
        cls._processes.clear()
        processes = [process for _, process in tracked]
        touched_ids = [server_id for server_id, _ in tracked]

        # JVMs inherited from an earlier run have no stdin to say "stop" to,
        # so they get terminated directly rather than left behind holding
        # their ports.
        adopted = list(cls._adopted.items())
        cls._adopted.clear()
        for server_id, pid in adopted:
            if cls._pid_alive_for(server_id, pid):
                cls._terminate_pid_tree(pid, timeout=10)
            touched_ids.append(server_id)

        for process in processes:
            try:
                process.stdin.write("stop\n")
                process.stdin.flush()
            except Exception:
                pass
        
        # Wait up to 15 seconds for processes to exit gracefully
        start_wait = time.time()
        while time.time() - start_wait < 15:
            all_stopped = True
            for process in processes:
                if process.poll() is None:
                    all_stopped = False
                    break
            if all_stopped:
                break
            time.sleep(0.5)
            
        for process in processes:
            if process.poll() is None:
                try:
                    process.kill()
                except Exception:
                    pass

        # The log-reader threads normally record this, but the interpreter is
        # on its way out and may never schedule them again. Without this the
        # rows keep claiming "running" until the next boot reconciles them.
        try:
            from .models import MinecraftServer

            MinecraftServer.objects.filter(id__in=touched_ids).update(
                status=MinecraftServer.Status.STOPPED, pid=None, current_players=0
            )
        except Exception:
            pass

    @classmethod
    def restart_server(cls, server):
        cls.stop_server(server)
        time.sleep(2)
        cls.start_server(server)

    @classmethod
    def send_command(cls, server, command, user=None):
        from .models import ServerCommand, ServerLog

        server_id = str(server.id)

        if server_id not in cls._processes:
            raise Exception("Server ishlamayapti")

        process = cls._processes[server_id]

        try:
            process.stdin.write(f"{command}\n")
            process.stdin.flush()

            ServerCommand.objects.create(server=server, user=user, command=command)

            return True

        except Exception as e:
            raise Exception(f"Komandani yuborishda xato: {str(e)}")

    @classmethod
    def get_server_status(cls, server):
        server_id = str(server.id)
        is_running = server_id in cls._processes or server_id in cls._adopted

        return {
            "id": str(server.id),
            "name": server.name,
            "status": server.status,
            "is_running": is_running,
            "pid": server.pid,
            "current_players": server.current_players,
            "max_players": server.max_players,
            "online_player_list": list(cls._online_players.get(server_id, [])),
            "minecraft_version": server.minecraft_version,
            "server_type": (
                server.server_type.server_type if server.server_type else None
            ),
            "port": server.port,
            "ram": {"min": server.min_ram, "max": server.max_ram},
            "is_installed": server.is_installed,
        }

    @classmethod
    def broadcast_status_update(cls):
        """Barcha launcher WS klientlariga server statusini yuborish"""
        from apps.servers.models import MinecraftServer, Server
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        channel_layer = get_channel_layer()
        if not channel_layer:
            return

        managed_servers = MinecraftServer.objects.select_related("server_type").all()
        external_servers = Server.objects.filter(is_active=True).all()

        servers_data = []
        for server in managed_servers:
            servers_data.append({
                "id": str(server.id),
                "name": server.name,
                "status": server.status,
                "current_players": server.current_players,
                "max_players": server.max_players,
                "is_managed": True,
            })

        for server in external_servers:
            servers_data.append({
                "id": str(server.id),
                "name": server.name,
                "status": server.status,
                "current_players": server.current_players,
                "max_players": server.max_players,
                "is_managed": False,
            })

        async_to_sync(channel_layer.group_send)(
            "launcher_status",
            {
                "type": "status_update",
                "data": {
                    "type": "status_update",
                    "servers": servers_data,
                    "timestamp": datetime.now().isoformat(),
                }
            }
        )

    @classmethod
    def delete_server(cls, server):
        if str(server.id) in cls._processes:
            cls.stop_server(server, force=True)

        server_path = cls.get_server_path(server)
        if os.path.exists(server_path):
            shutil.rmtree(server_path)

        server.delete()

    @classmethod
    def install_mod(cls, server, mod_file, mod_name):
        server_path = cls.get_server_path(server)
        mods_path = os.path.join(server_path, "mods")
        os.makedirs(mods_path, exist_ok=True)

        safe_filename = os.path.basename(mod_file.name)
        dest_path = os.path.join(mods_path, safe_filename)
        with open(dest_path, "wb") as f:
            for chunk in mod_file.chunks():
                f.write(chunk)

        return dest_path

    @classmethod
    def remove_mod(cls, server, mod_filename):
        server_path = cls.get_server_path(server)
        mod_path = os.path.join(server_path, "mods", mod_filename)

        if os.path.exists(mod_path):
            os.remove(mod_path)
            return True
        return False

    @classmethod
    def toggle_mod(cls, server, mod_filename, enable=True):
        server_path = cls.get_server_path(server)
        mods_path = os.path.join(server_path, "mods")

        if enable:
            disabled_path = os.path.join(mods_path, f"{mod_filename}.disabled")
            enabled_path = os.path.join(mods_path, mod_filename)
            if os.path.exists(disabled_path):
                os.rename(disabled_path, enabled_path)
        else:
            enabled_path = os.path.join(mods_path, mod_filename)
            disabled_path = os.path.join(mods_path, f"{mod_filename}.disabled")
            if os.path.exists(enabled_path):
                os.rename(enabled_path, disabled_path)

        return True

    @classmethod
    def get_server_files(cls, server, path=""):
        server_path = cls.get_server_path(server)
        server_path_abs = os.path.abspath(server_path)
        
        if path:
            target_path = os.path.abspath(os.path.normpath(os.path.join(server_path_abs, path)))
        else:
            target_path = server_path_abs

        if os.path.commonpath([server_path_abs, target_path]) != server_path_abs:
            raise Exception("Noto'g'ri fayl yo'li")

        if not os.path.exists(target_path):
            return []

        files = []
        for item in os.listdir(target_path):
            item_path = os.path.join(target_path, item)
            files.append(
                {
                    "name": item,
                    "path": os.path.join(path, item) if path else item,
                    "is_directory": os.path.isdir(item_path),
                    "size": (
                        os.path.getsize(item_path) if os.path.isfile(item_path) else 0
                    ),
                    "modified": datetime.fromtimestamp(
                        os.path.getmtime(item_path)
                    ).isoformat(),
                }
            )

        return sorted(files, key=lambda x: (not x["is_directory"], x["name"]))

    @classmethod
    def read_file(cls, server, file_path):
        server_path = cls.get_server_path(server)
        server_path_abs = os.path.abspath(server_path)
        full_path = os.path.abspath(os.path.normpath(os.path.join(server_path_abs, file_path)))

        if os.path.commonpath([server_path_abs, full_path]) != server_path_abs:
            raise Exception("Noto'g'ri fayl yo'li")

        if not os.path.exists(full_path):
            raise Exception("Fayl topilmadi")

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    @classmethod
    def write_file(cls, server, file_path, content):
        server_path = cls.get_server_path(server)
        server_path_abs = os.path.abspath(server_path)
        full_path = os.path.abspath(os.path.normpath(os.path.join(server_path_abs, file_path)))

        if os.path.commonpath([server_path_abs, full_path]) != server_path_abs:
            raise Exception("Noto'g'ri fayl yo'li")

        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return True

    @classmethod
    def _is_server_process(cls, server_id, pid, proc):
        popen_proc = cls._processes.get(server_id)
        if popen_proc:
            return popen_proc.pid == pid and popen_proc.poll() is None
        try:
            from apps.servers.models import MinecraftServer
            server = MinecraftServer.objects.filter(id=server_id).first()
            if not server:
                return False
            server_path = os.path.abspath(cls.get_server_path(server))
            try:
                proc_cwd = os.path.abspath(proc.cwd())
                if os.path.commonpath([server_path, proc_cwd]) == server_path:
                    return True
            except Exception:
                pass
            cmdline = proc.cmdline()
            cmdline_str = " ".join(cmdline).lower()
            if "java" in cmdline_str and (str(server_id) in cmdline_str or "authlib-injector" in cmdline_str or "server.jar" in cmdline_str):
                return True
        except Exception:
            pass
        return False

    @classmethod
    def start_monitoring(cls):
        if cls._monitor_thread and cls._monitor_thread.is_alive():
            return
        cls._monitor_thread = threading.Thread(target=cls._monitor_loop, daemon=True)
        cls._monitor_thread.start()

    @classmethod
    def _monitor_loop(cls):
        import psutil
        from apps.servers.models import MinecraftServer
        
        channel_layer = get_channel_layer()
        process_caches = {}
        stat_caches = {}

        # First act of the monitor, before it reports anything: repair the
        # statuses the previous backend never got to close out.
        try:
            repaired = cls.reconcile_statuses()
            if repaired:
                print(f"[servers] {repaired} ta serverning eskirgan holati tiklandi")
        except Exception as exc:
            print(f"[servers] holatlarni tiklab bo'lmadi: {exc}")

        while not cls._is_shutting_down:
            time.sleep(2)
            try:
                # Every status that claims the server is alive, not just
                # "running": a server killed while starting used to sit at
                # "starting" for ever, because nothing here ever looked at it.
                active_servers = MinecraftServer.objects.filter(
                    status__in=cls.ACTIVE_STATUSES,
                    pid__isnull=False,
                )

                for server in active_servers:
                    server_id = str(server.id)
                    pid = server.pid
                
                    try:
                        # Get or create cached Process instance
                        if server_id not in process_caches or process_caches[server_id].pid != pid:
                            process_caches[server_id] = psutil.Process(pid)
                        
                        proc = process_caches[server_id]
                    
                        if not proc.is_running() or not cls._is_server_process(server_id, pid, proc):
                            process_caches.pop(server_id, None)
                            stat_caches.pop(server_id, None)
                            cls._mark_stopped(server, "jarayon topilmadi")
                            continue

                        if server.status != MinecraftServer.Status.RUNNING:
                            # Alive, but not reported running yet. The log reader
                            # owns that flip -- it is the only thing that knows
                            # when the world has finished loading.
                            continue

                        # Non-blocking, and covers the JVM under the shell.
                        cpu, memory_mb = cls._collect_stats(
                            proc, stat_caches.setdefault(server_id, {})
                        )
                    
                        if channel_layer:
                            async_to_sync(channel_layer.group_send)(
                                f"server_{server_id}",
                                {
                                    "type": "server_stats",
                                    "stats": {
                                        "cpu": cpu,
                                        "memory": round(memory_mb, 1),
                                        "timestamp": datetime.now().isoformat()
                                    }
                                }
                            )
                    except psutil.AccessDenied:
                        # Says nothing about whether the server is up, so leave
                        # the status alone and retry with a fresh handle.
                        process_caches.pop(server_id, None)
                        stat_caches.pop(server_id, None)
                    except (psutil.NoSuchProcess, psutil.ZombieProcess):
                        process_caches.pop(server_id, None)
                        stat_caches.pop(server_id, None)
                        cls._mark_stopped(server, "jarayon yo'qoldi")
                    except Exception as e:
                        print(f"Error in monitor loop for server {server_id}: {e}")
            except Exception as exc:
                # A transient database lock or a psutil hiccup used to
                # escape this loop and kill the thread outright, and
                # then every status stayed frozen at whatever it last
                # said -- precisely the drift this monitor exists to
                # correct. Losing one cycle is fine; losing the thread
                # is not.
                print(f"[servers] monitor cycle failed: {exc}")

    @classmethod
    def get_player_lists(cls, server):
        server_path = cls.get_server_path(server)
        
        whitelist_path = os.path.join(server_path, "whitelist.json")
        ops_path = os.path.join(server_path, "ops.json")
        banned_path = os.path.join(server_path, "banned-players.json")
        
        whitelist = []
        if os.path.exists(whitelist_path):
            try:
                with open(whitelist_path, "r", encoding="utf-8") as f:
                    whitelist = json.load(f)
            except Exception:
                pass
                
        ops = []
        if os.path.exists(ops_path):
            try:
                with open(ops_path, "r", encoding="utf-8") as f:
                    ops = json.load(f)
            except Exception:
                pass
                
        banned = []
        if os.path.exists(banned_path):
            try:
                with open(banned_path, "r", encoding="utf-8") as f:
                    banned = json.load(f)
            except Exception:
                pass
                
        return {
            "whitelist": whitelist,
            "ops": ops,
            "banned": banned
        }

    @classmethod
    def modify_player_list(cls, server, list_type, action, username, reason="Banned by admin"):
        """
        list_type: 'whitelist', 'ops', 'banned'
        action: 'add', 'remove'
        """
        server_path = cls.get_server_path(server)
        file_map = {
            "whitelist": "whitelist.json",
            "ops": "ops.json",
            "banned": "banned-players.json"
        }
        
        if list_type not in file_map:
            raise Exception("Invalid list type")
            
        file_path = os.path.join(server_path, file_map[list_type])
        
        data = []
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
                
        uuid = cls._get_uuid_for_username(username)
        
        if action == "add":
            data = [item for item in data if item.get("name", "").lower() != username.lower()]
            
            if list_type == "whitelist":
                data.append({"uuid": uuid, "name": username})
                if str(server.id) in cls._processes:
                    cls.send_command(server, f"whitelist add {username}")
                    cls.send_command(server, "whitelist reload")
            elif list_type == "ops":
                data.append({
                    "uuid": uuid,
                    "name": username,
                    "level": 4,
                    "bypassesPlayerLimit": False
                })
                if str(server.id) in cls._processes:
                    cls.send_command(server, f"op {username}")
            elif list_type == "banned":
                created_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S %z") if datetime.now().tzinfo else datetime.now().strftime("%Y-%m-%d %H:%M:%S +0000")
                data.append({
                    "uuid": uuid,
                    "name": username,
                    "created": created_str,
                    "source": "Banned by Admin",
                    "expires": "forever",
                    "reason": reason
                })
                if str(server.id) in cls._processes:
                    cls.send_command(server, f"ban {username} {reason}")
                    
        elif action == "remove":
            data = [item for item in data if item.get("name", "").lower() != username.lower()]
            
            if list_type == "whitelist":
                if str(server.id) in cls._processes:
                    cls.send_command(server, f"whitelist remove {username}")
                    cls.send_command(server, "whitelist reload")
            elif list_type == "ops":
                if str(server.id) in cls._processes:
                    cls.send_command(server, f"deop {username}")
            elif list_type == "banned":
                if str(server.id) in cls._processes:
                    cls.send_command(server, f"pardon {username}")
                    
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        return True

    @classmethod
    def _get_uuid_for_username(cls, username):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.filter(username__iexact=username).first()
        if user and user.minecraft_uuid:
            return str(user.minecraft_uuid)
            
        import hashlib
        import uuid as uuid_lib
        hash_bytes = hashlib.md5(f"OfflinePlayer:{username}".encode('utf-8')).digest()
        hash_bytes = bytearray(hash_bytes)
        hash_bytes[6] = (hash_bytes[6] & 0x0f) | 0x30
        hash_bytes[8] = (hash_bytes[8] & 0x3f) | 0x80
        return str(uuid_lib.UUID(bytes=bytes(hash_bytes)))
