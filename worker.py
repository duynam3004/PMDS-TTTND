import time
import os
import datetime
import json
from app import app, db, ProcessingTask # Import app, db, and model from app.py
from detection_logic import run_photo_manipulation_detection, format_error_result, format_success_result

# Define the base directory for uploads based on app.py's UPLOAD_FOLDER
# This ensures consistency if paths change.
# Note: On PA, ensure UPLOAD_FOLDER is set correctly. Using /tmp might be safer.
BASE_UPLOAD_FOLDER = app.config['UPLOAD_FOLDER']
POLL_INTERVAL = 5 # Seconds between checking for new tasks

def process_pending_tasks():
    print(f"{datetime.datetime.utcnow()}: Worker checking for pending tasks...")
    with app.app_context(): # Need app context to use db
        # Find the oldest pending task
        task = db.session.query(ProcessingTask)\
                         .filter_by(status='PENDING')\
                         .order_by(ProcessingTask.created_at)\
                         .first()

        if task:
            print(f"Found task {task.id}. Processing...")
            task.status = 'PROCESSING'
            task.updated_at = datetime.datetime.utcnow()
            db.session.commit() # Commit status change immediately

            detection_result_json = None
            success = False
            try:
                # --- Run the actual detection ---
                # Ensure filepath is absolute and exists
                if not os.path.isabs(task.filepath):
                     # This shouldn't happen if saved correctly in app.py
                     raise ValueError(f"Filepath for task {task.id} is not absolute: {task.filepath}")
                if not os.path.exists(task.filepath):
                    raise FileNotFoundError(f"File not found for task {task.id}: {task.filepath}")

                detection_result = run_photo_manipulation_detection(task.filepath)
                detection_result_json = format_success_result(detection_result, task.original_filename)
                task.status = 'SUCCESS'
                success = True
                print(f"Task {task.id} completed successfully.")

            except Exception as e:
                print(f"Error processing task {task.id}: {e}")
                task.status = 'FAILURE'
                detection_result_json = format_error_result(e, task.original_filename)
                success = False

            finally:
                # Update task result and status in DB
                task.result_json = detection_result_json
                task.updated_at = datetime.datetime.utcnow()
                db.session.commit()

                # --- Cleanup: Delete the file AFTER processing ---
                if os.path.exists(task.filepath):
                    try:
                        os.remove(task.filepath)
                        print(f"Cleaned up file: {task.filepath}")
                        # Optionally remove the unique sub-directory if empty
                        try:
                            os.rmdir(os.path.dirname(task.filepath))
                            print(f"Removed empty directory: {os.path.dirname(task.filepath)}")
                        except OSError:
                            pass # Dir not empty or other error, ignore
                    except OSError as e:
                        print(f"Error deleting file {task.filepath}: {e}")
                        # Log this error seriously in a real app

        else:
            print("No pending tasks found.")

if __name__ == "__main__":
    print("Starting DB polling worker...")
    while True:
        try:
            process_pending_tasks()
        except Exception as e:
             # Log critical worker loop errors
             print(f"CRITICAL WORKER ERROR: {e}")
             # Avoid rapid failure loops
             time.sleep(60)
        time.sleep(POLL_INTERVAL)