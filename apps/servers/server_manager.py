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
                for member in archive.infolist():
                    member_path = os.path.abspath(
                        os.path.normpath(os.path.join(server_path, member.filename))
                    )
                    if not member_path.startswith(os.path.abspath(server_path)):
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
            return True
        except zipfile.BadZipFile as e:
            print(f"Error setting up server from ZIP: {e}")
            raise Exception("ZIP fayl ochilmadi — haqiqiy .zip ekanini tekshiring") from e
        except Exception as e:
            print(f"Error setting up server from ZIP: {e}")
            raise e

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

        ServerLog.objects.create(
            server=server,
            level="info",
            message=f"Server install boshlanmoqda: {install_cmd_str}",
        )

        try:
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

            if process.returncode == 0:
                server.is_installed = True
                server.status = MinecraftServer.Status.STOPPED
                server.save()

                ServerLog.objects.create(
                    server=server,
                    level="info",
                    message="Server muvaffaqiyatli install qilindi",
                )
                return True
            else:
                server.status = MinecraftServer.Status.ERROR
                server.save()
                raise Exception(
                    f"Install jarayoni xato bilan tugadi (code: {process.returncode})"
                )

        except Exception as e:
            server.status = MinecraftServer.Status.ERROR
            server.save()
            ServerLog.objects.create(
                server=server, level="error", message=f"Install xatosi: {str(e)}"
            )
            raise e

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

        server.status = MinecraftServer.Status.STARTING
        server.save()

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"server_{str(server.id)}",
                {"type": "server_status", "status": "starting"},
            )
            cls.broadcast_status_update()

        if server_type_config:
            if server_type_config.requires_args_file:
                java_cmd = cls._build_forge_command(
                    server_path, server_type_config, server
                )
            else:
                run_cmd_str = server_type_config.get_run_command(server)
                import shlex

                java_cmd = shlex.split(run_cmd_str)
        else:
            is_windows = platform.system() == "Windows"
            run_script = "run.bat" if is_windows else "run.sh"
            run_script_path = os.path.join(server_path, run_script)

            if os.path.exists(run_script_path):
                java_cmd = (
                    ["cmd", "/c", run_script, "nogui"]
                    if is_windows
                    else ["bash", run_script, "nogui"]
                )
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
        yggdrasil_url = f"{backend_url.rstrip('/')}/api/v1/yggdrasil/"
        agent_arg = f"-javaagent:{authlib_path}={yggdrasil_url}"

        if java_cmd and (java_cmd[0] == "java" or java_cmd[0].endswith("/java") or java_cmd[0].endswith("\\java") or java_cmd[0].endswith("java.exe")):
            java_cmd = [arg for arg in java_cmd if not (arg.startswith("-javaagent:") and "authlib-injector" in arg)]
            java_cmd.insert(1, agent_arg)

        user_args_path = os.path.join(server_path, "user_jvm_args.txt")
        if os.path.exists(user_args_path):
            try:
                with open(user_args_path, "r", encoding="utf-8") as f:
                    content = f.read()
                lines = content.splitlines()
                cleaned_lines = [l for l in lines if not ("-javaagent:" in l and "authlib-injector" in l)]
                cleaned_lines.append(agent_arg)
                with open(user_args_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(cleaned_lines) + "\n")
            except Exception as e:
                print(f"[DEBUG] Failed to write to user_jvm_args.txt: {e}")

        run_bat_path = os.path.join(server_path, "run.bat")
        if os.path.exists(run_bat_path):
            try:
                with open(run_bat_path, "r", encoding="utf-8") as f:
                    content = f.read()
                cleaned_content = re.sub(r"-javaagent:[^\s]*authlib-injector[^\s]*", "", content)
                new_content = re.sub(r"\bjava\b", f"java {agent_arg}", cleaned_content, flags=re.IGNORECASE)
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
                cleaned_content = re.sub(r"-javaagent:[^\s]*authlib-injector[^\s]*", "", content)
                new_content = re.sub(r"\bjava\b", f"java {agent_arg}", cleaned_content, flags=re.IGNORECASE)
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
    def _build_forge_command(cls, server_path, server_type_config, server):
        """Forge/NeoForge uchun args file'dan command yaratadi"""

        is_windows = platform.system() == "Windows"

        if is_windows:
            run_script = os.path.join(server_path, "run.bat")
            if os.path.exists(run_script):
                return ["cmd", "/c", "run.bat", "nogui"]
        else:
            run_script = os.path.join(server_path, "run.sh")
            if os.path.exists(run_script):
                return ["bash", "run.sh", "nogui"]

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
            server.status = MinecraftServer.Status.STOPPED
            server.save()
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
        
        processes = list(cls._processes.values())
        cls._processes.clear()
        
        for process in processes:
            try:
                process.stdin.write("stop\n")
                process.stdin.flush()
            except Exception:
                pass
        
        time.sleep(2)
        for process in processes:
            try:
                process.kill()
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
        is_running = server_id in cls._processes

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

        dest_path = os.path.join(mods_path, mod_file.name)
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
        target_path = os.path.join(server_path, path) if path else server_path

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
        full_path = os.path.join(server_path, file_path)

        if not full_path.startswith(server_path):
            raise Exception("Noto'g'ri fayl yo'li")

        if not os.path.exists(full_path):
            raise Exception("Fayl topilmadi")

        with open(full_path, "r") as f:
            return f.read()

    @classmethod
    def write_file(cls, server, file_path, content):
        server_path = cls.get_server_path(server)
        full_path = os.path.join(server_path, file_path)

        if not full_path.startswith(server_path):
            raise Exception("Noto'g'ri fayl yo'li")

        with open(full_path, "w") as f:
            f.write(content)

        return True

    @classmethod
    def start_monitoring(cls):
        if cls._monitor_thread and cls._monitor_thread.is_alive():
            return
        cls._monitor_thread = threading.Thread(target=cls._monitor_loop, daemon=True)
        cls._monitor_thread.start()

    @classmethod
    def _monitor_loop(cls):
        import psutil
        
        channel_layer = get_channel_layer()
        while not cls._is_shutting_down:
            time.sleep(2)
            for server_id, process in list(cls._processes.items()):
                try:
                    if process.poll() is not None:
                        continue
                    pid = process.pid
                    proc = psutil.Process(pid)
                    
                    cpu = proc.cpu_percent(interval=None)
                    mem_info = proc.memory_info()
                    memory_mb = mem_info.rss / (1024 * 1024)
                    
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
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                except Exception as e:
                    print(f"Error in monitor loop: {e}")

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
