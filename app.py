import os
import urllib.parse
import asyncio
import tempfile
from flask import Flask, request, send_file, make_response
from google import genai
from google.genai import types
import edge_tts

app = Flask(__name__)

# ================= CORS Allow =================
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Expose-Headers'] = 'X-Response-Text'
    return response

# ================= Configuration =================
API_KEY = os.environ.get("GEMINI_API_KEY")
# গুগলের আসল স্টেবল মডেল gemini-1.5-flash
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
ADMIN_PASSCODE = os.environ.get("ADMIN_PASSCODE", "9932857750")

client = genai.Client(api_key=API_KEY) if API_KEY else None
RESPONSE_PATH = os.path.join(tempfile.gettempdir(), "maya_response.mp3")

bot_state = {
    "creator": "Akash Mal",
    "mode": "natural",
    "language": "bn-IN",
    "voice_gender": "female",
    "admin_auth": False,
}

def get_system_prompt():
    return f"""তুমি একটি কৃত্রিম বুদ্ধিমত্তা সম্পন্ন ভয়েস অ্যাসিস্ট্যান্ট, তোমার নাম 'মায়া' (Maya)।
তোমাকে তৈরি করেছে 'আকাশ মাল' (Akash Mal)।

বর্তমান নিয়মাবলী:
১. তোমার বর্তমান ভাষা: {bot_state['language']} (বাংলা/হিন্দি/ইংরেজি)।
২. ব্যবহারকারীর সাথে মানুষের মতো স্বাভাবিক ও আন্তরিকভাবে কথা বলো। উত্তর ২-৩ লাইনের মধ্যে সংক্ষেপে দেবে।
৩. বর্তমান মোড: {bot_state['mode']}

মোড অনুযায়ী আচরণ:
- Natural Mode: মানুষের মতো সাধারণ খোশগল্প ("তুমি কি করছো?", "কেমন আছো?").
- Student Mode: পড়ালেখা একদম সহজ ভাষায় বুঝিয়ে দাও।
- Kitchen Mode: রান্নার স্টেপ-বাই-স্টেপ গাইড ও Pro-tip দাও।
- Doctor Mode: সাধারণ শারীরিক সমস্যায় প্যারাসিটামলের প্রাথমিক নিয়ম বলো।
"""

def ask_gemini(contents):
    if client is None:
        raise RuntimeError("GEMINI_API_KEY set kora nei")
    resp = client.models.generate_content(model=MODEL_NAME, contents=contents)
    return (resp.text or "").strip()

# অডিও ফাইল চেনার অটো-ডিটেকশন (মোবাইল WebM এবং ESP32 WAV দুটোই সাপোর্ট করবে)
def transcribe(audio_bytes):
    if audio_bytes.startswith(b"RIFF"):
        audio_mime = "audio/wav"
    elif audio_bytes.startswith(b"\x1aE\xdf\xa3"):
        audio_mime = "audio/webm"
    else:
        audio_mime = "audio/webm" # মোবাইলের ডিফল্ট

    prompt = ("Transcribe the spoken audio exactly as it is in Bengali, Hindi, or English. "
              "Output ONLY the transcription, nothing else.")
    part = types.Part.from_bytes(data=audio_bytes, mime_type=audio_mime)
    return ask_gemini([part, prompt])

def only_digits(text):
    return "".join(str(int(c)) for c in text if c.isdecimal())

