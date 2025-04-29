# worker.py (Dành cho PythonAnywhere Always-on Task - Local Models)
import time, os, datetime, json, logging, sys, signal, traceback

current_dir = os.path.dirname(os.path.abspath(__file__)); IMAGE_MODEL_LOADED = False; TEXT_MODEL_LOADED = False
if current_dir not in sys.path: sys.path.append(current_dir)
try:
    from app import app, db, ProcessingTask
    from detection_logic import run_ai_image_detection, format_error_result as format_image_error, format_success_result as format_image_success, IMAGE_MODEL_LOADED
    from text_detection_logic import run_ai_text_detection, format_error_result as format_text_error, format_success_result as format_text_success, TEXT_MODEL_LOADED
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - WORKER - %(message)s')
    log = logging.getLogger(__name__); log.info("Worker: Nạp xong app và logic.")
except Exception as import_err: print(f"WORKER CRITICAL IMPORT ERROR: {import_err}\n{traceback.format_exc()}", file=sys.stderr); sys.exit(1)

POLL_INTERVAL = 5
shutdown_requested = False
def handle_shutdown_signal(signum, frame): global shutdown_requested; log.warning(f"Nhận tín hiệu dừng ({signal.Signals(signum).name}). Thoát..."); shutdown_requested = True
signal.signal(signal.SIGINT, handle_shutdown_signal); signal.signal(signal.SIGTERM, handle_shutdown_signal)

def process_one_task():
    log.debug("Worker: Kiểm tra task..."); task = None; processed_task_flag = False
    try:
        with app.app_context():
            task = db.session.query(ProcessingTask).filter_by(status='PENDING').order_by(ProcessingTask.created_at).with_for_update(skip_locked=True).first()
            if task:
                processed_task_flag = True; log.info(f"Worker: Tìm thấy task {task.id} ({task.task_type})..."); task.status = 'PROCESSING'; task.updated_at = datetime.datetime.now(datetime.UTC); db.session.commit()
                identifier = task.original_filename or f"Đoạn text ({task.id})"; detection_result_json = None
                try:
                    if task.task_type == 'image':
                        if not IMAGE_MODEL_LOADED: raise RuntimeError("Model ảnh chưa nạp."); file_path = task.filepath
                        if not file_path or not os.path.exists(file_path): raise FileNotFoundError(f"Không tìm thấy file ảnh: {file_path}")
                        detection_result = run_ai_image_detection(file_path); detection_result_json = format_image_success(detection_result, identifier)
                    elif task.task_type == 'text':
                        if not TEXT_MODEL_LOADED: raise RuntimeError("Model text chưa nạp.")
                        if not task.input_text: raise ValueError("Task thiếu input text.")
                        detection_result = run_ai_text_detection(task.input_text); detection_result_json = format_text_success(detection_result, identifier)
                    else: raise ValueError(f"Loại task không rõ: {task.task_type}")
                    task.status = 'SUCCESS'; log.info(f"Worker: Task {task.id} ({task.task_type}) thành công.")
                except Exception as e:
                    log.error(f"Worker: Lỗi xử lý task {task.id} ({task.task_type}) '{identifier}': {e}", exc_info=True); task.status = 'FAILURE'
                    if task.task_type == 'image': detection_result_json = format_image_error(e, identifier)
                    elif task.task_type == 'text': detection_result_json = format_text_error(e, identifier)
                    else: detection_result_json = json.dumps({'status':'error', 'error_type':type(e).__name__, 'error_message':str(e)})
                finally:
                    if task:
                        task.result_json = detection_result_json; task.updated_at = datetime.datetime.now(datetime.UTC)
                        try: db.session.commit(); log.info(f"Worker: Task {task.id} status '{task.status}' committed.")
                        except Exception as commit_err: log.error(f"WORKER LỖI COMMIT task {task.id}: {commit_err}", exc_info=True); db.session.rollback(); processed_task_flag = False
                        if task.task_type == 'image' and task.filepath and os.path.exists(task.filepath):
                             try: os.remove(task.filepath); log.debug(f"Dọn file: {task.filepath}")
                             except OSError as rm_err: log.error(f"Lỗi dọn file {task.filepath}: {rm_err}")
            else: processed_task_flag = False # No task found
    except Exception as outer_exc:
         log.critical(f"WORKER LỖI NGOÀI DỰ KIẾN khi query task: {outer_exc}", exc_info=True)
         try:
             with app.app_context(): db.session.rollback()
         except Exception: pass
         time.sleep(30); processed_task_flag = False
    return processed_task_flag

if __name__ == "__main__":
    log.info("WORKER: Bắt đầu chạy liên tục (Always-on)...")
    if not IMAGE_MODEL_LOADED and not TEXT_MODEL_LOADED: log.critical("Không model nào nạp được. Worker dừng."); sys.exit(1)
    elif not IMAGE_MODEL_LOADED: log.warning("Model ảnh chưa nạp. Bỏ qua task ảnh.")
    elif not TEXT_MODEL_LOADED: log.warning("Model text chưa nạp. Bỏ qua task text.")
    else: log.info("Model sẵn sàng. Bắt đầu vòng lặp.")
    while not shutdown_requested:
        task_processed = False
        try: task_processed = process_one_task()
        except Exception as loop_exc: log.critical(f"LỖI VÒNG LẶP CHÍNH: {loop_exc}", exc_info=True); time.sleep(60)
        if not task_processed and not shutdown_requested:
            try:
                log.debug(f"Idle. Nghỉ {POLL_INTERVAL} giây...");
                for _ in range(POLL_INTERVAL):
                    if shutdown_requested: break; time.sleep(1)
            except KeyboardInterrupt: handle_shutdown_signal(signal.SIGINT, None)
    log.info("WORKER: Nhận tín hiệu dừng. Kết thúc."); sys.exit(0)
