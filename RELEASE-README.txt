MikroTik Real-Time Monitor
==========================

Dashboard monitoring MikroTik real-time untuk Windows 10/11 64-bit.
Tidak perlu instalasi, tidak perlu Python, dan tidak perlu hak administrator.


Isi folder ini
--------------
Mikrotik-Realtime-Monitor.exe   Aplikasi utama (portable, single file)
config.example.yaml             Contoh konfigurasi lengkap (opsional)
routers.json                    Profil router tersimpan (awal: kosong)
Demo.bat                        Uji tampilan tanpa router (data contoh)
README.txt                      Panduan ini


Menjalankan
-----------
1. Salin seluruh folder ini ke komputer tujuan (boleh lewat flashdisk).
   Letakkan di folder yang bisa ditulis (mis. Desktop atau D:\Tools), bukan
   di "Program Files", karena profil router disimpan di samping file .exe.
2. Klik dua kali "Mikrotik-Realtime-Monitor.exe".
3. Di layar "MikroTik Device Manager", isi:
   - Host / IP Address router
   - Login dan Password  (opsional; diperlukan untuk jumlah user aktif yang akurat)
   - SNMP Community      (default: public)
   - Versi RouterOS      (V6 / V7, atau SwOS untuk switch MikroTik)
4. Klik "Scan Interfaces", lalu pilih port yang dipantau dengan tombol "Use".
5. Klik "Save Profile", lalu "Connect" untuk membuka dashboard.

Profil tersimpan otomatis di routers.json, jadi koneksi berikutnya cukup
pilih profil lalu Connect. Tombol "Disconnect" menghentikan polling dan
kembali ke layar login tanpa menghapus profil.

Untuk mencoba tampilan tanpa router, klik dua kali Demo.bat (data contoh).


Syarat di router
----------------
Aktifkan SNMP (wajib):
    /snmp community add name=monitor addresses=192.168.0.0/16 read-access=yes
    /snmp set enabled=yes

Opsional, agar jumlah PPPoE/HotSpot user aktif akurat (RouterOS API):
    /ip service enable api
    /ip service set api address=192.168.0.0/16
    /user add name=monitor group=read password="password-kuat"

Sesuaikan alamat network dengan subnet Anda.


Kompatibilitas Windows
----------------------
- Windows 10 versi 1809 (build 17763) atau lebih baru, 64-bit.
- Windows 11, 64-bit.
- Visual C++ Redistributable TIDAK perlu di-install (DLL sudah dibundel).
- Jika SmartScreen muncul: klik "More info" lalu "Run anyway"
  (file .exe belum ditandatangani secara digital).
- Antivirus dapat memindai file saat pertama dijalankan; tunggu beberapa detik.
- Izinkan aplikasi keluar pada firewall untuk:
  UDP 161 (SNMP), TCP 8728/8729 (API), dan ICMP (ping).


Data dan privasi
----------------
Profil router, termasuk password, disimpan lokal di routers.json pada folder
ini. File routers.json yang disertakan sengaja kosong; isi melalui aplikasi.
Password dienkripsi dengan Windows DPAPI milik user yang sedang login, sehingga
hanya bisa dibuka di komputer dan akun Windows yang sama. Saat memindahkan
aplikasi ke komputer lain, salin routers.json bila ingin membawa daftar profil,
lalu ketik ulang password-nya di layar pengaturan.


Pemecahan masalah
-----------------
- Status OFFLINE / timeout     : cek IP router, SNMP community, dan firewall.
- Grafik kosong / NOT FOUND    : nama interface harus sama dengan ifName.
                                 Gunakan "Scan Interfaces" untuk melihat nama.
- Temp / Volt menampilkan "--" : model router tidak memiliki sensor tersebut.
- Active Users 0               : SNMP hanya menghitung HotSpot; aktifkan API
                                 untuk menghitung PPPoE.
- Ping loss 100%               : target memblokir ICMP atau firewall lokal.
- Scan tidak menemukan port    : host/community salah atau SNMP diblokir.

Panduan lengkap (bahasa Inggris) ada di README.md pada folder proyek.
