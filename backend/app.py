import os
import requests
from datetime import datetime

import markdown 
from flask import Flask, request, render_template

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_

from faster_whisper import WhisperModel
from werkzeug.utils import secure_filename

from flask import redirect

# ---------------------------------------------------
# Flask App Configuration
# ---------------------------------------------------

app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///meetings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Max upload size = 100MB
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024

db = SQLAlchemy(app)

# ---------------------------------------------------
# Upload Configuration
# ---------------------------------------------------

UPLOAD_FOLDER = "uploads"

# Create uploads folder automatically if missing
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Allowed audio/video extensions
ALLOWED_EXTENSIONS = {
    'mp3',
    'wav',
    'm4a',
    'mp4'
}

# ---------------------------------------------------
# Whisper Model Initialization
# ---------------------------------------------------

# Loads Faster-Whisper model into memory
model = WhisperModel("base")

# ---------------------------------------------------
# Database Model
# ---------------------------------------------------

class Meeting(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    filename = db.Column(
        db.String(255),
        nullable=False
    )

    transcript = db.Column(
        db.Text,
        nullable=False
    )

    summary = db.Column(
        db.Text,
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------

def allowed_file(filename):

    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    )

# ---------------------------------------------------
# AI Summarization Function
# ---------------------------------------------------


def generate_summary(transcript):

    transcript = transcript[:4000]

    prompt = f"""
    Summarize this meeting clearly.

    Use markdown formatting.

    Include:
    - Executive Summary
    - Key Points
    - Action Items

    Transcript:
    {transcript}
    """

    try:

        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "phi3",
                "prompt": prompt,
                "stream": False
            },
            timeout=300
        )

        result = response.json()

        return result.get(
            "response",
            "Summary could not be generated."
        )

    except requests.exceptions.Timeout:

        return """
## Summary Temporarily Unavailable

The AI model took too long to respond.

Transcript was successfully processed and saved.
Please try again with a shorter recording.
"""

    except Exception:

        return """
## Summary Generation Failed

Transcript was completed successfully,
but the AI summarization service
is currently unavailable.
"""

# ---------------------------------------------------
# Home Route
# ---------------------------------------------------

@app.route('/')
def home():

    return render_template('index.html')

@app.route('/history')
def history():

    search = request.args.get("q", "")

    if search:

        meetings = Meeting.query.filter(
            or_(
                Meeting.filename.ilike(f"%{search}%"),
                Meeting.transcript.ilike(f"%{search}%"),
                Meeting.summary.ilike(f"%{search}%")
            )
        ).order_by(
            Meeting.created_at.desc()
        ).all()

    else:

        meetings = Meeting.query.order_by(
            Meeting.created_at.desc()
        ).all()

    return render_template(
        "history.html",
        meetings=meetings,
        search=search
    )
@app.route('/meeting/<int:id>')
def meeting_detail(id):

    meeting = Meeting.query.get(id)

    if not meeting:

        return "Meeting not found", 404

    formatted_summary = markdown.markdown(
        meeting.summary
    )

    return render_template(
        'meeting_detail.html',
        meeting=meeting,
        formatted_summary=formatted_summary
    )
# ---------------------------------------------------
# Upload + Transcription + Summary Route
# ---------------------------------------------------

@app.route('/upload', methods=['POST'])
def upload_audio():

    # Validate audio key
    if 'audio' not in request.files:

        return {
            "error": "No audio file uploaded"
        }, 400

    audio = request.files['audio']

    # Validate empty filename
    if audio.filename == '':

        return {
            "error": "No selected file"
        }, 400

    # Validate file extension
    if not allowed_file(audio.filename):

        return {
            "error": "Unsupported file format"
        }, 400

    try:

        # Secure filename
        filename = secure_filename(audio.filename)

        filepath = os.path.join(
            UPLOAD_FOLDER,
            filename
        )

        # Save uploaded file
        audio.save(filepath)

        # ---------------------------------------------------
        # Whisper Transcription
        # ---------------------------------------------------

        segments, info = model.transcribe(filepath)

        transcript = ""

        for segment in segments:

            transcript += segment.text + " "

        # ---------------------------------------------------
        # AI Summary Generation
        # ---------------------------------------------------

        summary = generate_summary(transcript)

        # ---------------------------------------------------
        # Save To Database
        # ---------------------------------------------------

        meeting = Meeting(
            filename=filename,
            transcript=transcript,
            summary=summary
        )

        db.session.add(meeting)

        db.session.commit()

        # ---------------------------------------------------
        # API Response
        # ---------------------------------------------------

        return {
            "message": "Meeting processed successfully",
            "meeting_id": meeting.id,
            "transcript": transcript,
            "summary": summary
        }

    except Exception as e:

        return {
            "error": str(e)
        }, 500
