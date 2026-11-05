"""
Blockchain sederhana ArtVault (bukti kepemilikan karya).

Setiap block menyimpan:  index, tipe, data (JSON), prev_hash, hash, nonce
  hash = SHA-256( index | data | prev_hash | waktu | nonce )

Karena prev_hash = hash block sebelumnya, mengubah SATU block saja
membuat hash-nya berubah dan rantai setelahnya putus -> ketahuan saat verifikasi.

Tipe block:
  GENESIS  = block pertama (dibuat otomatis)
  UPLOAD   = karya pertama kali dicatat (pemilik = kreator)
  TRANSFER = kepemilikan pindah ke pembeli

Proof-of-work sederhana: hash harus diawali KESULITAN angka nol.
(jangan ubah KESULITAN setelah ada data, block lama akan dianggap tidak valid)
"""
import json
import os
from datetime import datetime

from crypto_tools import sha256_hex, chacha_decrypt

KESULITAN = 3
HASH_AWAL = "0" * 64          # prev_hash milik block genesis


def hitung_hash(index, data, prev_hash, waktu, nonce):
    """Sidik jari sebuah block."""
    return sha256_hex(("%s|%s|%s|%s|%s" % (index, data, prev_hash, waktu, nonce)).encode())


def _simpan_block(cur, index, tipe, artwork_id, isi, prev_hash):
    """Hitung nonce (proof-of-work) lalu simpan block ke database."""
    waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # waktu ikut disimpan di dalam data, jadi ikut terlindungi hash
    data = json.dumps(dict(isi, waktu=waktu), sort_keys=True, ensure_ascii=False)

    nonce = 0
    while True:
        h = hitung_hash(index, data, prev_hash, waktu, nonce)
        if h.startswith("0" * KESULITAN):
            break
        nonce += 1

    cur.execute(
        "INSERT INTO blockchain (block_index, block_type, artwork_id, data, "
        "prev_hash, hash, nonce, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (index, tipe, artwork_id, data, prev_hash, h, nonce, waktu))
    return {"block_index": index, "hash": h}


def tambah_block(cur, tipe, artwork_id, isi):
    """
    Tambah block di ujung rantai. Pakai cursor milik pemanggil supaya block
    ikut satu transaksi dengan perubahan lain (upload / pembelian);
    kalau salah satu gagal, semuanya dibatalkan.
    """
    cur.execute("SELECT block_index, hash FROM blockchain "
                "ORDER BY block_index DESC LIMIT 1 FOR UPDATE")
    terakhir = cur.fetchone()
    if terakhir is None:                         # rantai masih kosong -> buat genesis
        terakhir = _simpan_block(cur, 0, "GENESIS", None,
                                 {"pesan": "Genesis block ArtVault"}, HASH_AWAL)
    return _simpan_block(cur, terakhir["block_index"] + 1, tipe, artwork_id,
                         isi, terakhir["hash"])


def catat_upload(cur, artwork_id, judul, file_hash, user_id, username):
    return tambah_block(cur, "UPLOAD", artwork_id, {
        "artwork_id": artwork_id, "artwork": judul, "file_hash": file_hash,
        "from": "-", "from_id": None, "to": username, "to_id": user_id})


def catat_transfer(cur, artwork_id, judul, file_hash, dari_id, dari, ke_id, ke):
    return tambah_block(cur, "TRANSFER", artwork_id, {
        "artwork_id": artwork_id, "artwork": judul, "file_hash": file_hash,
        "from": dari, "from_id": dari_id, "to": ke, "to_id": ke_id})


def inisialisasi(db):
    """
    Dipanggil saat aplikasi start: pastikan genesis ada, dan karya yang diupload
    SEBELUM fitur blockchain ada ikut dicatat sebagai block UPLOAD.
    """
    with db.cursor() as cur:
        cur.execute(
            "SELECT a.id, a.title, a.file_hash, a.creator_id, u.username "
            "FROM artworks a JOIN users u ON u.id = a.creator_id "
            "WHERE a.id NOT IN (SELECT artwork_id FROM blockchain "
            "                   WHERE block_type='UPLOAD' AND artwork_id IS NOT NULL) "
            "ORDER BY a.id")
        belum = cur.fetchall()
        cur.execute("SELECT COUNT(*) AS n FROM blockchain")
        kosong = cur.fetchone()["n"] == 0
        if kosong and not belum:                 # cukup genesis saja
            tambah_block_genesis(cur)
        for k in belum:
            catat_upload(cur, k["id"], k["title"], k["file_hash"],
                         k["creator_id"], k["username"])
    db.commit()


def tambah_block_genesis(cur):
    _simpan_block(cur, 0, "GENESIS", None, {"pesan": "Genesis block ArtVault"}, HASH_AWAL)


def ambil_semua(cur):
    """Seluruh block (urut), isi JSON-nya sudah dibuka di kolom 'isi'."""
    cur.execute("SELECT * FROM blockchain ORDER BY block_index")
    hasil = cur.fetchall()
    for b in hasil:
        try:
            b["isi"] = json.loads(b["data"])
        except ValueError:
            b["isi"] = {}
    return hasil


def verifikasi(cur, folder_file):
    """
    Periksa seluruh rantai. Hasil: dict(blok=[...], karya=[...], semua_ok=bool)
      Per block : nomor berurutan? prev_hash cocok? hash cocok dengan isi? proof-of-work? pengirim sah?
      Per karya : ada block UPLOAD? hash file sama? pemilik di DB sama dengan blockchain?
                  file terenkripsi di disk masih utuh (hash SHA-256 sama)?
    """
    blok = ambil_semua(cur)
    hasil_blok = []
    info = {}      # artwork_id -> {"hash": hash file dari block UPLOAD, "pemilik": id pemilik menurut rantai}

    for i, b in enumerate(blok):
        masalah = []
        d = b["isi"]

        if b["block_index"] != i:
            masalah.append("Nomor block loncat (seharusnya %d)" % i)
        seharusnya = HASH_AWAL if i == 0 else blok[i - 1]["hash"]
        if b["prev_hash"] != seharusnya:
            masalah.append("prev_hash tidak sama dengan hash block sebelumnya (rantai putus)")
        if not d:
            masalah.append("Data block rusak / tidak terbaca")
        if hitung_hash(b["block_index"], b["data"], b["prev_hash"],
                       d.get("waktu", ""), b["nonce"]) != b["hash"]:
            masalah.append("Hash tidak cocok dengan isi block (data telah diubah)")
        elif not b["hash"].startswith("0" * KESULITAN):
            masalah.append("Proof-of-work tidak terpenuhi")
        if d and d.get("artwork_id") != b["artwork_id"]:
            masalah.append("artwork_id di data berbeda dengan kolom block")

        aid = b["artwork_id"]
        if b["block_type"] == "UPLOAD" and aid is not None:
            info[aid] = {"hash": d.get("file_hash"), "pemilik": d.get("to_id")}
        elif b["block_type"] == "TRANSFER" and aid is not None:
            if aid not in info:
                masalah.append("TRANSFER tanpa block UPLOAD sebelumnya")
            else:
                if d.get("from_id") != info[aid]["pemilik"]:
                    masalah.append("Pengirim bukan pemilik sah karya ini")
                info[aid]["pemilik"] = d.get("to_id")

        b["masalah"] = masalah
        b["ok"] = not masalah
        hasil_blok.append(b)

    # ---- cocokkan rantai dengan data karya di database & file di disk ----
    hasil_karya = []
    cur.execute("SELECT id, title, owner_id, file_hash, file_path, file_nonce "
                "FROM artworks ORDER BY id")
    for k in cur.fetchall():
        masalah = []
        rantai = info.get(k["id"])
        if rantai is None:
            masalah.append("Karya belum tercatat di blockchain")
        else:
            if rantai["hash"] != k["file_hash"]:
                masalah.append("Hash file di database berbeda dengan yang tercatat di blockchain")
            if rantai["pemilik"] != k["owner_id"]:
                masalah.append("Pemilik di database berbeda dengan pemilik menurut blockchain")

        try:
            with open(os.path.join(folder_file, k["file_path"]), "rb") as f:
                isi_file = chacha_decrypt(f.read(), k["file_nonce"])
            if rantai and sha256_hex(isi_file) != rantai["hash"]:
                masalah.append("Isi file berubah (hash SHA-256 tidak sama dengan saat upload)")
        except FileNotFoundError:
            masalah.append("File terenkripsi hilang dari penyimpanan")
        except Exception:
            masalah.append("File terenkripsi tidak bisa dibuka (rusak)")

        hasil_karya.append({"id": k["id"], "title": k["title"],
                            "ok": not masalah, "masalah": masalah})

    semua_ok = all(b["ok"] for b in hasil_blok) and all(k["ok"] for k in hasil_karya)
    return {"blok": hasil_blok, "karya": hasil_karya, "semua_ok": semua_ok}
