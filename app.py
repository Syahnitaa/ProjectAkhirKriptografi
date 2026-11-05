import base64
import io
import json
import math
import os
import re
import secrets
from datetime import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect, session,
                   flash, jsonify, send_file)
from PIL import Image, ImageOps
from werkzeug.utils import secure_filename
import bcrypt

import config
import donggle
from db import get_db
from crypto_tools import (aes_encrypt, aes_decrypt, aes_encrypt_gambar,
                          aes_decrypt_gambar, chacha_encrypt, chacha_decrypt,
                          sha256_hex, super_encrypt, vigenere_decrypt,
                          watermark_encrypt, watermark_decrypt, hex_ringkas,
                          AES_OVERHEAD)
from stego import (sisipkan_bytes, ambil_bytes, ambil_teks_lama, kapasitas_bytes,
                   PENANDA_WATERMARK, PENANDA_RAHASIA)
from media_chat import baca_gambar, muat_rahasia, nama_aman, ukuran_manusia
import blockchain

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024    # batas upload 15 MB

# Folder penyimpanan
STORAGE_DIR = os.path.join(app.root_path, "storage", "encrypted")   # file asli terenkripsi (TIDAK bisa diakses lewat web)
CHAT_DIR = os.path.join(app.root_path, "storage", "chat")           # file & gambar rahasia dari chat (TIDAK bisa diakses lewat web)
PREVIEW_DIR = os.path.join(app.root_path, "static", "previews")     # gambar pratinjau (publik)
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(CHAT_DIR, exist_ok=True)
os.makedirs(PREVIEW_DIR, exist_ok=True)

MAKS_FILE_CHAT = getattr(config, "CHAT_MAKS_FILE_MB", 10) * 1024 * 1024   # batas satu file di chat


# =====================================================
# DONGGLE: aplikasi hanya hidup & bisa dipakai kalau flashdisk donggle tercolok
# =====================================================
if config.REQUIRE_DONGGLE:
    _ok, _pesan, _lokasi = donggle.cek(paksa=True)
    if not _ok:
        raise SystemExit("\n[DONGGLE] " + _pesan + "\nAplikasi tidak dapat dihidupkan.\n")
    print("[DONGGLE] " + _pesan)

POLA_AJAX = re.compile(r"^/chat/\d+/\d+/(pesan|kirim|kirim-file|kirim-rahasia)$")


@app.before_request
def wajib_donggle():
    """Setiap request: donggle harus masih tercolok. Kalau dicabut -> logout paksa & halaman terkunci."""
    if not config.REQUIRE_DONGGLE or request.endpoint == "static":
        return None
    ok, pesan, _ = donggle.cek()
    if ok:
        return None
    session.clear()
    if request.is_json or POLA_AJAX.match(request.path):
        return jsonify(ok=False, pesan=pesan, redirect="/login"), 403
    return render_template("donggle.html", pesan=pesan), 403


@app.context_processor
def info_donggle():
    """Kirim status donggle ke semua template (ditampilkan di header)."""
    if not config.REQUIRE_DONGGLE:
        return {"donggle_lokasi": None}
    ok, _, lokasi = donggle.cek()
    return {"donggle_lokasi": lokasi if ok else None}


@app.after_request
def header_aman(respons):
    """Browser dilarang menebak jenis file (mencegah file unggahan dijalankan sebagai HTML/JS)."""
    respons.headers["X-Content-Type-Options"] = "nosniff"
    return respons


@app.errorhandler(413)
def terlalu_besar(_):
    """Upload melebihi MAX_CONTENT_LENGTH. Chat dijawab JSON, halaman lain lewat flash."""
    pesan = "Ukuran upload melebihi batas 15 MB"
    if request.path.startswith("/chat"):
        return jsonify(ok=False, pesan=pesan), 413
    flash(pesan)
    return redirect(request.referrer or "/")


def wajib_login(fungsi):
    """Pasang di atas route: halaman hanya bisa dibuka kalau sudah login penuh."""
    @wraps(fungsi)
    def pembungkus(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return fungsi(*args, **kwargs)
    return pembungkus


def wajib_role(role):
    """Pasang di bawah @wajib_login: halaman hanya untuk role tertentu (creator / collector)."""
    def dekorator(fungsi):
        @wraps(fungsi)
        def pembungkus(*args, **kwargs):
            if session.get("role") != role:
                flash("Halaman ini hanya untuk %s" % ("kreator" if role == "creator" else "kolektor"))
                return redirect("/")
            return fungsi(*args, **kwargs)
        return pembungkus
    return dekorator


@app.template_filter("rupiah")
def rupiah(angka):
    """500000 -> Rp 500.000"""
    return "Rp " + f"{int(angka):,}".replace(",", ".")


# =====================================================
# Fungsi bantu
# =====================================================
def selesai_login(user):
    """Tandai pengguna sudah login sepenuhnya (password + wajah beres)."""
    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]


def ambil_user_pending():
    """Ambil data user yang sudah benar password tapi belum verifikasi wajah."""
    user_id = session.get("pending_id")
    if not user_id:
        return None
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
            return cur.fetchone()
    finally:
        db.close()


