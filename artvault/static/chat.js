// Chat ArtVault: pesan teks, file (ChaCha20), dan gambar rahasia (AES + steganografi).
// Semua isi pesan dari server ditulis lewat textContent (bukan innerHTML) supaya aman dari XSS.

const infoChat = document.getElementById("data-chat").dataset;
const URL_DASAR = infoChat.url;
const DEBUG = infoChat.debug === "true";

const kotak = document.getElementById("kotak");
const teks = document.getElementById("teks");
const barisStatus = document.getElementById("status");
const panelRahasia = document.getElementById("panelRahasia");
let terakhir = 0;                      // id pesan terakhir yang sudah tampil

// ---------- pembantu ----------
function el(tag, kelas, isi) {
  const e = document.createElement(tag);
  if (kelas) e.className = kelas;
  if (isi !== undefined) e.textContent = isi;
  return e;
}

function baris(label, isi) {
  const p = el("div", "tahap");
  p.append(el("b", null, label), document.createTextNode(" " + isi));
  return p;
}

async function kirimJson(url, isi) {
  const res = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(isi),
  });
  return await res.json();
}

async function kirimForm(url, form) {
  const res = await fetch(url, { method: "POST", body: form });
  return await res.json();
}

function tampilStatus(pesan, galat) {
  barisStatus.textContent = pesan || "";
  barisStatus.className = "kecil" + (galat ? " galat" : "");
}

// ---------- tampilan demo: tahap-tahap enkripsi ----------
function rincianEnkripsi(m) {
  const d = el("details");
  d.append(el("summary", null, "🔍 lihat enkripsi"));

  if (m.jenis === "file" && m.enkripsi) {
    const e = m.enkripsi;
    d.append(
      baris("Algoritma:", e.algoritma + " (stream cipher, nonce acak per file)"),
      baris("Nonce:", e.nonce),
      baris("Ukuran:", e.ukuran_asli + " byte asli → " + e.ukuran_enc + " byte terenkripsi"),
      baris("Awal ciphertext di disk (hex):", e.cipher_awal),
      baris("SHA-256 isi asli:", e.sha256));
  } else if (m.jenis === "secret_image" && m.enkripsi) {
    const e = m.enkripsi;
    d.append(
      baris("1. Gambar rahasia:", e.ukuran_rahasia + " byte, SHA-256 " + e.sha256),
      baris("2. Setelah AES-GCM:", e.ukuran_aes + " byte. Awal (hex): " + e.aes_awal),
      baris("3. Disembunyikan di piksel gambar penutup (" + e.pembawa + ") lewat LSB:",
            "kapasitas terpakai " + e.terpakai + ". Perubahan warna hanya ±1, tak terlihat mata."));
  }

  if (m.teks) {                          // keterangan / pesan teks juga super-terenkripsi
    d.append(
      baris("Pesan asli:", m.teks),
      baris("Setelah Vigenère:", m.vigenere),
      baris("Setelah AES (tersimpan di DB):", m.aes));
  }
  return d;
}

// ---------- gelembung pesan ----------
function isiFile(m) {
  const kartu = el("div", "lampiran");
  const info = el("div", "lampiran-info");
  info.append(el("b", null, "📎 " + m.nama), el("span", "kecil", m.ukuran + " · terenkripsi ChaCha20"));
  const unduh = el("a", "tombol-kecil", "⬇ Unduh");
  unduh.href = URL_DASAR + "/pesan/" + m.id + "/unduh";
  kartu.append(info, unduh);
  return kartu;
}

function isiRahasia(m, menempel) {
  const kartu = el("div", "lampiran rahasia");
  const dasar = URL_DASAR + "/pesan/" + m.id;

  const penutup = el("img", "penutup");
  penutup.alt = "Gambar penutup";
  penutup.src = dasar + "/penutup";
  penutup.onload = () => { if (menempel) kotak.scrollTop = kotak.scrollHeight; };

  const hasil = el("div", "hasil-rahasia");
  hasil.hidden = true;

  const tombolBuka = el("button", "tombol-kecil", "🔓 Buka gambar rahasia");
  tombolBuka.type = "button";
  tombolBuka.onclick = () => {
    if (!hasil.hidden) {                 // sudah terbuka -> sembunyikan lagi
      hasil.hidden = true;
      tombolBuka.textContent = "🔓 Buka gambar rahasia";
      return;
    }
    hasil.replaceChildren(el("span", "kecil", "Mengekstrak & mendekripsi..."));
    hasil.hidden = false;
    const img = el("img", "penutup");
    img.alt = "Gambar rahasia";
    img.onload = () => {
      hasil.replaceChildren(el("div", "kecil", "✅ Gambar rahasia berhasil diekstrak & didekripsi:"), img);
    };
    img.onerror = () => {
      hasil.replaceChildren(el("span", "kecil galat", "Gagal membuka gambar rahasia (data rusak atau diubah)."));
    };
    img.src = dasar + "/buka";
    tombolBuka.textContent = "🙈 Sembunyikan lagi";
  };

  const unduhRahasia = el("a", "tombol-kecil", "⬇ Rahasia");
  unduhRahasia.href = dasar + "/buka?unduh=1";
  const unduhPenutup = el("a", "tombol-kecil", "⬇ Penutup");
  unduhPenutup.href = dasar + "/unduh";
  unduhPenutup.title = "Gambar penutup asli (PNG) yang berisi data tersembunyi";

  const aksi = el("div", "aksi");
  aksi.append(tombolBuka, unduhRahasia, unduhPenutup);
  kartu.append(penutup,
    el("div", "kecil", "🖼️ Gambar ini menyembunyikan gambar rahasia (" + m.ukuran + ")"),
    aksi, hasil);
  return kartu;
}

