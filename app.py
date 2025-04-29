# app.py (Render Version)
import os
import uuid
import datetime
import json
import logging
from flask import Flask, request, jsonify, render_template, url_for
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - APP - %(message)s')
log = logging.getLogger(__name__)
log.info("app.py: Bắt đầu cấu hình...")

# --- App Initialization ---
app = Flask(__name__)
log.info("app.py: Tạo xong instance Flask.")

# --- Configuration ---
# SECRET_KEY from Render Environment Variables
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    log.critical("app.py: !!! BIẾN MÔI TRƯỜNG SECRET_KEY CHƯA ĐẶT !!!")

# Other Config
USERNAME = os.environ.get("USER", "renderuser") # Less relevant on Render but used for path
APP_NAME = "AI-Detector"
# Use Render's standard /tmp or a dedicated disk if attached (check Render docs)
# /tmp is often ephemeral but okay for brief processing
BASE_TMP_UPLOAD_DIR = f'/tmp/{APP_NAME}/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Database Config (Read DATABASE_URL from Render Env Var)
local_db_fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'local_test_tasks.db')
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"): # Render uses postgresql, fix for SQLAlchemy
     database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or f'sqlite:///{local_db_fallback}'
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
log.info(f"app.py: Database URI được thiết lập (sẽ dùng DATABASE_URL trên Render).")

# --- Initialize Extensions ---
try:
    db = SQLAlchemy(app)
    migrate = Migrate(app, db)
    log.info("app.py: Khởi tạo SQLAlchemy & Migrate thành công.")
except Exception as ext_err:
     log.error(f"app.py: Lỗi khởi tạo Extension: {ext_err}", exc_info=True); raise

# --- Database Model (No changes needed from previous correct version) ---
class ProcessingTask(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())); task_type = db.Column(db.String(20), nullable=False, default='image'); original_filename = db.Column(db.String(255), nullable=True); filepath = db.Column(db.String(512), nullable=True); input_text = db.Column(db.Text, nullable=True); status = db.Column(db.String(20), nullable=False, default='PENDING'); result_json = db.Column(db.Text, nullable=True); created_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(datetime.UTC)); updated_at = db.Column(db.DateTime, default=lambda: datetime.datetime.now(datetime.UTC), onupdate=lambda: datetime.datetime.now(datetime.UTC));
    def __repr__(self): input_info = f"File: {self.original_filename}" if self.task_type == 'image' else f"Đoạn text"; return f'<Task {self.id} ({self.task_type} - {self.status}) {input_info}>'
log.info("app.py: Định nghĩa xong model ProcessingTask.")

# --- Helper ---
def allowed_file(filename): return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes (No functional changes needed from previous correct version) ---
@app.route('/')
def index(): log.info("app.py: Request for '/'."); return render_template('index.html')

@app.route('/upload_image', methods=['POST'])
def upload_image_file():
    log.info("app.py: Request for '/upload_image'.");
    # ... (rest of image upload logic - unchanged) ...
    if 'file' not in request.files: return jsonify({'error': 'Không có phần file nào'}), 400; file = request.files['file']; if file.filename == '': return jsonify({'error': 'Không có file nào được chọn'}), 400;
    if file and allowed_file(file.filename): original_filename = secure_filename(file.filename); log.info(f"app.py: Processing image: {original_filename}"); _, ext = os.path.splitext(original_filename); task_id = str(uuid.uuid4()); unique_subdir = os.path.join(BASE_TMP_UPLOAD_DIR, task_id[:2]); os.makedirs(unique_subdir, exist_ok=True); filepath = os.path.join(unique_subdir, f"{task_id}{ext}");
    try: file.save(filepath); log.info(f"app.py: File saved: {filepath}"); new_task = ProcessingTask(id=task_id, task_type='image', original_filename=original_filename, filepath=filepath, status='PENDING'); db.session.add(new_task); db.session.commit(); log.info(f"app.py: Task {task_id} (image) created for '{original_filename}'."); return jsonify({'task_id': new_task.id}), 202
    except Exception as e: db.session.rollback(); log.error(f"app.py: Error creating image task for {original_filename}: {e}", exc_info=True); if os.path.exists(filepath): try: os.remove(filepath); except OSError as re: log.error(f"app.py: Cleanup failed {filepath}: {re}"); return jsonify({'error': 'Lỗi server khi xử lý file ảnh'}), 500
    else: allowed_types = ', '.join(ALLOWED_EXTENSIONS); log.warning(f"app.py: Upload rejected ('{file.filename}'). Allowed: {allowed_types}"); return jsonify({'error': f"Loại file ảnh không cho phép. Cho phép: {allowed_types}"}), 400

