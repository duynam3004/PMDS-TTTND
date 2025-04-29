# detection_logic.py
import time, os, json, logging, sys, traceback
from PIL import Image, UnidentifiedImageError

log_format = '%(asctime)s - %(levelname)s - IMG_DL_Local - %(message)s'; logging.basicConfig(level=logging.INFO, format=log_format); log = logging.getLogger(__name__)
MODEL_NAME = "umm-maybe/AI-image-detector"
IMAGE_MODEL_LOADED = False; image_detector_pipeline = None
try:
    log.info(f"Nạp pipeline ảnh: {MODEL_NAME}...")
    from transformers import pipeline as hf_pipeline
    image_detector_pipeline = hf_pipeline("image-classification", model=MODEL_NAME)
    if image_detector_pipeline: IMAGE_MODEL_LOADED = True; log.info(f"Nạp xong model ảnh: {MODEL_NAME}.")
    else: log.error(f"Pipeline ảnh trả về None cho {MODEL_NAME}!")
except ImportError as e: log.error(f"LỖI IMPORT NGHIÊM TRỌNG: Thiếu transformers/torch/tf: {e}", exc_info=True)
except Exception as e: log.error(f"LỖI NGHIÊM TRỌNG NẠP MODEL ẢNH '{MODEL_NAME}': {e}", exc_info=True)

CONFIDENT_AI_THRESHOLD = 0.90; CONFIDENT_HUMAN_THRESHOLD = 0.90

def run_ai_image_detection(filepath):
    if not IMAGE_MODEL_LOADED or image_detector_pipeline is None: raise RuntimeError(f"Model ảnh '{MODEL_NAME}' chưa sẵn sàng.")
    log.info(f"Phân tích cục bộ ảnh: {filepath} dùng model {MODEL_NAME}")
    if not isinstance(filepath, str) or not os.path.exists(filepath): raise FileNotFoundError(f"File không hợp lệ: {filepath}")
    start_time = time.time(); final_result = None
    try:
        try:
            with Image.open(filepath) as img: img.verify(); log.debug(f"Ảnh hợp lệ: {filepath}")
        except Exception as img_err: log.error(f"Lỗi ảnh {filepath}: {img_err}", exc_info=True); raise ValueError(f"File ảnh lỗi: {img_err}") from img_err
        log.info(f"Chạy pipeline ảnh cho: {filepath}...")
        results = image_detector_pipeline(filepath); log.info(f"Kết quả pipeline thô: {results}")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict): raise ValueError("Sai định dạng kết quả pipeline ảnh.")
        scores_by_label = {item.get('label', '').upper(): item.get('score', 0.0) for item in results}
        ai_score = scores_by_label.get('AI', scores_by_label.get('ARTIFICIAL', 0.0)); human_score = scores_by_label.get('HUMAN', 0.0)
        final_classification = "Không chắc chắn"; top_label = "Unknown"; top_score = 0.0
        if ai_score >= human_score: top_label = "AI" if 'AI' in scores_by_label else "Artificial"; top_score = ai_score;
        else: top_label = "Human"; top_score = human_score;
        if top_label == "AI" and ai_score > CONFIDENT_AI_THRESHOLD: final_classification = "AI"
        elif top_label == "Human" and human_score > CONFIDENT_HUMAN_THRESHOLD: final_classification = "Người"
        is_ai = (final_classification == "AI"); confidence_percent = top_score * 100
        if final_classification == "Không chắc chắn": message = f"Model không chắc chắn. Nhãn chính: '{top_label}' ({confidence_percent:.2f}%)."
        else: message = f"Phân loại: '{final_classification}' ({confidence_percent:.2f}%)."
        processing_time = time.time() - start_time
        final_result = {'is_ai_generated': is_ai, 'confidence': round(top_score, 4), 'classification': final_classification, 'raw_classification': top_label, 'all_scores': scores_by_label, 'processing_time_seconds': round(processing_time, 2), 'message': message, 'local_model_used': MODEL_NAME}
        log.info(f"Kết quả ảnh đã định dạng: {final_result}"); return final_result
    except FileNotFoundError as fnf_err: log.error(f"Lỗi file: {fnf_err}", exc_info=True); raise fnf_err
    except ValueError as ve: log.error(f"Lỗi giá trị/ảnh: {ve}", exc_info=True); raise ve
    except RuntimeError as rt_err: log.error(f"Lỗi runtime: {rt_err}", exc_info=True); raise rt_err
    except Exception as e: log.error(f"Lỗi bất ngờ (ảnh): {e}", exc_info=True); raise RuntimeError(f"Lỗi bất ngờ: {e}") from e

def format_error_result(e, input_identifier="N/A"):
    error_data = { 'status': 'error', 'input_identifier': input_identifier or "N/A", 'error_type': type(e).__name__, 'error_message': str(e) }
    try: return json.dumps(error_data)
    except TypeError: return json.dumps({'status': 'error', 'error_type': type(e).__name__, 'error_message': repr(e)})

def format_success_result(detection_result, input_identifier="N/A"):
    success_data = { 'status': 'success', 'input_identifier': input_identifier or "N/A", 'detection': detection_result }
    try: return json.dumps(success_data)
    except TypeError: return json.dumps({'status': 'success', 'input_identifier': input_identifier or "N/A", 'error': 'Lỗi định dạng kết quả.'})
