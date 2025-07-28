from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
import markdown2
import re
import os
from werkzeug.utils import secure_filename
from better_profanity import profanity

app = Flask(__name__)

profanity.load_censor_words()

client = MongoClient("mongodb://localhost:27017/")
db = client["student_forum"]
questions_col = db["questions"]
answers_col = db["answers"]

UPLOAD_FOLDER = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx', 'pptx', 'mp4', 'mov', 'mp3'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ADMIN_KEY = "secret123"  # Change to a secure value for your deployment!

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    return filename.rsplit('.', 1)[1].lower()

def render_markup(text):
    def custom_repl(s):
        s = re.sub(r'\~\~(.*?)\~\~', r'<del>\1</del>', s)
        s = re.sub(r'\~(.*?)\~', r'<sub>\1</sub>', s)
        s = re.sub(r'\^\^(.*?)\^\^', r'<sup>\1</sup>', s)
        return s
    safe_html = markdown2.markdown(text or "", extras=['strike', 'fenced-code-blocks', 'break-on-newline'])
    return custom_repl(safe_html)

@app.route('/')
def index():
    questions = list(questions_col.find().sort("timestamp", -1))
    for q in questions:
        q['_id'] = str(q['_id'])
        q['text_rendered'] = render_markup(q.get('text', ''))
    return render_template('index.html', questions=questions)

@app.route('/ask', methods=['GET', 'POST'])
def ask():
    if request.method == 'POST':
        q_text = request.form.get('question', '').strip()
        attachments = []
        files = request.files.getlist('image')  # Name stays compatible with old templates
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(str(datetime.now().timestamp()) + "_" + file.filename)
                ext = get_file_type(filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                fileinfo = {
                    "url": f'uploads/{filename}',
                    "type": ext,
                    "name": file.filename
                }
                attachments.append(fileinfo)
        if q_text or attachments:
            censored_text = profanity.censor(q_text)
            q = {
                "text": censored_text,
                "timestamp": datetime.now(),
                "file_attachments": attachments,
            }
            q_id = questions_col.insert_one(q).inserted_id
            return redirect(url_for('question', question_id=str(q_id)))
    return render_template('ask.html')

@app.route('/question/<question_id>', methods=['GET', 'POST'])
def question(question_id):
    question = questions_col.find_one({"_id": ObjectId(question_id)})
    if not question:
        return "Question not found", 404
    if request.method == 'POST':
        ans_text = request.form.get('answer', '').strip()
        attachments = []
        files = request.files.getlist('image')
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(str(datetime.now().timestamp()) + "_" + file.filename)
                ext = get_file_type(filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                fileinfo = {
                    "url": f'uploads/{filename}',
                    "type": ext,
                    "name": file.filename
                }
                attachments.append(fileinfo)
        if ans_text or attachments:
            censored_ans = profanity.censor(ans_text)
            a = {
                "question_id": question['_id'],
                "text": censored_ans,
                "timestamp": datetime.now(),
                "file_attachments": attachments,
            }
            answers_col.insert_one(a)
            return redirect(url_for('question', question_id=question_id))
    answers = list(answers_col.find({"question_id": question['_id']}).sort("timestamp", 1))
    question['_id'] = str(question['_id'])
    question['text_rendered'] = render_markup(question.get('text', ''))
    for a in answers:
        a['_id'] = str(a['_id'])
        a['text_rendered'] = render_markup(a.get('text', ''))
    return render_template('question.html', question=question, answers=answers)

@app.route('/delete_question/<question_id>', methods=['POST'])
def delete_question(question_id):
    key = request.form.get('admin_key', '')
    if key != ADMIN_KEY:
        return "Not allowed. Wrong admin key.", 403
    questions_col.delete_one({'_id': ObjectId(question_id)})
    answers_col.delete_many({'question_id': ObjectId(question_id)})
    return redirect(url_for('index'))

@app.route('/delete_answer/<answer_id>/<question_id>', methods=['POST'])
def delete_answer(answer_id, question_id):
    key = request.form.get('admin_key', '')
    if key != ADMIN_KEY:
        return "Not allowed. Wrong admin key.", 403
    answers_col.delete_one({'_id': ObjectId(answer_id)})
    return redirect(url_for('question', question_id=question_id))

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
