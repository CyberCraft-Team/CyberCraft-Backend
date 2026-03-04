"""
ServerTypeConfig jadvaliga asosiy server turlarini qo'shadi.
Ishga tushirish: python manage.py shell < scripts/create_server_types.py
yoki: python manage.py runscript create_server_types (django-extensions bilan)
"""

import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from apps.servers.models import ServerTypeConfig

SERVER_TYPES = [
    {
        "server_type": "vanilla",
        "display_name": "Vanilla",
        "description": "Rasmiy Minecraft server",
        "is_installer": False,
        "run_command": "{java} -Xms{min_ram}M -Xmx{max_ram}M -jar {jar_file} nogui",
        "jar_file_name": "server.jar",
    },
    {
        "server_type": "paper",
        "display_name": "Paper",
        "description": "Yuqori samaradorlikka ega Spigot fork",
        "is_installer": False,
        "run_command": "{java} -Xms{min_ram}M -Xmx{max_ram}M -jar {jar_file} nogui",
        "jar_file_name": "paper.jar",
    },
    {
        "server_type": "spigot",
        "display_name": "Spigot",
        "description": "CraftBukkit asosidagi server",
        "is_installer": False,
        "run_command": "{java} -Xms{min_ram}M -Xmx{max_ram}M -jar {jar_file} nogui",
        "jar_file_name": "spigot.jar",
    },
    {
        "server_type": "forge",
        "display_name": "Forge",
        "description": "Modlar uchun eng mashhur platforma",
        "is_installer": True,
        "install_command": "{java} -jar {jar_file} --installServer",
        "run_command": "{java} -Xms{min_ram}M -Xmx{max_ram}M @libraries/net/minecraftforge/forge/*/unix_args.txt nogui",
        "requires_args_file": True,
        "args_file_pattern": "libraries/net/minecraftforge/forge/*/unix_args.txt",
        "jar_file_name": "forge-installer.jar",
    },
    {
        "server_type": "fabric",
        "display_name": "Fabric",
        "description": "Yengil va tez modlar platformasi",
        "is_installer": True,
        "install_command": "{java} -jar {jar_file} server -mcversion {mc_version} -downloadMinecraft",
        "run_command": "{java} -Xms{min_ram}M -Xmx{max_ram}M -jar fabric-server-launch.jar nogui",
        "jar_file_name": "fabric-installer.jar",
    },
    {
        "server_type": "neoforge",
        "display_name": "NeoForge",
        "description": "Forge ning yangi avlodi (1.20.1+)",
        "is_installer": True,
        "install_command": "{java} -jar {jar_file} --installServer",
        "run_command": "{java} -Xms{min_ram}M -Xmx{max_ram}M @libraries/net/neoforged/neoforge/*/unix_args.txt nogui",
        "requires_args_file": True,
        "args_file_pattern": "libraries/net/neoforged/neoforge/*/unix_args.txt",
        "jar_file_name": "neoforge-installer.jar",
    },
    {
        "server_type": "purpur",
        "display_name": "Purpur",
        "description": "Paper asosidagi qo'shimcha funksiyali server",
        "is_installer": False,
        "run_command": "{java} -Xms{min_ram}M -Xmx{max_ram}M -jar {jar_file} nogui",
        "jar_file_name": "purpur.jar",
    },
    {
        "server_type": "custom",
        "display_name": "Custom",
        "description": "Boshqa turdagi serverlar",
        "is_installer": False,
        "run_command": "{java} -Xms{min_ram}M -Xmx{max_ram}M -jar {jar_file} nogui",
        "jar_file_name": "server.jar",
    },
]


def create_server_types():
    created = 0
    updated = 0

    for config in SERVER_TYPES:
        obj, is_created = ServerTypeConfig.objects.update_or_create(
            server_type=config["server_type"],
            defaults={
                "display_name": config["display_name"],
                "description": config["description"],
                "is_installer": config.get("is_installer", False),
                "install_command": config.get("install_command", ""),
                "run_command": config["run_command"],
                "requires_args_file": config.get("requires_args_file", False),
                "args_file_pattern": config.get("args_file_pattern", ""),
                "jar_file_name": config["jar_file_name"],
                "is_active": True,
            },
        )
        if is_created:
            created += 1
            print(f"✓ Yaratildi: {config['display_name']}")
        else:
            updated += 1
            print(f"↻ Yangilandi: {config['display_name']}")

    print(f"\nJami: {created} ta yaratildi, {updated} ta yangilandi")


if __name__ == "__main__":
    create_server_types()
