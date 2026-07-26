import os
import json
import re
import time
import asyncio  # YENİ: Asenkron işlemler için

from groq import Groq
import ollama
from dotenv import load_dotenv
import os_actions
import skills.discord_skill as discord_skill
import skills.discord_ipc as discord_ipc
import system_prompt

# .env dosyasındaki ortam değişkenlerini yükler
load_dotenv()


class MustafaYargicBrain:
    def __init__(self):
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        # Kısa Süreli Hafıza (Context Memory)
        self.history = []

        # ==========================================
        # FAZ 7: MODÜLER YETENEK YÖNETİCİSİ
        # ==========================================
        # .env dosyasından Discord özelliğinin açık/kapalı durumunu okuyoruz (Varsayılan: True)
        self.enable_discord = str(os.getenv("ENABLE_DISCORD", "True")).lower() in ["true", "1", "yes"]

        # Sistem promptunu ve araçları ayarlara göre DİNAMİK olarak alıyoruz
        self.system_prompt_text = system_prompt.get_system_prompt(self.enable_discord)
        self.assistant_tools = system_prompt.get_assistant_tools(self.enable_discord)

        # Discord Modülü açıksa IPC sınıfını tanımla ama BAĞLANMA! (Kalp Atışı görevi üstlenecek)
        if self.enable_discord:
            client_id = os.getenv("DISCORD_CLIENT_ID")
            client_secret = os.getenv("DISCORD_CLIENT_SECRET")
            if client_id and client_secret:
                self.ipc = discord_ipc.DiscordIPC(client_id, client_secret)
                # DİKKAT: self.ipc.connect() satırı buradan silindi!
            else:
                self.ipc = None
                print("[SİSTEM UYARISI] Discord kimlik bilgileri eksik, IPC başlatılamadı.")
        else:
            self.ipc = None
            print("[SİSTEM BİLGİSİ] Discord eklentisi devre dışı. Soket aranmayacak.")

    def _clean_json_string(self, raw_str):
        """LLM'in üretebileceği markdown (```json) bloklarını ayıklayan süzgeç."""
        if not isinstance(raw_str, str):
            return raw_str
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw_str, flags=re.MULTILINE)
        cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE)
        return cleaned.strip()

    def analyze_intent(self, user_message, mode="cloud"):
        print(f"\n[MUSTAFA YARGIÇ - {mode.upper()} MODU] Analiz ediliyor...")
        try:
            if mode == "cloud":
                return self._ask_groq(user_message)
            elif mode == "local":
                return self._ask_ollama(user_message)
        except Exception as e:
            print(f"Hata oluştu: {e}")
            return None

    def _ask_groq(self, message):
        # Dinamik promptu API'ye gönderiyoruz
        messages = [{"role": "system", "content": self.system_prompt_text}] + self.history + [
            {"role": "user", "content": message}]

        response = self.groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=self.assistant_tools,  # Dinamik Araçlar
            tool_choice={"type": "function", "function": {"name": "execute_assistant_action"}},
            temperature=0.0
        )

        tool_call = response.choices[0].message.tool_calls[0]
        # Regex süzgecinden geçiriyoruz
        args_str = self._clean_json_string(tool_call.function.arguments)
        args = json.loads(args_str)

        return {
            "intent": args.get("intent", "unknown_fallback"),
            "parameters": {k: v for k, v in args.items() if k not in ["intent", "tts_text"]},
            "tts_text": args.get("tts_text", "Emredersiniz")
        }

    def _ask_ollama(self, message):
        TARGET_MODEL = "llama3.2"

        # Dinamik promptu API'ye gönderiyoruz
        messages = [{"role": "system", "content": self.system_prompt_text}] + self.history + [
            {"role": "user", "content": message}]

        response = ollama.chat(
            model=TARGET_MODEL,
            messages=messages,
            tools=self.assistant_tools,  # Dinamik Araçlar
            options={"temperature": 0.0}
        )

        if "tool_calls" in response["message"] and response["message"]["tool_calls"]:
            args = response["message"]["tool_calls"][0]["function"]["arguments"]

            # Ollama bazen string, bazen dict döner. String ise temizle ve JSON'a çevir:
            if isinstance(args, str):
                args = json.loads(self._clean_json_string(args))

            return {
                "intent": args.get("intent", "unknown_fallback"),
                "parameters": {k: v for k, v in args.items() if k not in ["intent", "tts_text"]},
                "tts_text": args.get("tts_text", "Emredersiniz")
            }

        return {"intent": "unknown_fallback", "parameters": {}, "tts_text": "Anlayamadım efendim."}

    def execute_command(self, user_message, mode="cloud"):
        intent_data = self.analyze_intent(user_message, mode)

        if not intent_data:
            print("Sistem hatası: Niyet analizi başarısız oldu.")
            return None

        intent = intent_data.get("intent")
        parameters = intent_data.get("parameters") or {}
        tts_text = intent_data.get("tts_text", "Emredersiniz")

        print(f"\n[MUSTAFA YARGIÇ]: {tts_text}")
        print(f"[DEBUG - YAPAY ZEKA ÇIKTISI] Intent: {intent} | Parameters: {parameters}\n")

        # Geçmişi Güncelleme (Context Memory Kaydı)
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": tts_text})
        self.history = self.history[-10:]

        # --- KÜÇÜK MODEL (OLLAMA) OTOMATİK DÜZELTME SİSTEMİ ---
        action_fallback = parameters.get("action")
        if intent == "unknown_fallback" and action_fallback:
            if action_fallback in ["set_volume", "mute", "unmute", "open_app", "close_app"]:
                intent = "system_actions"
                print(
                    f"[AUTO-FIX] Yapay zeka niyeti unuttu, '{action_fallback}' eyleminden 'system_actions' olarak düzeltildi.")
            elif action_fallback in ["teleport"] and self.enable_discord:
                intent = "discord_actions"
            elif action_fallback in ["play", "pause", "next", "prev", "toggle"]:
                intent = "media_control"
        # -----------------------------------------------------------

        # ==========================================
        # BÜYÜK YÖNLENDİRİCİ (THE ROUTER) - KATEGORİK MİMARİ
        # ==========================================

        if intent == "system_actions":
            action = parameters.get("action")
            target = parameters.get("target")

            if action == "open_app":
                if target:
                    os_actions.open_application(target)
                else:
                    print("[SİSTEM UYARISI] Yapay zeka açılacak uygulamayı tespit edemedi.")
            elif action == "close_app":
                if target:
                    os_actions.close_application(target)
                else:
                    print("[SİSTEM UYARISI] Yapay zeka kapanacak uygulamayı tespit edemedi.")
            elif target == "mic":
                os_actions.system_mic_control(action)
            elif target == "audio":
                if action == "set_volume":
                    try:
                        level = int(parameters.get("level"))
                        if level is not None:
                            os_actions.set_system_volume(level / 100.0)
                    except (ValueError, TypeError):
                        print(f"[SİSTEM HATA] Geçersiz ses seviyesi formatı.")
                else:
                    os_actions.system_audio_control(action)

        elif intent == "discord_actions":
            if not self.enable_discord:
                print("[SİSTEM UYARISI] Discord modülü kapalı olduğu halde komut ulaştı. Reddediliyor.")
                return

            action = parameters.get("action")
            target = parameters.get("target")

            if not self.ipc or not self.ipc.connected:
                print("[SİSTEM UYARISI] Discord arka kapısı (IPC) kapalı! Bağlantıyı kontrol edin.")
                return

            if action == "teleport":
                server = parameters.get("server") or ""
                channel = parameters.get("channel") or parameters.get("target") or ""

                result = self.ipc.teleport_to_channel(server, channel)

                if result.get("status") == "not_found":
                    print(f"[SİSTEM] '{channel}' hafızada yok. Klavye otomasyonu deneniyor...")
                    self.ipc.last_seen_channel_id = None
                    success = discord_skill.go_to_channel(server, channel, "voice")

                    if success:
                        print("[SİSTEM] Klavye otomasyonu başarılı! Otonom IPC kaydı için pusuya yatıldı...")
                        # 4 saniye yerine 8 saniye bekliyor ve ana thread'i boğmuyor (os_actions'ta düzeltilmişti)
                        for _ in range(40):
                            if self.ipc.last_seen_channel_id:
                                break
                            time.sleep(0.2)

                        if self.ipc.last_seen_channel_id:
                            print(
                                f"[SİSTEM] BİNGO! '{channel}' kanalının gizli ID'si yakalandı ve kalıcı hafızaya eklendi.")
                            self.ipc.update_cache(server, "genel", channel, self.ipc.last_seen_channel_id, "voice")
                        else:
                            print("[SİSTEM UYARISI] Kanala girildi ancak Discord IPC ID'yi yakalayamadı.")

                    if not success:
                        print("[SİSTEM] Klavye engellendi veya başarısız. Etkileşimli öğrenme moduna geçiliyor...")
                        self.ipc.learn_channel_interactive(server, channel)

            elif action == "leave":
                self.ipc.disconnect_voice()

            elif target == "mic":
                self.ipc.control_mic(action)
            elif target == "deafen":
                self.ipc.control_deafen(action)

        elif intent == "add_task":
            print(f"[SİSTEM] N8N'e gönderilecek görev: {parameters.get('title')}")
        elif intent == "media_control":
            os_actions.media_control(parameters.get("action"))
        elif intent == "informational":
            print(f"[SİSTEM] Bilgi araması: {parameters}")
        else:
            print("[SİSTEM] Bilinmeyen niyet veya eylem: ", intent_data)

    # ==========================================
    # FAZ 8: ASENKRON DÖNGÜ VE KALP ATIŞI
    # ==========================================
    async def _discord_heartbeat(self):
        """Her 60 saniyede bir sessizce Discord'un açık olup olmadığını kontrol eder."""
        if not self.enable_discord or not self.ipc:
            return

        print("[HEARTBEAT] Discord otonom tarayıcısı aktif edildi. (60 saniyede bir aranacak)")
        while True:
            if not self.ipc.connected:
                # Ana asenkron döngüyü kitlememek için bağlantı işçisini thread'e atıyoruz
                success = await asyncio.to_thread(self.ipc.connect)
                if success:
                    print("\n[HEARTBEAT] BİNGO! Discord açıldı ve arka kapıdan sızıldı.")

            # Her kontrol arası 60 saniye dinlen
            await asyncio.sleep(60)

    async def run(self):
        """Asistanın hiç kapanmayan Ana Döngüsü (Event Loop)"""
        print("=" * 60)
        print("🚀 MUSTAFA YARGIÇ - OTONOM ASENKRON DÖNGÜ BAŞLADI 🚀")
        print("=" * 60)

        # Heartbeat (Kalp atışı) görevini ana döngüye dahil edip arka planda çalışmaya bırakıyoruz
        if self.enable_discord and self.ipc:
            asyncio.create_task(self._discord_heartbeat())

        # Sürekli dinleme (Terminal giriş) döngüsü
        while True:
            try:
                # Kullanıcıdan input alırken de asenkron bekleme yapıyoruz ki Heartbeat arkada tıkır tıkır çalışsın
                try:
                    user_message = await asyncio.to_thread(input, "\n[SİZ]: ")
                except UnicodeDecodeError:
                    # Arka plan yazıları terminal buffer'ını bozarsa sessizce pas geç
                    continue

                if not user_message.strip():
                    continue

                # --- LLM'E GİTMEDEN ÖNCEKİ LOKAL GÜVENLİK KONTROLÜ ---
                komut = user_message.strip().lower()
                if komut in ["/bye", "/exit", "çıkış", "kapat", "exit"]:
                    print("\n[SİSTEM] Güvenli çıkış yapılıyor. Görüşmek üzere efendim!")
                    break

                # LLM işlemini ve aksiyonları ayrı bir iş parçacığında çalıştır
                await asyncio.to_thread(self.execute_command, user_message, "cloud")

            except (KeyboardInterrupt, EOFError):
                print("\n[SİSTEM] Döngü manuel olarak sonlandırıldı.")
                break
            except Exception as e:
                print(f"\n[SİSTEM HATA] Ana döngüde beklenmedik hata: {e}")

# --- OTONOM BAŞLATICI ---
if __name__ == "__main__":
    asistan = MustafaYargicBrain()

    try:
        # Asenkron dünyayı başlatıyoruz!
        asyncio.run(asistan.run())
    finally:
        # Program kapandığında açık olan tüm soketleri temizle
        if asistan.ipc and asistan.ipc.connected:
            asistan.ipc.client.close()
            print("\n[SİSTEM] IPC Bağlantısı güvenlice kapatıldı.")