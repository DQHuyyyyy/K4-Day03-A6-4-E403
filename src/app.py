"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.
"""

import json
import os
import sys
from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import các thành phần từ file của Role 2, Role 3 & Multi-Provider Adapter
# Chỉ import AVAILABLE_TOOLS: app.py tra tool qua registry, không phụ thuộc tên hàm cụ thể
# ➔ Duy thêm/đổi tool trong tools.py cũng không làm app.py gãy import nữa.
from tools import AVAILABLE_TOOLS
from prompts import CHATBOT_BASELINE_PROMPT, REACT_SYSTEM_PROMPT, MAX_ITERATIONS
from providers import get_llm_provider

load_dotenv()

def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")

    # Fallback kiểm tra nếu file ở thư mục hiện tại
    if not os.path.exists(config_path):
        config_path = "test_cases.json"

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_baseline_chatbot(user_query: str, provider) -> str:
    """
    Dựng Chatbot gốc (Baseline) không có công cụ.

    ⚠️ RÀNG BUỘC CHẤM ĐIỂM (CODELAB mục 2): Baseline phải dùng ĐÚNG 1 LLM call và
    số lần gọi tool = 0. Không nhúng sẵn kết quả tool vào system prompt, không
    khẳng định hành động đã hoàn tất.
    """
    # Đúng một lần gọi LLM duy nhất, không hề đụng tới AVAILABLE_TOOLS
    return provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)


def run_baseline_suite(tests, provider):
    """Chạy Chatbot Baseline trên TOÀN BỘ test cases và thu kết quả cho Role 5 làm báo cáo."""
    results = []

    for tc in tests:
        print(f"\n{'=' * 60}")
        print(f"💬 [BASELINE] Case #{tc['id']} — {tc['category']}")
        print(f"❓ Câu hỏi : {tc['question']}")
        print(f"🎯 Kỳ vọng : {tc['expected_behavior']}")
        print("-" * 60)

        response = run_baseline_chatbot(tc["question"], provider)

        # Cảnh báo sớm nếu Provider trả về lỗi cấu hình thay vì câu trả lời thật
        if response.startswith("[") and "Error" in response.split("]")[0]:
            print(f"⚠️ LỖI PROVIDER: {response}")
        else:
            print(f"🤖 Chatbot trả lời:\n{response}")

        results.append({
            "id": tc["id"],
            "category": tc["category"],
            "question": tc["question"],
            "response": response,
            "tool_calls": 0,   # Baseline không có quyền gọi tool ➔ luôn bằng 0
        })

    return results


def export_baseline_markdown(results):
    """In ra khối Markdown để Role 5 dán thẳng vào mục 2 của docs/trace_eval.md."""
    print(f"\n\n{'=' * 60}")
    print("📋 KHỐI MARKDOWN — DÁN VÀO docs/trace_eval.md (MỤC 2)")
    print(f"{'=' * 60}\n")

    total_tool_calls = sum(r["tool_calls"] for r in results)
    print(f"> Provider: `{os.getenv('LLM_PROVIDER', 'mock')}` · "
          f"Tổng số lần Baseline gọi tool: **{total_tool_calls}** "
          f"(checkpoint yêu cầu phải bằng 0)\n")

    for r in results:
        print(f"### Case #{r['id']} — {r['category']}")
        print(f"* **Câu hỏi**: *\"{r['question']}\"*")
        print(f"* **Phản hồi Baseline**: {r['response'].strip()}")
        print(f"* **Số lần gọi tool**: `{r['tool_calls']}`")
        print("* **Phân loại**: `correct` / `safe fallback` / `hallucinated` ➔ ________")
        print("* **Nhận xét**: ________\n")


def run_react_agent(user_query: str, provider):
    """
    Vòng lặp ReAct Agent (Thought -> Action -> Observation) có Guardrails.

    🚧 CHƯA TRIỂN KHAI — thuộc phạm vi MỐC 3.
    Cố ý để trống thay vì in kịch bản dựng sẵn: CODELAB liệt kê "để model tự bịa
    Observation thay vì application chèn kết quả tool thực tế" vào danh sách lỗi bị trừ điểm.
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    print(f"🚧 Vòng lặp ReAct sẽ được lắp ở Mốc 3 "
          f"({len(AVAILABLE_TOOLS)} tool đã đăng ký, MAX_ITERATIONS = {MAX_ITERATIONS}).")


if __name__ == "__main__":
    print("==================================================")
    print("🏫 ĐẠI HỌC VINUNI - BÀI LAB 3: CHATBOT VS REACT AGENT")
    print("==================================================")

    # Khởi tạo Multi-Provider LLM Adapter (Đọc từ biến môi trường LLM_PROVIDER)
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json")
    print(f"🛠️ Tool đã đăng ký trong AVAILABLE_TOOLS: {list(AVAILABLE_TOOLS.keys())}")

    # --- MỐC 2: Chạy Chatbot Baseline trên toàn bộ bộ đề ---
    print("\n--- DEMO 1: CHATBOT BASELINE (1 LLM call mỗi câu, 0 lần gọi tool) ---")
    results = run_baseline_suite(tests, provider)
    export_baseline_markdown(results)
