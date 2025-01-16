from flask import Flask, render_template, request, redirect, url_for
import os
import ocr_script
import json

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Your time_slots dictionary
time_slots = {
    "Monday": {
        "A11": {"start": "08:30", "end": "10:00"},
        "B11": {"start": "10:05", "end": "11:35"},
        "C11": {"start": "11:40", "end": "13:10"},
        "A21": {"start": "13:15", "end": "14:45"},
        "A14": {"start": "14:50", "end": "16:20"},
        "B21": {"start": "16:25", "end": "17:55"},
        "C21": {"start": "18:00", "end": "19:30"},
    },
    "Tuesday": {
        "D11": {"start": "08:30", "end": "10:00"},
        "E11": {"start": "10:05", "end": "11:35"},
        "F11": {"start": "11:40", "end": "13:10"},
        "D21": {"start": "13:15", "end": "14:45"},
        "E14": {"start": "14:50", "end": "16:20"},
        "E21": {"start": "16:25", "end": "17:55"},
        "F21": {"start": "18:00", "end": "19:30"},
    },
    "Wednesday": {
        "A12": {"start": "08:30", "end": "10:00"},
        "B12": {"start": "10:05", "end": "11:35"},
        "C12": {"start": "11:40", "end": "13:10"},
        "A22": {"start": "13:15", "end": "14:45"},
        "B14": {"start": "14:50", "end": "16:20"},
        "B22": {"start": "16:25", "end": "17:55"},
        "A24": {"start": "18:00", "end": "19:30"},
    },
    "Thursday": {
        "D12": {"start": "08:30", "end": "10:00"},
        "E12": {"start": "10:05", "end": "11:35"},
        "F12": {"start": "11:40", "end": "13:10"},
        "D22": {"start": "13:15", "end": "14:45"},
        "F14": {"start": "14:50", "end": "16:20"},
        "E22": {"start": "16:25", "end": "17:55"},
        "F22": {"start": "18:00", "end": "19:30"},
    },
    "Friday": {
        "A13": {"start": "08:30", "end": "10:00"},
        "B13": {"start": "10:05", "end": "11:35"},
        "C13": {"start": "11:40", "end": "13:10"},
        "A23": {"start": "13:15", "end": "14:45"},
        "C14": {"start": "14:50", "end": "16:20"},
        "B23": {"start": "16:25", "end": "17:55"},
        "B24": {"start": "18:00", "end": "19:30"},
    },
    "Saturday": {
        "D13": {"start": "08:30", "end": "10:00"},
        "E13": {"start": "10:05", "end": "11:35"},
        "F13": {"start": "11:40", "end": "13:10"},
        "D23": {"start": "13:15", "end": "14:45"},
        "D14": {"start": "14:50", "end": "16:20"},
        "D24": {"start": "18:00", "end": "19:30"},
    }
}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_timetable(extracted_data, selected_options):
    timetable = {}
    for day in time_slots:
        timetable[day] = {}
        for slot in time_slots[day]:
            timetable[day][slot] = []  # Initialize for each day-slot combination

    for entry in extracted_data:
        for slot in entry["slots"]:
            for day, slots in time_slots.items():
                if slot in slots:
                    info = []
                    if "course_name" in selected_options:
                        info.append(entry["course_name"].strip())
                    if "course_code" in selected_options:
                        info.append(entry["course_code"].strip())
                    if "venue" in selected_options:
                        info.append(entry["venue"].strip())
                    if "faculty_name" in selected_options:
                        info.append(entry["faculty_name"].strip())
                    timetable[day][slot].append(info)  # Add info for matched day-slot

    return timetable

@app.route("/", methods=['GET'])
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_image():
    if 'schedule_image' not in request.files:
        return redirect(url_for('index'))
    file = request.files['schedule_image']
    if file.filename == '':
        return redirect(url_for('index'))
    if file and allowed_file(file.filename):
        filename = file.filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        extracted_data = ocr_script.run_ocr_and_extract(file_path)
        selected_options = request.form.getlist("display_options")
        if not selected_options:
            selected_options = ["course_name", "venue"]
        timetable = generate_timetable(extracted_data, selected_options)

        return render_template('index.html', time_slots=time_slots, timetable=timetable, selected_options=selected_options, extracted_data=extracted_data)

    return redirect(url_for('index'))

@app.route("/submit_timetable", methods=["POST"])
def submit_timetable():
    if request.method == "POST":
      timetable_data = request.form.get("timetable_data") #extracts the json string
      if timetable_data:
        print(timetable_data) #do what you want with the data here.
    return redirect(url_for('index'))

if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(host='0.0.0.0', debug=True)