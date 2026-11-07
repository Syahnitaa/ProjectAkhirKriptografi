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
    if (hasil.dihapus) { tutupChat(hasil.pesan); return; }      // karya dihapus kreator saat chat terbuka
    if (!hasil.ok || hasil.pesan.length === 0) return;
    const pertama = terakhir === 0;
    let menempel = false;
    hasil.pesan.forEach((m) => { menempel = tampilkan(m) || menempel; });
    if (pertama || menempel) kotak.scrollTop = kotak.scrollHeight;
  } catch (e) { /* koneksi putus sebentar, coba lagi di putaran berikutnya */ }
}

// ---------- kirim ----------
const semuaTombol = ["kirim", "tombolFile", "tombolRahasia", "kirimRahasia"].map((i) => document.getElementById(i));
const tombolKirim = document.getElementById("kirim");
const tombolKirimRahasia = document.getElementById("kirimRahasia");
const tray = document.getElementById("lampiranTray");
const fPenutup = document.getElementById("fPenutup");
const fRahasia = document.getElementById("fRahasia");
let sedangKirim = false;
let lampiran = null;                   // file yang sudah dipilih tapi BELUM dikirim (menunggu Send)

function kunci(ya) {
  sedangKirim = ya;
  document.getElementById("tombolFile").disabled = ya;
  document.getElementById("tombolRahasia").disabled = ya;
  perbaruiTombol();
}

// Tombol Send hanya aktif kalau ada yang bisa dikirim (teks atau lampiran)
function perbaruiTombol() {
  tombolKirim.disabled = sedangKirim || (!teks.value.trim() && !lampiran);
  tombolKirimRahasia.disabled = sedangKirim || !fPenutup.files[0] || !fRahasia.files[0];
}

// ---------- pratinjau sebelum kirim ----------
let urlPratinjau = null;
function bersihUrl() { if (urlPratinjau) { URL.revokeObjectURL(urlPratinjau); urlPratinjau = null; } }

function ukuranTeks(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

function batalLampiran() {
  lampiran = null;
  bersihUrl();
  tray.hidden = true;
  tray.replaceChildren();
  perbaruiTombol();
}

function pilihLampiran(berkas) {
  const batas = parseFloat(infoChat.maksFile || "10") * 1048576;
  if (berkas.size > batas) { tampilStatus("File terlalu besar (maksimal " + ukuranTeks(batas) + ")", true); return; }
  if (berkas.size === 0) { tampilStatus("File kosong", true); return; }

  bersihUrl();
  lampiran = berkas;
  tampilStatus("");

  const kartu = el("div", "lampiran-pratinjau");
  if (berkas.type.startsWith("image/")) {
    urlPratinjau = URL.createObjectURL(berkas);
    const img = el("img", "pratinjau-img");
    img.alt = "Pratinjau";
    img.src = urlPratinjau;
    kartu.append(img);
  } else {
    kartu.append(el("div", "pratinjau-ikon", "📎"));
  }
  const info = el("div", "pratinjau-info");
  info.append(el("b", null, berkas.name), el("span", "kecil", ukuranTeks(berkas.size) + " · akan dienkripsi ChaCha20"),
              el("span", "kecil", "Tekan Send untuk mengirim. Teks di kotak pesan ikut jadi keterangan; untuk kirim teks saja, batalkan lampiran (✕)."));
  const hapus = el("button", "ikon-batal", "✕");
  hapus.type = "button";
  hapus.title = "Batalkan";
  hapus.onclick = batalLampiran;
  kartu.append(info, hapus);

  tray.replaceChildren(kartu);
  tray.hidden = false;
  perbaruiTombol();
  teks.focus();
}

// Pratinjau kecil untuk dua gambar di panel gambar rahasia
function pratinjauSlot(input, kotakId) {
  const kotak = document.getElementById(kotakId);
  const berkas = input.files[0];
  if (kotak.dataset.url) { URL.revokeObjectURL(kotak.dataset.url); kotak.dataset.url = ""; }
  if (!berkas) { kotak.replaceChildren(document.createTextNode("No image selected")); perbaruiTombol(); return; }
  const url = URL.createObjectURL(berkas);
  kotak.dataset.url = url;
  const img = el("img");
  img.src = url;
  img.alt = "Pratinjau";
  kotak.replaceChildren(img, el("span", "kecil", berkas.name + " · " + ukuranTeks(berkas.size)));
  perbaruiTombol();
}
fPenutup.addEventListener("change", () => pratinjauSlot(fPenutup, "prevPenutup"));
fRahasia.addEventListener("change", () => pratinjauSlot(fRahasia, "prevRahasia"));

async function selesaiKirim(jawaban) {
  if (jawaban.ok) {
    teks.value = "";
    tampilStatus(jawaban.pesan || "");
    perbaruiTombol();
    await ambil();
  } else {
    tampilStatus(jawaban.pesan || "Gagal mengirim", true);
    if (jawaban.dihapus) tutupChat(jawaban.pesan);
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
    const jawaban = await kirimForm(URL_DASAR + "/kirim-file", form);
    await selesaiKirim(jawaban);
    if (jawaban.ok) batalLampiran();     // terkirim -> bersihkan pratinjau (kalau gagal, tetap ada untuk dicoba lagi)
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
      fPenutup.value = "";
      fRahasia.value = "";
      pratinjauSlot(fPenutup, "prevPenutup");
      pratinjauSlot(fRahasia, "prevRahasia");
    }
  } catch (e) {
    tampilStatus("Gagal mengirim gambar rahasia, coba lagi", true);
  }
  kunci(false);
}

// ---------- tombol ----------
const pilihFile = document.getElementById("pilihFile");

// Send: kalau ada lampiran -> kirim lampiran (teks jadi keterangan); kalau tidak -> kirim teks
function kirimSekarang() {
  if (sedangKirim) return;
  if (lampiran) kirimBerkas(lampiran);
  else kirimTeks();
}
tombolKirim.onclick = kirimSekarang;
teks.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); kirimSekarang(); } });
teks.addEventListener("input", perbaruiTombol);

document.getElementById("tombolFile").onclick = () => pilihFile.click();
pilihFile.onchange = () => {
  if (pilihFile.files[0]) pilihLampiran(pilihFile.files[0]);   // hanya pratinjau, belum terkirim
  pilihFile.value = "";                  // supaya file yang sama bisa dipilih lagi
};

document.getElementById("tombolRahasia").onclick = () => { panelRahasia.hidden = !panelRahasia.hidden; };
document.getElementById("batalRahasia").onclick = () => { panelRahasia.hidden = true; };
document.getElementById("kirimRahasia").onclick = kirimRahasia;

// Karya dihapus: hentikan polling, kunci semua input, beri tahu pengguna
function tutupChat(pesan) {
  clearInterval(pemantau);
  lampiran = null;
  teks.disabled = true;
  document.getElementById("tombolFile").disabled = true;
  document.getElementById("tombolRahasia").disabled = true;
  tombolKirim.disabled = true;
  tombolKirimRahasia.disabled = true;
  panelRahasia.hidden = true;
  tray.hidden = true;
  kunci = () => {};                      // cegah tombol hidup lagi setelah proses kirim yang sedang berjalan
  tampilStatus(pesan, true);
}

perbaruiTombol();
ambil();
const pemantau = setInterval(ambil, 2500);                // cek pesan baru tiap 2,5 detik
