import os
import platform
import time
import requests
import json
import fnmatch
from pypresence import Client
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI = "http://127.0.0.1:6463"


def get_app_data_dir():
    """İşletim sistemine göre güvenli ve gizli AppData klasörünü bulur/oluşturur."""
    app_name = "MustafaYargicAsistan"

    if platform.system() == "Windows":
        base_dir = os.environ.get("LOCALAPPDATA", os.environ.get("APPDATA"))
    else:
        base_dir = os.path.expanduser("~/.config")

    app_dir = os.path.join(base_dir, app_name)
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


TOKEN_FILE = os.path.join(get_app_data_dir(), "discord_tokens.json")
CACHE_FILE = os.path.join(get_app_data_dir(), "discord_cache.json")


class DiscordIPC:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret

        # ==========================================
        # LINUX DERİN SOKET TARAMASI (FLATPAK KÖPRÜSÜ)
        # ==========================================
        if platform.system() == "Linux":
            print("\n[DİSCORD IPC] Linux sistemi tespit edildi, soket derin taraması başlatılıyor...")
            uid = os.getuid()
            base_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")

            found_socket_dir = None

            # Sadece belirli klasörleri değil, kullanıcının XDG çalışma dizinini kökten uca tara
            for root, dirnames, filenames in os.walk(base_dir):
                for filename in fnmatch.filter(filenames, 'discord-ipc-*'):
                    full_path = os.path.join(root, filename)
                    print(f"[DİSCORD IPC] Soket bulundu: {full_path}")
                    found_socket_dir = root
                    break
                if found_socket_dir:
                    break

            if found_socket_dir:
                print(f"[DİSCORD IPC] Rota '{found_socket_dir}' olarak ayarlandı.")
                os.environ["XDG_RUNTIME_DIR"] = found_socket_dir
            else:
                print("[DİSCORD IPC] KRİTİK HATA: Sistemde hiçbir 'discord-ipc-0' soketi bulunamadı!")
                print("[DİSCORD IPC] Discord uygulamasının açık olduğundan emin olun.")
        # ==========================================

        self.client = Client(self.client_id)
        self.connected = False
        self.access_token = None
        self.last_seen_channel_id = None

    # --- DOSYA YÖNETİMİ ---
    def _load_json(self, file_path):
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_json(self, file_path, data):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def update_cache(self, server_name, category_name, channel_name, channel_id, channel_type="text",
                     score_increment=1):
        """Kanal verisini Hiyerarşik JSON yapısına (Tipiyle birlikte) kaydeder."""
        cache = self._load_json(CACHE_FILE)

        server = server_name.lower()
        category = category_name.lower()
        channel = channel_name.lower()

        if server not in cache:
            cache[server] = {}
        if category not in cache[server]:
            cache[server][category] = {}

        if channel not in cache[server][category]:
            cache[server][category][channel] = {"id": channel_id, "type": channel_type, "use_count": 0}

        cache[server][category][channel]["use_count"] += score_increment
        self._save_json(CACHE_FILE, cache)
        print(
            f"[DİSCORD IPC ÖĞRENME] '{channel}' ({channel_type}) kanalının puanı {cache[server][category][channel]['use_count']} oldu.")

    def _on_channel_select_event(self, data):
        """Discord'dan gelen anlık kanal değişim olaylarını yakalar."""
        try:
            channel_id = data.get('channel_id')
            if channel_id:
                self.last_seen_channel_id = channel_id
                print(f"\n[DİSCORD IPC EVENT] Kanal hareketi yakalandı! Gizli ID: {channel_id}")
        except Exception as e:
            print(f"[DİSCORD IPC EVENT HATA] {e}")

    def _subscribe_to_events(self):
        """Kullanıcının Discord içi hareketlerini dinlemeye başlar."""
        try:
            self.client.register_event("VOICE_CHANNEL_SELECT", self._on_channel_select_event)
            self.client.subscribe("VOICE_CHANNEL_SELECT")
            print("[DİSCORD IPC] Otonom Veri Toplayıcı (Event Listener) aktif edildi.")
        except Exception as e:
            print(f"[DİSCORD IPC] Event Listener abonelik hatası (API kısıtlaması olabilir): {e}")

    def teleport_to_channel(self, server_name, channel_name):
        """Güven eşiğine göre çakışmaları çözer ve TİPİNE GÖRE kanala ışınlanır."""
        if not self.connected: return {"status": "error", "message": "Bağlantı yok"}

        cache = self._load_json(CACHE_FILE)
        target_srv = server_name.lower()
        target_ch = channel_name.lower()

        matches = []

        for srv, categories in cache.items():
            if target_srv in srv or srv in target_srv:
                for cat, channels in categories.items():
                    for ch, data in channels.items():
                        if target_ch in ch or ch in target_ch:
                            matches.append({
                                "server": srv, "category": cat, "channel": ch,
                                "id": data["id"], "type": data.get("type", "text"),
                                "use_count": data["use_count"]
                            })

        if not matches:
            print(f"[DİSCORD IPC] '{channel_name}' önbellekte bulunamadı. Fallback'e yönlendiriliyor.")
            return {"status": "not_found"}

        # Çakışma Çözümü ve Eşik Matematiği
        total_count = sum(m["use_count"] for m in matches)
        best_match = max(matches, key=lambda x: x["use_count"])

        is_confident = (len(matches) == 1) or (total_count > 0 and (best_match["use_count"] / total_count) > 0.80)

        if is_confident:
            print(
                f"[DİSCORD IPC] Güven eşiği sağlandı! '{best_match['channel']}' ({best_match['type']}) kanalına ışınlanılıyor.")
            try:
                if best_match["type"] == "voice":
                    self.client.select_voice_channel(best_match["id"])
                else:
                    self.client.select_text_channel(best_match["id"])

                self.update_cache(best_match["server"], best_match["category"], best_match["channel"], best_match["id"], best_match["type"])

                return {"status": "success", "channel": best_match["channel"]}

            except Exception as e:
                if "5003" in str(e):
                    print(f"[DİSCORD IPC] Zaten '{best_match['channel']}' kanalındasınız!")

                    self.update_cache(best_match["server"], best_match["category"], best_match["channel"], best_match["id"], best_match["type"])

                    return {"status": "success", "channel": best_match["channel"]}

                print(f"[DİSCORD IPC HATA] Işınlanma başarısız oldu: {e}")
                return {"status": "api_error", "message": str(e)}
        else:
            print(f"[DİSCORD IPC] Düşük Güven! Sistem kullanıcıdan teyit isteyecek.")
            options = [m["category"] for m in matches]
            return {"status": "conflict", "options": options}

    def learn_channel_interactive(self, server_name, channel_name):
        """Etkileşimli Öğrenme: Klavye şelalesi başarısız olduğunda kullanıcıdan tıklamasını bekler."""
        import asyncio
        print(
            f"\n[MUSTAFA YARGIÇ] Efendim, '{channel_name}' kanalının yerini henüz bilmiyorum ve klavyeye erişemiyorum.")
        print(
            f"[MUSTAFA YARGIÇ] Lütfen Discord üzerinden kanala bir kez tıklayın, koordinatlarını kalıcı olarak öğreneyim (15 saniyeniz var).")

        self.last_seen_channel_id = None

        # Sistemi dondurmadan 15 saniye bekle
        for _ in range(75):
            if self.last_seen_channel_id:
                break
            self.client.loop.run_until_complete(asyncio.sleep(0.2))

        if self.last_seen_channel_id:
            print(f"\n[DİSCORD IPC] Harika! ID yakalandı. '{server_name}' - '{channel_name}' olarak kaydediliyor...")
            # Yakalanan ID'yi kalıcı hafızaya yaz
            self.update_cache(server_name, "genel", channel_name, self.last_seen_channel_id, "voice")

            print(f"[MUSTAFA YARGIÇ] Öğrendim! 3 saniye içinde sizi oraya ışınlıyorum...")
            self.client.loop.run_until_complete(asyncio.sleep(3))

            # Öğrendiği kanala hemen otonom olarak ışınlan
            return self.teleport_to_channel(server_name, channel_name)
        else:
            print("\n[MUSTAFA YARGIÇ HATA] Zaman aşımı. Herhangi bir kanala tıklamadınız.")
            return {"status": "timeout"}

    # --- BAĞLANTI VE OAUTH2 ---
    def connect(self):
        try:
            print("[DİSCORD IPC] Soket başlatılıyor...")
            self.client.start()

            saved_tokens = self._load_json(TOKEN_FILE)
            if saved_tokens and 'access_token' in saved_tokens:
                try:
                    self.client.authenticate(saved_tokens['access_token'])
                    self.connected = True
                    print("[DİSCORD IPC] Başarıyla doğrulandı (Önbellekten)! Arka kapı açık.")
                    self._subscribe_to_events()
                    return True
                except Exception as e:
                    print(f"[DİSCORD IPC] Kayıtlı token geçersiz olmuş, yenisi alınacak. ({e})")

            print("[DİSCORD IPC] Yeni yetki bekleniyor... Lütfen Discord ekranını kontrol et!")
            auth_response = self.client.authorize(
                self.client_id,
                scopes=['rpc', 'rpc.voice.read', 'rpc.voice.write']
            )

            token_data = self._exchange_code_for_token(auth_response['data']['code'])

            if not token_data or 'access_token' not in token_data:
                return False

            self._save_json(TOKEN_FILE, token_data)
            self.access_token = token_data['access_token']
            self.client.authenticate(self.access_token)

            self.connected = True
            print("[DİSCORD IPC] Başarıyla doğrulandı (Yeni Token)! Arka kapı sonuna kadar açık.")
            self._subscribe_to_events()
            return True

        except Exception as e:
            print(f"[DİSCORD IPC] Bağlantı Hatası: {e}")
            self.connected = False
            return False

    def _exchange_code_for_token(self, code):
        url = 'https://discord.com/api/v10/oauth2/token'
        data = {
            'client_id': self.client_id, 'client_secret': self.client_secret,
            'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        return requests.post(url, data=data, headers=headers).json()

    # --- AKILLI KASLAR (SMART CONTROLS) ---
    def control_mic(self, action="toggle"):
        """Mikrofonu kesin duruma getirir veya akıllıca tersine çevirir (toggle)."""
        if not self.connected: return False
        try:
            if action == "mute":
                self.client.set_voice_settings(mute=True)
                print("[DİSCORD IPC] Mikrofon kesin olarak KAPATILDI.")
            elif action == "unmute":
                self.client.set_voice_settings(mute=False)
                print("[DİSCORD IPC] Mikrofon kesin olarak AÇILDI.")
            elif action == "toggle":
                # Mevcut durumu öğren ve tam tersini uygula
                current_settings = self.client.get_voice_settings()
                # pypresence yanıtı genellikle {'data': {'mute': True/False}} şeklindedir
                current_mute = current_settings.get('data', {}).get('mute', False)

                self.client.set_voice_settings(mute=not current_mute)
                durum = "AÇILDI" if current_mute else "KAPATILDI"
                print(f"[DİSCORD IPC] Mikrofon durumu tersine çevrildi: {durum}")
            return True
        except Exception as e:
            print(f"[DİSCORD IPC HATA] Mikrofon kontrolü başarısız: {e}")
            return False

    def control_deafen(self, action="toggle"):
        """Kulaklığı kesin duruma getirir veya akıllıca tersine çevirir (toggle)."""
        if not self.connected: return False
        try:
            if action == "mute":
                self.client.set_voice_settings(deaf=True)
                print("[DİSCORD IPC] Sağırlaştırma kesin olarak AKTİF.")
            elif action == "unmute":
                self.client.set_voice_settings(deaf=False)
                print("[DİSCORD IPC] Sağırlaştırma kesin olarak KAPALI.")
            elif action == "toggle":
                current_settings = self.client.get_voice_settings()
                current_deaf = current_settings.get('data', {}).get('deaf', False)

                self.client.set_voice_settings(deaf=not current_deaf)
                durum = "KAPALI" if current_deaf else "AKTİF"
                print(f"[DİSCORD IPC] Sağırlaştırma tersine çevrildi: {durum}")
            return True
        except Exception as e:
            print(f"[DİSCORD IPC HATA] Sağırlaştırma kontrolü başarısız: {e}")
            return False


# --- İZOLE TEST ALANI ---
if __name__ == "__main__":
    import asyncio

    if not CLIENT_ID or not CLIENT_SECRET:
        print("[HATA] .env dosyasında CLIENT_ID veya CLIENT_SECRET eksik!")
    else:
        ipc = DiscordIPC(CLIENT_ID, CLIENT_SECRET)

        if ipc.connect():
            # ==========================================
            # TEST DEĞİŞKENLERİ (Sadece burayı değiştirin)
            # ==========================================
            TEST_SUNUCU = "PURNA"
            TEST_KATEGORI = "Metin Kanalları"
            TEST_KANAL = "genel"
            # ==========================================

            print("\n--- ETKİLEŞİMLİ ÖĞRENME TESTİ (YENİ MİMARİ) ---")
            print(f"[TEST] Asistanı eğitiyoruz. Lütfen Discord'da '{TEST_KANAL}' kanalına MANUEL OLARAK tıklayın.")
            print("[TEST] Tıkladığınız an sistem ID'yi yakalayacak. 15 saniye bekleniyor...\n")

            # Pypresence'ın kendi döngüsüne (loop) nefes aldırarak 15 saniye bekliyoruz
            for i in range(75):
                if ipc.last_seen_channel_id:
                    print(f"\n[BİLGİ] Harika! Kanal ID'si yakalandı: {ipc.last_seen_channel_id}")
                    break
                # İşlemciyi kilitlemez, Discord'dan gelen sinyallere kapıyı açar!
                ipc.client.loop.run_until_complete(asyncio.sleep(0.2))

            if ipc.last_seen_channel_id:
                # 3. Aşama: Yakalanan ID'yi JSON dosyasına değişken isimleriyle kalıcı olarak kaydet
                print(
                    f"[TEST] Şimdi bu ID'yi '{TEST_SUNUCU}' sunucusundaki '{TEST_KANAL}' kanalı olarak kaydediyoruz...")
                ipc.update_cache(TEST_SUNUCU, TEST_KATEGORI, TEST_KANAL, ipc.last_seen_channel_id, "voice")

                print("\n[TEST] Öğrenme tamamlandı! Lütfen Discord'dan BAŞKA BİR KANALA veya GENEL'E geçin.")
                print(f"[TEST] 5 saniye sonra sistem sizi otonom olarak '{TEST_KANAL}' kanalına GERİ ÇEKECEK!")

                # Yine sistemi dondurmadan 5 saniye bekliyoruz
                ipc.client.loop.run_until_complete(asyncio.sleep(5))

                result = ipc.teleport_to_channel(TEST_SUNUCU, TEST_KANAL)
                print(f"Işınlanma Sonucu: {result}")
            else:
                print("\n[HATA] 15 saniye boyunca hiçbir kanal hareketi yakalanamadı.")

            ipc.client.close()