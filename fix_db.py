import sqlite3
import os

def fix():
    db_path = 'db.sqlite3'
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("1. Adding columns to 'servers' table...")
    # category
    try:
        cursor.execute("ALTER TABLE servers ADD COLUMN category varchar(50) NOT NULL DEFAULT 'Survival'")
        print("  - Added 'category'")
    except sqlite3.OperationalError as e:
        print(f"  - 'category' skip: {e}")

    # last_wipe
    try:
        cursor.execute("ALTER TABLE servers ADD COLUMN last_wipe date NULL")
        print("  - Added 'last_wipe'")
    except sqlite3.OperationalError as e:
        print(f"  - 'last_wipe' skip: {e}")

    print("2. Creating 'server_gallery_images' table...")
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "server_gallery_images" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, 
                "image" varchar(100) NOT NULL, 
                "caption" varchar(200) NOT NULL, 
                "order" integer NOT NULL, 
                "server_id" bigint NOT NULL REFERENCES "servers" ("id") DEFERRABLE INITIALLY DEFERRED
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS server_gallery_images_server_id_4b2e8d90 ON server_gallery_images (server_id)")
        print("  - Success")
    except Exception as e:
        print(f"  - Error: {e}")

    print("3. Creating 'server_features' table...")
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS "server_features" (
                "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT, 
                "title" varchar(100) NOT NULL, 
                "description" text NOT NULL, 
                "icon" varchar(50) NOT NULL, 
                "order" integer NOT NULL, 
                "server_id" bigint NOT NULL REFERENCES "servers" ("id") DEFERRABLE INITIALLY DEFERRED
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS server_features_server_id_351d673b ON server_features (server_id)")
        print("  - Success")
    except Exception as e:
        print(f"  - Error: {e}")

    print("4. Checking 'servers_minecraftserver' for missing FKs...")
    try:
        cursor.execute("ALTER TABLE servers_minecraftserver ADD COLUMN server_jar_id char(32) NULL REFERENCES server_jars(id)")
        print("  - Added 'server_jar_id'")
    except sqlite3.OperationalError:
        print("  - 'server_jar_id' exists or skip")

    try:
        cursor.execute("ALTER TABLE servers_minecraftserver ADD COLUMN server_type_id varchar(20) NULL REFERENCES server_type_configs(server_type)")
        print("  - Added 'server_type_id'")
    except sqlite3.OperationalError:
        print("  - 'server_type_id' exists or skip")

    conn.commit()
    conn.close()
    print("\nDatabase patching finished.")

if __name__ == "__main__":
    fix()
