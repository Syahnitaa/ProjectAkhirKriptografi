# Pengaturan aplikasi - ubah sesuai komputer kalian

# Koneksi MySQL
DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""          # isi kalau MySQL kalian pakai password
DB_NAME = "artvault"

# Kunci rahasia (ganti dengan teks acak buatan sendiri)
SECRET_KEY = "ganti-teks-acak-ini"          # untuk session login Flask
MASTER_KEY = "ganti-kunci-enkripsi-ini"     # untuk enkripsi data (AES)

# ---------- Face recognition ----------
REQUIRE_FACE = True       # True = daftar & login wajib wajah. False = dilewati (testing)
FACE_THRESHOLD = 0.45     # batas jarak wajah saat login. Makin KECIL makin ketat
FACE_ENROLL_MAX = 0.40    # batas konsistensi rekaman wajah saat daftar
FACE_MAX_GAGAL = 3        # gagal verifikasi wajah sebanyak ini -> harus login ulang dari awal
DEBUG_JARAK = True        # True = tampilkan angka jarak (untuk kalibrasi). Matikan saat demo akhir

# ---------- Chat ----------
VIGENERE_KEY = "ARTVAULT"   # kunci Vigenere (HURUF A-Z saja), tahap 1 super enkripsi chat
DEBUG_CHAT = True           # True = chat menampilkan tombol "lihat enkripsi" (untuk demo). Matikan jika tak perlu
CHAT_MAKS_FILE_MB = 10      # ukuran maksimal satu file yang dikirim lewat chat (MB, maksimal total upload 15 MB)
