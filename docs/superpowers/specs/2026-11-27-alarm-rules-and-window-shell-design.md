# Desain: Settings alarm dari log, audio custom, dan shell jendela native

Status: draft untuk persetujuan  
Tanggal: 2026-11-27  
Repo: `Mikrotik-Realtime-Monitor`

## Intent

Pengguna tidak ingin lagi menyunting `config.yaml` untuk pekerjaan sehari-hari. Semua pengaturan yang dipakai tiap hari harus bisa dicapai dari UI. Khusus alarm, pengguna ingin menentukan sendiri kata/kalimat dari log RouterOS yang memicu bunyi, memilih atau meng-upload audio, dan mengelola aturan tersebut. Terakhir, jendela aplikasi harus langsung maximize dan memakai tombol minimize / maximize / restore down / close milik sistem operasi, bukan tombol buatan aplikasi.

## Goals

1. Tombol **Settings** di header dashboard membuka panel/tab **Advanced** di halaman setup yang sudah ada, tanpa menghentikan collector.
2. Panel Advanced memuat pengaturan lanjutan per profil yang sekarang masih hardcode di `ProfileStore.to_appconfig()`.
3. Pengelola aturan alarm: tambah/edit/hapus aturan, enable/disable, pilih suara bawaan atau upload audio custom, atur cooldown, dan tombol test.
4. Aturan log hanya dievaluasi untuk RouterOS (`device_type == "routerros"` / `ros_version` V6 atau V7). Untuk SwOS dan perangkat SNMP generik, aturan log dilewati; warning ping/DNS tetap berjalan.
5. Aturan bawaan mempertahankan perilaku sekarang: `"radius server is not responding"` → `assets/audio-alarm.mp3`, dan DNS loss > 1% → `assets/warning.mp3`.
6. Semua jendela dibuka maximize. Kontrol jendela mengikuti OS Windows 10/11.

## Non-goals

- Tidak menambah regex engine; pencocokan cukup substring case-insensitive.
- Tidak membuat server syslog/SNMP trap. Log tetap diambil dari `/log` lewat RouterOS API yang sudah ada.
- Tidak membuat aturan per-router. Daftar aturan bersifat global, tetapi dievaluasi hanya saat profil aktif bertipe RouterOS.
- Tidak menyimpan path absolut audio custom, tidak meng-commit audio user, tidak memasukkannya ke bundle PyInstaller.
- Tidak mengubah format `config.yaml` dan dukungan `${ENV}`-nya; `--config` tetap jalur override/otomasi.

## Anti-goals

- Halaman setup tidak boleh menjadi tumpukan field mentah tanpa label; gunakan tab/group dengan nilai default yang jelas.
- Jangan mengubah tombol **Disconnect** menjadi Settings; Disconnect tetap menghentikan collector dan kembali ke setup.
- Jangan memakai title bar buatan dengan glyph `— □ ×` kalau kontrol native sudah diminta.

## Constraints

- Windows 10/11 64-bit, PyInstaller onefile, portabel dari folder `Release`.
- `app.paths.app_dir()` = folder project saat source, folder EXE saat frozen. `resource_path()` mencari file di samping EXE dulu, lalu di `_MEIPASS`.
- File user (aturan + audio) tidak boleh ditulis ke `assets/` karena folder itu bagian dari bundle. Gunakan helper baru `user_dir()`: `%LOCALAPPDATA%\MikroTik-Realtime-Monitor` di Windows, fallback `app_dir()/".userdata"` di source/non-Windows.
- Password profil sudah dienkripsi DPAPI di `routers.json` (`app/profiles.py`, `app/secrets.py`). Jangan mundur ke plaintext.
- Test Qt berjalan dengan `QT_QPA_PLATFORM=offscreen`; jangan menambah dependency baru.

## Pendekatan yang dipertimbangkan

### A. Tab Advanced di `SetupWindow` (dipilih)
Tombol gear di header dashboard menandai tab Advanced pada jendela setup yang sudah ada. Collector tidak dihentikan.

- Kelebihan: satu jendela setup, sesuai kesepakatan pengguna, tidak menambah siklus hidup window baru.
- Kekurangan: `SetupWindow` menjadi lebih padat, tetapi perlu tab/group yang rapi.

### B. Dialog Alarm Manager terpisah
Tombol gear membuka `AlarmManagerDialog` mandiri.

- Kelebihan: daftar aturan lebih lega, mudah ditambah kolom di masa depan.
- Kekurangan: menambah jendela dan satu lagi alurshow/hide; bertentangan dengan kesepakatan "panel di halaman setup".

### C. Menu dari tombol Disconnect
Tombol Disconnect diubah menjadi menu `Settings` / `Disconnect`.

- Kelebihan: paling sedikit widget baru.
- Kekurangan: menyatukan dua aksi dengan risiko berbeda menjadi satu kontrol; pengguna sudah dikonfirmasi ingin tombol Settings tersendiri.

Keputusan: **A**. Alternatif B bisa dipakai kemudian kalau daftar aturan tumbuh, tetapi bukan untuk iterasi ini.