@app.route('/detect_text', methods=['POST'])
def detect_text_input():
    log.info("app.py: Request for '/detect_text'.");
    # ... (rest of text detection logic - unchanged) ...
    if not request.is_json: return jsonify({'error': 'Yêu cầu phải là JSON'}), 400; data = request.get_json(); if not data: return jsonify({'error': 'Dữ liệu JSON không hợp lệ hoặc trống'}), 400; input_text = data.get('text_input', '').strip(); if not input_text: return jsonify({'error': 'Thiếu nội dung văn bản (text_input)'}), 400; task_id = str(uuid.uuid4()); log.info(f"app.py: Processing text input for task {task_id}...");
    try: new_task = ProcessingTask(id=task_id, task_type='text', input_text=input_text, status='PENDING'); db.session.add(new_task); db.session.commit(); log.info(f"app.py: Task {task_id} (text) created."); return jsonify({'task_id': new_task.id}), 202
    except Exception as e: db.session.rollback(); log.error(f"app.py: Error creating text task in DB: {e}", exc_info=True); return jsonify({'error': 'Lỗi server khi tạo task xử lý văn bản'}), 500

@app.route('/status/<task_id>')
def task_status(task_id):
    log.debug(f"app.py: Status check for task_id: {task_id}");
    # ... (rest of status logic - unchanged) ...
    try: task = ProcessingTask.query.get(task_id); if not task: log.warning(f"app.py: Status check fail: Task ID not found: {task_id}"); return jsonify({'state': 'NOT_FOUND', 'status': 'Không tìm thấy Task ID.'}), 404; response = {'task_id': task.id, 'task_type': task.task_type, 'state': task.status, 'result': None, 'status': f'Trạng thái Task: {task.status}'};
    if task.result_json: try: response['result'] = json.loads(task.result_json); except json.JSONDecodeError: log.warning(f"app.py: Failed decode result_json task {task_id}"); response['result'] = {'error': 'Lỗi phân tích dữ liệu kết quả'};
    if task.status == 'SUCCESS': response['status'] = 'Hoàn thành'; elif task.status == 'FAILURE': response['status'] = 'Thất bại'; elif task.status == 'PROCESSING': response['status'] = 'Đang xử lý...'; elif task.status == 'PENDING': response['status'] = 'Đang chờ trong hàng đợi...';
    log.debug(f"app.py: Returning status task {task_id}: {response['state']}"); return jsonify(response)
    except Exception as e: log.error(f"app.py: Error fetching status task {task_id}: {e}", exc_info=True); return jsonify({'error': 'Lỗi server khi lấy trạng thái task'}), 500

# --- CLI Commands ---
@app.cli.command('init-db')
def init_db_command(): print("Initializing LOCAL database..."); try: with app.app_context(): db.create_all(); print('Local DB tables ensured.'); except Exception as e: print(f"Error initializing local DB: {e}")

# --- Local Dev Runner ---
# This block is ignored by Gunicorn on Render
if __name__ == '__main__':
    log.info("app.py: Running in local development mode.")
    try: os.makedirs(BASE_TMP_UPLOAD_DIR, exist_ok=True); log.info(f"app.py: Ensured tmp dir: {BASE_TMP_UPLOAD_DIR}")
    except Exception as dir_err: log.error(f"app.py: Could not create tmp dir: {dir_err}")
    with app.app_context(): db.create_all() # Create local SQLite if not exists
    app.run(debug=True, host='0.0.0.0', port=5000)
