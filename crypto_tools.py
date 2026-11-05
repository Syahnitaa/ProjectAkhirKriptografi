"""
Kumpulan fungsi kriptografi ArtVault.
  - AES-GCM   : teks pendek (email, harga, chat), teks watermark, dan gambar rahasia di chat
  - ChaCha20  : file karya & file kiriman chat (sengaja BEDA dari algoritma teks)
  - SHA-256   : sidik jari (hash) file, dipakai blockchain & cek keutuhan
  - Vigenere  : sandi klasik, tahap 1 SUPER ENKRIPSI chat
  - Super enkripsi chat = Vigenere (klasik) -> AES-GCM (modern)

Tiap kegunaan memakai KUNCI TURUNAN sendiri (SHA-256 dari MASTER_KEY + label),
jadi kunci untuk teks, file, watermark, dan gambar rahasia tidak saling tertukar.
"""
import base64
import hashlib

from Crypto.Cipher import AES, ChaCha20

import config

# Kunci 32 byte dibuat dari MASTER_KEY di config.py
KEY = hashlib.sha256(config.MASTER_KEY.encode()).digest()                  # untuk AES
KEY_FILE = hashlib.sha256(("file-" + config.MASTER_KEY).encode()).digest()  # untuk ChaCha20
KEY_WATERMARK = hashlib.sha256(("wm-" + config.MASTER_KEY).encode()).digest()   # AES: teks watermark
KEY_GAMBAR = hashlib.sha256(("img-" + config.MASTER_KEY).encode()).digest()     # AES: gambar rahasia chat

AES_OVERHEAD = 32     # nonce (16 byte) + tag (16 byte) yang ditambahkan AES-GCM

# Kunci Vigenere (huruf saja). Diatur di config.py; kalau belum ada pakai bawaan.
KEY_VIGENERE = getattr(config, "VIGENERE_KEY", "ARTVAULT")


# ---------- AES (teks) ----------
def aes_encrypt(teks):
    """Teks biasa -> teks acak (base64)."""
    cipher = AES.new(KEY, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(teks.encode())
    # Gabungkan nonce + tag + ciphertext supaya bisa didekripsi lagi
    return base64.b64encode(cipher.nonce + tag + ciphertext).decode()


def aes_decrypt(data_base64):
    """Teks acak (base64) -> teks biasa."""
    mentah = base64.b64decode(data_base64)
    nonce, tag, ciphertext = mentah[:16], mentah[16:32], mentah[32:]
    cipher = AES.new(KEY, AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag).decode()


# ---------- AES (data biner: watermark & gambar rahasia) ----------
def _aes_bytes_enc(data, key):
    """bytes -> nonce(16) + tag(16) + ciphertext (bytes mentah, bukan base64)."""
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(data)
    return cipher.nonce + tag + ciphertext


def _aes_bytes_dec(blob, key):
    """Kebalikan _aes_bytes_enc. Error kalau kunci salah atau data diubah (GCM)."""
    if len(blob) < AES_OVERHEAD:
        raise ValueError("Data AES terlalu pendek")
    nonce, tag, ciphertext = blob[:16], blob[16:32], blob[32:]
    return AES.new(key, AES.MODE_GCM, nonce=nonce).decrypt_and_verify(ciphertext, tag)


def aes_encrypt_gambar(data):
    """Gambar rahasia (bytes) -> blob AES-GCM yang siap disisipkan lewat steganografi."""
    return _aes_bytes_enc(data, KEY_GAMBAR)


def aes_decrypt_gambar(blob):
    return _aes_bytes_dec(blob, KEY_GAMBAR)


def watermark_encrypt(teks):
    """Teks watermark -> blob AES-GCM. Blob inilah yang disisipkan ke piksel (LSB)."""
    return _aes_bytes_enc(teks.encode("utf-8"), KEY_WATERMARK)


def watermark_decrypt(blob):
    return _aes_bytes_dec(blob, KEY_WATERMARK).decode("utf-8")


def hex_ringkas(data, n=24):
    """Cuplikan hex untuk tampilan demo, mis. '8f02c1…' (dipotong jika lebih dari n byte)."""
    teks = data[:n].hex()
    return teks + ("…" if len(data) > n else "")


# ---------- ChaCha20 (file) ----------
def chacha_encrypt(data):
    """Isi file (bytes) -> (nonce, data terenkripsi). Nonce disimpan di database."""
    cipher = ChaCha20.new(key=KEY_FILE)
    nonce_b64 = base64.b64encode(cipher.nonce).decode()
    return nonce_b64, cipher.encrypt(data)


def chacha_decrypt(data_terenkripsi, nonce_b64):
    """Kebalikan chacha_encrypt."""
    cipher = ChaCha20.new(key=KEY_FILE, nonce=base64.b64decode(nonce_b64))
    return cipher.decrypt(data_terenkripsi)


# ---------- SHA-256 ----------
def sha256_hex(data):
    """Sidik jari file. Isi file berubah 1 bit saja, hasilnya beda total."""
    return hashlib.sha256(data).hexdigest()


# ---------- Vigenere (sandi klasik) ----------
def _vigenere(teks, kunci, arah):
    """
    arah = +1 untuk enkripsi, -1 untuk dekripsi.
    Setiap HURUF digeser sejauh huruf kunci (A=0, B=1, ... Z=25), berulang.
    Huruf besar/kecil dipertahankan. Angka, spasi, emoji, tanda baca TIDAK diubah,
    dan tidak memajukan posisi kunci.
    """
    kunci = [ord(c) - 65 for c in kunci.upper() if "A" <= c <= "Z"]
    if not kunci:
        raise ValueError("Kunci Vigenere harus berisi huruf A-Z")

    hasil = []
    posisi = 0                                   # posisi huruf kunci yang dipakai
    for ch in teks:
        if "A" <= ch <= "Z":
            awal = 65
        elif "a" <= ch <= "z":
            awal = 97
        else:
            hasil.append(ch)                     # bukan huruf -> biarkan
            continue
        geser = kunci[posisi % len(kunci)] * arah
        hasil.append(chr((ord(ch) - awal + geser) % 26 + awal))
        posisi += 1
    return "".join(hasil)


def vigenere_encrypt(teks, kunci=None):
    return _vigenere(teks, kunci or KEY_VIGENERE, +1)


def vigenere_decrypt(teks, kunci=None):
    return _vigenere(teks, kunci or KEY_VIGENERE, -1)


# ---------- SUPER ENKRIPSI (chat): Vigenere -> AES ----------
def super_encrypt(teks):
    """Pesan asli -> Vigenere (klasik) -> AES-GCM (modern) -> base64 untuk disimpan di DB."""
    return aes_encrypt(vigenere_encrypt(teks))


def super_decrypt(data_base64):
    """Kebalikannya: AES dibuka dulu, baru Vigenere dibuka."""
    return vigenere_decrypt(aes_decrypt(data_base64))
