# GONKAFARM

[English](#english) | [Bahasa Indonesia](#bahasa-indonesia)

---

## Bahasa Indonesia

**GONKAFARM** adalah sistem otomasi API farming berperforma tinggi yang dirancang untuk mengelola akun secara massal, mengambil OTP dari worker secara otomatis, dan melakukan sinkronisasi data langsung ke *9router*.

### Fitur Utama
- **Auto Farming**: Menjalankan skrip farm secara paralel dan efisien.
- **Worker & OTP Integration**: Integrasi otomatis pengambilan kode OTP/verifikasi dari worker eksternal.
- **9router Sync**: Sinkronisasi endpoint dan manajemen sesi mulus melalui *9router*.
- **Proxy Support**: Mendukung rotasi proxy berbasis *webshare* untuk mencegah blokir IP.

### Struktur Proyek
- `farm.py`: Modul utama eksekusi otomasi farming.
- `gonka.py`: Core CLI dan orkestrasi worker.
- `router9.py`: Handler sinkronisasi dan routing via 9router.
- `mail.py`: Penanganan verifikasi email/inbox.
- `solver.py`: Pemecah captcha otomatis.
- `config.py`: Pengaturan konfigurasi global.

### Instalasi & Penggunaan
1. Install dependensi:
   ```bash
   pip install -r requirements.txt
   ```
2. Salin `.env.example` ke `.env` dan sesuaikan nilainya:
   ```bash
   cp .env.example .env
   ```
3. Jalankan skrip farming:
   ```bash
   python farm.py
   ```

---

## English

**GONKAFARM** is a high-performance API farming automation system designed for mass account management, automated worker OTP retrieval, and seamless data synchronization with *9router*.

### Key Features
- **Auto Farming**: Run high-efficiency parallel farming routines.
- **Worker & OTP Integration**: Automated fetching of OTP/verification codes from worker nodes.
- **9router Sync**: Seamless endpoint synchronization and session management via *9router*.
- **Proxy Support**: Built-in *webshare* proxy rotation support to prevent IP bans.

### Project Structure
- `farm.py`: Main farming automation execution module.
- `gonka.py`: Core CLI and worker orchestration.
- `router9.py`: Sync handler and routing via 9router.
- `mail.py`: Email inbox verification handler.
- `solver.py`: Automated captcha solver.
- `config.py`: Global configuration setup.

### Installation & Usage
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and configure settings:
   ```bash
   cp .env.example .env
   ```
3. Run the farming script:
   ```bash
   python farm.py
   ```

## License
MIT License
