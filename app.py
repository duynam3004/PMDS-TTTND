import os
import uuid
import datetime # Need this
from flask import Flask, request, jsonify, render_template, url_for
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
# Removed Celery imports

# --- Configuration ---
UPLOAD_FOLDER = 'uploads' # Adjust path for PA later
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-local-secret-key') # Use environment variable
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# --- Database Configuration (SQLite for local/simple PA) ---
# For PA, you might change this later to MySQL/Postgres connection string
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tasks.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Ensure upload folder exists (will adjust path on PA)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- Database Model for Tasks ---
class ProcessingTask(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(512), nullable=False) # Store path for worker
    status = db.Column(db.String(20), nullable=False, default='PENDING') # PENDING, PROCESSING, SUCCESS, FAILURE
    result_json = db.Column(db.Text, nullable=True) # Store result as JSON string
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def __repr__(self):
        return f'<Task {self.id} ({self.status})>'

# --- Helper Function (no change) ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        original_filename = secure_filename(file.filename)
        _, ext = os.path.splitext(original_filename)
        # Create a unique sub-directory within uploads for better management
        task_id = str(uuid.uuid4())
        relative_dir = os.path.join(UPLOAD_FOLDER, task_id[:2]) # Use first 2 chars of UUID for subdir
        absolute_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_dir)
        os.makedirs(absolute_dir, exist_ok=True) # Create subdir

        unique_filename = f"{task_id}{ext}"
        # Store the *absolute* path for the worker, relative might be ambiguous
        filepath = os.path.join(absolute_dir, unique_filename)
        # Store relative path for potential future use if needed
        relative_filepath = os.path.join(relative_dir, unique_filename)

        try:
            file.save(filepath)

            # Create a task entry in the database
            new_task = ProcessingTask(
                id=task_id,
                original_filename=original_filename,
                filepath=filepath, # Worker needs the absolute path on the server
                status='PENDING'
            )
            db.session.add(new_task)
            db.session.commit()

            # Return the database task ID
            return jsonify({'task_id': new_task.id}), 202

        except Exception as e:
            db.session.rollback() # Rollback DB changes if save/commit fails
            if os.path.exists(filepath): os.remove(filepath)
            app.logger.error(f"Error during upload or DB task creation: {e}")
            return jsonify({'error': 'Failed to process file'}), 500
    else:
        return jsonify({'error': f"File type not allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

@app.route('/status/<task_id>')
def task_status(task_id):
    # Query the database for the task status
    task = ProcessingTask.query.get(task_id)

    if not task:
        return jsonify({'state': 'NOT_FOUND', 'status': 'Task ID not found.'}), 404

    response = {
        'task_id': task.id,
        'state': task.status, # Use DB status directly
        'result': None,
        'status': f'Task status: {task.status}'
    }

    if task.status == 'SUCCESS':
        import json
        try:
            response['result'] = json.loads(task.result_json) if task.result_json else None
            response['status'] = 'Complete'
        except json.JSONDecodeError:
             response['status'] = 'Complete (Error decoding result)'
             response['result'] = {'error': 'Failed to parse result JSON'}
    elif task.status == 'FAILURE':
        response['status'] = 'Task failed'
        # Store error details in result_json in the worker
        import json
        try:
            response['result'] = json.loads(task.result_json) if task.result_json else {'error': 'Unknown failure'}
        except json.JSONDecodeError:
             response['result'] = {'error': 'Failed to parse failure details'}
    elif task.status == 'PROCESSING':
        response['status'] = 'Processing...'
    elif task.status == 'PENDING':
        response['status'] = 'Waiting in queue...'

    return jsonify(response)

# Command to create DB tables (run once locally and once on PA)
@app.cli.command('init-db')
def init_db_command():
    """Creates the database tables."""
    with app.app_context(): # Ensure we are in app context
         db.create_all()
    print('Initialized the database.')

if __name__ == '__main__':
    # Create DB if it doesn't exist when running locally
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)