def decide_reply(user_text):
    lower = user_text.lower()

    if not user_text:
        return "আমি ঠিক শুনতে পাইনি, আরেকবার বলো তো?"

    # ---- Settings mode ----
    if "setting mode" in lower or "সেটিংস মোড" in user_text:
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
        if "female" in lower or "মহিলা" in lower:
            bot_state["voice_gender"] = "female"
            return "মহিলা কণ্ঠ সিলেক্ট করা হলো।"
        if "male" in lower or "পুরুষ" in lower:
            bot_state["voice_gender"] = "male"
            return "পুরুষ কণ্ঠ সিলেক্ট করা হলো।"
        if "exit" in lower or "বাহির" in lower:
            bot_state["mode"] = "natural"
            bot_state["admin_auth"] = False
            return "সেটিংস থেকে বের হওয়া হলো।"
        return "ভাষা বা কণ্ঠ কী করতে চান? বাংলা, হিন্দি, ইংরেজি, পুরুষ বা মহিলা বলুন।"

    # ---- Modes ----
    if "student mode" in lower or "স্টুডেন্ট মোড" in lower:
        bot_state["mode"] = "student"
        return "স্টুডেন্ট মোড চালু হয়েছে। তোমার পড়ালেখা সংক্রান্ত প্রশ্ন করো।"
    if "kitchen mode" in lower or "কিচেন মোড" in lower:
        bot_state["mode"] = "kitchen"
        return "কিচেন মোড চালু হয়েছে। বলো আজ কী রান্না হবে?"
    if "doctor mode" in lower or "ডাক্তার মোড" in lower:
        bot_state["mode"] = "doctor"
        return "ডাক্তার মোড চালু হয়েছে। তোমার শারীরিক সমস্যার কথা বলো।"
    if "natural mode" in lower or "ন্যাচারাল মোড" in lower:
        bot_state["mode"] = "natural"
        return "ন্যাচারাল মোড চালু হয়েছে।"

    # ---- Chat ----
    try:
        chat_prompt = f"{get_system_prompt()}\n\nব্যবহারকারী বলেছেন: {user_text}\nমায়ার উত্তর:"
        reply = ask_gemini(chat_prompt).replace("*", "")
        return reply or "আমি ঠিক বুঝতে পারিনি, আবার বলো।"
    except Exception as e:
        print("Chat Error:", e)
        return "দুঃখিত, এই মুহূর্তে উত্তর দিতে পারছি না।"

async def text_to_speech(text, output_file):
    voice_map = {
        ("bn-IN", "female"): "bn-IN-TanishaaNeural",
        ("bn-IN", "male"): "bn-IN-BashkarNeural",
        ("hi-IN", "female"): "hi-IN-SwaraNeural",
        ("hi-IN", "male"): "hi-IN-MadhurNeural",
        ("en-US", "female"): "en-US-JennyNeural",
        ("en-US", "male"): "en-US-GuyNeural",
    }
    selected_voice = voice_map.get((bot_state["language"], bot_state["voice_gender"]), "bn-IN-TanishaaNeural")
    communicate = edge_tts.Communicate(text, selected_voice)
    await communicate.save(output_file)

@app.route("/")
def home():
    return "Maya is awake", 200

@app.route("/process_audio", methods=["GET", "POST", "OPTIONS"])
def process_audio():
    if request.method == "OPTIONS":
        return make_response("", 200)

    if request.method == "GET":
        if os.path.exists(RESPONSE_PATH):
            return send_file(RESPONSE_PATH, mimetype="audio/mpeg", conditional=False)
        return "No audio ready", 200

    user_text = ""

    # ১. টেক্সট পাঠানো হলে
    if "text" in request.form:
        user_text = request.form["text"].strip()
    # ২. অডিও ফাইল পাঠানো হলে
    elif "audio" in request.files:
        audio_bytes = request.files["audio"].read()
        try:
            user_text = transcribe(audio_bytes)
            print(f"Transcribed User Text: {user_text}")
        except Exception as e:
            print("STT Error:", e)
    else:
        audio_bytes = request.get_data()
        if audio_bytes and len(audio_bytes) >= 100:
            try:
                user_text = transcribe(audio_bytes)
                print(f"Transcribed User Text: {user_text}")
            except Exception as e:
                print("STT Error:", e)

    reply_text = decide_reply(user_text)
    print(f"Maya: {reply_text}")

    try:
        asyncio.run(text_to_speech(reply_text, RESPONSE_PATH))
    except Exception as e:
        print("TTS Error:", e)
        return "TTS error", 500

    resp = make_response(send_file(RESPONSE_PATH, mimetype="audio/mpeg", conditional=False))
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Response-Text"] = urllib.parse.quote(reply_text.encode("utf-8"))
    return resp

@app.route("/response.mp3", methods=["GET"])
def response_mp3():
    if not os.path.exists(RESPONSE_PATH):
        return "No response yet", 404
    resp = send_file(RESPONSE_PATH, mimetype="audio/mpeg", conditional=False)
    resp.headers["Cache-Control"] = "no-store"
    return resp

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