function tampilkan(m) {
  const menempel = kotak.scrollHeight - kotak.scrollTop - kotak.clientHeight < 80;
  const bubble = el("div", "bubble " + (m.dari_saya ? "saya" : "lawan"));

  if (m.jenis === "file") bubble.append(isiFile(m));
  else if (m.jenis === "secret_image") bubble.append(isiRahasia(m, menempel));

  if (m.teks) bubble.append(el("div", null, m.teks));           // textContent: aman dari XSS
  bubble.append(el("span", "waktu", m.waktu));
  if (DEBUG) bubble.append(rincianEnkripsi(m));

  kotak.append(bubble);
  terakhir = Math.max(terakhir, m.id);
  return menempel;
}

async function ambil() {
  try {
    const res = await fetch(URL_DASAR + "/pesan?after=" + terakhir);
    const hasil = await res.json();
    if (!hasil.ok || hasil.pesan.length === 0) return;
    const pertama = terakhir === 0;
    let menempel = false;
    hasil.pesan.forEach((m) => { menempel = tampilkan(m) || menempel; });
    if (pertama || menempel) kotak.scrollTop = kotak.scrollHeight;
  } catch (e) { /* koneksi putus sebentar, coba lagi di putaran berikutnya */ }
}

// ---------- kirim ----------
const semuaTombol = ["kirim", "tombolFile", "tombolRahasia", "kirimRahasia"].map((i) => document.getElementById(i));
function kunci(ya) { semuaTombol.forEach((t) => { t.disabled = ya; }); }

async function selesaiKirim(jawaban) {
  if (jawaban.ok) {
    teks.value = "";
    tampilStatus(jawaban.pesan || "");
    await ambil();
  } else {
    tampilStatus(jawaban.pesan || "Gagal mengirim", true);
  }
}

async function kirimTeks() {
  const isi = teks.value.trim();
  if (!isi) return;
  kunci(true);
  try {
    await selesaiKirim(await kirimJson(URL_DASAR + "/kirim", { teks: isi }));
  } catch (e) {
    tampilStatus("Gagal mengirim, coba lagi", true);
  }
  kunci(false);
  teks.focus();
}

async function kirimBerkas(berkas) {
  const form = new FormData();
  form.append("berkas", berkas);
  form.append("keterangan", teks.value.trim());
  kunci(true);
  tampilStatus("🔐 Mengenkripsi (ChaCha20) & mengirim " + berkas.name + "...");
  try {
    await selesaiKirim(await kirimForm(URL_DASAR + "/kirim-file", form));
  } catch (e) {
    tampilStatus("Gagal mengirim file, coba lagi", true);
  }
  kunci(false);
}

async function kirimRahasia() {
  const penutup = document.getElementById("fPenutup").files[0];
  const rahasia = document.getElementById("fRahasia").files[0];
  if (!penutup || !rahasia) { tampilStatus("Pilih gambar penutup DAN gambar rahasia", true); return; }

  const form = new FormData();
  form.append("penutup", penutup);
  form.append("rahasia", rahasia);
  form.append("keterangan", teks.value.trim());
  kunci(true);
  tampilStatus("🔐 Mengenkripsi (AES) & menyembunyikan di gambar penutup... (bisa beberapa detik)");
  try {
    const jawaban = await kirimForm(URL_DASAR + "/kirim-rahasia", form);
    await selesaiKirim(jawaban);
    if (jawaban.ok) {
      panelRahasia.hidden = true;
      document.getElementById("fPenutup").value = "";
      document.getElementById("fRahasia").value = "";
    }
  } catch (e) {
    tampilStatus("Gagal mengirim gambar rahasia, coba lagi", true);
  }
  kunci(false);
}

// ---------- tombol ----------
const pilihFile = document.getElementById("pilihFile");
document.getElementById("kirim").onclick = kirimTeks;
teks.addEventListener("keydown", (e) => { if (e.key === "Enter") kirimTeks(); });

document.getElementById("tombolFile").onclick = () => pilihFile.click();
pilihFile.onchange = () => {
  if (pilihFile.files[0]) kirimBerkas(pilihFile.files[0]);
  pilihFile.value = "";                  // supaya file yang sama bisa dipilih lagi
};

document.getElementById("tombolRahasia").onclick = () => { panelRahasia.hidden = !panelRahasia.hidden; };
document.getElementById("batalRahasia").onclick = () => { panelRahasia.hidden = true; };
document.getElementById("kirimRahasia").onclick = kirimRahasia;

ambil();
setInterval(ambil, 2500);                // cek pesan baru tiap 2,5 detik
