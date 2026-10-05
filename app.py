import os
import asyncio
import hmac
import wave
import tempfile
from flask import Flask, request, send_file
from google import genai
from google.genai import types
import edge_tts

try:
    import miniaudio          # mp3 -> WAV converter (ESP32 WAV bajay)
except Exception as _e:
    miniaudio = None
    print("miniaudio import failed:", _e)

app = Flask(__name__)

# ================= Render Environment Variables =================
# GEMINI_API_KEY  : Google AI Studio key (Render Environment-e dao, code-e noy)
# GEMINI_MODEL    : optional, default niche dewa ache
# ADMIN_PASSCODE  : settings-er password (Render Environment-e dao, code-e likho na)
# DEVICE_KEY      : ESP32-r gopon chabi, shudhu ESP32 e ei chabi diye server use korte parbe
API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
ADMIN_PASSCODE = os.environ.get("ADMIN_PASSCODE", "")
MAX_REPLY_CHARS = int(os.environ.get("MAX_REPLY_CHARS", "220"))   # uttor-er sorbocho akkhor (choto uttor = druto, kom data)
DEVICE_KEY = os.environ.get("DEVICE_KEY", "")   # ESP32-r gopon chabi (Render Environment-e dao)

client = genai.Client(api_key=API_KEY) if API_KEY else None

RESPONSE_PATH = os.path.join(tempfile.gettempdir(), "maya_response.mp3")
WAV_PATH = os.path.join(tempfile.gettempdir(), "maya_response.wav")

bot_state = {
    "creator": "Akash Mal",
    "mode": "natural",
    "language": "bn-IN",       # bn-IN, hi-IN, en-US
    "voice_gender": "female",  # female, male
    "admin_auth": False,
}


