import os
import json
import subprocess
import re
from encodings.hex_codec import hex_decode

import psutil
import platform
import shutil

# ==========================================
# 1. OPTİMİZASYON: İŞLETİM SİSTEMİ TESPİTİ
# (Modül yüklendiğinde sadece 1 kez çalışır)
# ==========================================
CURRENT_OS = platform.system()


# ==========================================
# ORTAK YARDIMCI FONKSİYONLAR
# ==========================================
def get_app_data_dir():
    """İşletim sistemine göre güvenli ve gizli AppData klasörünü bulur/oluşturur."""
    app_name = "MustafaYargicAsistan"

    if CURRENT_OS == "Windows":
        base_dir = os.environ.get("LOCALAPPDATA", os.environ.get("APPDATA"))
    else:
        base_dir = os.path.expanduser("~/.config")

    app_dir = os.path.join(base_dir, app_name)
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def load_aliases():
    """JSON dosyasını AppData klasöründen okur, yoksa boş bir şablonla oluşturur."""
    file_path = os.path.join(get_app_data_dir(), "app_aliases.json")

    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    else:
        print(f"[SİSTEM] {file_path} bulunamadı. Örnek şablon oluşturuluyor...")
        default_aliases = {
            "discord": "flatpak run com.discordapp.Discord" if CURRENT_OS == "Linux" else "C:\\Program Files\\Discord\\Update.exe --processStart Discord.exe"
        }
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(default_aliases, file, indent=4, ensure_ascii=False)
        return default_aliases


# ==========================================
# WINDOWS ÖZEL KASLARI
# ==========================================
def _find_shortcut_in_start_menu(target_name_lower):
    """Windows Başlat Menüsü klasörlerini tarar."""
    user_start_menu = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
    system_start_menu = os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs")

    target_norm = re.sub(r'[^a-z0-9]', '', target_name_lower)

    for directory in [user_start_menu, system_start_menu]:
        if not os.path.exists(directory):
            continue
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(".lnk"):
                    clean_name = file[:-4].lower().strip()
                    file_norm = re.sub(r'[^a-z0-9]', '', clean_name)

                    if target_name_lower == clean_name or target_norm == file_norm:
                        return os.path.join(root, file)
    return None


def _open_app_windows(app_path, safe_target, target_name_lower):
    # Katman 1: Aliases (app_path doluysa doğrudan çalıştır)
    if app_path:
        if app_path.startswith("steam://") or app_path.startswith("http"):
            os.startfile(app_path)
            return True
        else:
            try:
                # Geçerli bir dosya yoluysa Popen çalışır
                subprocess.Popen(app_path)
                return True
            except FileNotFoundError:
                print(f"[WINDOWS] '{app_path}' doğrudan bulunamadı, Başlat Menüsü taranıyor...")
                pass  # Hata verirse pes etme, aşağıdaki katmanlara (Katman 2) geç!

    # Katman 2: Başlat Menüsü Kısayolları
    print(f"[WINDOWS] '{safe_target}' Başlat Menüsünde aranıyor...")
    shortcut_path = _find_shortcut_in_start_menu(target_name_lower)
    if shortcut_path:
        os.startfile(shortcut_path)
        return True

    # Katman 3: Sistem PATH (Çalıştır / cmd mantığı)
    os.system(f'start "" "{safe_target}"')
    return True


def _close_app_windows(found_exe_names, safe_target, alias_path=""):
    killed = False
    if found_exe_names:
        for exe in found_exe_names:
            print(f"[WINDOWS] Kapatma sinyali gönderiliyor: {exe}")
            subprocess.run(["taskkill", "/F", "/IM", exe, "/T"], creationflags=subprocess.CREATE_NO_WINDOW)
            killed = True

    if not killed and safe_target:
        guess_exe = f"{safe_target}.exe"
        subprocess.run(["taskkill", "/F", "/IM", guess_exe, "/T"], creationflags=subprocess.CREATE_NO_WINDOW)
    return True