def jarak_wajah(a, b):
    """Jarak Euclidean antara 2 vektor wajah. Makin kecil = makin mirip."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def vektor_valid(v):
    """Pastikan v adalah daftar 128 angka (bentuk data wajah yang benar)."""
    return (isinstance(v, list) and len(v) == 128
            and all(isinstance(x, (int, float)) for x in v))


def proses_rekaman_wajah(daftar):
    """
    Cek rekaman wajah saat DAFTAR. Hasil: (rata-rata, pesan_error).
    Rekaman harus banyak dan konsisten, supaya data wajah yang disimpan berkualitas.
    """
    if not isinstance(daftar, list) or not (5 <= len(daftar) <= 10):
        return None, "Rekaman wajah kurang, silakan rekam ulang"
    if not all(vektor_valid(d) for d in daftar):
        return None, "Data wajah tidak valid"

    rata2 = [sum(d[i] for d in daftar) / len(daftar) for i in range(128)]

    # Setiap rekaman harus dekat dengan rata-ratanya
    for d in daftar:
        if jarak_wajah(d, rata2) > config.FACE_ENROLL_MAX:
            return None, "Rekaman wajah tidak konsisten (bergerak / terlalu gelap), rekam ulang"
    return rata2, None


# =====================================================
# Halaman utama
# =====================================================
@app.route("/")
@wajib_login
def home():
    karya = ambil_karya("WHERE a.status = 'available'", ())
    return render_template("home.html", karya=karya)


# =====================================================
# Register (data akun + wajah, sekaligus dalam satu langkah)
# =====================================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", butuh_wajah=config.REQUIRE_FACE)

    data = request.get_json() or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip()
    password = str(data.get("password", ""))
    role = data.get("role")

    if not username or not email or not password:
        return jsonify(ok=False, pesan="Semua kolom wajib diisi")
    if role not in ("creator", "collector"):
        return jsonify(ok=False, pesan="Role tidak valid")

    # Wajah WAJIB direkam saat daftar. Tanpa wajah = akun tidak dibuat.
    face_enc = None
    if config.REQUIRE_FACE:
        rata2, error = proses_rekaman_wajah(data.get("descriptors"))
        if error:
            return jsonify(ok=False, pesan=error)
        face_enc = aes_encrypt(json.dumps(rata2))   # vektor wajah dienkripsi AES

    # Password di-hash (bcrypt), email dienkripsi (AES)
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    email_enc = aes_encrypt(email)

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE username=%s", (username,))
            if cur.fetchone():
                return jsonify(ok=False, pesan="Username sudah dipakai")

            cur.execute(
                "INSERT INTO users (username, email_enc, password_hash, role, face_template_enc) "
                "VALUES (%s, %s, %s, %s, %s)",
                (username, email_enc, password_hash, role, face_enc),
            )
        db.commit()
    finally:
        db.close()

    flash("Registrasi berhasil, silakan login")
    return jsonify(ok=True, pesan="Registrasi berhasil", redirect="/login")


# =====================================================
# Login TAHAP 1: username + password
# =====================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        db = get_db()
        try:
            with db.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE username=%s", (username,))
                user = cur.fetchone()
        finally:
            db.close()

        # Cocokkan password dengan hash di database
        if user and bcrypt.checkpw(password.encode(), user["password_hash"].encode()):

            # Mode testing: wajah dilewati
            if not config.REQUIRE_FACE:
                selesai_login(user)
                return redirect("/")

            # Akun tanpa data wajah tidak boleh login (wajah hanya didaftarkan saat register)
            if user["face_template_enc"] is None:
                flash("Akun ini tidak punya data wajah. Silakan daftar ulang.")
                return redirect("/login")

            # Password benar, tapi BELUM dianggap login.
            # Simpan dulu sebagai "pending", lanjut ke verifikasi wajah.
            session.clear()
            session["pending_id"] = user["id"]
            return redirect("/face/verify")

        flash("Username atau password salah")
        return redirect("/login")

    return render_template("login.html")


# =====================================================
# Login TAHAP 2: verifikasi wajah
# =====================================================
@app.route("/face/verify", methods=["GET", "POST"])
def face_verify():
    user = ambil_user_pending()
    if not user or user["face_template_enc"] is None:
        return redirect("/login")

    if request.method == "GET":
        return render_template("face_verify.html")

    data = request.get_json() or {}
    daftar = data.get("descriptors")

    # Harus 3 rekaman wajah dari kamera
    if not isinstance(daftar, list) or len(daftar) != 3 or not all(vektor_valid(d) for d in daftar):
        return jsonify(ok=False, pesan="Data wajah tidak valid")

    # Dekripsi vektor wajah tersimpan, lalu bandingkan
    tersimpan = json.loads(aes_decrypt(user["face_template_enc"]))
    terjauh = max(jarak_wajah(tersimpan, d) for d in daftar)

    # SEMUA rekaman harus cocok (bukan cuma salah satu)
    if terjauh < config.FACE_THRESHOLD:
        selesai_login(user)
        return jsonify(ok=True, redirect="/",
                       pesan="Wajah cocok!" + (" (jarak %.2f)" % terjauh if config.DEBUG_JARAK else ""))

    # Gagal: hitung percobaan, kalau kebanyakan harus login ulang dari awal
    gagal = session.get("gagal_wajah", 0) + 1
    session["gagal_wajah"] = gagal
    info = " (jarak %.2f)" % terjauh if config.DEBUG_JARAK else ""

    if gagal >= config.FACE_MAX_GAGAL:
        session.clear()
        flash("Verifikasi wajah gagal %d kali. Silakan login ulang." % config.FACE_MAX_GAGAL)
        return jsonify(ok=False, redirect="/login",
                       pesan="Terlalu banyak percobaan gagal" + info)

    return jsonify(ok=False,
                   pesan="Wajah tidak cocok%s. Sisa percobaan: %d" % (info, config.FACE_MAX_GAGAL - gagal))


# =====================================================
# Karya digital: ambil data
# =====================================================
def ambil_karya(kondisi, parameter):
    """Ambil daftar karya + nama kreator/pemilik. Harga didekripsi (AES) di sini."""
    sql = ("SELECT a.*, u.username AS creator_name, o.username AS owner_name "
           "FROM artworks a "
           "JOIN users u ON a.creator_id = u.id "
           "JOIN users o ON a.owner_id = o.id "
           + kondisi + " ORDER BY a.created_at DESC")
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(sql, parameter)
            hasil = cur.fetchall()
    finally:
        db.close()

    for k in hasil:
        k["harga"] = int(aes_decrypt(k["price_enc"]))    # harga di DB terenkripsi
    return hasil


@app.route("/karya-saya")
@wajib_login
@wajib_role("creator")
def karya_saya():
    uid = session["user_id"]
    karya = ambil_karya("WHERE a.creator_id = %s OR a.owner_id = %s", (uid, uid))
    return render_template("karya_saya.html", karya=karya)


# =====================================================
# Upload karya (khusus kreator)
#   1. Watermark: enkripsi AES -> sisipkan tersembunyi (steganografi LSB)
#   2. Hash file                       -> SHA-256
#   3. Enkripsi file asli              -> ChaCha20
#   4. Buat pratinjau                  -> untuk galeri
#   5. Enkripsi harga                  -> AES
#   6. Catat block UPLOAD              -> blockchain
# =====================================================
@app.route("/upload", methods=["GET", "POST"])
@wajib_login
@wajib_role("creator")
def upload():
    if request.method == "GET":
        return render_template("upload.html")

    judul = request.form.get("title", "").strip()
    deskripsi = request.form.get("description", "").strip()
    harga = request.form.get("price", "").strip()
    berkas = request.files.get("image")

    if not judul or not berkas or berkas.filename == "":
        flash("Judul dan gambar wajib diisi")
        return redirect("/upload")
    if not harga.isdigit() or int(harga) <= 0:
        flash("Harga harus berupa angka lebih dari 0")
        return redirect("/upload")

    # Pastikan benar-benar gambar PNG / JPG
    try:
        gambar = Image.open(berkas.stream)
        if gambar.format not in ("PNG", "JPEG"):
            raise ValueError("format tidak didukung")
        gambar = ImageOps.exif_transpose(gambar).convert("RGB")
    except Exception:
        flash("File harus berupa gambar PNG atau JPG")
        return redirect("/upload")

    # 1. Watermark: teks dienkripsi AES dulu, BARU disisipkan ke piksel (steganografi LSB).
    #    Jadi yang tersembunyi di gambar adalah data acak, bukan teks yang bisa langsung dibaca.
    watermark = "Dibuat oleh %s - %s" % (session["username"],
                                         datetime.now().strftime("%Y-%m-%d %H:%M"))
    watermark_blob = watermark_encrypt(watermark)
    try:
        gambar_wm = sisipkan_bytes(gambar, PENANDA_WATERMARK, watermark_blob)
    except ValueError:
        flash("Gambar terlalu kecil untuk disisipi watermark")
        return redirect("/upload")

    # Simpan ke PNG (lossless, supaya watermark tidak rusak)
    buffer = io.BytesIO()
    gambar_wm.save(buffer, format="PNG")
    data_asli = buffer.getvalue()

    # 2. Hash file
    file_hash = sha256_hex(data_asli)

    # 3. Enkripsi file asli dengan ChaCha20, simpan di folder storage
    nonce, data_enc = chacha_encrypt(data_asli)
    nama = secrets.token_hex(16)                          # nama file acak
    with open(os.path.join(STORAGE_DIR, nama + ".bin"), "wb") as f:
        f.write(data_enc)

    # 4. Pratinjau (kecil, JPG) untuk ditampilkan di galeri
    pratinjau = gambar.copy()
    pratinjau.thumbnail((600, 600))
    pratinjau.save(os.path.join(PREVIEW_DIR, nama + ".jpg"), "JPEG", quality=80)

    # 5. Harga dienkripsi AES
    harga_enc = aes_encrypt(harga)

    nama_asli = (secure_filename(os.path.splitext(berkas.filename)[0]) or "karya") + ".png"

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO artworks (creator_id, owner_id, title, description, "
                "preview_path, file_path, file_nonce, original_filename, file_hash, "
                "watermark_enc, price_enc) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (session["user_id"], session["user_id"], judul, deskripsi,
                 "previews/" + nama + ".jpg", nama + ".bin", nonce, nama_asli,
                 file_hash, base64.b64encode(watermark_blob).decode(), harga_enc),
            )
            # 6. Catat ke blockchain (satu transaksi dengan INSERT karya di atas)
            blockchain.catat_upload(cur, cur.lastrowid, judul, file_hash,
                                    session["user_id"], session["username"])
        db.commit()
    finally:
        db.close()

    flash("Karya berhasil diupload dan dicatat di blockchain!")
    return redirect("/karya-saya")


# =====================================================
# Detail karya + BELI
# =====================================================
@app.route("/karya/<int:karya_id>")
@wajib_login
def detail_karya(karya_id):
    hasil = ambil_karya("WHERE a.id = %s", (karya_id,))
    if not hasil:
        flash("Karya tidak ditemukan")
        return redirect("/")

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM blockchain WHERE artwork_id=%s ORDER BY block_index", (karya_id,))
            riwayat = cur.fetchall()
    finally:
        db.close()
    for b in riwayat:
        b["isi"] = json.loads(b["data"])
    return render_template("detail.html", k=hasil[0], riwayat=riwayat)


@app.route("/karya/<int:karya_id>/beli", methods=["POST"])
@wajib_login
@wajib_role("collector")
def beli(karya_id):
    """
    Beli karya. Satu transaksi database (semua berhasil atau semua batal):
      1. kepemilikan karya pindah ke pembeli, status jadi 'sold'
      2. riwayat dicatat di tabel transactions
      3. block TRANSFER ditambahkan ke blockchain
    (pembayaran hanya simulasi, belum ada payment gateway)
    """
    pembeli_id = session["user_id"]
    db = get_db()
    try:
        with db.cursor() as cur:
            # FOR UPDATE: kunci baris karya, supaya 2 pembeli tidak bisa membeli bersamaan
            cur.execute("SELECT * FROM artworks WHERE id=%s FOR UPDATE", (karya_id,))
            k = cur.fetchone()
            if not k:
                flash("Karya tidak ditemukan")
                return redirect("/")
            if k["status"] != "available":
                flash("Maaf, karya ini sudah terjual")
                return redirect("/karya/%d" % karya_id)
            if k["owner_id"] == pembeli_id:
                flash("Karya ini sudah milikmu")
                return redirect("/karya/%d" % karya_id)

            penjual_id = k["owner_id"]
            cur.execute("SELECT username FROM users WHERE id=%s", (penjual_id,))
            penjual = cur.fetchone()["username"]

            cur.execute("UPDATE artworks SET owner_id=%s, status='sold' WHERE id=%s",
                        (pembeli_id, karya_id))
            cur.execute("INSERT INTO transactions (artwork_id, buyer_id, seller_id, price_enc) "
                        "VALUES (%s, %s, %s, %s)",
                        (karya_id, pembeli_id, penjual_id, k["price_enc"]))
            blockchain.catat_transfer(cur, karya_id, k["title"], k["file_hash"],
                                      penjual_id, penjual, pembeli_id, session["username"])
        db.commit()
    finally:
        db.close()

    flash("Pembelian berhasil! Karya kini milikmu dan kepemilikan tercatat di blockchain.")
    return redirect("/koleksi")


@app.route("/koleksi")
@wajib_login
@wajib_role("collector")
def koleksi():
    karya = ambil_karya("WHERE a.owner_id = %s", (session["user_id"],))
    return render_template("karya_saya.html", karya=karya, judul="Koleksi Saya",
                           kosong="Belum ada karya yang kamu beli. Lihat Galeri untuk mulai membeli.")


# =====================================================
# Blockchain: daftar block + verifikasi integritas
# =====================================================
@app.route("/blockchain", methods=["GET", "POST"])
@wajib_login
def halaman_blockchain():
    db = get_db()
    try:
        with db.cursor() as cur:
            hasil = None
            if request.method == "POST":                     # tombol "Verifikasi"
                hasil = blockchain.verifikasi(cur, STORAGE_DIR)
                blok = hasil["blok"]
            else:
                blok = blockchain.ambil_semua(cur)
    finally:
        db.close()
    return render_template("blockchain.html", blok=blok, hasil=hasil)


# =====================================================
# Download file asli (hanya PEMILIK karya)
# =====================================================
@app.route("/karya/<int:karya_id>/download")
@wajib_login
def download(karya_id):
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT * FROM artworks WHERE id=%s", (karya_id,))
            k = cur.fetchone()
    finally:
        db.close()

    if not k or k["owner_id"] != session["user_id"]:
        flash("Kamu tidak berhak mengunduh karya ini")
        return redirect("/")

    # Baca file terenkripsi, lalu dekripsi ChaCha20
    with open(os.path.join(STORAGE_DIR, k["file_path"]), "rb") as f:
        data_enc = f.read()
    data = chacha_decrypt(data_enc, k["file_nonce"])

    # Cek keutuhan: hash harus sama dengan saat upload
    if sha256_hex(data) != k["file_hash"]:
        flash("File rusak atau telah diubah (hash tidak cocok)!")
        return redirect("/karya-saya")

    return send_file(io.BytesIO(data), mimetype="image/png",
                     as_attachment=True, download_name=k["original_filename"])


# =====================================================
# Cek watermark: upload gambar, baca & dekripsi watermark tersembunyinya
#   piksel (LSB) -> blob terenkripsi -> dekripsi AES -> teks watermark
# =====================================================
@app.route("/watermark", methods=["GET", "POST"])
@wajib_login
def cek_watermark():
    hasil = None
    if request.method == "POST":
        berkas = request.files.get("image")
        try:
            gambar = Image.open(berkas.stream)
            gambar.load()
        except Exception:
            flash("File harus berupa gambar")
            return render_template("watermark.html", hasil=None)

        hasil = {"status": "kosong"}
        blob = ambil_bytes(gambar, PENANDA_WATERMARK)
        if blob is not None:
            hasil["mentah"] = hex_ringkas(blob, 32)       # bit LSB apa adanya: data acak
            hasil["ukuran"] = len(blob)
            try:
                hasil["teks"] = watermark_decrypt(blob)   # dekripsi AES-GCM
                hasil["status"] = "ok"
            except Exception:
                hasil["status"] = "rusak"                 # kunci salah / data diubah
        else:
            lama = ambil_teks_lama(gambar)                # karya lama, sebelum watermark dienkripsi
            if lama:
                hasil.update(status="lama", teks=lama)
    return render_template("watermark.html", hasil=hasil)


# =====================================================
# CHAT antar pengguna (per karya, untuk nego)
#
#   Teks           : pesan -> Vigenere (klasik) -> AES-GCM (modern) -> simpan di DB
#   File           : isi file -> ChaCha20 -> storage/chat/*.bin   (nama file -> AES)
#   Gambar rahasia : gambar rahasia -> AES-GCM -> disembunyikan di gambar penutup
#                    (steganografi LSB) -> storage/chat/*.png
#
#   Isi chat di database / di disk TIDAK PERNAH berupa data asli.
#   File & gambar hanya bisa diambil oleh dua orang yang sedang bercakap-cakap.
# =====================================================
MAKS_PESAN = 1000   # panjang maksimal satu pesan / keterangan (karakter)
JENIS_BERKAS = ("file", "secret_image")


def cek_percakapan(artwork_id, peer_id):
    """
    Pastikan percakapan ini sah. Hasil: (karya, lawan_bicara) atau (None, None).
    Aturan: bukan chat dengan diri sendiri, dan salah satu pihak adalah pemilik karya.
    """
    saya = session["user_id"]
    if peer_id == saya:
        return None, None

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT id, title, owner_id, preview_path FROM artworks WHERE id=%s", (artwork_id,))
            karya = cur.fetchone()
            cur.execute("SELECT id, username, role FROM users WHERE id=%s", (peer_id,))
            lawan = cur.fetchone()
    finally:
        db.close()

    if not karya or not lawan or karya["owner_id"] not in (saya, peer_id):
        return None, None
    return karya, lawan


def buka_pesan(enc):
    """Dekripsi satu pesan (AES -> Vigenere). Mengembalikan (teks, tahap_vigenere)."""
    try:
        tahap_vigenere = aes_decrypt(enc)              # hasil buka AES = teks Vigenere
        return vigenere_decrypt(tahap_vigenere), tahap_vigenere
    except Exception:
        return "[pesan tidak bisa dibuka]", ""


def nama_berkas_pesan(enc):
    """Nama file di pesan (terenkripsi AES) -> teks. Aman dari data rusak."""
    try:
        return aes_decrypt(enc)
    except Exception:
        return "berkas"


def simpan_pesan(artwork_id, pengirim, penerima, keterangan, jenis="text", berkas=None):
    """
    Simpan satu pesan. Keterangan / isi teks selalu lewat super enkripsi (Vigenere -> AES).
    'berkas' (untuk jenis file / secret_image) = dict: path, nonce, nama, ukuran, hash.
    Kalau penyimpanan ke database gagal, file yang sudah ditulis di disk ikut dihapus.
    """
    b = berkas or {}
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (artwork_id, sender_id, receiver_id, message_enc, kind, "
                "file_path, file_nonce, file_name_enc, file_size, file_hash) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (artwork_id, pengirim, penerima, super_encrypt(keterangan), jenis,
                 b.get("path"), b.get("nonce"),
                 aes_encrypt(b["nama"]) if b else None,
                 b.get("ukuran"), b.get("hash")))
        db.commit()
    except Exception:
        if b.get("path"):
            try:
                os.remove(os.path.join(CHAT_DIR, b["path"]))
            except OSError:
                pass
        raise
    finally:
        db.close()


@app.route("/chat")
@wajib_login
def chat_inbox():
    """Daftar percakapan milik saya (satu baris = satu karya + satu lawan bicara)."""
    uid = session["user_id"]
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT c.artwork_id, c.peer_id, a.title, a.preview_path, "
                "       p.username AS peer_name, m.message_enc, m.kind, m.file_name_enc, "
                "       m.sender_id, m.created_at "
                "FROM (SELECT artwork_id, "
                "             IF(sender_id=%s, receiver_id, sender_id) AS peer_id, "
                "             MAX(id) AS last_id "
                "      FROM messages WHERE sender_id=%s OR receiver_id=%s "
                "      GROUP BY artwork_id, IF(sender_id=%s, receiver_id, sender_id)) c "
                "JOIN artworks a ON a.id = c.artwork_id "
                "JOIN users p ON p.id = c.peer_id "
                "JOIN messages m ON m.id = c.last_id "
                "ORDER BY c.last_id DESC",
                (uid, uid, uid, uid))
            daftar = cur.fetchall()
    finally:
        db.close()

    for d in daftar:
        if d["kind"] == "file":
            teks = "📎 " + nama_berkas_pesan(d["file_name_enc"])
        elif d["kind"] == "secret_image":
            teks = "🖼️ Gambar rahasia"
        else:
            teks, _ = buka_pesan(d["message_enc"])
        d["cuplikan"] = ("Kamu: " if d["sender_id"] == uid else "") + (
            teks if len(teks) <= 60 else teks[:57] + "...")
        d["waktu"] = d["created_at"].strftime("%d %b %H:%M")
    return render_template("chat_inbox.html", daftar=daftar)


@app.route("/chat/<int:artwork_id>/<int:peer_id>")
@wajib_login
def chat_room(artwork_id, peer_id):
    karya, lawan = cek_percakapan(artwork_id, peer_id)
    if not karya:
        flash("Percakapan tidak ditemukan")
        return redirect("/chat")
    return render_template("chat.html", karya=karya, lawan=lawan,
                           debug=config.DEBUG_CHAT,
                           maks_file_mb=MAKS_FILE_CHAT // (1024 * 1024))


@app.route("/chat/<int:artwork_id>/<int:peer_id>/kirim", methods=["POST"])
@wajib_login
def chat_kirim(artwork_id, peer_id):
    karya, lawan = cek_percakapan(artwork_id, peer_id)
    if not karya:
        return jsonify(ok=False, pesan="Percakapan tidak valid"), 403

    teks = str((request.get_json() or {}).get("teks", "")).strip()
    if not teks:
        return jsonify(ok=False, pesan="Pesan kosong")
    if len(teks) > MAKS_PESAN:
        return jsonify(ok=False, pesan="Pesan maksimal %d karakter" % MAKS_PESAN)

    simpan_pesan(artwork_id, session["user_id"], peer_id, teks)    # Vigenere -> AES
    return jsonify(ok=True)


# ---------- kirim FILE (ChaCha20) ----------
@app.route("/chat/<int:artwork_id>/<int:peer_id>/kirim-file", methods=["POST"])
@wajib_login
def chat_kirim_file(artwork_id, peer_id):
    karya, lawan = cek_percakapan(artwork_id, peer_id)
    if not karya:
        return jsonify(ok=False, pesan="Percakapan tidak valid"), 403

    berkas = request.files.get("berkas")
    keterangan = request.form.get("keterangan", "").strip()
    if not berkas or not berkas.filename:
        return jsonify(ok=False, pesan="Pilih file yang mau dikirim")
    if len(keterangan) > MAKS_PESAN:
        return jsonify(ok=False, pesan="Keterangan maksimal %d karakter" % MAKS_PESAN)

    data = berkas.read(MAKS_FILE_CHAT + 1)
    if not data:
        return jsonify(ok=False, pesan="File kosong")
    if len(data) > MAKS_FILE_CHAT:
        return jsonify(ok=False, pesan="File terlalu besar (maksimal %s)" % ukuran_manusia(MAKS_FILE_CHAT))

    nonce, data_enc = chacha_encrypt(data)                     # ChaCha20
    nama_disk = secrets.token_hex(16) + ".bin"
    with open(os.path.join(CHAT_DIR, nama_disk), "wb") as f:
        f.write(data_enc)

    simpan_pesan(artwork_id, session["user_id"], peer_id, keterangan, "file", {
        "path": nama_disk, "nonce": nonce, "nama": nama_aman(berkas.filename),
        "ukuran": len(data), "hash": sha256_hex(data)})
    return jsonify(ok=True)


# ---------- kirim GAMBAR RAHASIA (AES + steganografi) ----------
@app.route("/chat/<int:artwork_id>/<int:peer_id>/kirim-rahasia", methods=["POST"])
@wajib_login
def chat_kirim_rahasia(artwork_id, peer_id):
    karya, lawan = cek_percakapan(artwork_id, peer_id)
    if not karya:
        return jsonify(ok=False, pesan="Percakapan tidak valid"), 403

    f_penutup, f_rahasia = request.files.get("penutup"), request.files.get("rahasia")
    keterangan = request.form.get("keterangan", "").strip()
    if not f_penutup or not f_penutup.filename or not f_rahasia or not f_rahasia.filename:
        return jsonify(ok=False, pesan="Pilih gambar penutup DAN gambar rahasia")
    if len(keterangan) > MAKS_PESAN:
        return jsonify(ok=False, pesan="Keterangan maksimal %d karakter" % MAKS_PESAN)

    try:
        penutup = baca_gambar(f_penutup.stream, "Gambar penutup")
        rahasia = baca_gambar(f_rahasia.stream, "Gambar rahasia")

        # Gambar rahasia dikecilkan seperlunya agar muat di kapasitas gambar penutup
        batas = kapasitas_bytes(penutup) - AES_OVERHEAD
        if batas < 1000:
            raise ValueError("Gambar penutup terlalu kecil (minimal sekitar 100 x 100 piksel)")
        isi, keterangan_ukuran = muat_rahasia(rahasia, batas)
    except ValueError as e:
        return jsonify(ok=False, pesan=str(e))

    blob = aes_encrypt_gambar(isi)                                      # 1. AES-GCM
    pembawa = sisipkan_bytes(penutup, PENANDA_RAHASIA, blob)            # 2. sembunyikan di piksel (LSB)
    buf = io.BytesIO()
    pembawa.save(buf, format="PNG")                                     # PNG: lossless, bit tersembunyi aman
    nama_disk = secrets.token_hex(16) + ".png"
    with open(os.path.join(CHAT_DIR, nama_disk), "wb") as f:
        f.write(buf.getvalue())

    ekstensi = ".png" if isi[:4] == b"\x89PNG" else ".jpg"
    simpan_pesan(artwork_id, session["user_id"], peer_id, keterangan, "secret_image", {
        "path": nama_disk, "nonce": None,
        "nama": nama_aman(os.path.splitext(f_rahasia.filename)[0], "rahasia") + ekstensi,
        "ukuran": len(isi), "hash": sha256_hex(isi)})
    return jsonify(ok=True, pesan="Gambar rahasia terkirim (%s)" % keterangan_ukuran)


# ---------- ambil file / gambar dari pesan (hanya dua orang di percakapan) ----------
def ambil_pesan_berkas(artwork_id, peer_id, pesan_id, jenis):
    """Cari pesan berkas milik percakapan ini. Hasil: baris pesan atau None."""
    karya, lawan = cek_percakapan(artwork_id, peer_id)
    if not karya:
        return None
    saya = session["user_id"]
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT * FROM messages WHERE id=%s AND artwork_id=%s AND kind=%s AND "
                "((sender_id=%s AND receiver_id=%s) OR (sender_id=%s AND receiver_id=%s))",
                (pesan_id, artwork_id, jenis, saya, peer_id, peer_id, saya))
            return cur.fetchone()
    finally:
        db.close()


def kirim_gambar(data, mimetype, nama, unduh):
    """Kirim bytes gambar ke browser. Tidak boleh disimpan di cache bersama."""
    resp = send_file(io.BytesIO(data), mimetype=mimetype, as_attachment=unduh, download_name=nama)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


def baca_pembawa(pesan):
    """Buka file gambar pembawa (PNG berisi gambar rahasia) dari disk."""
    return Image.open(os.path.join(CHAT_DIR, pesan["file_path"]))


@app.route("/chat/<int:artwork_id>/<int:peer_id>/pesan/<int:pesan_id>/unduh")
@wajib_login
def chat_unduh(artwork_id, peer_id, pesan_id):
    """
    Unduh file (jenis 'file': ChaCha20 dibuka lalu dicek hash-nya) atau
    gambar penutup mentah (jenis 'secret_image': PNG yang berisi data tersembunyi).
    """
    pesan = ambil_pesan_berkas(artwork_id, peer_id, pesan_id, "file")
    if pesan:
        try:
            with open(os.path.join(CHAT_DIR, pesan["file_path"]), "rb") as f:
                data = chacha_decrypt(f.read(), pesan["file_nonce"])
        except (OSError, ValueError):
            return "File tidak ditemukan di penyimpanan", 404
        if sha256_hex(data) != pesan["file_hash"]:
            return "File rusak atau telah diubah (hash tidak cocok)", 409
        # octet-stream + attachment: file apa pun (termasuk .html) hanya diunduh, tidak dijalankan
        return send_file(io.BytesIO(data), mimetype="application/octet-stream",
                         as_attachment=True, download_name=nama_berkas_pesan(pesan["file_name_enc"]))

    pesan = ambil_pesan_berkas(artwork_id, peer_id, pesan_id, "secret_image")
    if not pesan:
        return "Tidak ditemukan", 404
    try:
        with open(os.path.join(CHAT_DIR, pesan["file_path"]), "rb") as f:
            data = f.read()
    except OSError:
        return "File tidak ditemukan di penyimpanan", 404
    return kirim_gambar(data, "image/png", "gambar-penutup.png", True)


@app.route("/chat/<int:artwork_id>/<int:peer_id>/pesan/<int:pesan_id>/penutup")
@wajib_login
def chat_penutup(artwork_id, peer_id, pesan_id):
    """Gambar penutup versi kecil (JPG) untuk ditampilkan di gelembung chat."""
    pesan = ambil_pesan_berkas(artwork_id, peer_id, pesan_id, "secret_image")
    if not pesan:
        return "Tidak ditemukan", 404
    try:
        kecil = baca_pembawa(pesan).convert("RGB")
    except OSError:
        return "File tidak ditemukan di penyimpanan", 404
    kecil.thumbnail((480, 480))
    buf = io.BytesIO()
    kecil.save(buf, format="JPEG", quality=80)
    return kirim_gambar(buf.getvalue(), "image/jpeg", "penutup.jpg", False)


@app.route("/chat/<int:artwork_id>/<int:peer_id>/pesan/<int:pesan_id>/buka")
@wajib_login
def chat_buka_rahasia(artwork_id, peer_id, pesan_id):
    """
    Buka gambar rahasia:  piksel (LSB) -> blob terenkripsi -> dekripsi AES-GCM -> gambar asli.
    ?unduh=1 untuk mengunduh, tanpa itu gambar ditampilkan langsung di chat.
    """
    pesan = ambil_pesan_berkas(artwork_id, peer_id, pesan_id, "secret_image")
    if not pesan:
        return "Tidak ditemukan", 404
    try:
        blob = ambil_bytes(baca_pembawa(pesan), PENANDA_RAHASIA)
    except OSError:
        return "File tidak ditemukan di penyimpanan", 404
    if blob is None:
        return "Tidak ada data tersembunyi di gambar ini", 409
    try:
        isi = aes_decrypt_gambar(blob)
    except ValueError:
        return "Gambar rahasia rusak atau telah diubah (verifikasi AES gagal)", 409
    if sha256_hex(isi) != pesan["file_hash"]:
        return "Gambar rahasia tidak cocok dengan hash saat dikirim", 409

    format_asli = Image.open(io.BytesIO(isi)).format        # PNG / JPEG (kita sendiri yang membuatnya)
    return kirim_gambar(isi, "image/png" if format_asli == "PNG" else "image/jpeg",
                        nama_berkas_pesan(pesan["file_name_enc"]),
                        request.args.get("unduh") == "1")


def info_enkripsi(b):
    """Rincian proses enkripsi satu pesan berkas, untuk tampilan demo (DEBUG_CHAT)."""
    try:
        if b["kind"] == "file":
            ukuran_enc = os.path.getsize(os.path.join(CHAT_DIR, b["file_path"]))
            with open(os.path.join(CHAT_DIR, b["file_path"]), "rb") as f:
                awal = f.read(24)
            return {"algoritma": "ChaCha20", "nonce": b["file_nonce"],
                    "ukuran_asli": b["file_size"], "ukuran_enc": ukuran_enc,
                    "cipher_awal": hex_ringkas(awal, 24) + ("…" if ukuran_enc > 24 else ""),
                    "sha256": b["file_hash"]}

        pembawa = baca_pembawa(b)
        blob = ambil_bytes(pembawa, PENANDA_RAHASIA) or b""
        kapasitas = kapasitas_bytes(pembawa) + 6
        return {"algoritma": "AES-GCM + LSB", "ukuran_rahasia": b["file_size"],
                "ukuran_aes": len(blob), "aes_awal": hex_ringkas(blob, 24),
                "pembawa": "%d x %d piksel" % pembawa.size,
                "terpakai": "%.1f%%" % (100.0 * (len(blob) + 6) / max(kapasitas, 1)),
                "sha256": b["file_hash"]}
    except Exception:
        return None


@app.route("/chat/<int:artwork_id>/<int:peer_id>/pesan")
@wajib_login
def chat_pesan(artwork_id, peer_id):
    """Dipanggil browser tiap beberapa detik: ambil pesan baru (id > after)."""
    karya, lawan = cek_percakapan(artwork_id, peer_id)
    if not karya:
        return jsonify(ok=False), 403

    saya = session["user_id"]
    setelah = request.args.get("after", 0, type=int)

    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute(
                "SELECT * FROM messages "
                "WHERE artwork_id=%s AND id>%s AND "
                "((sender_id=%s AND receiver_id=%s) OR (sender_id=%s AND receiver_id=%s)) "
                "ORDER BY id",
                (artwork_id, setelah, saya, peer_id, peer_id, saya))
            baris = cur.fetchall()
    finally:
        db.close()

    hasil = []
    for b in baris:
        teks, tahap_vigenere = buka_pesan(b["message_enc"])
        item = {"id": b["id"], "dari_saya": b["sender_id"] == saya, "jenis": b["kind"],
                "teks": teks, "waktu": b["created_at"].strftime("%H:%M")}
        if b["kind"] in JENIS_BERKAS:
            item.update(nama=nama_berkas_pesan(b["file_name_enc"]),
                        ukuran=ukuran_manusia(b["file_size"]))
        if config.DEBUG_CHAT:                # untuk demo: tampilkan tiap tahap enkripsi
            item["vigenere"] = tahap_vigenere
            item["aes"] = b["message_enc"]
            if b["kind"] in JENIS_BERKAS:
                item["enkripsi"] = info_enkripsi(b)
        hasil.append(item)
    return jsonify(ok=True, pesan=hasil)


# =====================================================
# Logout
# =====================================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# Saat start: pastikan block genesis ada & karya lama ikut tercatat di blockchain
try:
    _db = get_db()
    try:
        blockchain.inisialisasi(_db)
    finally:
        _db.close()
except Exception as e:
    print("Peringatan: blockchain belum diinisialisasi (%s)" % e)


if __name__ == "__main__":
    app.run(debug=True)
