import os

from flask import Flask, request
from faster_whisper import WhisperModel

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

model = WhisperModel("base")

@app.route('/')
def home():
    return {"message": "Server running"}

@app.route('/upload', methods=['POST'])
def upload_audio():

    audio = request.files['audio']

    filepath = os.path.join(
        UPLOAD_FOLDER,
        audio.filename
    )

    audio.save(filepath)

    segments, info = model.transcribe(filepath)  #“AI, listen to this audio and convert speech into text.”

    transcript = ""

    for segment in segments:
        transcript += segment.text

    return {
        "transcript": transcript
    }

if __name__ == '__main__':
    app.run(debug=True)