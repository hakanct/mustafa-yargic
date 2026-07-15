import os
import json
import re  # YENİ: Regex güvenlik süzgeci için eklendi
from time import sleep

from groq import Groq
import ollama
from dotenv import load_dotenv
import os_actions
import skills.discord_skill as discord_skill
import skills.discord_ipc as discord_ipc
import system_prompt

# .env dosyasındaki GROQ_API_KEY'i yükler
load_dotenv()

SYSTEM_PROMPT = system_prompt.SYSTEM_PROMPT
ASSISTANT_TOOLS = system_prompt.ASSISTANT_TOOLS


class MustafaYargicBrain:
    def __init__(self):
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        # YENİ: Kısa Süreli Hafıza (Context Memory)
        # Sadece kullanıcının dediklerini ve asistanın yanıtlarını tutar.
        self.history = []

        # IPC Arka Kapısını sistem açılırken BİR KERE başlatır ve sürekli açık tutar
        client_id = os.getenv("DISCORD_CLIENT_ID")
        client_secret = os.getenv("DISCORD_CLIENT_SECRET")
        if client_id and client_secret:
            self.ipc = discord_ipc.DiscordIPC(client_id, client_secret)
            self.ipc.connect()
        else:
            self.ipc = None
            print("[SİSTEM UYARISI] Discord kimlik bilgileri eksik, IPC başlatılamadı.")

    def _clean_json_string(self, raw_str):
        """YENİ: LLM'in üretebileceği markdown (```json) bloklarını ayıklayan süzgeç."""
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
        # YENİ: Geçmiş mesajları API'ye gönderiyoruz
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.history + [
            {"role": "user", "content": message}]

        response = self.groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=ASSISTANT_TOOLS,
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
        # YENİ: Ollama modelini belirliyoruz (İndirdiğin modele göre değiştirebilirsin)
        TARGET_MODEL = "llama3.2"

        # Geçmiş mesajları API'ye gönderiyoruz
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + self.history + [
            {"role": "user", "content": message}]

        response = ollama.chat(
            model=TARGET_MODEL,
            messages=messages,
            tools=ASSISTANT_TOOLS,
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

        # YENİ: Geçmişi Güncelleme (Context Memory Kaydı)
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": tts_text})
        # Hafızayı şişirmemek için sadece son 5 diyaloğu (10 mesaj) tutuyoruz
        self.history = self.history[-10:]

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
                os_actions.system_audio_control(action)

        elif intent == "discord_actions":
            action = parameters.get("action")
            target = parameters.get("target")

            if not self.ipc or not self.ipc.connected:
                print("[SİSTEM] Discord arka kapısı (IPC) kapalı! Bağlantıyı kontrol edin.")
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
                        import asyncio
                        for _ in range(20):
                            if self.ipc.last_seen_channel_id:
                                break
                            self.ipc.client.loop.run_until_complete(asyncio.sleep(0.2))
                        if self.ipc.last_seen_channel_id:
                            print(
                                f"[SİSTEM] BİNGO! '{channel}' kanalının gizli ID'si yakalandı ve kalıcı hafızaya eklendi.")
                            self.ipc.update_cache(server, "genel", channel, self.ipc.last_seen_channel_id, "voice")
                        else:
                            print("[SİSTEM UYARISI] Kanala girildi ancak Discord IPC ID'yi yakalayamadı.")

                    if not success:
                        print("[SİSTEM] Klavye engellendi veya başarısız. Etkileşimli öğrenme moduna geçiliyor...")
                        self.ipc.learn_channel_interactive(server, channel)

            elif target == "mic":
                self.ipc.control_mic(action)
            elif target == "deafen":
                self.ipc.control_deafen(action)

        elif intent == "add_task":
            print(f"[SİSTEM] N8N'e gönderilecek görev: {parameters.get('title')}")
        elif intent == "media_control":
            print(f"[SİSTEM] Medya kontrolü: {parameters}")
        elif intent == "informational":
            print(f"[SİSTEM] Bilgi araması: {parameters}")
        else:
            print("[SİSTEM] Bilinmeyen niyet veya eylem: ", intent_data)


# --- UÇTAN UCA TEST ALANI ---
if __name__ == "__main__":
    asistan = MustafaYargicBrain()

    print("=" * 60)
    print("🚀 MUSTAFA YARGIÇ - BÜYÜK YEREL (LOCAL) SİSTEM TESTİ 🚀")
    print("=" * 60)

    # Test senaryoları (Adı ve Kullanıcı Mesajı)
    test_senaryolari = [
        ("Uygulama Açma", "youtube music uygulamasını açar mısın?"),
        ("Discord Işınlanma", "Mustafa purna sunucusunda lobi kanalına katıl."),
        ("Sistem Ses Kontrolü", "Mustafa sistem mikrofonunu kapat."),
        ("Bağlam Hafızası (Context)", "Şimdi o açtığın uygulamayı geri kapat."),
        ("Discord İçi Kontrol", "Discord'da mikrofonumu aç.")
    ]

    import time

    for test_adi, mesaj in test_senaryolari:
        print(f"\n{'-' * 40}")
        print(f"[TEST: {test_adi.upper()}]")
        print(f"KULLANICI: {mesaj}")
        print(f"{'-' * 40}")

        # Sadece "local" modda çalıştırarak Llama 3.2'yi sınıyoruz
        asistan.execute_command(mesaj, mode="cloud")

        # İşletim sisteminin ve Discord soketinin (IPC) işlemleri
        # rahatça tamamlayabilmesi için her komut arası 5 saniye bekliyoruz.
        time.sleep(5)

    # ==========================================
    # GÜVENLİ ÇIKIŞ (GRACEFUL SHUTDOWN)
    # ==========================================
    time.sleep(2)
    if asistan.ipc and asistan.ipc.connected:
        asistan.ipc.client.close()
        print("\n[SİSTEM] IPC Bağlantısı güvenlice kapatıldı.")
    print("\n[SİSTEM] BÜYÜK SINAV BAŞARIYLA TAMAMLANDI!")