## Desain detail

### 1. Entry point Settings

- `HeaderBar` (`app/ui.py:958`) mendapat `settings_clicked = Signal()` dan tombol gear `Settings`, ditempatkan sebelum tombol `Disconnect`.
- `MonitorWindow` mendapat `settings_requested = Signal()` baru. Jangan pakai ulang `setup_requested`, karena sinyal itu sekarang berarti disconnect dan mematikan collector.
- `main.py`:
  - `show_setup()` tetap untuk disconnect: stop dashboard, tampilkan setup.
  - `show_settings()` baru: buat/pakai ulang `SetupWindow`, pilih tab Advanced, `showMaximized()`, tanpa stop dashboard. Mode settings menyembunyikan toolbar Connect/Save/New/Delete; Close hanya `hide()` panel.
- Hubungkan `dash.settings_requested.connect(show_settings)`.
- Hubungkan `setup.settings_applied.connect(dash.apply_config)` untuk live apply.

### 2. Halaman setup bertab

`SetupWindow._build_ui()` memakai `QTabWidget` dengan empat tab:

1. **Koneksi** — form yang sudah ada (mode, IP, login, password, community, API port, identity).
2. **Interface** — discover/selected list yang sudah ada, plus kolom `max_mbps` untuk tiap interface yang dipantau.
3. **Alarm** — pengelola aturan (lihat bagian 3).
4. **Lanjutan** — override per profil untuk SNMP port/timeout/retries, API interval, polling interval/history, ping interval/timeout/window dan target, serta OID temperature/voltage/cpu/active_users.

Perubahan data:

- `RouterProfile` (`app/profiles.py:42`) mendapat field opsional dengan default yang sama seperti hardcode saat ini: `snmp_port=161`, `snmp_timeout=1.0`, `snmp_retries=1`, `api_interval=2.0`, `polling_interval=1.0`, `history_seconds=120`, `ping_interval=1.0`, `ping_timeout_ms=1000`, `ping_window=60`, `ping_targets` default 4 DNS publik yang sekarang, `oids_temperature`, `oids_voltage`, `oids_cpu`, `oids_active_users` memakai default `OidsConfig`.
- `ProfileStore.load()` membaca field lama yang tidak ada dengan aman via `.get(..., default)`; `routers.json` lama tetap terbaca.
- `ProfileStore.to_appconfig()` memakai field-field tersebut, bukan nilai hardcode.
- `_collect_profile()` / `_load_profile()` di `app/setup.py` mengisi field baru.

### 3. Model aturan alarm

Modul baru `app/alarms.py`:

```text
AlarmRule:
  id: str
  name: str                     # auto dari phrase, bukan field editable
  enabled: bool = True
  phrase: str                   # editable
  field: str = "message"        # internal, tetap "message"
  sound: str = "bundled:audio-alarm.mp3" | "custom:<relative path>"  # editable
  volume: float = 1.0           # internal, tidak ada UI
  cooldown_s: float = 30.0      # editable

AlarmSettings:
  log_rules: list[AlarmRule]
  ping_warning_enabled: bool = True
  ping_warning_sound: str = "bundled:warning.mp3"
```

`AlarmStore` menyimpan `alarm_rules.json` di `user_dir()`. Default saat file belum ada:

- satu aturan log: `id="radius"`, `phrase="radius server is not responding"`, `field="message"`, `sound="bundled:audio-alarm.mp3"`, `cooldown_s=30`, `enabled=True`;
- `ping_warning_enabled=True`, `ping_warning_sound="bundled:warning.mp3"`.

Pencocokan: `phrase.strip().lower() in str(entry.get(field, "")).lower()`. Aturan dengan phrase kosong dilewati. Field yang bisa diedit pengguna hanya `phrase`, `sound`, `cooldown_s`, dan `enabled`; `name` dibuat otomatis dari phrase, `field` tetap `message`, `volume` tetap `1.0`.

Eksekusi di `MonitorWindow._update_logs()`:

- Evaluasi aturan log **hanya** jika `config.router.device_type == "routeros"` atau `config.router.ros_version` termasuk `("V6", "V7")`.
- Untuk SwOS/other SNMP, blok aturan log dilewati; `_check_dns_warning()` tetap dipanggil untuk semua tipe.
- Dedupe: kunci `(rule.id, time, message)` menggantikan kunci lama; `cooldown_s` mencegah aturan yang sama bunyi berulang dalam waktu singkat. Batas memori `_alarm_seen` tetap 200 entri.
- `alarm_btn` tetap master switch untuk aturan log; checkbox terpisah di tab Alarm mengontrol `ping_warning_enabled`.

### 4. Audio custom

