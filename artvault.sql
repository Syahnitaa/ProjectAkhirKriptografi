-- =====================================================
-- ArtVault - Galeri Karya Digital Aman
-- Database: MySQL (InnoDB, utf8mb4)
-- Kolom berakhiran _enc = disimpan TERENKRIPSI (base64)
-- =====================================================

CREATE DATABASE IF NOT EXISTS artvault
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE artvault;

-- -----------------------------------------------------
-- 1. USERS (kreator & kolektor)
-- Login: username + password (hash) -> verifikasi wajah
-- -----------------------------------------------------
CREATE TABLE users (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  username          VARCHAR(50)  NOT NULL UNIQUE,
  email_enc         TEXT         NOT NULL,            -- email terenkripsi
  password_hash     VARCHAR(255) NOT NULL,            -- bcrypt / SHA-256 + salt
  role              ENUM('creator','collector') NOT NULL,
  face_template_enc TEXT NULL,                        -- vektor wajah terenkripsi AES, direkam SAAT REGISTER
                                                      -- (aplikasi menolak login kalau kosong)
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- 2. ARTWORKS (karya digital)
-- -----------------------------------------------------
CREATE TABLE artworks (
  id                INT AUTO_INCREMENT PRIMARY KEY,
  creator_id        INT NOT NULL,                     -- pembuat asli (tetap)
  owner_id          INT NOT NULL,                     -- pemilik saat ini (berubah saat dibeli)
  title             VARCHAR(150) NOT NULL,
  description       TEXT NULL,
  preview_path      VARCHAR(255) NOT NULL,            -- gambar pratinjau (untuk galeri, tidak terenkripsi)
  file_path         VARCHAR(255) NOT NULL,            -- file asli resolusi penuh (TERENKRIPSI ChaCha20)
  file_nonce        VARCHAR(64)  NOT NULL,            -- nonce/IV enkripsi file
  original_filename VARCHAR(255) NOT NULL,
  file_hash         CHAR(64)     NOT NULL,            -- SHA-256 file asli (masuk blockchain)
  watermark_enc     TEXT         NOT NULL,            -- teks watermark TERENKRIPSI AES (base64); blob yang sama disisipkan ke piksel via LSB
  price_enc         TEXT         NOT NULL,            -- harga terenkripsi
  status            ENUM('available','sold') NOT NULL DEFAULT 'available',
  deleted_at        TIMESTAMP NULL DEFAULT NULL,       -- terisi = karya dihapus kreator (soft delete, riwayat blockchain tetap utuh)
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (creator_id) REFERENCES users(id),
  FOREIGN KEY (owner_id)   REFERENCES users(id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- 3. MESSAGES (chat nego, per karya)
-- kind = text          : message_enc = pesan, Vigenere -> AES
-- kind = file          : file dikirim, ChaCha20 (file_path = storage/chat/*.bin)
-- kind = secret_image  : gambar rahasia, AES lalu disembunyikan di gambar penutup
--                        via steganografi LSB (file_path = storage/chat/*.png)
-- Untuk file / gambar, message_enc = keterangan (boleh kosong), tetap Vigenere -> AES
-- -----------------------------------------------------
CREATE TABLE messages (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  artwork_id    INT NOT NULL,
  sender_id     INT NOT NULL,
  receiver_id   INT NOT NULL,
  message_enc   TEXT NOT NULL,                        -- ciphertext super enkripsi
  kind          ENUM('text','file','secret_image') NOT NULL DEFAULT 'text',
  file_path     VARCHAR(255) NULL,                    -- nama file di storage/chat/
  file_nonce    VARCHAR(64)  NULL,                    -- nonce ChaCha20 (hanya kind=file)
  file_name_enc TEXT         NULL,                    -- nama file asli, terenkripsi AES
  file_size     INT          NULL,                    -- ukuran isi asli (byte)
  file_hash     CHAR(64)     NULL,                    -- SHA-256 isi asli (cek keutuhan)
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (artwork_id)  REFERENCES artworks(id),
  FOREIGN KEY (sender_id)   REFERENCES users(id),
  FOREIGN KEY (receiver_id) REFERENCES users(id),
  INDEX idx_chat (artwork_id, sender_id, receiver_id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- 4. TRANSACTIONS (riwayat pembelian)
-- Satu baris = satu pembelian yang sudah selesai
-- -----------------------------------------------------
CREATE TABLE transactions (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  artwork_id  INT NOT NULL,
  buyer_id    INT NOT NULL,
  seller_id   INT NOT NULL,
  price_enc   TEXT NOT NULL,                          -- harga kesepakatan terenkripsi
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (artwork_id) REFERENCES artworks(id),
  FOREIGN KEY (buyer_id)   REFERENCES users(id),
  FOREIGN KEY (seller_id)  REFERENCES users(id)
) ENGINE=InnoDB;

-- -----------------------------------------------------
-- 5. BLOCKCHAIN (bukti kepemilikan)
-- UPLOAD   = karya pertama kali dicatat (pemilik = kreator)
-- TRANSFER = kepemilikan berpindah ke pembeli
-- Block pertama (genesis) dibuat oleh aplikasi saat start
-- -----------------------------------------------------
CREATE TABLE blockchain (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  block_index INT NOT NULL UNIQUE,
  block_type  ENUM('GENESIS','UPLOAD','TRANSFER') NOT NULL,
  artwork_id  INT NULL,                               -- NULL untuk genesis
  data        TEXT NOT NULL,                          -- JSON: {artwork, file_hash, from, to}
  prev_hash   CHAR(64) NOT NULL,
  hash        CHAR(64) NOT NULL,                      -- SHA-256(index + data + prev_hash + timestamp + nonce)
  nonce       INT NOT NULL DEFAULT 0,                 -- opsional, kalau mau pakai proof-of-work sederhana
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (artwork_id) REFERENCES artworks(id)
) ENGINE=InnoDB;
