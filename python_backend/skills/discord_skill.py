import time
import platform
import subprocess

CURRENT_OS = platform.system()

# Sadece Windows'ta çalışacak kütüphaneler
if CURRENT_OS == "Windows":
    import pygetwindow as gw
    import ctypes


# ==========================================
# İŞLETİM SİSTEMİNE ÖZEL ODAKLANMA (FOCUS) İŞÇİLERİ
# ==========================================
def _focus_discord_windows():
    discord_win = None
    for win in gw.getAllWindows():
        if win.title == "Discord" or win.title.endswith("- Discord"):
            discord_win = win
            break

    if not discord_win:
        print("[DİSCORD YETENEĞİ] HATA: Discord açık değil.")
        return False
    try:
        if discord_win.isMinimized:
            discord_win.restore()
            time.sleep(0.2)
        user32 = ctypes.windll.user32
        user32.keybd_event(0x12, 0, 0, 0)
        time.sleep(0.05)
        user32.SetForegroundWindow(discord_win._hWnd)
        user32.keybd_event(0x12, 0, 2, 0)
        time.sleep(0.1)
    except:
        pass
    time.sleep(0.8)
    return True


def _focus_discord_linux():
    print("[LINUX] Discord (Vesktop) penceresi odaklanıyor...")
    try:
        # wmctrl çalışırsa pencere öne gelir, çalışmazsa sessizce pas geçer
        subprocess.run(["wmctrl", "-a", "discord"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["wmctrl", "-a", "vesktop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
    time.sleep(0.8)
    return True


def _focus_discord_mac():
    try:
        subprocess.run(["open", "-a", "Discord"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except:
        pass
    time.sleep(0.8)
    return True


def _focus_discord():
    """İşletim sistemine göre doğru odaklanma işçisini çağırır."""
    if CURRENT_OS == "Windows":
        return _focus_discord_windows()
    elif CURRENT_OS == "Linux":
        return _focus_discord_linux()
    elif CURRENT_OS == "Darwin":
        return _focus_discord_mac()
    return False


# ==========================================
# KLAVYE ŞELALESİ (THE KEYBOARD WATERFALL)
# ==========================================
def _send_keys_waterfall(search_query):
    """
    Klavye otomasyonunu katman katman dener.
    Biri başarısız olursa diğerine geçer. Hiçbiri çalışmazsa False döner.
    """

    # KATMAN 1: PyAutoGUI (Windows, Mac, Linux X11)
    try:
        import pyautogui
        import pyperclip
        pyautogui.hotkey('ctrl', 'k')
        time.sleep(0.5)
        pyperclip.copy(search_query)
        pyautogui.hotkey('ctrl', 'v')
        time.sleep(1.2)
        pyautogui.press('enter')
        return True
    except Exception as e:
        print(f"[ŞELALE] PyAutoGUI başarısız oldu veya engellendi: {e}")

    # KATMAN 2 & 3: Wayland Özel Araçları (Sadece Linux)
    if CURRENT_OS == "Linux":
        # Katman 2: wtype (Wayland Native)
        try:
            print("[ŞELALE] wtype deneniyor...")
            subprocess.run(["wtype", "-M", "ctrl", "k", "-m", "ctrl"], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            subprocess.run(["wtype", search_query], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.2)
            subprocess.run(["wtype", "-k", "Return"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[ŞELALE] wtype başarısız oldu: {e}")

        # Katman 3: ydotool (Hardware Level Wayland)
        try:
            print("[ŞELALE] ydotool deneniyor (sudo gerekebilir)...")
            # 29: LCtrl, 37: K, 28: Enter
            subprocess.run(["ydotool", "key", "29:1", "37:1", "37:0", "29:0"], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            subprocess.run(["ydotool", "type", search_query], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            time.sleep(1.2)
            subprocess.run(["ydotool", "key", "28:1", "28:0"], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            return True
        except Exception as e:
            print(f"[ŞELALE] ydotool başarısız oldu: {e}")

    # Bütün katmanlar çökerse False döndür (Beyin bu durumda kullanıcıdan tıklamasını isteyecek)
    print("[ŞELALE] TÜM KLAVYE SİMÜLASYONLARI BAŞARISIZ! Yetki veya destek yok.")
    return False


# ==========================================
# EVRENSEL TRAFİK POLİSLERİ (YÖNLENDİRİCİLER)
# ==========================================
def go_to_channel(server_name, channel_name, channel_type="text"):
    try:
        print(f"[DİSCORD YETENEĞİ] Kanala Gidiliyor: '{channel_name}' ({server_name}) - Tip: {channel_type}")

        if not _focus_discord():
            return False

        # Prefix belirleme
        if channel_type == "voice":
            prefix = "!"
            clean_channel = channel_name.replace('!', '').strip()
        elif channel_type == "text":
            prefix = "#"
            clean_channel = channel_name.replace('#', '').strip()
        else:
            prefix = "@"
            clean_channel = channel_name.replace('@', '').strip()

        # Arama kelimesini oluşturma
        search_query = f"{prefix}{clean_channel}"
        if server_name:
            server_first_word = server_name.split()[0].strip()
            search_query = f"{prefix}{clean_channel} {server_first_word}"

        # Şelaleyi tetikle ve sonucu beyne bildir
        success = _send_keys_waterfall(search_query)

        if success:
            print(f"[DİSCORD YETENEĞİ] '{channel_name}' kanalına gidildi.")
            return True
        else:
            return False

    except Exception as e:
        print(f"[DİSCORD YETENEĞİ] İşlem sırasında hata oluştu: {e}")
        return False


# Mute ve Deafen fonksiyonlarını şimdilik tutuyoruz ancak beyin wpctl kullanacak
def mute_toggle():
    try:
        print(f"[DİSCORD YETENEĞİ] Mikrofon sessize alma/açma işlemi başlatılıyor.")
        if not _focus_discord(): return False
        import pyautogui
        pyautogui.hotkey('ctrl', 'shift', 'm', interval=0.1)
        time.sleep(0.2)
        return True
    except:
        return False


def deafen_toggle():
    try:
        print(f"[DİSCORD YETENEĞİ] Kulaklık sessize alma/açma işlemi başlatılıyor.")
        if not _focus_discord(): return False
        import pyautogui
        pyautogui.hotkey('ctrl', 'shift', 'd', interval=0.2)
        return True
    except:
        return False


# --- İZOLE TEST ALANI ---
if __name__ == "__main__":
    # go_to_channel("hakanct Dev", "genel")
    # send_message("hakanct Dev", "genel", "Mustafa Yargıç 'İlk Kelime' filtresi testidir. Hedef şaştı mı?")
    go_to_channel("purna", "oyun", "voice")
    # mute_toggle()
    # deafen_toggle()