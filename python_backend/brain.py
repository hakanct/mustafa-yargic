import os
import json
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

class MustafaYargicBrain:
    def __init__(self):
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        # IPC Arka Kapısını sistem açılırken BİR KERE başlatır ve sürekli açık tutar
        client_id = os.getenv("DISCORD_CLIENT_ID")
        client_secret = os.getenv("DISCORD_CLIENT_SECRET")
        if client_id and client_secret:
            self.ipc = discord_ipc.DiscordIPC(client_id, client_secret)
            self.ipc.connect()
        else:
            self.ipc = None
            print("[SİSTEM UYARISI] Discord kimlik bilgileri eksik, IPC başlatılamadı.")

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
        response = self.groq_client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        return json.loads(response.choices[0].message.content)

    def _ask_ollama(self, message):
        response = ollama.chat(
            model="llama3.2",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message}
            ],
            format="json",
            options={"temperature": 0.0}
        )
        return json.loads(response['message']['content'])

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

        # ==========================================
        # BÜYÜK YÖNLENDİRİCİ (THE ROUTER) - KATEGORİK MİMARİ
        # ==========================================
        if intent == "system_actions":
            action = parameters.get("action")
            target = parameters.get("target")

            if action == "open_app":
                os_actions.open_application(target)
            elif action == "close_app":
                os_actions.close_application(target)
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
                channel = parameters.get("channel") or ""

                # ADIM 1: Hafızadan (Cache) Işınlanmayı Dene
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
                            print(f"[SİSTEM] BİNGO! '{channel}' kanalının gizli ID'si yakalandı ve kalıcı hafızaya eklendi.")
                            self.ipc.update_cache(server, "genel", channel, self.ipc.last_seen_channel_id, "voice")
                        else:
                            print("[SİSTEM UYARISI] Kanala girildi ancak Discord IPC ID'yi yakalayamadı.")
                            

                    if not success:
                        print("[SİSTEM] Klavye engellendi veya başarısız. Etkileşimli öğrenme moduna geçiliyor...")
                        self.ipc.learn_channel_interactive(server, channel)

            # Discord içi ses/kulaklık kontrolleri
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

    print("-" * 50)
    print("Mustafa Yargıç Uçtan Uca Şelale Testi")
    print("-" * 50)

    # Önceki testte JSON dosyasına kaydettiğimiz otonom kanal geçişini test edelim!
    mesaj = "Mustafa purna sunucusunda lobi sesli kanalına katıl."
    print(f"\nKULLANICI: {mesaj}")
    asistan.execute_command(mesaj, mode="cloud")

    import time
    #time.sleep(3)

    #mesaj_2 = "Mustafa mikrofonu aç."
    #print(f"\nKULLANICI: {mesaj_2}")
    #asistan.execute_command(mesaj_2, mode="cloud")

    #time.sleep(3)

    #mesaj_3 = "Mustafa discordda mikrofonu aç."
    #print(f"\nKULLANICI: {mesaj_3}")
    #asistan.execute_command(mesaj_3, mode="cloud")

    #time.sleep(3)

    #mesaj_4 = "Mustafa steam uygulamasını aç."
    #print(f"\nKULLANICI: {mesaj_4}")
    #asistan.execute_command(mesaj_4, mode="cloud")

    time.sleep(3)

    mesaj_5 = "Mustafa youtube music uygulamasını aç."
    print(f"\nKULLANICI: {mesaj_5}")
    asistan.execute_command(mesaj_5, mode="cloud")

    # ==========================================
    # GÜVENLİ ÇIKIŞ (GRACEFUL SHUTDOWN)
    # ==========================================
    # İşletim sisteminin ve Discord soketinin paketleri işleyebilmesi için
    # program kapanmadan önce kısa bir süre tanıyoruz.
    time.sleep(2)
    if asistan.ipc and asistan.ipc.connected:
        asistan.ipc.client.close()
        print("\n[SİSTEM] IPC Bağlantısı güvenlice kapatıldı.")
    print("[SİSTEM] Test başarıyla tamamlandı.")
