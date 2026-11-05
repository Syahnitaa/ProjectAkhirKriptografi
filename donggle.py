"""
Donggle (kunci fisik USB / flashdisk) untuk ArtVault.

Aplikasi HANYA bisa hidup dan dipakai kalau donggle yang sah sedang tercolok.

Cara kerja:
  1. Saat pendaftaran donggle (python buat_donggle.py), dibuat TOKEN acak.
       - TOKEN ditulis ke flashdisk sebagai file  artvault.key
       - Server hanya menyimpan HASH = SHA-256(token | serial_volume) di donggle.json
         (token aslinya tidak pernah disimpan di server)
  2. Saat aplikasi start dan di setiap request, server memindai flashdisk yang tercolok,
     membaca artvault.key, menghitung hash yang sama, lalu membandingkannya (constant-time).
  3. Kalau flashdisk dicabut / tidak cocok -> aplikasi terkunci dan pengguna otomatis logout.

Serial volume (Windows): nomor seri unik partisi flashdisk. Dengan serial ikut di hash,
file artvault.key yang DISALIN ke flashdisk lain tidak akan diterima (clone ditolak).
"""
import hashlib
import hmac
import json
import os
import string
import time

import config

NAMA_FILE = "artvault.key"
MAGIC = "ARTVAULT-DONGGLE"
FILE_DAFTAR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "donggle.json")

HANYA_REMOVABLE = getattr(config, "DONGGLE_HANYA_REMOVABLE", True)
LOKASI_TAMBAHAN = getattr(config, "DONGGLE_LOKASI_TAMBAHAN", [])
CACHE_DETIK = getattr(config, "DONGGLE_CACHE_DETIK", 2)

_cache = {"waktu": 0.0, "hasil": None}


# =====================================================
# Mencari flashdisk yang tercolok
# =====================================================
def lokasi_drive():
    """Daftar folder akar drive eksternal yang tercolok (flashdisk)."""
    hasil = []
    if os.name == "nt":                                        # Windows: E:\, F:\, ...
        import ctypes
        kernel = ctypes.windll.kernel32
        bitmask = kernel.GetLogicalDrives()
        for i, huruf in enumerate(string.ascii_uppercase):
            if bitmask & (1 << i):
                akar = huruf + ":\\"
                tipe = kernel.GetDriveTypeW(akar)              # 2 = removable, 3 = fixed
                if tipe == 2 or (not HANYA_REMOVABLE and tipe == 3 and huruf != "C"):
                    hasil.append(akar)
    else:                                                      # Linux / macOS
        for dasar in ("/media", "/run/media", "/Volumes", "/mnt"):
            if not os.path.isdir(dasar):
                continue
            for nama in sorted(os.listdir(dasar)):
                p1 = os.path.join(dasar, nama)
                if os.path.isdir(p1):
                    hasil.append(p1)
                    try:                                       # /media/<user>/<LABEL>
                        for sub in sorted(os.listdir(p1)):
                            p2 = os.path.join(p1, sub)
                            if os.path.isdir(p2):
                                hasil.append(p2)
                    except OSError:
                        pass
    for p in LOKASI_TAMBAHAN:                                  # untuk testing
        if os.path.isdir(p):
            hasil.append(p)
    return hasil


def serial_volume(lokasi):
    """Nomor seri partisi (Windows). Di OS lain: None."""
    if os.name != "nt":
        return None
    import ctypes
    drive = os.path.splitdrive(os.path.abspath(lokasi))[0]
    if not drive:
        return None
    serial = ctypes.c_uint32(0)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(drive + "\\"), None, 0, ctypes.byref(serial), None, None, None, 0)
    return "%08X" % serial.value if ok else None


# =====================================================
# Hash token & data pendaftaran
# =====================================================
def hitung_hash(token, serial):
    return hashlib.sha256(("%s|%s" % (token, serial or "")).encode()).hexdigest()


def baca_pendaftaran():
    """Isi donggle.json (hash donggle yang sah) atau None kalau belum didaftarkan."""
    try:
        with open(FILE_DAFTAR, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data.get("hash"), str):
            return data
    except (OSError, ValueError):
        pass
    return None


def baca_token(lokasi):
    """Baca token dari artvault.key di flashdisk. None kalau file tidak ada / formatnya salah."""
    try:
        with open(os.path.join(lokasi, NAMA_FILE), "r", encoding="utf-8") as f:
            baris = [b.strip() for b in f.read().splitlines() if b.strip()]
        if len(baris) >= 2 and baris[0] == MAGIC:
            return baris[1]
    except (OSError, UnicodeDecodeError):
        pass
    return None


def daftarkan(lokasi, pakai_serial=True):
    """
    Jadikan folder/drive 'lokasi' sebagai donggle: tulis artvault.key, simpan hash di donggle.json.
    Hasil: (hash, serial yang dipakai).
    """
    import secrets
    token = secrets.token_hex(32)
    serial = serial_volume(lokasi) if pakai_serial else None
    if pakai_serial and serial is None and os.name == "nt":
        raise RuntimeError("Serial flashdisk tidak terbaca. Coba lagi atau pakai --tanpa-serial")
    pakai_serial = serial is not None

    with open(os.path.join(lokasi, NAMA_FILE), "w", encoding="utf-8") as f:
        f.write("%s\n%s\n" % (MAGIC, token))

    h = hitung_hash(token, serial)
    with open(FILE_DAFTAR, "w", encoding="utf-8") as f:
        json.dump({"hash": h, "pakai_serial": pakai_serial}, f, indent=2)
    return h, serial


# =====================================================
# Pengecekan utama
# =====================================================
def _periksa():
    daftar = baca_pendaftaran()
    if daftar is None:
        return False, "Donggle belum didaftarkan. Jalankan:  python buat_donggle.py", None

    ada_file = False
    for lokasi in lokasi_drive():
        token = baca_token(lokasi)
        if token is None:
            continue
        ada_file = True
        serial = serial_volume(lokasi) if daftar.get("pakai_serial") else None
        if daftar.get("pakai_serial") and serial is None:
            continue
        if hmac.compare_digest(hitung_hash(token, serial), daftar["hash"]):
            return True, "Donggle terdeteksi di %s" % lokasi, lokasi

    if ada_file:
        return False, "Flashdisk terdeteksi, tetapi BUKAN donggle ArtVault yang sah (kunci tidak cocok).", None
    return False, "Donggle tidak ditemukan. Colokkan flashdisk donggle ArtVault ke komputer.", None


def cek(paksa=False):
    """
    Cek apakah donggle sah sedang tercolok. Hasil: (ok, pesan, lokasi).
    Hasil di-cache beberapa detik supaya tidak memindai drive di setiap request.
    """
    sekarang = time.time()
    if not paksa and _cache["hasil"] is not None and sekarang - _cache["waktu"] < CACHE_DETIK:
        return _cache["hasil"]
    hasil = _periksa()
    _cache["waktu"], _cache["hasil"] = sekarang, hasil
    return hasil
