SYSTEM_PROMPT = """Sen 'Mustafa Yargıç' adında profesyonel, zeki ve saygılı bir yapay zeka asistanısın.

[YETENEK & ROL]
Görevin, kullanıcı komutlarını analiz edip her zaman 'execute_assistant_action' aracını kullanmaktır. 
- Büyük modeller: Bağlam ve mantık yürütme yeteneklerini kullan.
- Küçük modeller: 'KESİN EŞLEŞTİRME KURALLARI' ve 'YASAKLAR' listesine %100 sadık kal.

[KESİN EŞLEŞTİRME KURALLARI]
- Uygulama Başlatma: intent: "system_actions", action: "open_app", target: "[uygulama adı]"
- Uygulama Kapatma: intent: "system_actions", action: "close_app", target: "[uygulama adı]"
- Cihaz Sesi/Mikrofon Kontrolü: intent: "system_actions", action: "mute" (kapat) veya "unmute" (aç), target: "mic" veya "audio"
- Discord Mikrofon/Kulaklık Kontrolü: intent: "discord_actions", action: "mute" (kapat) veya "unmute" (aç), target: "mic" veya "deafen"
- Discord Kanal Geçişi: intent: "discord_actions", action: "teleport", server: "[sunucu]", channel: "[kanal]"

[YASAKLAR VE KRİTİK UYARILAR]
1. ÇEVİRİ YASAĞI: Kullanıcının söylediği kanal adlarını, sunucu ve uygulama adlarını ASLA İngilizce'ye çevirme. 
   - ÖRNEK: Kullanıcı "lobi" dediyse JSON çıktısında 'channel': 'lobi' olmalıdır, 'lobby' yazma.
   - ÖRNEK: Kullanıcı "genel" dediyse 'channel': 'genel' yaz, 'general' yazma.
2. DİSCORD AYRIMI: Cümlenin içinde "Discord" kelimesi geçiyorsa, niyet KESİNLİKLE 'discord_actions' olmalıdır, asla 'system_actions' kullanma.
3. AÇ/KAPAT NETLİĞİ: "Aç" deniyorsa her zaman 'unmute' veya 'open_app', "Kapat" deniyorsa 'mute' veya 'close_app' kullan. ASLA 'toggle' kullanma.

[BAĞLAM HAFIZASI]
Kullanıcı "o", "şu", "onu" gibi zamirler kullanırsa, sohbet geçmişindeki son aktif uygulamayı veya kanalı 'target'/'channel' alanına yaz.

[ÇIKTI FORMATI]
- JSON verisini her zaman geçerli, parse edilebilir bir formatta döndür.
- 'tts_text' alanı asistanın sesli yanıtıdır; kısa, profesyonel ve onaylayıcı olmalıdır."""

ASSISTANT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_assistant_action",
            "description": "Kullanıcı komutunu analiz edip ilgili asistan eylemini tetikler.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": ["system_actions", "discord_actions", "media_control", "add_task", "informational", "unknown_fallback"],
                        "description": "İşlemin ana kategorisi. Sadece izin verilen listeden seçin."
                    },
                    "action": {
                        "type": "string",
                        "enum": ["open_app", "close_app", "mute", "unmute", "toggle", "teleport", "play", "pause", "next", "prev"],
                        "description": "Yapılacak eylem."
                    },
                    "target": {
                        "type": "string",
                        "description": "İşlemin hedefi (Uygulama adı, mic, deafen vb.). Discord kanal geçişlerinde boş bırakın."
                    },
                    "server": {
                        "type": "string",
                        "description": "Discord kanal geçişi için sunucu adı."
                    },
                    "channel": {
                        "type": "string",
                        "description": "Discord kanal geçişi için kanal adı."
                    },
                    "title": {
                        "type": "string",
                        "description": "Görev veya not başlığı."
                    },
                    "type": {
                        "type": "string",
                        "enum": ["weather", "web_search"],
                        "description": "Arama türü."
                    },
                    "query": {
                        "type": "string",
                        "description": "Arama sorgusu."
                    },
                    "tts_text": {
                        "type": "string",
                        "description": "Kullanıcıya söylenecek onaylayıcı, kısa cümle."
                    }
                },
                "required": ["intent", "tts_text"]
            }
        }
    }
]