# ==========================================
# LINUX ÖZEL KASLARI (EVRENSEL MİMARİ)
# ==========================================
def _parse_linux_desktop_entry(target_name_lower):
    """XDG Standartlarına göre .desktop dosyalarını okur ve çalıştırılabilir komutu (Exec) süzer."""
    directories = [
        os.path.expanduser("~/.local/share/applications"),
        "/usr/share/applications",
        "/var/lib/flatpak/exports/share/applications",
        "/var/lib/snapd/desktop/applications"
    ]

    # Hedef kelimedeki tüm boşluk ve özel karakterleri sil (Örn: "youtube music" -> "youtubemusic")
    target_norm = re.sub(r'[^a-z0-9]', '', target_name_lower)

    for directory in directories:
        if not os.path.exists(directory):
            continue
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(".desktop"):
                    # Dosya adındaki tüm boşluk/özel karakterleri sil (Örn: "youtube_music.desktop" -> "youtubemusicdesktop")
                    file_norm = re.sub(r'[^a-z0-9]', '', file.lower())

                    # Hem normal hem de normalize edilmiş (agresif) eşleşmeyi kontrol et
                    if target_name_lower in file.lower() or target_norm in file_norm:
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if line.startswith("Exec="):
                                        # Exec= satırını al ve %U, %F gibi parametreleri temizle
                                        exec_cmd = line.strip()[5:]
                                        exec_cmd = re.sub(r'%[a-zA-Z]', '', exec_cmd).strip()
                                        return exec_cmd
                        except:
                            continue
    return None


