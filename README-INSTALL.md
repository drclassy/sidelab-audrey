# AUDREY Install Guide

Panduan ini dibuat untuk PC Puskesmas atau PC baru yang belum pernah dipakai menjalankan AUDREY.

## Mode yang Didukung

### 1. DeepSeek Mode
Mode default untuk PC 8GB atau unit yang tidak sanggup inference lokal.

Yang berjalan lokal:
- Python
- CLI AUDREY
- aturan klinis, ICD, template, Telegram

Yang berjalan di cloud:
- generasi jawaban DeepSeek

Rekomendasi minimum:
- Windows 10/11 64-bit
- RAM 8 GB masih bisa untuk mode ini
- Internet aktif
- `DEEPSEEK_API_KEY` di file `.env`

### 2. Local Mode
Semua berjalan di 1 PC:
- Python
- Ollama
- model lokal
- CLI AUDREY

Mode ini tetap tersedia sebagai fallback, tetapi lebih cocok untuk PC yang lebih kuat.

Rekomendasi minimum:
- Windows 10/11 64-bit
- RAM 16 GB
- Disk kosong minimal 10 GB
- Internet saat setup pertama

## File Penting

- `AUDREY.bat`
  Launcher utama. User cukup double-click `AUDREY.bat`.

- `install.bat`
  Helper internal untuk setup awal: venv, dependency, `.env`, dan pengecekan opsional Ollama.

- `run.bat`
  Helper internal untuk menjalankan AUDREY memakai virtual environment lokal.

- `diagnose-audrey.bat`
  Membuat laporan diagnostik jika setup atau runtime gagal.

- `.env`
  Konfigurasi DeepSeek dan Telegram untuk fitur `/send`.

## Langkah Install

1. Install Python dari:
   `https://www.python.org/downloads/`

   Sangat penting:
   - centang `Add Python to PATH`

2. Jika ingin mode Local, install Ollama dari:
   `https://ollama.com/download`

3. Buka folder AUDREY.

4. double-click `AUDREY.bat`

5. Audrey akan otomatis:
   - setup bila PC ini belum pernah dipakai
   - lalu langsung menjalankan aplikasi

## Jika /send Ingin Dipakai

Copy `.env.example` menjadi `.env` bila belum ada, lalu isi:

```env
DEEPSEEK_API_KEY=isi_api_key_deepseek
DEEPSEEK_MODEL=deepseek-v4-flash
TELEGRAM_BOT_TOKEN=isi_token_bot
TELEGRAM_CHAT_ID=isi_chat_id
```

## Jika Install Gagal

Jalankan:

`diagnose-audrey.bat`

File laporan akan dibuat di folder:

`diagnostics/`

File ini berguna untuk melihat:
- versi Python
- status virtual environment
- status Ollama jika ada
- status DeepSeek environment
- status `.env`

## Masalah yang Paling Sering

### DeepSeek ada, tapi jawaban lambat atau error
Kemungkinan penyebab:
- `DEEPSEEK_API_KEY` belum diisi
- koneksi internet bermasalah
- rate limit / server sibuk

Solusi awal:
- cek file `.env`
- coba mode Local jika Ollama tersedia
- jalankan `diagnose-audrey.bat`

### Ollama ada, tapi model tidak bisa jalan
Kemungkinan penyebab:
- RAM kurang
- pagefile Windows terlalu kecil
- service Ollama belum aktif

Gejala umum:
- `ollama --version` normal
- tetapi inferensi gagal atau timeout

Solusi awal:
- restart komputer
- buka aplikasi Ollama dan pastikan aktif
- jalankan `diagnose-audrey.bat`

### Python terinstall, tetapi package gagal
Kemungkinan penyebab:
- Python tidak masuk PATH
- internet tidak stabil
- policy PC memblokir install package

### Telegram tidak jalan
Kemungkinan penyebab:
- `.env` belum diisi
- token/chat id salah

## Rekomendasi Operasional

Untuk pemakaian 1 PC dengan RAM 8 GB:
- pakai `DeepSeek Mode`

Untuk banyak PC:
- jangan buru-buru install model lokal di semua unit
- lebih baik pakai DeepSeek dulu, lalu Local hanya di unit yang kuat
