import os
import asyncio
from flask import Flask, request, send_file
import google.generativeai as genai
import edge_tts

app = Flask(__name__)

# Google AI Studio API Key কনফিগারেশন
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
# Gemini 1.5 Flash দ্রুত কাজ করে এবং অডিও বুঝতে পারে
model = genai.GenerativeModel("gemini-1.5-flash")

bot_state = {
    "creator": "Akash Mal",
    "mode": "natural",
    "language": "bn-IN",      # bn-IN, hi-IN, en-US
    "voice_gender": "female", # female, male
    "admin_auth": False
}

PASS_CODE = "9932857750"

def get_system_prompt():
    return f"""তুমি একটি কৃত্রিম বুদ্ধিমত্তা সম্পন্ন ভয়েস অ্যাসিস্ট্যান্ট, তোমার নাম 'মায়া' (Maya)।
তোমাকে তৈরি করেছে 'আকাশ মাল' (Akash Mal)। 

বর্তমান নিয়মাবলী:
১. তোমার বর্তমান ভাষা: {bot_state['language']} (বাংলা/হিন্দি/ইংরেজি)।
২. ব্যবহারকারীর সাথে মানুষের মতো স্বাভাবিক ও আন্তরিকভাবে কথা বলো। উত্তর যথাসম্ভব ২-৩ লাইনের মধ্যে সংক্ষেপে দেবে যাতে ভয়েসে শুনতে ভালো লাগে।
৩. বর্তমান মোড: {bot_state['mode']}

মোড অনুযায়ী আচরণ:
- Natural Mode: মানুষের মতো সাধারণ খোশগল্প ("তুমি কি করছো?", "কেমন আছো?").
- Student Mode: পড়ালেখা একদম সহজ ভাষায় বুঝিয়ে দাও।
- Kitchen Mode: রান্নার স্টেপ-বাই-স্টেপ গাইড ও Pro-tip দাও।
- Doctor Mode: সাধারণ শারীরিক সমস্যায় (যেমন ঠান্ডা লাগা, জ্বর) প্যারাসিটামলের প্রাথমিক নিয়ম বলো (বড় সমস্যায় ডাক্তারের কাছে যেতে বলবে)।
"""

async def text_to_speech(text, output_file):
    voice_map = {
        ("bn-IN", "female"): "bn-IN-TanishaaNeural",
        ("bn-IN", "male"): "bn-IN-BashkarNeural",
        ("hi-IN", "female"): "hi-IN-SwaraNeural",
        ("hi-IN", "male"): "hi-IN-MadhurNeural",
        ("en-US", "female"): "en-US-JennyNeural",
        ("en-US", "male"): "en-US-GuyNeural"
    }
    selected_voice = voice_map.get((bot_state["language"], bot_state["voice_gender"]), "bn-IN-TanishaaNeural")
    communicate = edge_tts.Communicate(text, selected_voice)
    await communicate.save(output_file)

@app.route('/process_audio', methods=['POST'])
def process_audio():
    if 'audio' not in request.files:
        return "No audio file", 400

    audio_file = request.files['audio']
    audio_path = "input.wav"
    audio_file.save(audio_path)

    try:
        # ১. Gemini দিয়ে অডিও থেকে টেক্সট বের করা (STT)
        uploaded_audio = genai.upload_file(path=audio_path)
        transcribe_prompt = "Transcribe the spoken audio exactly as it is in Bengali, Hindi, or English. Output ONLY the transcription, nothing else."
        transcribe_res = model.generate_content([transcribe_prompt, uploaded_audio])
        user_text = transcribe_res.text.strip()
        uploaded_audio.delete() # মেমোরি খালি করা
        print(f"User: {user_text}")
    except Exception as e:
        print("STT Error:", e)
        user_text = ""

    reply_text = ""

    # ২. সেটিংস মোড ও সিকিউরিটি পাসওয়ার্ড চেক
    if "setting mode" in user_text.lower() or "সেটিংস মোড" in user_text:
        bot_state["mode"] = "setting"
        reply_text = "সেটিংস মোডে স্বাগতম। দয়া করে অ্যাডমিন পাসওয়ার্ড বলুন।"
    elif bot_state["mode"] == "setting" and not bot_state["admin_auth"]:
        clean_text = "".join(filter(str.isdigit, user_text))
        if PASS_CODE in clean_text:
            bot_state["admin_auth"] = True
            reply_text = "পাসওয়ার্ড মিলে গেছে। আপনি ভাষা বা ভয়েস পরিবর্তন করতে পারেন।"
        else:
            bot_state["mode"] = "natural"
            reply_text = "ভুল পাসওয়ার্ড! অ্যাক্সেস বাতিল।"
    elif bot_state["mode"] == "setting" and bot_state["admin_auth"]:
        lower = user_text.lower()
        if "bangla" in lower or "বাংলা" in lower:
            bot_state["language"] = "bn-IN"
            reply_text = "ভাষা বাংলায় পরিবর্তন করা হলো।"
        elif "hindi" in lower or "হিন্দি" in lower:
            bot_state["language"] = "hi-IN"
            reply_text = "ভাষা হিন্দিতে পরিবর্তন করা হলো।"
        elif "english" in lower or "ইংরেজি" in lower:
            bot_state["language"] = "en-US"
            reply_text = "Language changed to English."
        elif "male" in lower or "পুরুষ" in lower:
            bot_state["voice_gender"] = "male"
            reply_text = "পুরুষ কণ্ঠ সিলেক্ট করা হলো।"
        elif "female" in lower or "মহিলা" in lower:
            bot_state["voice_gender"] = "female"
            reply_text = "মহিলা কণ্ঠ সিলেক্ট করা হলো।"
        elif "exit" in lower or "বাহির" in lower:
            bot_state["mode"] = "natural"
            bot_state["admin_auth"] = False
            reply_text = "সেটিংস থেকে বের হওয়া হলো।"
    else:
        # ৩. মোড পরিবর্তন চেকিং
        if "student mode" in user_text.lower():
            bot_state["mode"] = "student"
            reply_text = "স্টুডেন্ট মোড চালু হয়েছে। তোমার পড়ালেখা সংক্রান্ত প্রশ্ন করো।"
        elif "kitchen mode" in user_text.lower():
            bot_state["mode"] = "kitchen"
            reply_text = "কিচেন মোড চালু হয়েছে। বলো আজ কী রান্না হবে?"
        elif "doctor mode" in user_text.lower():
            bot_state["mode"] = "doctor"
            reply_text = "ডাক্তার মোড চালু হয়েছে। তোমার শারীরিক সমস্যার কথা বলো।"
        elif "natural mode" in user_text.lower():
            bot_state["mode"] = "natural"
            reply_text = "ন্যাচারাল মোড চালু হয়েছে।"
        else:
            # ৪. Gemini AI দিয়ে উত্তর তৈরি
            chat_prompt = f"{get_system_prompt()}\n\nব্যবহারকারী বলেছেন: {user_text}\nমায়ার উত্তর:"
            response = model.generate_content(chat_prompt)
            reply_text = response.text.replace("*", "") # টেক্সট ক্লিন করা

    print(f"Maya: {reply_text}")

    # ৫. ভয়েস জেনারেট (TTS)
    output_audio = "response.mp3"
    asyncio.run(text_to_speech(reply_text, output_audio))
    return send_file(output_audio, mimetype="audio/mpeg")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)