def _open_app_linux(app_path, safe_target, target_name_lower):
    # Katman 1: Aliases (.AppImage, özel scriptler, Flatpak id'leri)
    if app_path:
        subprocess.Popen(app_path.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    # Katman 2: XDG Desktop Entries (Sistem Menüsü)
    print(f"[LINUX] '{safe_target}' masaüstü dosyalarında aranıyor (.desktop)...")
    exec_cmd = _parse_linux_desktop_entry(target_name_lower)
    if exec_cmd:
        print(f"[LINUX] Eşleşme bulundu, çalıştırılıyor: {exec_cmd}")
        subprocess.Popen(exec_cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    # Katman 3: PATH Çevre Değişkeni Taraması (shutil.which)
    print(f"[LINUX] '{safe_target}' Sistem PATH'inde (Terminal Komutlarında) aranıyor...")
    system_cmd = shutil.which(safe_target.lower())
    if system_cmd:
        subprocess.Popen([system_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    print(f"[HATA] '{safe_target}' Linux sisteminde bulunamadı. Lütfen app_aliases.json dosyasına ekleyin.")
    return False


def _close_app_linux(found_exe_names, safe_target, alias_path=""):
    killed = False

    # 1. AŞAMA: Eğer uygulama bir Flatpak ise, kendi özel ve anında kapatan komutuyla öldür
    if alias_path and "flatpak run" in alias_path.lower():
        parts = alias_path.split()
        if len(parts) > 2:
            app_id = parts[2]
            print(f"[LINUX] Flatpak uygulaması kapatılıyor: {app_id}")
            subprocess.run(["flatpak", "kill", app_id])
            killed = True

    # 2. AŞAMA: RAM'de bulduğumuz işlemleri SIGKILL (-9) ile anında yok et (Vesktop Gecikme Çözümü)
    if found_exe_names:
        for exe in found_exe_names:
            print(f"[LINUX] Zorla kapatma sinyali gönderiliyor (SIGKILL): {exe}")
            subprocess.run(["pkill", "-9", "-f", exe])
            killed = True

    # 3. AŞAMA: Hala ölmediyse safe_target ile kör atış (Yine SIGKILL)
    if not killed and safe_target:
        subprocess.run(["pkill", "-9", "-f", safe_target])
    return True


# ==========================================
# TRAFİK POLİSLERİ (ANA YÖNLENDİRİCİLER)
# ==========================================
def open_application(target_name):
    """Hedef ismini alır, güvenlik filtresinden geçirir ve uygun işletim sistemi işçisine devreder."""
    aliases = load_aliases()
    target_name_lower = target_name.lower().strip()

    safe_target = re.sub(r'[^a-zA-Z0-9\s_-]', '', target_name).strip()
    if not safe_target:
        return False

    app_path = aliases.get(target_name_lower)
    if app_path:
        print(f"[{target_name}] özel yoldan (aliases) yönlendiriliyor.")

    try:
        if CURRENT_OS == "Windows":
            return _open_app_windows(app_path, safe_target, target_name_lower)
        elif CURRENT_OS == "Linux":
            return _open_app_linux(app_path, safe_target, target_name_lower)
        else:
            print(f"[SİSTEM] Desteklenmeyen İşletim Sistemi: {CURRENT_OS}")
            return False
    except Exception as e:
        print(f"[SİSTEM] Uygulama açılırken hata oluştu: {e}")
        return False


def close_application(target_name):
    """RAM'i evrensel olarak tarar, aliases'tan tersine mühendislik yapar ve uygun işçiye devreder."""
    aliases = load_aliases()
    target_name_lower = target_name.lower().strip()
    safe_target = re.sub(r'[^a-zA-Z0-9\s_-]', '', target_name_lower).strip()

    alias_path = aliases.get(target_name_lower, "")

    print(f"[{target_name}] arka planda taranıyor...")
    found_exe_names = set()

    # TERSİNE MÜHENDİSLİK (Reverse Alias Extraction)
    # Hedef adını bulamazsa Alias dosyasındaki yoldan dosya adını çeker (Örn: pear-desktop)
    search_terms = [target_name_lower, safe_target]
    if alias_path:
        if "flatpak run" in alias_path.lower():
            parts = alias_path.split()
            if len(parts) > 2:
                search_terms.append(parts[2].lower())  # com.discordapp.Discord
        else:
            base = os.path.basename(alias_path.split()[0]).lower()
            search_terms.append(base)  # pear-desktop.appimage
            search_terms.append(base.split('.')[0])  # pear-desktop

    # 1 karakterden kısa terimleri çöpe at
    search_terms = [term for term in search_terms if len(term) > 1]

    # İşletim sisteminden bağımsız evrensel RAM ve CMD satırı taraması
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            p_name = proc.info.get('name')
            p_cmd = proc.info.get('cmdline')
            if not p_name: continue

            p_name_lower = p_name.lower()
            p_cmd_str = " ".join(p_cmd).lower() if p_cmd else ""

            # Dinamik ürettiğimiz tüm kelimeleri RAM'de ara
            for term in search_terms:
                term_norm = re.sub(r'[^a-z0-9]', '', term)

                # 1. Normal Eşleşme
                if term in p_name_lower or term in p_cmd_str:
                    found_exe_names.add(p_name)
                    break

                    # 2. Agresif (Normalize Edilmiş) Eşleşme
                p_name_norm = re.sub(r'[^a-z0-9]', '', p_name_lower)
                p_cmd_norm = re.sub(r'[^a-z0-9]', '', p_cmd_str)

                if term_norm and (term_norm in p_name_norm or term_norm in p_cmd_norm):
                    found_exe_names.add(p_name)
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    try:
        # Sonucu tespit edilen OS'e göre uygun işçiye pasla
        if CURRENT_OS == "Windows":
            return _close_app_windows(found_exe_names, safe_target, alias_path)
        elif CURRENT_OS == "Linux":
            return _close_app_linux(found_exe_names, safe_target, alias_path)
        else:
            return False
    except Exception as e:
        print(f"[SİSTEM] Uygulama kapatılırken beklenmedik bir hata: {e}")
        return False


# ==========================================
# DONANIMSAL SES KONTROLLERİ (OS-LEVEL AUDIO)
# ==========================================

def _get_windows_volume_interface(is_mic=False):
    """PYCAW KULLANMADAN direkt Windows COM API ile Saf (Native) Ses Kontrolü."""
    import comtypes
    from ctypes import POINTER, cast, c_float, c_uint
    from ctypes.wintypes import DWORD, BOOL
    from comtypes import IUnknown, GUID, COMMETHOD

    # Windows Ses Çekirdeği Kimlikleri (GUIDs)
    CLSID_MMDeviceEnumerator = GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}')
    
    class IMMDevice(IUnknown):
        _iid_ = GUID('{D666063F-1587-4E43-81F1-B948E807363F}')
        _methods_ = [
            COMMETHOD([], comtypes.HRESULT, 'Activate',
                      (['in'], POINTER(GUID), 'iid'),
                      (['in'], DWORD, 'dwClsCtx'),
                      (['in'], POINTER(DWORD), 'pActivationParams'),
                      (['out', 'retval'], POINTER(POINTER(IUnknown)), 'ppInterface'))
        ]

    class IMMDeviceEnumerator(IUnknown):
        _iid_ = GUID('{A95664D2-9614-4F35-A746-DE8DB63617E6}')
        _methods_ = [
            COMMETHOD([], comtypes.HRESULT, 'EnumAudioEndpoints', (['in'], DWORD), (['in'], DWORD), (['out', 'retval'], POINTER(POINTER(IUnknown)))),
            COMMETHOD([], comtypes.HRESULT, 'GetDefaultAudioEndpoint',
                      (['in'], DWORD, 'dataFlow'),
                      (['in'], DWORD, 'role'),
                      (['out', 'retval'], POINTER(POINTER(IMMDevice)), 'ppEndpoint'))
        ]

    class IAudioEndpointVolume(IUnknown):
        _iid_ = GUID('{5CDF2C82-841E-4546-9722-0CF74078229A}')
        _methods_ = [
            COMMETHOD([], comtypes.HRESULT, 'RegisterControlChangeNotify', (['in'], POINTER(IUnknown))),
            COMMETHOD([], comtypes.HRESULT, 'UnregisterControlChangeNotify', (['in'], POINTER(IUnknown))),
            COMMETHOD([], comtypes.HRESULT, 'GetChannelCount', (['out', 'retval'], POINTER(c_uint))),
            COMMETHOD([], comtypes.HRESULT, 'SetMasterVolumeLevel', (['in'], c_float), (['in'], POINTER(GUID))),
            COMMETHOD([], comtypes.HRESULT, 'SetMasterVolumeLevelScalar', (['in'], c_float, 'fLevel'), (['in'], POINTER(GUID), 'pguidEventContext')),
            COMMETHOD([], comtypes.HRESULT, 'GetMasterVolumeLevel', (['out', 'retval'], POINTER(c_float))),
            COMMETHOD([], comtypes.HRESULT, 'GetMasterVolumeLevelScalar', (['out', 'retval'], POINTER(c_float), 'pfLevel')),
            COMMETHOD([], comtypes.HRESULT, 'SetChannelVolumeLevel', (['in'], c_uint), (['in'], c_float), (['in'], POINTER(GUID))),
            COMMETHOD([], comtypes.HRESULT, 'SetChannelVolumeLevelScalar', (['in'], c_uint), (['in'], c_float), (['in'], POINTER(GUID))),
            COMMETHOD([], comtypes.HRESULT, 'GetChannelVolumeLevel', (['in'], c_uint), (['out', 'retval'], POINTER(c_float))),
            COMMETHOD([], comtypes.HRESULT, 'GetChannelVolumeLevelScalar', (['in'], c_uint), (['out', 'retval'], POINTER(c_float))),
            COMMETHOD([], comtypes.HRESULT, 'SetMute', (['in'], BOOL, 'bMute'), (['in'], POINTER(GUID), 'pguidEventContext')),
            COMMETHOD([], comtypes.HRESULT, 'GetMute', (['out', 'retval'], POINTER(BOOL), 'pbMute'))
        ]

    try:
        comtypes.CoInitialize()
        enumerator = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator,
            IMMDeviceEnumerator,
            comtypes.CLSCTX_INPROC_SERVER
        )
        
        # eRender = 0 (Hoparlör), eCapture = 1 (Mikrofon), eMultimedia = 1
        data_flow = 1 if is_mic else 0
        endpoint = enumerator.GetDefaultAudioEndpoint(data_flow, 1)
        
        # 23 = CLSCTX_ALL
        interface = endpoint.Activate(IAudioEndpointVolume._iid_, 23, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception as e:
        print(f"[WINDOWS SES HATA] Native COM Arayüzü başlatılamadı: {e}")
        return None


def _set_windows_audio(is_mic, action):
    """Windows mikrofon/hoparlör tamamen susturur veya açar."""
    try:
        volume = _get_windows_volume_interface(is_mic)
        if not volume: return False
        
        current_mute = volume.GetMute()
        
        if action == "mute":
            volume.SetMute(1, None)
        elif action == "unmute":
            volume.SetMute(0, None)
        elif action == "toggle":
            volume.SetMute(0 if current_mute else 1, None)
            
        return True
    except Exception as e:
        print(f"[DONANIM HATA] Windows ses kontrolü başarısız: {e}")
        return False


def system_mic_control(action="toggle"):
    """Sistem genelinde varsayılan mikrofonu wpctl (Linux) veya pycaw (Windows) ile ayarlar."""
    try:
        if CURRENT_OS == "Linux":
            val = "toggle"
            if action == "mute":
                val = "1"
            elif action == "unmute":
                val = "0"
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", val], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            print(f"[DONANIM] Mikrofon durumu donanımsal olarak değiştirildi (Linux): {action.upper()}")
            return True
        elif CURRENT_OS == "Windows":
            success = _set_windows_audio(is_mic=True, action=action)
            if success:
                print(f"[DONANIM] Windows mikrofon durumu donanımsal değiştirildi: {action.upper()}")
            return success
    except Exception as e:
        print(f"[DONANIM] Mikrofon kontrol hatası: {e}")
        return False


def system_audio_control(action="toggle"):
    """Sistem genelinde varsayılan hoparlörü wpctl (Linux) veya pycaw (Windows) ile ayarlar."""
    try:
        if CURRENT_OS == "Linux":
            val = "toggle"
            if action == "mute":
                val = "1"
            elif action == "unmute":
                val = "0"
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", val], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            print(f"[DONANIM] Sistem sesi donanımsal olarak değiştirildi (Linux): {action.upper()}")
            return True
        elif CURRENT_OS == "Windows":
            success = _set_windows_audio(is_mic=False, action=action)
            if success:
                print(f"[DONANIM] Windows hoparlör durumu donanımsal değiştirildi: {action.upper()}")
            return success
    except Exception as e:
        print(f"[DONANIM] Hoparlör kontrol hatası: {e}")
        return False


# ==========================================
# SİSTEM SES SEVİYESİ KONTROLLERİ
# ==========================================

_SAVED_SYSTEM_VOLUME = None


def _get_system_volume_linux():
    result = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], capture_output=True, text=True)
    output_text = result.stdout.strip()
    if not output_text: return None

    match = re.search(r"([\d\.]+)", output_text)
    if match: return float(match.group(1))
    return None


def _get_system_volume_windows():
    """Windows'ta master ses seviyesini okur (0.0 - 1.0 arası)."""
    try:
        volume = _get_windows_volume_interface(is_mic=False)
        if not volume: return None
        return volume.GetMasterVolumeLevelScalar()
    except Exception as e:
        print(f"[WINDOWS SES HATA] Ses okuma başarısız: {e}")
        return None


def get_system_volume():
    try:
        if CURRENT_OS == "Linux":
            return _get_system_volume_linux()
        elif CURRENT_OS == "Windows":
            return _get_system_volume_windows()
    except Exception as e:
        print(f"[DONANIM] Hoparlör kontrol hatası: {e}")
        return None


def _set_system_volume_linux(target_volume):
    volume_str = f"{target_volume:.2f}"
    subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", volume_str], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    return True


def _set_system_volume_windows(target_volume):
    """Windows'ta master ses seviyesini ayarlar."""
    try:
        volume = _get_windows_volume_interface(is_mic=False)
        if not volume: return False
        
        # Olası çökmeleri engellemek için değeri 0.0 ile 1.0 aralığına zorla
        safe_volume = max(0.0, min(1.0, float(target_volume)))
        volume.SetMasterVolumeLevelScalar(safe_volume, None)
        return True
    except Exception as e:
        print(f"[WINDOWS SES HATA] Ses ayarlama başarısız: {e}")
        return False


def set_system_volume(target_volume):
    global _SAVED_SYSTEM_VOLUME
    try:
        if CURRENT_OS == "Linux":
            if _SAVED_SYSTEM_VOLUME is not None:
                _SAVED_SYSTEM_VOLUME = target_volume
            else:
                _set_system_volume_linux(target_volume)
        elif CURRENT_OS == "Windows":
            if _SAVED_SYSTEM_VOLUME is not None:
                _SAVED_SYSTEM_VOLUME = target_volume
            else:
                _set_system_volume_windows(target_volume)
        return True
    except Exception as e:
        print(f"[DONANIM] Hoparlör kontrol hatası: {e}")
        return False


# ==========================================
# DUCKİNG İŞLEMLERİ
# ==========================================

def start_ducking():
    """Asistan dinlemeye başladığında (veya konuştuğunda) müziği kısar."""
    global _SAVED_SYSTEM_VOLUME
    print("[DUCKING] Ses geçici olarak kısılıyor.")

    current_volume = get_system_volume()
    if current_volume is None: return False

    if _SAVED_SYSTEM_VOLUME is None:
        _SAVED_SYSTEM_VOLUME = current_volume

    if CURRENT_OS == "Linux":
        _set_system_volume_linux(current_volume * 0.30)
    elif CURRENT_OS == "Windows":
        _set_system_volume_windows(current_volume * 0.30)

    return True


def stop_ducking():
    """Asistan sustuğunda (işlem bittiğinde) müziği eski haline döndürür."""
    global _SAVED_SYSTEM_VOLUME
    print("[DUCKING] Ses orijinal seviyesine döndürülüyor.")

    if _SAVED_SYSTEM_VOLUME is None:
        return False

    if CURRENT_OS == "Linux":
        _set_system_volume_linux(_SAVED_SYSTEM_VOLUME)
    elif CURRENT_OS == "Windows":
        _set_system_volume_windows(_SAVED_SYSTEM_VOLUME)

    _SAVED_SYSTEM_VOLUME = None
    return True


# ==========================================
# MEDYA KONTROLLERİ
# ==========================================
def _media_control_linux(action):
    try:
        subprocess.run(["playerctl", action], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"[Linux] Medya kontrol hatası: {e}")


def _media_control_windows(action):
    import ctypes

    if action in ["play", "pause"]:
        is_playing = _is_media_playing_windows()

        if is_playing is not None:
            if action == "play" and is_playing:
                print("[MEDYA] Medya zaten çalıyor. Tuş basma işlemi pas geçildi.")
                return True
            elif action == "pause" and not is_playing:
                print("[MEDYA] Medya zaten duraklatılmış. Tuş basma işlemi pas geçildi.")
                return True

    VK_MEDIA_NEXT = 0xB0
    VK_MEDIA_PREV = 0xB1
    VK_MEDIA_PLAY_PAUSE = 0xB3

    windows_key_map = {
        "play-pause": VK_MEDIA_PLAY_PAUSE,
        "play": VK_MEDIA_PLAY_PAUSE,
        "pause": VK_MEDIA_PLAY_PAUSE,
        "next": VK_MEDIA_NEXT,
        "previous": VK_MEDIA_PREV
    }

    vk_code = windows_key_map.get(action)

    if vk_code:
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)  # key down
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # key up
        print(f"[WINDOWS] Medya donanım tuşu tetiklendi: {action.upper()}")
        return True
    else:
        print(f"[WINDOWS] Geçersiz medya komutu: {action}")
        return False


