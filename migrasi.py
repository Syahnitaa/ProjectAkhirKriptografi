"""
Migrasi database ArtVault lama -> versi baru (jalankan SEKALI, aman diulang).

    python migrasi.py

Yang dilakukan:
  1. artworks.watermark_text (teks polos)  ->  artworks.watermark_enc (terenkripsi AES)
  2. messages: tambah kolom untuk file & gambar rahasia di chat
  3. artworks.deleted_at (untuk fitur hapus karya)
  4. buat folder storage/chat

Catatan: gambar karya yang SUDAH diupload sebelumnya tetap berisi watermark format lama
(teks polos di dalam piksel). Gambar itu tidak diubah karena hash-nya sudah tercatat di
blockchain. Halaman "Cek Watermark" tetap bisa membacanya dan menandainya "format lama".
Karya yang diupload sesudah migrasi otomatis memakai watermark terenkripsi.
"""
import base64
import os

import config
from crypto_tools import watermark_encrypt
from db import get_db


def kolom_ada(cur, tabel, kolom):
    cur.execute("SELECT COUNT(*) AS n FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
                (config.DB_NAME, tabel, kolom))
    return cur.fetchone()["n"] > 0


def main():
    db = get_db()
    try:
        with db.cursor() as cur:
            # --- 1. watermark ---
            if kolom_ada(cur, "artworks", "watermark_text") and not kolom_ada(cur, "artworks", "watermark_enc"):
                cur.execute("ALTER TABLE artworks CHANGE watermark_text watermark_enc TEXT NOT NULL")
                cur.execute("SELECT id, watermark_enc FROM artworks")
                for k in cur.fetchall():
                    enc = base64.b64encode(watermark_encrypt(k["watermark_enc"])).decode()
                    cur.execute("UPDATE artworks SET watermark_enc=%s WHERE id=%s", (enc, k["id"]))
                print("[ok] watermark di database sekarang terenkripsi AES")
            else:
                print("[lewati] kolom watermark sudah versi baru")

            # --- 2. chat ---
            tambah = [
                ("kind", "ENUM('text','file','secret_image') NOT NULL DEFAULT 'text'"),
                ("file_path", "VARCHAR(255) NULL"),
                ("file_nonce", "VARCHAR(64) NULL"),
                ("file_name_enc", "TEXT NULL"),
                ("file_size", "INT NULL"),
                ("file_hash", "CHAR(64) NULL"),
            ]
            for nama, tipe in tambah:
                if kolom_ada(cur, "messages", nama):
                    print("[lewati] messages.%s sudah ada" % nama)
                else:
                    cur.execute("ALTER TABLE messages ADD COLUMN %s %s" % (nama, tipe))
                    print("[ok] messages.%s ditambahkan" % nama)

            # --- 3. hapus karya (soft delete) ---
            if kolom_ada(cur, "artworks", "deleted_at"):
                print("[lewati] artworks.deleted_at sudah ada")
            else:
                cur.execute("ALTER TABLE artworks ADD COLUMN deleted_at TIMESTAMP NULL DEFAULT NULL")
                print("[ok] artworks.deleted_at ditambahkan")
        db.commit()
    finally:
        db.close()

    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage", "chat"), exist_ok=True)
    print("Selesai.")


if __name__ == "__main__":
    main()
