"""
Steganografi LSB: menyembunyikan data di dalam gambar.

Cara kerja:
  Setiap piksel punya angka warna (0-255) untuk R, G, B.
  Kita ganti BIT PALING AKHIR (LSB) angka itu dengan bit data rahasia.
  Perubahannya cuma +-1 dari 255, jadi mata manusia tidak bisa membedakan.

Format data yang disisipkan:
  penanda (2 byte) + panjang data (4 byte) + data
  Penanda = "label" supaya gambar biasa tidak dibaca sebagai data rahasia:
      WM = watermark karya   (isinya teks watermark yang SUDAH dienkripsi AES)
      SI = gambar rahasia    (isinya gambar rahasia yang SUDAH dienkripsi AES)

Steganografi hanya MENYEMBUNYIKAN, bukan mengamankan. Karena itu isi yang disisipkan
selalu dienkripsi AES lebih dulu (di crypto_tools.py): kalau ada orang yang berhasil
membaca bit LSB-nya, yang didapat tetap data acak.

PENTING: gambar harus disimpan sebagai PNG (lossless).
         JPG akan merusak bit-bit tersembunyi ini.
"""
import numpy as np
from PIL import Image

PENANDA_WATERMARK = b"WM"
PENANDA_RAHASIA = b"SI"
PENANDA_LAMA = b"AV"          # format lama: watermark teks polos, panjang 2 byte (hanya dibaca)

HEADER = 6                    # 2 byte penanda + 4 byte panjang


def _piksel(gambar):
    """Semua angka warna gambar (R,G,B,R,G,B,...) sebagai array numpy."""
    return np.frombuffer(gambar.convert("RGB").tobytes(), dtype=np.uint8)


def kapasitas_bytes(gambar):
    """Berapa byte data yang muat di gambar ini (1 bit per angka warna, dikurangi header)."""
    lebar, tinggi = gambar.size
    return (lebar * tinggi * 3) // 8 - HEADER


def sisipkan_bytes(gambar, penanda, data):
    """Sisipkan data (bytes) ke gambar. Hasilnya gambar RGB baru; gambar asli tidak diubah."""
    muatan = penanda + len(data).to_bytes(4, "big") + data
    bit = np.unpackbits(np.frombuffer(muatan, dtype=np.uint8))   # 1 byte -> 8 bit

    piksel = _piksel(gambar).copy()
    if bit.size > piksel.size:
        raise ValueError("Gambar terlalu kecil untuk menyimpan data tersembunyi "
                         "(butuh %d byte, kapasitas %d byte)" % (len(data), kapasitas_bytes(gambar)))

    piksel[:bit.size] = (piksel[:bit.size] & 0xFE) | bit         # ganti bit terakhir
    return Image.frombytes("RGB", gambar.size, piksel.tobytes())


def ambil_bytes(gambar, penanda):
    """Baca data tersembunyi dari gambar. Hasil None kalau tidak ada / bukan milik kita."""
    piksel = _piksel(gambar)
    if piksel.size < HEADER * 8:
        return None

    header = np.packbits(piksel[:HEADER * 8] & 1).tobytes()
    if header[:2] != penanda:
        return None

    panjang = int.from_bytes(header[2:6], "big")
    akhir = (HEADER + panjang) * 8
    if akhir > piksel.size:                  # panjang tidak masuk akal -> bukan data kita
        return None
    return np.packbits(piksel[HEADER * 8:akhir] & 1).tobytes()


def ambil_teks_lama(gambar):
    """
    Baca watermark FORMAT LAMA (teks polos, tanpa enkripsi) dari karya yang diupload
    sebelum fitur enkripsi watermark ada. Hasil None kalau tidak ada.
    """
    piksel = _piksel(gambar)
    if piksel.size < 32:
        return None
    header = np.packbits(piksel[:32] & 1).tobytes()
    if header[:2] != PENANDA_LAMA:
        return None
    panjang = int.from_bytes(header[2:4], "big")
    if (4 + panjang) * 8 > piksel.size:
        return None
    try:
        return np.packbits(piksel[32:32 + panjang * 8] & 1).tobytes().decode("utf-8")
    except UnicodeDecodeError:
        return None