def _is_media_playing_windows():
    """Windows'ta medyanın aktif olarak çalıp çalmadığını kontrol eder."""
    import asyncio
    try:
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager
    except ImportError:
        print("[WINDOWS] 'winsdk' kütüphanesi eksik. Durum tespiti yapılamıyor.")
        return None  # Kütüphane yoksa kör atış yapmaya devam etmesi için None dönüyoruz

    async def get_status():
        manager = await GlobalSystemMediaTransportControlsSessionManager.request_async()
        session = manager.get_current_session()
        if session:
            info = session.get_playback_info()
            # PlaybackStatus değerleri: 2 = Stopped, 3 = Playing, 4 = Paused
            return info.playback_status == 4
        return False  # Açık bir medya uygulaması yoksa çalmıyordur

    return asyncio.run(get_status())


def media_control(action="toggle"):
    media_actions = {
        "toggle": "play-pause",
        "play": "play",
        "pause": "pause",
        "next": "next",
        "prev": "previous",
    }
    target_action = media_actions.get(action)
    if target_action:
        if CURRENT_OS == "Linux":
            _media_control_linux(target_action)
        elif CURRENT_OS == "Windows":
            _media_control_windows(target_action)
    else:
        print(f"[MEDYA UYARISI] Geçersiz eylem: {action}")


# --- TEST ALANI ---
if __name__ == "__main__":
    pass
    # open_application("youtube music")
    # close_application("youtube music")
    # system_mic_control("toggle")
    # system_audio_control("toggle")