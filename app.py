import os
import asyncio
import tempfile
from flask import Flask, request, send_file
from google import genai
from google.genai import types
import edge_tts

app = Flask(__name__)

# ================= Render Environment Variables =================
# GEMINI_API_KEY  : Google AI Studio key (Render Environment-e dao, code-e noy)
# GEMINI_MODEL    : optional, default niche dewa ache
# ADMIN_PASSCODE  : settings-er password (Render Environment-e dao, code-e likho na)
API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
ADMIN_PASSCODE = os.environ.get("ADMIN_PASSCODE", "")

client = genai.Client(api_key=API_KEY) if API_KEY else None

RESPONSE_PATH = os.path.join(tempfile.gettempdir(), "maya_response.mp3")

bot_state = {
    "creator": "Akash Mal",
    "mode": "natural",
    "language": "bn-IN",       # bn-IN, hi-IN, en-US
    "voice_gender": "female",  # female, male
    "admin_auth": False,
}


def get_system_prompt():
    return f"""তুমি একটি কৃত্রিম বুদ্ধিমত্তা সম্পন্ন ভয়েস অ্যাসিস্ট্যান্ট, তোমার নাম 'মায়া' (Maya)।
তোমাকে তৈরি করেছে 'আকাশ মাল' (Akash Mal)।

বর্তমান নিয়মাবলী:
১. তোমার বর্তমান ভাষা: {bot_state['language']} (বাংলা/হিন্দি/ইংরেজি)।
২. ব্যবহারকারীর সাথে মানুষের মতো স্বাভাবিক ও আন্তরিকভাবে কথা বলো। উত্তর যথাসম্ভব ২-৩ লাইনের মধ্যে সংক্ষেপে দেবে যাতে ভয়েসে শুনতে ভালো লাগে।
৩. বর্তমান মোড: {bot_state['mode']}

মোড অনুযায়ী আচরণ:
- Natural Mode: মানুষের মতো সাধারণ খোশগল্প ("তুমি কি করছো?", "কেমন আছো?").
- Student Mode: পড়ালেখা একদম সহজ ভাষায় বুঝিয়ে দাও।
- Kitchen Mode: রান্নার স্টেপ-বাই-স্টেপ গাইড ও Pro-tip দাও।
- Doctor Mode: সাধারণ শারীরিক সমস্যায় (যেমন ঠান্ডা লাগা, জ্বর) প্যারাসিটামলের প্রাথমিক নিয়ম বলো (বড় সমস্যায় ডাক্তারের কাছে যেতে বলবে)।
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
    # Bangla digit (৯৯৩) o English digit dutoi 0-9 e convert kore
    return "".join(str(int(c)) for c in text if c.isdecimal())


def decide_reply(user_text):
    lower = user_text.lower()

    if not user_text:
        return "আমি ঠিক বুঝতে পারিনি, আবার বলো।"

    # ---- Settings mode + admin password ----
    if "setting mode" in lower or "সেটিংস মোড" in user_text:
        if not ADMIN_PASSCODE:
            return "সেটিংস এখন বন্ধ আছে।"
        bot_state["mode"] = "setting"
        bot_state["admin_auth"] = False
        return "সেটিংস মোডে স্বাগতম। দয়া করে অ্যাডমিন পাসওয়ার্ড বলুন।"

    if bot_state["mode"] == "setting" and not bot_state["admin_auth"]:
        if ADMIN_PASSCODE and ADMIN_PASSCODE in only_digits(user_text):
            bot_state["admin_auth"] = True
            return "পাসওয়ার্ড মিলে গেছে। আপনি ভাষা বা ভয়েস পরিবর্তন করতে পারেন।"
        bot_state["mode"] = "natural"
        return "ভুল পাসওয়ার্ড! অ্যাক্সেস বাতিল।"

    if bot_state["mode"] == "setting" and bot_state["admin_auth"]:
        if "bangla" in lower or "বাংলা" in lower:
            bot_state["language"] = "bn-IN"
            return "ভাষা বাংলায় পরিবর্তন করা হলো।"
        if "hindi" in lower or "হিন্দি" in lower:
            bot_state["language"] = "hi-IN"
            return "ভাষা হিন্দিতে পরিবর্তন করা হলো।"
        if "english" in lower or "ইংরেজি" in lower:
            bot_state["language"] = "en-US"
            return "Language changed to English."
        if "female" in lower or "মহিলা" in lower:   # "female" age check, karon "male" ta "female"-er bhitore ache
            bot_state["voice_gender"] = "female"
            return "মহিলা কণ্ঠ সিলেক্ট করা হলো।"
        if "male" in lower or "পুরুষ" in lower:
            bot_state["voice_gender"] = "male"
            return "পুরুষ কণ্ঠ সিলেক্ট করা হলো।"
        if "exit" in lower or "বাহির" in lower or "বের" in lower:
            bot_state["mode"] = "natural"
            bot_state["admin_auth"] = False
            return "সেটিংস থেকে বের হওয়া হলো।"
        return "ভাষা বা কণ্ঠ কী করতে চান? বাংলা, হিন্দি, ইংরেজি, পুরুষ, মহিলা বা এক্সিট বলুন।"

    # ---- Mode change ----
    if "student mode" in lower:
        bot_state["mode"] = "student"
        return "স্টুডেন্ট মোড চালু হয়েছে। তোমার পড়ালেখা সংক্রান্ত প্রশ্ন করো।"
    if "kitchen mode" in lower:
        bot_state["mode"] = "kitchen"
        return "কিচেন মোড চালু হয়েছে। বলো আজ কী রান্না হবে?"
    if "doctor mode" in lower:
        bot_state["mode"] = "doctor"
        return "ডাক্তার মোড চালু হয়েছে। তোমার শারীরিক সমস্যার কথা বলো।"
    if "natural mode" in lower:
        bot_state["mode"] = "natural"
        return "ন্যাচারাল মোড চালু হয়েছে।"

    # ---- Normal chat ----
    try:
        chat_prompt = f"{get_system_prompt()}\n\nব্যবহারকারী বলেছেন: {user_text}\nমায়ার উত্তর:"
        reply = ask_gemini(chat_prompt).replace("*", "")
        return reply or "আমি ঠিক বুঝতে পারিনি, আবার বলো।"
    except Exception as e:
        print("Chat Error:", e)
        return "দুঃখিত, এই মুহূর্তে উত্তর দিতে পারছি না। একটু পরে আবার বলো।"


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


@app.route("/")
def home():
    # Render server ghum theke jagate ESP32 ei page-e ping kore
    return "Maya is awake", 200


@app.route("/process_audio", methods=["POST"])
def process_audio():
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

    return "OK", 200


@app.route("/response.mp3", methods=["GET"])
def response_mp3():
    # ESP32 ekhan theke MP3 niye speaker-e bajay
    if not os.path.exists(RESPONSE_PATH):
        return "No response yet", 404
    resp = send_file(RESPONSE_PATH, mimetype="audio/mpeg", conditional=False)
    resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
