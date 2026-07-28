"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.
"""

def score_candidate(candidate_id: str, job_id: str) -> str:
    """Chấm độ khớp giữa CV ứng viên và mô tả công việc, trả về điểm 0-100.
    Args: candidate_id (str): Mã ứng viên, VD 'CAND-001'
          job_id (str): Mã vị trí tuyển dụng, VD 'JD-001'
    Returns: str: Điểm khớp kèm giải thích các kỹ năng đạt/thiếu
    """
    return "TODO"


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    "score_candidate": score_candidate
}