- Tombol **Upload** memakai `QFileDialog` dengan filter `.mp3 .wav .ogg`.
- Validasi: ekstensi termasuk daftar dan ukuran maksimal 2 MB.
- File disalin ke `user_dir()/alarms/<uuid>.<ext>`; nama asli hanya dipakai sebagai label. UUID mencegah path traversal dan tabrakan nama.
- Aturan menyimpan `custom:alarms/<uuid>.<ext>`, bukan path absolut. Resolver baru `user_path(relative)` di `app/paths.py` dipakai untuk memuatnya.
- Tombol **Test** memakai `AlarmPlayer` yang sudah ada untuk preview.
- Saat aturan dihapus, file custom dihapus hanya jika tidak direferensikan aturan lain. File hilang/rusak jatuh ke fallback `winsound.Beep` / `QApplication.beep()` yang sudah ada.
- `.gitignore` ditambah `.userdata/`, `alarm_rules.json`, dan `user_data/` bila fallback source dipakai.

### 5. Shell jendela native

- `FramelessMixin.setup_frameless()` tidak lagi memakai `Qt.FramelessWindowHint`. Flag kini mengandalkan frame OS (`Qt.Window` dengan hint minimize/maximize/close standar).
- `TitleBar` (`app/ui.py:10`) tetap menampilkan judul + konteks + accent, tetapi tombol `— □ ×`, drag, dan double-click toggle dihapus. Import `QSizeGrip`/`_QSizeGrip` yang jadi orphan ikut dibersihkan.
- `setWindowTitle()` sudah ada di `SetupWindow`, `MonitorWindow`, `LogDetailWindow`; judul OS akan memakainya.
- Semua titik tampil diubah ke `showMaximized()`:
  - `main.py:67` demo,
  - `main.py:86` mode `--config`,
  - `main.py:108` dan `:115` setup,
  - `main.py:128` sudah benar,
  - `app/ui.py:1536` detail log.
- Helper kecil `show_maximized(window)` boleh ditambahkan kalau memudahkan test, tapi bukan keharusan.

### 6. Test

- `tests/test_alarms.py` baru: substring matching, abaikan phrase kosong, dedupe per aturan, cooldown, dan gating RouterOS-only.
- Update `tests/test_left_panel.py` yang masih menguji `_should_alarm()` lama agar menguji rule matcher baru; perilaku RADIUS tetap sama.
- Update `tests/test_collapsible.py` dan `tests/test_dashboard_extras.py` bila resolver audio berubah.
- Test shell: pastikan title bar tidak punya tombol min/max/close buatan dan flag tidak mengandung `FramelessWindowHint`.
- Jalankan `pytest tests -q` penuh sebelum commit.

## Keputusan tambahan dari pemeriksaan desain

- Perubahan pengaturan berlaku **langsung live** melalui `MonitorWindow.apply_config()`, bukan reconnect berikutnya. `show_settings()` tetap tidak menghentikan collector saat membuka panel.
- Jika satu entri log cocok dengan beberapa aturan aktif, **hanya aturan pertama** dalam urutan daftar yang diputar. `AlarmPlayer` tetap satu instance; tidak ada queue suara.
- Cooldown dihitung dari waktu **bunyi terakhir**, bukan dari log terakhir yang cocok. Entri yang cocok tetapi tertahan cooldown tetap dimasukkan ke `_alarm_seen`, supaya tidak bunyi belakangan saat cooldown berakhir.
- Field yang bisa diedit pengguna hanya `phrase`, `sound`, `cooldown_s`, dan `enabled`; `name`, `field`, dan `volume` bersifat internal.

Keputusan pengguna:

1. Saat Settings dibuka dari dashboard, toolbar Connect/Save/New/Delete disembunyikan dan tombol Close native **hanya menutup panel Settings**, tidak menghentikan aplikasi.
2. Perubahan pengaturan **langsung live**, bukan menunggu reconnect.
3. Gear Settings **tetap tampil** di mode `--demo` dan `--config`. Karena `config.yaml` tetap authoritative untuk koneksi, tab Koneksi/Interface/Lanjutan dibaca-saja di kedua mode itu; tab Alarm tetap aktif. Ini keputusan builder yang dicatat di sini.

Konsekuensi live apply: `SetupWindow` memancarkan `settings_applied(config)`; `MonitorWindow.apply_config(config)` menghentikan worker lama, mengganti config, menyusun ulang collector, dan menjalankannya kembali dengan flag demo yang sama. `MonitorState` dibuat ulang agar counter dan history konsisten dengan interface/interval baru. Panel Settings tetap terbuka setelah apply.

## Yang diserahkan ke builder

- Layout pasti tab/group, label, ikon, dan styling.
- Apakah orphan audio dihapus segera saat rule dihapus atau saat save berikutnya.
- Nama file test dan helper internal.
- Detail validasi MIME selain extension/size.

## Catatan urutan implementasi

1. `user_dir()` + `alarm_rules.json` + `.gitignore`.
2. `app/alarms.py` + test murni (tanpa UI).
3. Integrasi gating di `_update_logs` + test UI offscreen.
4. Tab Alarm + upload audio + test resolver.
5. Ekstensi `RouterProfile` + tab Lanjutan + test load/save lama.
6. Settings signal + `show_settings()`.
7. Window flags native + `showMaximized()` di semua titik.
8. Full test, build EXE, verifikasi demo + RouterOS + SwOS.
