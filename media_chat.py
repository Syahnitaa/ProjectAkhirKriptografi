"""
Fungsi bantu untuk file & gambar di chat (dipisah dari app.py supaya rapi).

  - baca_gambar()         : buka & validasi gambar upload
  - muat_rahasia()        : kecilkan gambar rahasia sampai muat di gambar penutup
  - nama_aman()           : bersihkan nama file dari pengguna
  - ukuran_manusia()      : 1536 -> "1,5 KB"
"""
import io
import os

from PIL import Image, ImageOps
from werkzeug.utils import secure_filename

MAKS_PIKSEL = 16_000_000        # batas ukuran gambar (lebar x tinggi), cegah gambar raksasa memenuhi memori
FORMAT_GAMBAR = ("PNG", "JPEG")


def baca_gambar(stream, nama_peran="Gambar"):
    """
    Buka gambar PNG/JPG dari upload -> gambar PIL mode RGB.
    Error (ValueError) berisi pesan yang siap ditampilkan ke pengguna.
    """
    try:
        gambar = Image.open(stream)
        format_asli = gambar.format
        lebar, tinggi = gambar.size            # belum membaca piksel, jadi murah
    except Exception:
        raise ValueError("%s harus berupa file PNG atau JPG" % nama_peran)

    if format_asli not in FORMAT_GAMBAR:
        raise ValueError("%s harus berupa file PNG atau JPG" % nama_peran)
    if lebar * tinggi > MAKS_PIKSEL:
        raise ValueError("%s terlalu besar (maksimal %d juta piksel)" % (nama_peran, MAKS_PIKSEL // 1_000_000))

    try:
        return ImageOps.exif_transpose(gambar).convert("RGB")
    except Exception:
        raise ValueError("%s rusak / tidak bisa dibaca" % nama_peran)


def _png(gambar):
    buf = io.BytesIO()
    gambar.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(gambar, kualitas):
    buf = io.BytesIO()
    gambar.save(buf, format="JPEG", quality=kualitas)
    return buf.getvalue()


def muat_rahasia(gambar, batas_byte):
    """
    Ubah gambar rahasia menjadi bytes yang ukurannya <= batas_byte (kapasitas gambar penutup).
      1. Coba PNG dulu (lossless, kualitas utuh).
      2. Kalau terlalu besar: JPEG dengan kualitas diturunkan, lalu ukuran gambar diperkecil.
    Hasil: (bytes, keterangan) — keterangan dipakai untuk memberi tahu pengguna.
    """
    lebar, tinggi = gambar.size

    # Gambar sangat besar langsung ke JPEG: meng-encode PNG puluhan megapiksel lambat dan jarang muat
    if lebar * tinggi <= 4_000_000:
        data = _png(gambar)
        if len(data) <= batas_byte:
            return data, "PNG, kualitas asli"

    skala = 1.0
    for _ in range(14):
        g = gambar if skala == 1.0 else gambar.resize(
            (max(1, int(lebar * skala)), max(1, int(tinggi * skala))), Image.LANCZOS)
        for kualitas in (90, 80, 65, 50):
            data = _jpeg(g, kualitas)
            if len(data) <= batas_byte:
                if skala == 1.0:
                    return data, "dimampatkan ke JPEG (kualitas %d) agar muat" % kualitas
                return data, "dimampatkan ke JPEG dan diperkecil menjadi %dx%d agar muat" % g.size
        skala *= 0.75

    raise ValueError("Gambar penutup terlalu kecil untuk menampung gambar rahasia ini. "
                     "Pakai gambar penutup yang lebih besar.")


def nama_aman(nama, cadangan="berkas"):
    """Nama file dari pengguna -> nama aman (tanpa folder / karakter aneh), maksimal 100 karakter."""
    nama = secure_filename(os.path.basename(nama or "")) or cadangan
    pokok, ekstensi = os.path.splitext(nama)
    return pokok[:90] + ekstensi[:10]


def ukuran_manusia(n):
    """1536 -> '1,5 KB'"""
    n = float(n or 0)
    for satuan in ("B", "KB", "MB", "GB"):
        if n < 1024 or satuan == "GB":
            teks = ("%d" % n) if satuan == "B" else ("%.1f" % n).replace(".", ",")
            return "%s %s" % (teks, satuan)
        n /= 1024
