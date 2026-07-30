import edge_tts
import pygame
import os


async def speak(text):
    """Metni Microsoft Edge TTS ile sese çevirir ve pygame ile anında oynatır."""
    if not text:
        return

    # tr-TR-AhmetNeural (Erkek) veya tr-TR-EmelNeural (Kadın)
    voice = "tr-TR-AhmetNeural"
    output_file = "response.mp3"

    try:
        # Metni sese çevir ve MP3 olarak kaydet
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_file)

        # Pygame ile sesi oynat
        pygame.mixer.init()
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()

        # Ses bitene kadar bekle
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

    except Exception as e:
        print(f"[TTS HATA] Seslendirme başarısız: {e}")
    finally:
        # Çöpü temizle (Dosyayı sil ve ses motorunu kapat)
        pygame.mixer.quit()
        if os.path.exists(output_file):
            os.remove(output_file)