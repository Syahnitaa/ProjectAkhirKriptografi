"""
Jadikan sebuah flashdisk sebagai DONGGLE ArtVault (jalankan SEKALI per donggle).

    python buat_donggle.py                 # pilih flashdisk dari daftar
    python buat_donggle.py E:\\             # langsung pakai drive E:
    python buat_donggle.py E:\\ --tanpa-serial   # tidak mengikat ke nomor seri flashdisk

Yang dilakukan:
  1. Menulis file artvault.key (berisi token acak) ke flashdisk.
  2. Menyimpan HASH token di donggle.json (token asli tidak disimpan di server).

Membuat donggle baru MENGGANTIKAN donggle lama (flashdisk lama tidak berlaku lagi).
"""
import os
import sys

import donggle


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pakai_serial = "--tanpa-serial" not in sys.argv
    timpa = "--timpa" in sys.argv

    if args:
        lokasi = args[0]
    else:
        pilihan = donggle.lokasi_drive()
        if not pilihan:
            print("Tidak ada flashdisk terdeteksi. Colokkan flashdisk, atau sebutkan lokasinya:")
            print("   python buat_donggle.py E:\\")
            return 1
        print("Flashdisk terdeteksi:")
        for i, p in enumerate(pilihan, 1):
            print("  %d. %s" % (i, p))
        jawab = input("Pilih nomor flashdisk yang dijadikan donggle: ").strip()
        if not jawab.isdigit() or not (1 <= int(jawab) <= len(pilihan)):
            print("Pilihan tidak valid.")
            return 1
        lokasi = pilihan[int(jawab) - 1]

    if not os.path.isdir(lokasi):
        print("Lokasi tidak ditemukan: %s" % lokasi)
        return 1

    if donggle.baca_pendaftaran() and not timpa:
        jawab = input("Donggle sudah pernah dibuat. Donggle lama akan TIDAK berlaku. Lanjut? (y/N): ")
        if jawab.strip().lower() != "y":
            print("Dibatalkan.")
            return 0

    try:
        h, serial = donggle.daftarkan(lokasi, pakai_serial)
    except (RuntimeError, OSError) as e:
        print("Gagal membuat donggle: %s" % e)
        return 1

    print("\nDonggle berhasil dibuat di %s" % lokasi)
    print("  File kunci  : %s" % os.path.join(lokasi, donggle.NAMA_FILE))
    print("  Serial drive: %s" % (serial if serial else "(tidak dipakai)"))
    print("  Hash server : %s..." % h[:16])
    print("\nJalankan aplikasi:  python app.py   (flashdisk harus tetap tercolok)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
