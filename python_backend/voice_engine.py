import os
import json
import time
import pyaudio
import numpy as np
from dotenv import load_dotenv
from vosk import Model, KaldiRecognizer
from faster_whisper import WhisperModel
import gc

load_dotenv()

class VoiceEngine:
    def __init__(self):
        self.mode = os.getenv("STT_MODE", "performance").lower()
        wake_words_env = os.getenv("WAKE_WORDS", "mustafa,jarvis,asistan")
        # Kelimeleri temizleyip listeye çeviriyoruz
        self.wake_words = [w.strip().lower() for w in wake_words_env.split(",")]

        print("=" * 50)
        print(f"🎙️ [SES MOTORU] Başlatılıyor... Mod: {self.mode.upper()}")
        print(f"🎙️ [SES MOTORU] Uyandırma Kelimeleri: {self.wake_words}")
        print("=" * 50)

        # ==========================================
        # 1. KATMAN: VOSK (Uyandırma - Wake Word)
        # ==========================================
        try:
            # İşlemciyi yormamak için loglamayı kapatıyoruz
            from vosk import SetLogLevel
            SetLogLevel(-1)

            # İndirdiğimiz 35 MB'lık modeli yüklüyoruz
            self.vosk_model = Model("models/vosk")

            # SADECE UYANDIRMA KELİMELERİNİ DİNLE (Kısıtlı Sözlük - RAM/CPU Dostu)
            grammar = json.dumps(self.wake_words + ["[unk]"])
            self.recognizer = KaldiRecognizer(self.vosk_model, 16000, grammar)
            print("[SES MOTORU] Vosk (Uyandırma) Katmanı: HAZIR")
        except Exception as e:
            print(f"[SES MOTORU HATA] Vosk modeli yüklenemedi. 'models/vosk' klasörünü kontrol edin.\nHata: {e}")
            self.vosk_model = None

        # ==========================================
        # 2. KATMAN: FASTER-WHISPER (Anlama / STT)
        # ==========================================
        self.whisper_model = None
        self.audio = pyaudio.PyAudio()

        # Performans modundaysak büyük modeli hemen ekran kartına (VRAM) yükle
        if self.mode == "performance":
            self._load_whisper()

    def _load_whisper(self):
        """Faster-Whisper modelini VRAM'e (veya CPU'ya) yükler."""
        if self.whisper_model is None:
            print("[SES MOTORU] Faster-Whisper (Small) Belleğe Yükleniyor... (Bu biraz sürebilir)")

            self.whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
            print("[SES MOTORU] Faster-Whisper Katmanı: HAZIR")

    def _unload_whisper(self):
        """Oyun modunda ekran kartı belleğini (VRAM) temizler."""
        if self.whisper_model is not None and self.mode == "gaming":
            print("[SES MOTORU] Oyun Modu: Faster-Whisper VRAM'den siliniyor...")
            del self.whisper_model
            self.whisper_model = None
            gc.collect()  # Python çöp toplayıcısını (Garbage Collector) zorla çalıştır

    def listen_for_wake_word(self):
        """7/24 Sıfıra yakın sistem tüketimiyle uyandırma kelimelerini bekler."""
        if not self.vosk_model:
            return False

        # 16kHz, Tek Kanal (Mono) mikrofon akışı aç
        stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=4000)
        stream.start_stream()

        print("\n[UYKU MODU] Asistan dinliyor... (Uyandırmak için seslenin)")

        try:
            while True:
                data = stream.read(4000, exception_on_overflow=False)
                # Vosk sesi analiz eder
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "")

                    # Eğer duyulan kelime bizim belirlediğimiz listedeyse: UYAN!
                    if text in self.wake_words:
                        print(f"\n⚡ [UYANDIRMA KELİMESİ DUYULDU]: {text.upper()}")
                        stream.stop_stream()
                        stream.close()
                        return True
        except Exception as e:
            print(f"[SES MOTORU HATA] Dinleme sırasında hata: {e}")
            stream.stop_stream()
            stream.close()
            return False

    def record_and_transcribe(self):
        """Asistan uyandıktan sonra ana komutu kaydeder (Sessizliği algılayana kadar) ve metne çevirir."""
        # 1. Eğer oyun modundaysak, modeli uyandığı an yükle (Gecikme burada yaşanır)
        if self.mode == "gaming":
            self._load_whisper()

        # Kayıt Ayarları
        RATE = 16000
        CHUNK = 1024
        SILENCE_THRESHOLD = 500  # Ses eşiği (Mikrofonuna göre bunu artırıp azaltabilirsin)
        SILENCE_DURATION = 1.5  # Kaç saniye susarsan komut bitmiş sayılacak?

        stream = self.audio.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
        print("🎙️ [DİNLİYORUM] Lütfen komutunuzu söyleyin...")

        frames = []
        silent_chunks = 0
        is_recording = False

        # Maksimum 10 saniye dinle veya 1.5 saniye sessizlik algılandığında dur
        for _ in range(0, int(RATE / CHUNK * 10)):
            data = stream.read(CHUNK, exception_on_overflow=False)
            audio_data = np.frombuffer(data, dtype=np.int16)
            rms_volume = np.sqrt(np.mean(np.square(audio_data.astype(np.float32))))

            if rms_volume > SILENCE_THRESHOLD:
                is_recording = True
                silent_chunks = 0
            elif is_recording:
                silent_chunks += 1

            if is_recording:
                frames.append(data)

            # 1.5 Saniye sessizlik algılandıysa döngüyü kır
            if is_recording and silent_chunks > (RATE / CHUNK * SILENCE_DURATION):
                print("🔇 [SESSİZLİK] Komut algılandı, işleniyor...")
                break

        stream.stop_stream()
        stream.close()

        if not frames:
            print("⚠️ Hiçbir ses algılanmadı.")
            self._unload_whisper()
            return ""

        # Ses verisini Faster-Whisper'ın anlayacağı Float32 Numpy dizisine çevir
        audio_np = np.frombuffer(b''.join(frames), dtype=np.int16).astype(np.float32) / 32768.0

        # Sesi metne çevir
        segments, _ = self.whisper_model.transcribe(audio_np, language="tr", beam_size=5)

        transcript = " ".join([segment.text for segment in segments]).strip()

        # YENİ: Whisper Halüsinasyon Filtresi
        hallucinations = [
            "bir sonraki videoda görüşürüz",
            "izlediğiniz için teşekkürler",
            "altyazı",
            "abone olmayı unutmayın"
        ]

        for h in hallucinations:
            if h in transcript.lower():
                print("⚠️ [STT UYARISI] Whisper halüsinasyonu tespit edildi, yoksayılıyor.")
                self._unload_whisper()
                return ""

        print(f"✅ [STT ÇIKTISI]: {transcript}")

        # 2. İşlem bittikten sonra oyun modundaysak ekran kartını boşalt
        self._unload_whisper()

        return transcript


# --- İZOLE TEST ALANI ---
if __name__ == "__main__":
    engine = VoiceEngine()

    # 7/24 Uyandırma kelimesini bekle
    if engine.listen_for_wake_word():
        # Uyandığı an komutu dinle ve metne dök
        komut = engine.record_and_transcribe()
        print(f"Test Sonucu: {komut}")