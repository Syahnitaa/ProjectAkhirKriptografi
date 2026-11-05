# ArtVault — Galeri Karya Digital Aman

Flask + MySQL. Fitur keamanan: bcrypt, verifikasi wajah, AES-GCM, ChaCha20, SHA-256,
Vigenère (super enkripsi chat), steganografi LSB, dan blockchain bukti kepemilikan.

## Menjalankan

```bash
pip install -r requirements.txt
mysql -u root < artvault.sql        # database baru
# ATAU kalau database lama sudah berisi data:  python migrasi.py
python app.py                       # buka http://127.0.0.1:5000
```

Ubah `config.py` sesuai komputer (password MySQL, `SECRET_KEY`, `MASTER_KEY`).
**Jangan ganti `MASTER_KEY` setelah ada data**, semua data terenkripsi tidak bisa dibuka lagi.

## Peta enkripsi

| Data | Algoritma |
|---|---|
| Email, harga, template wajah, nama file chat | AES-GCM |
| Pesan chat (teks & keterangan) | Vigenère → AES-GCM (super enkripsi) |
| **Watermark karya** | AES-GCM → disembunyikan di piksel (LSB) — *baru* |
| File karya (upload) | ChaCha20 |
| **File yang dikirim di chat** | ChaCha20 — *baru* |
| **Gambar rahasia di chat** | AES-GCM → disembunyikan di gambar penutup (LSB) — *baru* |
| Keutuhan file / bukti kepemilikan | SHA-256 + blockchain |

Setiap kegunaan memakai kunci turunan sendiri (SHA-256 dari `MASTER_KEY` + label).

## Skenario demo (±10 menit)

Siapkan 2 browser (atau 1 biasa + 1 incognito): **kreator** dan **kolektor**.
Pastikan `DEBUG_CHAT = True` agar tombol "🔍 lihat enkripsi" muncul. Matikan `DEBUG_JARAK` kalau tidak perlu.

1. **Upload + watermark terenkripsi** (kreator) — upload gambar. Buka *Karya Saya* → download file asli →
   buka **Cek Watermark**, upload PNG itu: tampil bit LSB yang acak, lalu teks hasil dekripsi AES.
   Upload JPG biasa → "tidak ada watermark".
2. **Kirim file** (kolektor) — buka *Chat / Nego* pada karya, klik 📎, pilih file apa saja.
   Klik "🔍 lihat enkripsi": algoritma ChaCha20, nonce, ukuran, awal ciphertext, SHA-256.
   Kreator mengunduh file → isinya identik. Pihak ketiga tidak bisa mengaksesnya.
3. **Kirim gambar rahasia** (kolektor) — klik 🖼️, pilih *gambar penutup* (foto besar) dan *gambar rahasia*.
   Di chat yang terlihat hanya gambar penutup biasa. Klik "🔍 lihat enkripsi": rahasia → AES → LSB.
   Kreator klik **🔓 Buka gambar rahasia** → gambar rahasia muncul. Tombol "⬇ Penutup" mengunduh PNG stego asli
   (bandingkan dengan aslinya: beda warna hanya ±1, tak terlihat).
4. **Integritas** — ubah satu byte file di `storage/chat/` lalu unduh lagi: ditolak (hash SHA-256 tidak cocok).
5. Lanjut ke beli karya → halaman **Blockchain** → *Verifikasi Integritas*.

## Batasan yang perlu diketahui

- Gambar penutup harus cukup besar: kapasitas ≈ (lebar × tinggi × 3) / 8 byte.
  Foto 800×600 muat ±180 KB. Gambar rahasia yang terlalu besar otomatis dikecilkan
  (PNG → JPEG → diperkecil), dan pengirim diberi tahu.
- Gambar penutup yang diunduh harus tetap **PNG**. Jika dikompres jadi JPG / di-screenshot,
  data tersembunyi rusak (sifat LSB).
- Satu file chat maks. `CHAT_MAKS_FILE_MB` (10 MB); total satu upload maks. 15 MB.
- Karya yang diupload **sebelum** fitur ini tetap berisi watermark format lama (teks polos di piksel);
  gambarnya tidak diubah karena hash-nya sudah ada di blockchain. Cek Watermark menandainya "format lama".
