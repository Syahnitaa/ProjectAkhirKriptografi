// Fungsi bantu face-api.js (dipakai halaman daftar & verifikasi wajah)
// Tugas JS di sini HANYA mengubah wajah menjadi 128 angka.
// Penyimpanan, enkripsi, dan pencocokan dilakukan di Python.
// Foto/video TIDAK pernah disimpan maupun dikirim, hanya 128 angka.

const LOKASI_MODEL = "/static/models";

// 1. Muat model AI (sekali di awal)
async function muatModel() {
  await faceapi.nets.tinyFaceDetector.loadFromUri(LOKASI_MODEL);   // mendeteksi wajah
  await faceapi.nets.faceLandmark68Net.loadFromUri(LOKASI_MODEL);  // titik-titik wajah
  await faceapi.nets.faceRecognitionNet.loadFromUri(LOKASI_MODEL); // ubah wajah -> 128 angka
}

// 2. Nyalakan kamera
async function nyalakanKamera(video) {
  const stream = await navigator.mediaDevices.getUserMedia({ video: true });
  video.srcObject = stream;
  await video.play();
}

// 3. Ambil 128 angka dari wajah yang terlihat di kamera (null kalau tidak ada wajah)
async function ambilWajah(video) {
  const opsi = new faceapi.TinyFaceDetectorOptions({ inputSize: 416, scoreThreshold: 0.6 });
  const hasil = await faceapi
    .detectSingleFace(video, opsi)
    .withFaceLandmarks()
    .withFaceDescriptor();
  return hasil ? Array.from(hasil.descriptor) : null;
}

// 4. Rekam wajah beberapa kali. Hasil null kalau ada yang gagal terdeteksi
async function rekamWajah(video, jumlah, onProgress) {
  const hasil = [];
  for (let i = 1; i <= jumlah; i++) {
    onProgress(i, jumlah);
    let wajah = null;
    for (let coba = 0; coba < 10 && !wajah; coba++) {
      wajah = await ambilWajah(video);
      if (!wajah) await tunggu(300);
    }
    if (!wajah) return null;
    hasil.push(wajah);
    await tunggu(400);
  }
  return hasil;
}

// 5. Kirim data ke Flask (format JSON)
async function kirimKeServer(url, data) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return await res.json();
}

function tunggu(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