def get_system_prompt():
    return f"""à¦¤à§à¦®à¦¿ à¦à¦•à¦Ÿà¦¿ à¦•à§ƒà¦¤à§à¦°à¦¿à¦® à¦¬à§à¦¦à§à¦§à¦¿à¦®à¦¤à§à¦¤à¦¾ à¦¸à¦®à§à¦ªà¦¨à§à¦¨ à¦­à¦¯à¦¼à§‡à¦¸ à¦…à§à¦¯à¦¾à¦¸à¦¿à¦¸à§à¦Ÿà§à¦¯à¦¾à¦¨à§à¦Ÿ, à¦¤à§‹à¦®à¦¾à¦° à¦¨à¦¾à¦® 'à¦®à¦¾à¦¯à¦¼à¦¾' (Maya)à¥¤
à¦¤à§‹à¦®à¦¾à¦•à§‡ à¦¤à§ˆà¦°à¦¿ à¦•à¦°à§‡à¦›à§‡ 'à¦†à¦•à¦¾à¦¶ à¦®à¦¾à¦²' (Akash Mal)à¥¤

à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦¨à¦¿à¦¯à¦¼à¦®à¦¾à¦¬à¦²à§€:
à§§. à¦¤à§‹à¦®à¦¾à¦° à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦­à¦¾à¦·à¦¾: {bot_state['language']} (à¦¬à¦¾à¦‚à¦²à¦¾/à¦¹à¦¿à¦¨à§à¦¦à¦¿/à¦‡à¦‚à¦°à§‡à¦œà¦¿)à¥¤
à§¨. à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦°à¦•à¦¾à¦°à§€à¦° à¦¸à¦¾à¦¥à§‡ à¦®à¦¾à¦¨à§à¦·à§‡à¦° à¦®à¦¤à§‹ à¦¸à§à¦¬à¦¾à¦­à¦¾à¦¬à¦¿à¦• à¦“ à¦†à¦¨à§à¦¤à¦°à¦¿à¦•à¦­à¦¾à¦¬à§‡ à¦•à¦¥à¦¾ à¦¬à¦²à§‹à¥¤ à¦‰à¦¤à§à¦¤à¦° à¦–à§à¦¬ à¦›à§‹à¦Ÿ à¦°à¦¾à¦–à¦¬à§‡: à¦¸à¦°à§à¦¬à§‹à¦šà§à¦š à§§-à§¨à¦Ÿà¦¿ à¦›à§‹à¦Ÿ à¦¬à¦¾à¦•à§à¦¯, à§¨à§« à¦¶à¦¬à§à¦¦à§‡à¦° à¦®à¦§à§à¦¯à§‡à¥¤ à¦•à§‹à¦¨à§‹ à¦¤à¦¾à¦²à¦¿à¦•à¦¾ à¦¬à¦¾ à¦¬à¦¿à¦¶à§‡à¦· à¦šà¦¿à¦¹à§à¦¨ à¦¬à§à¦¯à¦¬à¦¹à¦¾à¦° à¦•à¦°à¦¬à§‡ à¦¨à¦¾à¥¤
à§©. à¦¬à¦°à§à¦¤à¦®à¦¾à¦¨ à¦®à§‹à¦¡: {bot_state['mode']}

à¦®à§‹à¦¡ à¦…à¦¨à§à¦¯à¦¾à¦¯à¦¼à§€ à¦†à¦šà¦°à¦£:
- Natural Mode: à¦®à¦¾à¦¨à§à¦·à§‡à¦° à¦®à¦¤à§‹ à¦¸à¦¾à¦§à¦¾à¦°à¦£ à¦–à§‹à¦¶à¦—à¦²à§à¦ª ("à¦¤à§à¦®à¦¿ à¦•à¦¿ à¦•à¦°à¦›à§‹?", "à¦•à§‡à¦®à¦¨ à¦†à¦›à§‹?").
- Student Mode: à¦ªà¦¡à¦¼à¦¾à¦²à§‡à¦–à¦¾ à¦à¦•à¦¦à¦® à¦¸à¦¹à¦œ à¦­à¦¾à¦·à¦¾à¦¯à¦¼ à¦¬à§à¦à¦¿à¦¯à¦¼à§‡ à¦¦à¦¾à¦“à¥¤
- Kitchen Mode: à¦°à¦¾à¦¨à§à¦¨à¦¾à¦° à¦¸à§à¦Ÿà§‡à¦ª-à¦¬à¦¾à¦‡-à¦¸à§à¦Ÿà§‡à¦ª à¦—à¦¾à¦‡à¦¡ à¦“ Pro-tip à¦¦à¦¾à¦“à¥¤
- Doctor Mode: à¦¸à¦¾à¦§à¦¾à¦°à¦£ à¦¶à¦¾à¦°à§€à¦°à¦¿à¦• à¦¸à¦®à¦¸à§à¦¯à¦¾à¦¯à¦¼ (à¦¯à§‡à¦®à¦¨ à¦ à¦¾à¦¨à§à¦¡à¦¾ à¦²à¦¾à¦—à¦¾, à¦œà§à¦¬à¦°) à¦ªà§à¦¯à¦¾à¦°à¦¾à¦¸à¦¿à¦Ÿà¦¾à¦®à¦²à§‡à¦° à¦ªà§à¦°à¦¾à¦¥à¦®à¦¿à¦• à¦¨à¦¿à¦¯à¦¼à¦® à¦¬à¦²à§‹ (à¦¬à¦¡à¦¼ à¦¸à¦®à¦¸à§à¦¯à¦¾à¦¯à¦¼ à¦¡à¦¾à¦•à§à¦¤à¦¾à¦°à§‡à¦° à¦•à¦¾à¦›à§‡ à¦¯à§‡à¦¤à§‡ à¦¬à¦²à¦¬à§‡)à¥¤
"""


def ask_gemini(contents):
    if client is None:
        raise RuntimeError("GEMINI_API_KEY set kora nei")
    resp = client.models.generate_content(model=MODEL_NAME, contents=contents)
    return (resp.text or "").strip()


def transcribe(audio_bytes):
    prompt = ("Transcribe the spoken audio exactly as it is in Bengali, Hindi, or English. "
              "Output ONLY the transcription, nothing else.")
    part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
    return ask_gemini([part, prompt])


def only_digits(text):
    # Bangla digit (à§¯à§¯à§©) o English digit dutoi 0-9 e convert kore
    return "".join(str(int(c)) for c in text if c.isdecimal())


def shorten(text, limit=None):
    # Uttor beshi lomba hole sentence-er sesh-e kete dao
    limit = limit or MAX_REPLY_CHARS
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last = max(cut.rfind("à¥¤"), cut.rfind("."), cut.rfind("?"), cut.rfind("!"))
    return cut[:last + 1] if last > 40 else cut


