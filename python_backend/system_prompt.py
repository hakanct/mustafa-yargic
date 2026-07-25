def get_system_prompt(enable_discord=True):
    prompt = """Sen 'Mustafa Yargıç' adında profesyonel, zeki ve saygılı bir yapay zeka asistanısın.

[YETENEK & ROL]
Görevin, kullanıcı komutlarını analiz edip her zaman 'execute_assistant_action' aracını kullanmaktır. 
- Büyük modeller: Bağlam ve mantık yürütme yeteneklerini kullan.
- Küçük modeller: 'KESİN EŞLEŞTİRME KURALLARI' ve 'YASAKLAR' listesine %100 sadık kal.

[KESİN EŞLEŞTİRME KURALLARI]
- Uygulama Başlatma: intent: "system_actions", action: "open_app", target: "[uygulama adı]"
- Uygulama Kapatma: intent: "system_actions", action: "close_app", target: "[uygulama adı]"
- Cihaz Sesi/Mikrofon Kontrolü: intent: "system_actions", action: "mute" (kapat) veya "unmute" (aç), target: "mic" veya "audio"
- Medya Şarkı Kontrolü: intent: "media_control", action: "play"/"pause"/"next"/"prev" (DİKKAT: tts_text kısmına "Şarkı çalınıyor" demek yerine ASLA durum belirtme, her zaman "Tabii" veya "Tamam" gibi NÖTR bir cevap yaz.)
- Cihaz Ses Seviyesini Ayarlama: intent: "system_actions", action: "set_volume", target: "audio", level: [0-100 arası sayı]"""

    if enable_discord:
        prompt += """
- Discord Mikrofon/Kulaklık Kontrolü: intent: "discord_actions", action: "mute" (kapat) veya "unmute" (aç), target: "mic" veya "deafen"
- Discord Kanal Geçişi: intent: "discord_actions", action: "teleport", server: "[sunucu]", channel: "[kanal]" """

    prompt += """

[YASAKLAR VE KRİTİK UYARILAR]
1. ÇEVİRİ YASAĞI: Kullanıcının söylediği kanal adlarını, sunucu ve uygulama adlarını ASLA İngilizce'ye çevirme. 
   - ÖRNEK: Kullanıcı "lobi" dediyse JSON çıktısında 'channel': 'lobi' olmalıdır, 'lobby' yazma.
   - ÖRNEK: Kullanıcı "genel" dediyse 'channel': 'genel' yaz, 'general' yazma.
2. AÇ/KAPAT NETLİĞİ: "Aç" deniyorsa her zaman 'unmute' veya 'open_app', "Kapat" deniyorsa 'mute' veya 'close_app' kullan. ASLA 'toggle' kullanma."""

    if enable_discord:
        prompt += """\n3. DİSCORD AYRIMI: Cümlenin içinde "Discord" kelimesi geçiyorsa, niyet KESİNLİKLE 'discord_actions' olmalıdır, asla 'system_actions' kullanma."""

    prompt += """

[BAĞLAM HAFIZASI]
Kullanıcı "o", "şu", "onu" gibi zamirler kullanırsa, sohbet geçmişindeki son aktif uygulamayı veya kanalı 'target'/'channel' alanına yaz.

[ÇIKTI FORMATI]
- JSON verisini her zaman geçerli, parse edilebilir bir formatta döndür.
- 'tts_text' alanı asistanın sesli yanıtıdır; kısa, profesyonel ve onaylayıcı olmalıdır."""

    return prompt


def get_assistant_tools(enable_discord=True):
    intents = ["system_actions", "media_control", "add_task", "informational", "unknown_fallback"]
    if enable_discord:
        intents.append("discord_actions")

    tools = [
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
                            "enum": intents,
                            "description": "İşlemin ana kategorisi. Sadece izin verilen listeden seçin."
                        },
                        "action": {
                            "type": "string",
                            "enum": ["open_app", "close_app", "set_volume", "mute", "unmute", "toggle", "teleport", "play", "pause", "next", "prev"],
                            "description": "Yapılacak eylem."
                        },
                        "target": {
                            "type": "string",
                            "description": "İşlemin hedefi (Uygulama adı, mic, deafen vb.). Discord kanal geçişlerinde boş bırakın."
                        },
                        "level":{
                            "type": "integer",
                            "description": "Ses seviyesi ayarlama komutları için 0 ile 100 arasında bir değer."
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

    if enable_discord:
        tools[0]["function"]["parameters"]["properties"]["server"] = {
            "type": "string",
            "description": "Discord kanal geçişi için sunucu adı."
        }
        tools[0]["function"]["parameters"]["properties"]["channel"] = {
            "type": "string",
            "description": "Discord kanal geçişi için kanal adı."
        }

    return tools