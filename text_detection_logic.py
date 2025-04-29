# text_detection_logic.py
import time, os, json, logging, sys, traceback

log_format = '%(asctime)s - %(levelname)s - TXT_DL_Local - %(message)s'; logging.basicConfig(level=logging.INFO, format=log_format); log = logging.getLogger(__name__)
TEXT_MODEL_NAME = "Hello-SimpleAI/chatgpt-detector-roberta"
TEXT_MODEL_LOADED = False; text_detector_pipeline = None
try:
    log.info(f"Nạp pipeline text: {TEXT_MODEL_NAME}...")
    from transformers import pipeline as hf_pipeline
    text_detector_pipeline = hf_pipeline("text-classification", model=TEXT_MODEL_NAME)
    if text_detector_pipeline: TEXT_MODEL_LOADED = True; log.info(f"Nạp xong model text: {TEXT_MODEL_NAME}.")
    else: log.error(f"Pipeline text trả về None cho {TEXT_MODEL_NAME}!")
except ImportError as e: log.error(f"LỖI IMPORT NGHIÊM TRỌNG: Thiếu transformers/torch/tf: {e}", exc_info=True)
except Exception as e: log.error(f"LỖI NGHIÊM TRỌNG NẠP MODEL TEXT '{TEXT_MODEL_NAME}': {e}", exc_info=True)

UNCERTAINTY_THRESHOLD = 0.60

def run_ai_text_detection(input_text):
    if not TEXT_MODEL_LOADED or text_detector_pipeline is None: raise RuntimeError(f"Model text '{TEXT_MODEL_NAME}' chưa sẵn sàng.")
    log.info(f"Phân tích cục bộ text (50 chars): {input_text[:50]}... dùng model {TEXT_MODEL_NAME}")
    if not input_text or not isinstance(input_text, str): raise ValueError("Nội dung văn bản không hợp lệ.")
    start_time = time.time(); final_result = None
    try:
        log.info(f"Chạy pipeline phân loại text...")
        results = text_detector_pipeline(input_text); log.info(f"Kết quả pipeline thô: {results}")
        if not isinstance(results, list) or not results or not isinstance(results[0], dict): raise ValueError("Sai định dạng kết quả pipeline text.")
        top_result = results[0]; label = top_result.get('label', 'Unknown').upper(); top_score = top_result.get('score', 0.0)
        raw_top_label = "AI/ChatGPT (LABEL_1)" if label == 'LABEL_1' else ("Human (LABEL_0)" if label == 'LABEL_0' else label)
        if top_score < UNCERTAINTY_THRESHOLD: final_classification = "Không chắc chắn"; is_ai = False; message = f"Model không chắc chắn (Điểm: {top_score*100:.2f}% cho '{raw_top_label}')."
        elif label == 'LABEL_1': final_classification = "AI tạo"; is_ai = True; message = f"Phân loại: '{final_classification}' ({top_score*100:.2f}%)."
        else: final_classification = "Người viết"; is_ai = False; message = f"Phân loại: '{final_classification}' ({top_score*100:.2f}%)."
        confidence = round(top_score, 4); processing_time = time.time() - start_time
        final_result = {'is_ai_generated': is_ai, 'confidence': confidence, 'classification': final_classification, 'raw_classification': raw_top_label, 'processing_time_seconds': round(processing_time, 2), 'message': message, 'local_model_used': TEXT_MODEL_NAME}
        log.info(f"Kết quả phân tích text đã định dạng: {final_result}"); return final_result
    except ValueError as ve: log.error(f"Lỗi giá trị/đầu vào text: {ve}", exc_info=True); raise ve
    except RuntimeError as rt_err: log.error(f"Lỗi runtime text: {rt_err}", exc_info=True); raise rt_err
    except Exception as e: log.error(f"Lỗi bất ngờ (text): {e}", exc_info=True); raise RuntimeError(f"Lỗi bất ngờ: {e}") from e

def format_error_result(e, input_identifier="đoạn text"):
    error_data = { 'status': 'error', 'input_identifier': input_identifier or "đoạn text", 'error_type': type(e).__name__, 'error_message': str(e) }
    try: return json.dumps(error_data)
    except TypeError: return json.dumps({'status': 'error', 'error_type': type(e).__name__, 'error_message': repr(e)})

def format_success_result(detection_result, input_identifier="đoạn text"):
    success_data = { 'status': 'success', 'input_identifier': input_identifier or "đoạn text", 'detection': detection_result }
    try: return json.dumps(success_data)
    except TypeError: return json.dumps({'status': 'success', 'input_identifier': input_identifier or "đoạn text", 'error': 'Lỗi định dạng kết quả thành công.'})