def decide_reply(user_text):
    lower = user_text.lower()

    if not user_text:
        return "à¦†à¦®à¦¿ à¦ à¦¿à¦• à¦¬à§à¦à¦¤à§‡ à¦ªà¦¾à¦°à¦¿à¦¨à¦¿, à¦†à¦¬à¦¾à¦° à¦¬à¦²à§‹à¥¤"

    # ---- Settings mode + admin password ----
    if "setting mode" in lower or "à¦¸à§‡à¦Ÿà¦¿à¦‚à¦¸ à¦®à§‹à¦¡" in user_text:
        if not ADMIN_PASSCODE:
            return "à¦¸à§‡à¦Ÿà¦¿à¦‚à¦¸ à¦à¦–à¦¨ à¦¬à¦¨à§à¦§ à¦†à¦›à§‡à¥¤"
        bot_state["mode"] = "setting"
        bot_state["admin_auth"] = False
        return "à¦¸à§‡à¦Ÿà¦¿à¦‚à¦¸ à¦®à§‹à¦¡à§‡ à¦¸à§à¦¬à¦¾à¦—à¦¤à¦®à¥¤ à¦¦à¦¯à¦¼à¦¾ à¦•à¦°à§‡ à¦…à§à¦¯à¦¾à¦¡à¦®à¦¿à¦¨ à¦ªà¦¾à¦¸à¦“à¦¯à¦¼à¦¾à¦°à§à¦¡ à¦¬à¦²à§à¦¨à¥¤"

    if bot_state["mode"] == "setting" and not bot_state["admin_auth"]:
        if ADMIN_PASSCODE and ADMIN_PASSCODE in only_digits(user_text):
            bot_state["admin_auth"] = True
            return "à¦ªà¦¾à¦¸à¦“à¦¯à¦¼à¦¾à¦°à§à¦¡ à¦®à¦¿à¦²à§‡ à¦—à§‡à¦›à§‡à¥¤ à¦†à¦ªà¦¨à¦¿ à¦­à¦¾à¦·à¦¾ à¦¬à¦¾ à¦­à¦¯à¦¼à§‡à¦¸ à¦ªà¦°à¦¿à¦¬à¦°à§à¦¤à¦¨ à¦•à¦°à¦¤à§‡ à¦ªà¦¾à¦°à§‡à¦¨à¥¤"
        bot_state["mode"] = "natural"
        return "à¦­à§à¦² à¦ªà¦¾à¦¸à¦“à¦¯à¦¼à¦¾à¦°à§à¦¡! à¦…à§à¦¯à¦¾à¦•à§à¦¸à§‡à¦¸ à¦¬à¦¾à¦¤à¦¿à¦²à¥¤"

    if bot_state["mode"] == "setting" and bot_state["admin_auth"]:
        if "bangla" in lower or "à¦¬à¦¾à¦‚à¦²à¦¾" in lower:
            bot_state["language"] = "bn-IN"
            return "à¦­à¦¾à¦·à¦¾ à¦¬à¦¾à¦‚à¦²à¦¾à¦¯à¦¼ à¦ªà¦°à¦¿à¦¬à¦°à§à¦¤à¦¨ à¦•à¦°à¦¾ à¦¹à¦²à§‹à¥¤"
        if "hindi" in lower or "à¦¹à¦¿à¦¨à§à¦¦à¦¿" in lower:
            bot_state["language"] = "hi-IN"
            return "à¦­à¦¾à¦·à¦¾ à¦¹à¦¿à¦¨à§à¦¦à¦¿à¦¤à§‡ à¦ªà¦°à¦¿à¦¬à¦°à§à¦¤à¦¨ à¦•à¦°à¦¾ à¦¹à¦²à§‹à¥¤"
        if "english" in lower or "à¦‡à¦‚à¦°à§‡à¦œà¦¿" in lower:
            bot_state["language"] = "en-US"
            return "Language changed to English."
        if "female" in lower or "à¦®à¦¹à¦¿à¦²à¦¾" in lower:   # "female" age check, karon "male" ta "female"-er bhitore ache
            bot_state["voice_gender"] = "female"
            return "à¦®à¦¹à¦¿à¦²à¦¾ à¦•à¦£à§à¦  à¦¸à¦¿à¦²à§‡à¦•à§à¦Ÿ à¦•à¦°à¦¾ à¦¹à¦²à§‹à¥¤"
        if "male" in lower or "à¦ªà§à¦°à§à¦·" in lower:
            bot_state["voice_gender"] = "male"
            return "à¦ªà§à¦°à§à¦· à¦•à¦£à§à¦  à¦¸à¦¿à¦²à§‡à¦•à§à¦Ÿ à¦•à¦°à¦¾ à¦¹à¦²à§‹à¥¤"
        if "exit" in lower or "à¦¬à¦¾à¦¹à¦¿à¦°" in lower or "à¦¬à§‡à¦°" in lower:
            bot_state["mode"] = "natural"
            bot_state["admin_auth"] = False
            return "à¦¸à§‡à¦Ÿà¦¿à¦‚à¦¸ à¦¥à§‡à¦•à§‡ à¦¬à§‡à¦° à¦¹à¦“à¦¯à¦¼à¦¾ à¦¹à¦²à§‹à¥¤"
        return "à¦­à¦¾à¦·à¦¾ à¦¬à¦¾ à¦•à¦£à§à¦  à¦•à§€ à¦•à¦°à¦¤à§‡ à¦šà¦¾à¦¨? à¦¬à¦¾à¦‚à¦²à¦¾, à¦¹à¦¿à¦¨à§à¦¦à¦¿, à¦‡à¦‚à¦°à§‡à¦œà¦¿, à¦ªà§à¦°à§à¦·, à¦®à¦¹à¦¿à¦²à¦¾ à¦¬à¦¾ à¦à¦•à§à¦¸à¦¿à¦Ÿ à¦¬à¦²à§à¦¨à¥¤"

    # ---- Mode change ----
    if "student mode" in lower:
        bot_state["mode"] = "student"
        return "à¦¸à§à¦Ÿà§à¦¡à§‡à¦¨à§à¦Ÿ à¦®à§‹à¦¡ à¦šà¦¾à¦²à§ à¦¹à¦¯à¦¼à§‡à¦›à§‡à¥¤ à¦¤à§‹à¦®à¦¾à¦° à¦ªà¦¡à¦¼à¦¾à¦²à§‡à¦–à¦¾ à¦¸à¦‚à¦•à§à¦°à¦¾à¦¨à§à¦¤ à¦ªà§à¦°à¦¶à§à¦¨ à¦•à¦°à§‹à¥¤"
    if "kitchen mode" in lower:
        bot_state["mode"] = "kitchen"
        return "à¦•à¦¿à¦šà§‡à¦¨ à¦®à§‹à¦¡ à¦šà¦¾à¦²à§ à¦¹à¦¯à¦¼à§‡à¦›à§‡à¥¤ à¦¬à¦²à§‹ à¦†à¦œ à¦•à§€ à¦°à¦¾à¦¨à§à¦¨à¦¾ à¦¹à¦¬à§‡?"
    if "doctor mode" in lower:
        bot_state["mode"] = "doctor"
        return "à¦¡à¦¾à¦•à§à¦¤à¦¾à¦° à¦®à§‹à¦¡ à¦šà¦¾à¦²à§ à¦¹à¦¯à¦¼à§‡à¦›à§‡à¥¤ à¦¤à§‹à¦®à¦¾à¦° à¦¶à¦¾à¦°à§€à¦°à¦¿à¦• à¦¸à¦®à¦¸à§à¦¯à¦¾à¦° à¦•à¦¥à¦¾ à¦¬à¦²à§‹à¥¤"
    if "natural mode" in lower:
        bot_state["mode"] = "natural"
        return "à¦¨à§à¦¯à¦¾à¦šà¦¾à¦°à¦¾à¦² à¦®à§‹à¦¡ à¦šà¦¾à¦²à§ à¦¹à¦¯à¦¼à§‡à¦›à§‡à¥¤"

    # ---- Normal chat ----
    try:
        chat_prompt = f"{get_system_prompt()}\n\nà¦¬à§à¦¯à¦¬à¦¹à¦¾à¦°à¦•à¦¾à¦°à§€ à¦¬à¦²à§‡à¦›à§‡à¦¨: {user_text}\nà¦®à¦¾à¦¯à¦¼à¦¾à¦° à¦‰à¦¤à§à¦¤à¦°:"
        reply = shorten(ask_gemini(chat_prompt).replace("*", ""))
        return reply or "à¦†à¦®à¦¿ à¦ à¦¿à¦• à¦¬à§à¦à¦¤à§‡ à¦ªà¦¾à¦°à¦¿à¦¨à¦¿, à¦†à¦¬à¦¾à¦° à¦¬à¦²à§‹à¥¤"
    except Exception as e:
        print("Chat Error:", e)
        return "à¦¦à§à¦ƒà¦–à¦¿à¦¤, à¦à¦‡ à¦®à§à¦¹à§‚à¦°à§à¦¤à§‡ à¦‰à¦¤à§à¦¤à¦° à¦¦à¦¿à¦¤à§‡ à¦ªà¦¾à¦°à¦›à¦¿ à¦¨à¦¾à¥¤ à¦à¦•à¦Ÿà§ à¦ªà¦°à§‡ à¦†à¦¬à¦¾à¦° à¦¬à¦²à§‹à¥¤"