@app.route('/delete/<int:id>', methods=['POST'])
def delete_meeting_ui(id):

    meeting = Meeting.query.get(id)

    if not meeting:

        return "Meeting not found", 404

    db.session.delete(meeting)

    db.session.commit()

    return redirect('/history')
# ---------------------------------------------------
# UI UPLOAD ROUTE
# ---------------------------------------------------
@app.route('/upload-ui', methods=['POST'])
def upload_ui():

    if 'audio' not in request.files:

        return "<p>No audio uploaded</p>"

    audio = request.files['audio']

    filename = secure_filename(audio.filename)

    filepath = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    audio.save(filepath)

    segments, info = model.transcribe(filepath)

    transcript = ""

    for segment in segments:

        transcript += segment.text + " "

    summary = generate_summary(transcript)
    formatted_summary = markdown.markdown(summary)

    meeting = Meeting(
        filename=filename,
        transcript=transcript,
        summary=summary
    )

    db.session.add(meeting)

    db.session.commit()

    return f'''
    <div class="result-box">

        <h2>Transcript</h2>

        <p>{transcript}</p>

        <hr>

        <h2>Summary</h2>

        <div class="summary-box">
            {formatted_summary}
        </div>

    </div>
'''
# ---------------------------------------------------
# GET ALL MEETINGS
# ---------------------------------------------------

@app.route('/meetings', methods=['GET'])
def get_meetings():

    search = request.args.get("q", "")

    if search:

        meetings = Meeting.query.filter(
            db.or_(
                Meeting.filename.ilike(f"%{search}%"),
                Meeting.transcript.ilike(f"%{search}%"),
                Meeting.summary.ilike(f"%{search}%")
            )
        ).all()

    else:

        meetings = Meeting.query.all()

    results = []

    for meeting in meetings:

        results.append({
            "id": meeting.id,
            "filename": meeting.filename,
            "transcript": meeting.transcript,
            "summary": meeting.summary,
            "created_at": meeting.created_at
        })

    return results

# ---------------------------------------------------
# GET SINGLE MEETING
# ---------------------------------------------------

@app.route('/meetings/<int:id>', methods=['GET'])
def get_meeting(id):

    meeting = Meeting.query.get(id)

    if not meeting:

        return {
            "error": "Meeting not found"
        }, 404

    return {
        "id": meeting.id,
        "filename": meeting.filename,
        "transcript": meeting.transcript,
        "summary": meeting.summary,
        "created_at": meeting.created_at
    }

# ---------------------------------------------------
# UPDATE MEETING
# ---------------------------------------------------

@app.route('/meetings/<int:id>', methods=['PUT'])
def update_meeting(id):

    meeting = Meeting.query.get(id)

    if not meeting:

        return {
            "error": "Meeting not found"
        }, 404

    # Validate JSON body
    if not request.json:

        return {
            "error": "Invalid JSON body"
        }, 400

    data = request.json

    # Update summary
    meeting.summary = data.get(
        'summary',
        meeting.summary
    )

    # Update transcript
    meeting.transcript = data.get(
        'transcript',
        meeting.transcript
    )

    db.session.commit()

    return {
        "message": "Meeting updated successfully",
        "meeting": {
            "id": meeting.id,
            "summary": meeting.summary,
            "transcript": meeting.transcript
        }
    }

# ---------------------------------------------------
# DELETE MEETING
# ---------------------------------------------------

@app.route('/meetings/<int:id>', methods=['DELETE'])
def delete_meeting(id):

    meeting = Meeting.query.get(id)

    if not meeting:

        return {
            "error": "Meeting not found"
        }, 404

    # Delete uploaded file if exists
    filepath = os.path.join(
        UPLOAD_FOLDER,
        meeting.filename
    )

    if os.path.exists(filepath):

        os.remove(filepath)

    # Delete database row
    db.session.delete(meeting)

    db.session.commit()

    return {
        "message": "Meeting deleted successfully"
    }

# ---------------------------------------------------
# Create Database Tables
# ---------------------------------------------------

with app.app_context():

    db.create_all()

# ---------------------------------------------------
# Run Flask App
# ---------------------------------------------------

if __name__ == '__main__':

    app.run(debug=True)