async def text_to_speech(text, output_file):
    voice_map = {
        ("bn-IN", "female"): "bn-IN-TanishaaNeural",
        ("bn-IN", "male"): "bn-IN-BashkarNeural",
        ("hi-IN", "female"): "hi-IN-SwaraNeural",
        ("hi-IN", "male"): "hi-IN-MadhurNeural",
        ("en-US", "female"): "en-US-JennyNeural",
        ("en-US", "male"): "en-US-GuyNeural",
    }
    selected_voice = voice_map.get(
        (bot_state["language"], bot_state["voice_gender"]), "bn-IN-TanishaaNeural")
    communicate = edge_tts.Communicate(text, selected_voice)
    await communicate.save(output_file)


def authorized():
    # DEVICE_KEY Render-e set kora thakle shudhu sothik chabi-wala (ESP32) dhukte parbe.
    # Set kora na thakle sobai-ke dibe (pore DEVICE_KEY set korle tala lagbe).
    if not DEVICE_KEY:
        return True
    sent = request.headers.get("X-Maya-Key") or request.args.get("key") or ""
    return hmac.compare_digest(sent.encode("utf-8"), DEVICE_KEY.encode("utf-8"))


def mp3_to_wav16k(mp3_path, wav_path):
    # ESP32-te MP3 decoder nei, tai server-e 16 kHz mono 16-bit WAV bonaye pathai
    if miniaudio is None:
        raise RuntimeError("miniaudio install hoyni")
    with open(mp3_path, "rb") as f:
        data = f.read()
    decoded = miniaudio.decode(
        data,
        output_format=miniaudio.SampleFormat.SIGNED16,
        nchannels=1,
        sample_rate=16000,
    )
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(decoded.samples.tobytes())


@app.route("/")
def home():
    # Render server ghum theke jagate ESP32 ei page-e ping kore
    return "Maya is awake", 200


@app.route("/process_audio", methods=["POST"])
def process_audio():
    if not authorized():
        return "Unauthorized", 401

    # ESP32 raw WAV body pathay; multipart 'audio' field-o cholbe
    if "audio" in request.files:
        audio_bytes = request.files["audio"].read()
    else:
        audio_bytes = request.get_data()

    if not audio_bytes or len(audio_bytes) < 100:
        return "No audio received", 400

    user_text = ""
    try:
        user_text = transcribe(audio_bytes)
        print(f"User: {user_text}")
    except Exception as e:
        print("STT Error:", e)

    reply_text = decide_reply(user_text)
    print(f"Maya: {reply_text}")

    try:
        asyncio.run(text_to_speech(reply_text, RESPONSE_PATH))
    except Exception as e:
        print("TTS Error:", e)
        return "TTS error", 500

    try:
        mp3_to_wav16k(RESPONSE_PATH, WAV_PATH)
    except Exception as e:
        print("WAV Convert Error:", e)
        return "WAV convert error", 500

    return "OK", 200


@app.route("/response.mp3", methods=["GET"])
def response_mp3():
    if not authorized():
        return "Unauthorized", 401
    # ESP32 ekhan theke MP3 niye speaker-e bajay
    if not os.path.exists(RESPONSE_PATH):
        return "No response yet", 404
    resp = send_file(RESPONSE_PATH, mimetype="audio/mpeg", conditional=False)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/response.wav", methods=["GET"])
def response_wav():
    # ESP32 ekhan theke WAV niye nijer I2S diye speaker-e bajay
    if not authorized():
        return "Unauthorized", 401
    if not os.path.exists(WAV_PATH):
        return "No response yet", 404
    resp = send_file(WAV_PATH, mimetype="audio/wav", conditional=False)
    resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
