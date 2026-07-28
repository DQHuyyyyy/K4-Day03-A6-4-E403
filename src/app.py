"""
🚀 CORE AGENT APP (Dành cho Role 4: Core Agent Developer)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.
"""

import json
import os
import re
import sys
import unicodedata
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
from tools import AVAILABLE_TOOLS, reset_state
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
        # Mỗi case xuất phát từ cùng một trạng thái lịch phỏng vấn:
        # book_interview là hành động GHI, nếu không reset thì case sau sẽ thấy
        # lịch đã bị case trước chiếm mất.
        reset_state()

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


# =====================================================================
# 🧠 MỐC 3 — REACT AGENT LOOP (PARSER ➔ EXECUTOR ➔ LOOP ➔ GUARDRAILS)
# =====================================================================
# 4 nguyên tắc bất biến (CODELAB mục 4):
#   1. Không lặp vô hạn        ➔ phanh MAX_ITERATIONS
#   2. Mỗi Action ➔ đúng 1 Observation do APP chèn, LLM không được tự bịa
#   3. Observation quay lại prompt làm ngữ cảnh cho Thought kế tiếp
#   4. Không khẳng định khi thiếu bằng chứng ➔ phải có Observation mới Final Answer
# =====================================================================

# Action: tên_tool[tham_số_1, tham_số_2]
ACTION_PATTERN = re.compile(r"Action\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[(.*?)\]", re.DOTALL)
FINAL_PATTERN = re.compile(r"Final\s+Answer\s*:\s*(.+)", re.DOTALL)
THOUGHT_PATTERN = re.compile(
    r"Thought\s*:\s*(.+?)(?=\n\s*(?:Action|Final\s+Answer)\s*:|$)", re.DOTALL
)

# Guardrail G4 của Role 3 bắt Agent DỪNG bằng Final Answer để xin phép trước khi
# gọi book_interview. Nhận diện lời xin phép đó để mô phỏng lượt trả lời của người dùng.
# Khớp trên bản đã bỏ dấu để không phụ thuộc việc LLM có gõ dấu tiếng Việt hay không.
CONFIRM_REQUEST_PATTERN = re.compile(
    r"xac nhan|dong y|cho phep|ban co muon|tien hanh dat|co dat lich", re.IGNORECASE
)
USER_CONFIRMATION = "User: Tôi xác nhận, hãy tiến hành đặt lịch."


def strip_accents(text: str) -> str:
    """
    Bỏ dấu tiếng Việt để so khớp từ khoá không phụ thuộc dấu.

    Lưu ý: 'đ'/'Đ' (U+0111/U+0110) KHÔNG tách được bằng NFD nên phải thay tay,
    nếu không 'đồng ý' sẽ ra 'đong y' và mọi so khớp với 'dong y' đều trượt.
    """
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text)
        if unicodedata.category(ch) != "Mn"
    )


def strip_fake_observation(raw: str) -> str:
    """
    Cắt bỏ mọi thứ từ chỗ LLM tự sinh dòng 'Observation:' trở đi.

    Nguyên tắc bất biến số 2: Observation là kết quả THẬT do application chèn vào
    sau khi thực thi tool. Nếu để LLM tự bịa Observation thì toàn bộ grounding sụp đổ
    — đây là lỗi CODELAB liệt kê trong danh sách commonErrors.
    """
    match = re.search(r"\n\s*Observation\s*:", raw)
    return raw[:match.start()] if match else raw


def parse_llm_output(raw: str) -> dict:
    """Tách Thought / Action / Final Answer từ output thô của LLM."""
    text = strip_fake_observation(raw)

    thought_match = THOUGHT_PATTERN.search(text)
    action_match = ACTION_PATTERN.search(text)
    final_match = FINAL_PATTERN.search(text)

    # Nếu có cả Action lẫn Final Answer, cái nào xuất hiện TRƯỚC thì thắng
    is_final = final_match is not None and (
        action_match is None or final_match.start() < action_match.start()
    )

    args = []
    if action_match and not is_final:
        raw_args = action_match.group(2).strip()
        if raw_args:
            # Bỏ nháy đơn/nháy kép/backtick mà LLM hay bọc quanh tham số
            args = [a.strip().strip("'\"`") for a in raw_args.split(",")]

    return {
        "thought": thought_match.group(1).strip() if thought_match else "",
        "tool_name": action_match.group(1) if (action_match and not is_final) else None,
        "args": args,
        "final_answer": final_match.group(1).strip() if is_final else None,
        "clean_text": text.strip(),
    }


def execute_tool(tool_name: str, args: list) -> str:
    """
    Thực thi tool và trả về Observation THẬT.

    Mọi nhánh hỏng đều trả chuỗi 'LỖI: ...' để Agent đọc và tự phục hồi (Agent V2),
    thay vì để exception làm chết cả vòng lặp.
    """
    tool_fn = AVAILABLE_TOOLS.get(tool_name)

    # Recovery 1 — Unknown Tool: nói rõ tool nào hợp lệ để Agent chọn lại
    if tool_fn is None:
        return (
            f"LỖI: Tool '{tool_name}' không tồn tại. "
            f"Các tool hợp lệ gồm: {', '.join(AVAILABLE_TOOLS.keys())}."
        )

    # Recovery 2 — Malformed Args: gợi ý lại đúng cú pháp thay vì crash
    try:
        return tool_fn(*args)
    except TypeError as exc:
        return (
            f"LỖI: Sai số lượng tham số khi gọi '{tool_name}' "
            f"(nhận {len(args)} tham số). Chi tiết: {exc}"
        )
    except Exception as exc:  # lưới an toàn cuối cùng, không để vòng lặp chết
        return f"LỖI: Tool '{tool_name}' gặp sự cố ngoài dự kiến: {exc}"


def run_react_agent(user_query: str, provider, auto_confirm: bool = False) -> dict:
    """
    Vòng lặp ReAct Agent: Thought -> Action -> Observation, có Guardrails.

    auto_confirm: Guardrail G4 bắt Agent dừng lại xin phép người dùng trước khi gọi
        ``book_interview``. Bộ chạy test là phi tương tác nên không có ai trả lời,
        Agent sẽ đứng mãi ở lời xin phép và đường ghi dữ liệu không bao giờ được
        chứng minh. Khi bật cờ này, application tự đóng vai người dùng đáp "Tôi xác
        nhận" đúng MỘT lần — trace log nhờ đó thể hiện được cả hai: G4 chặn đúng lúc,
        và thao tác ghi hoàn tất sau khi đã được cho phép.

        Cờ này do TỪNG test case tự khai báo (trường ``auto_confirm`` trong
        config/test_cases.json), KHÔNG bật mặc định. Lý do: ở câu bẫy #5 Agent từ chối
        đúng và câu từ chối đó cũng chứa chữ "bạn có muốn...", nếu tự động đồng ý thì
        application sẽ ép Agent thử đặt lịch tiếp cho một ứng viên không tồn tại —
        biến một lần từ chối chuẩn thành 3 bước thừa.

    Trả về dict gồm trace log đầy đủ để Role 5 dán vào docs/trace_eval.md.
    """
    reset_state()   # mỗi câu hỏi xuất phát từ cùng một trạng thái lịch phỏng vấn

    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")

    history = []          # chuỗi Thought/Action/Observation nối lại làm ngữ cảnh
    trace = []            # bản ghi từng bước cho báo cáo
    seen_actions = set()  # phát hiện Agent gọi lặp lại y hệt một Action
    tool_calls = 0
    final_answer = None
    stopped_by_guardrail = False
    confirmation_given = False

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")

        # Nguyên tắc 3: toàn bộ Observation trước đó quay lại prompt
        prompt = f"Question: {user_query}\n"
        if history:
            prompt += "\n".join(history) + "\n"

        raw = provider.generate(prompt, system_prompt=REACT_SYSTEM_PROMPT)
        parsed = parse_llm_output(raw)

        if parsed["thought"]:
            print(f"🧠 Thought: {parsed['thought']}")

        # --- Nhánh 1: Agent chốt câu trả lời cuối cùng ---
        if parsed["final_answer"] is not None:
            # G4 — Agent đã xem lịch trống, chưa đặt, và đang xin phép người dùng.
            # Điều kiện chặt để không kích hoạt nhầm ở các case chỉ hỏi lý thuyết.
            checked_slots = any(
                e["action"] and e["action"].startswith("check_interview_slots")
                for e in trace
            )
            already_booked = any(
                e["action"] and e["action"].startswith("book_interview")
                and e["observation"] and not e["observation"].startswith("LỖI:")
                for e in trace
            )
            asking_permission = bool(
                CONFIRM_REQUEST_PATTERN.search(strip_accents(parsed["final_answer"]))
            )

            if (auto_confirm and not confirmation_given and checked_slots
                    and not already_booked and asking_permission):
                confirmation_given = True
                print(f"🏁 Final Answer (xin xác nhận): {parsed['final_answer']}")
                print(f"🔐 [MÔ PHỎNG NGƯỜI DÙNG] {USER_CONFIRMATION}")

                history.append(f"Thought: {parsed['thought']}")
                history.append(f"Final Answer: {parsed['final_answer']}")
                history.append(USER_CONFIRMATION)

                trace.append({
                    "step": step,
                    "thought": parsed["thought"],
                    "action": None,
                    "observation": None,
                    "final_answer": None,
                    "pending_final": parsed["final_answer"],   # lời xin phép theo G4
                })
                continue   # sang lượt sau, giờ Agent đã được phép gọi book_interview

            final_answer = parsed["final_answer"]
            print(f"🏁 Final Answer: {final_answer}")
            trace.append({
                "step": step,
                "thought": parsed["thought"],
                "action": None,
                "observation": None,
                "final_answer": final_answer,
            })
            break

        # --- Nhánh 2: Agent gọi tool ---
        if parsed["tool_name"] is None:
            # Recovery 3 — Parse Error: dạy lại cú pháp đúng cho bước sau
            action_label = None
            observation = (
                "LỖI: Không đọc được Action. Hãy dùng đúng định dạng: "
                "Action: tên_tool[tham_số_1, tham_số_2]"
            )
            print(f"⚠️ Không parse được Action từ output của LLM.")
        else:
            action_label = f"{parsed['tool_name']}[{', '.join(parsed['args'])}]"
            print(f"🛠️ Action: {action_label}")

            signature = (parsed["tool_name"], tuple(parsed["args"]))
            if signature in seen_actions:
                # Recovery 4 — Repeated Action: Agent không tự biết mình đang kẹt lặp
                observation = (
                    f"LỖI: Bạn đã gọi '{action_label}' ở bước trước và đã nhận kết quả. "
                    "Đừng lặp lại, hãy dùng tool khác hoặc trả Final Answer."
                )
                print("🔁 Phát hiện Action lặp lại — chèn cảnh báo thay vì gọi tool.")
            else:
                seen_actions.add(signature)

                # Cảnh báo rõ với hành động GHI không đảo ngược được
                if parsed["tool_name"] == "book_interview":
                    print(f"🔐 [HÀNH ĐỘNG GHI] {action_label} — không đảo ngược được.")

                observation = execute_tool(parsed["tool_name"], parsed["args"])
                tool_calls += 1

        print(f"👁️ Observation: {observation}")

        # Nguyên tắc 2: chính application chèn Observation vào lịch sử
        history.append(f"Thought: {parsed['thought']}")
        if action_label:
            history.append(f"Action: {action_label}")
        history.append(f"Observation: {observation}")

        trace.append({
            "step": step,
            "thought": parsed["thought"],
            "action": action_label,
            "observation": observation,
            "final_answer": None,
            "pending_final": None,
        })

    # --- Guardrail: hết ngân sách vòng lặp mà chưa có Final Answer ---
    if final_answer is None:
        stopped_by_guardrail = True
        final_answer = (
            f"Xin lỗi, tôi đã thử {MAX_ITERATIONS} bước nhưng chưa hoàn tất được yêu cầu này. "
            "Tôi dừng lại để tránh lặp vô hạn và KHÔNG thực hiện thao tác nào chưa chắc chắn. "
            "Bạn vui lòng kiểm tra lại mã ứng viên/khung giờ, hoặc thử một ngày khác."
        )
        print(f"\n🛡️ GUARDRAIL TRIGGERED: Đã đạt giới hạn {MAX_ITERATIONS} bước. Ngắt lặp an toàn!")
        print(f"🏁 Safe Fallback: {final_answer}")

    return {
        "final_answer": final_answer,
        "trace": trace,
        "tool_calls": tool_calls,
        "steps": len(trace),
        "stopped_by_guardrail": stopped_by_guardrail,
    }


def run_react_suite(tests, provider):
    """Chạy ReAct Agent trên toàn bộ test cases và thu trace log cho Role 5."""
    results = []

    for tc in tests:
        print(f"\n{'=' * 60}")
        print(f"🧠 [REACT AGENT] Case #{tc['id']} — {tc['category']}")
        print(f"🎯 Kỳ vọng : {tc['expected_behavior'][:120]}...")
        print("-" * 60)

        # Chỉ case nào tự khai báo mới được mô phỏng người dùng bấm xác nhận
        outcome = run_react_agent(
            tc["question"], provider, auto_confirm=tc.get("auto_confirm", False)
        )
        outcome.update({
            "id": tc["id"],
            "category": tc["category"],
            "question": tc["question"],
        })
        results.append(outcome)

    return results


def export_react_markdown(results):
    """In khối Markdown trace log để Role 5 dán vào docs/trace_eval.md (mục 3)."""
    print(f"\n\n{'=' * 60}")
    print("📋 KHỐI MARKDOWN — TRACE LOG REACT AGENT")
    print(f"{'=' * 60}\n")

    for r in results:
        print(f"### Case #{r['id']} — {r['category']}")
        print(f"**Câu hỏi**: *\"{r['question']}\"*\n")
        print("```text")
        for entry in r["trace"]:
            if entry["thought"]:
                print(f"Thought {entry['step']}: {entry['thought']}")
            if entry["action"]:
                print(f"Action {entry['step']}: {entry['action']}")
            if entry["observation"]:
                print(f"Observation {entry['step']}: {entry['observation']}")
            if entry.get("pending_final"):
                # Guardrail G4 chặn lại xin phép, rồi người dùng đồng ý
                print(f"Final Answer {entry['step']} (G4 - xin xác nhận): {entry['pending_final']}")
                print(USER_CONFIRMATION)
            print()
        print(f"Final Answer: {r['final_answer']}")
        print("```\n")
        print(f"* **Số bước**: `{r['steps']}/{MAX_ITERATIONS}` · "
              f"**Số lần gọi tool**: `{r['tool_calls']}` · "
              f"**Guardrail ngắt**: `{'CÓ' if r['stopped_by_guardrail'] else 'KHÔNG'}`")
        print("* **Nhận xét**: ________\n")


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

    # Cảnh báo cấu hình Guardrail: luồng dài nhất (case #4) cần 4 bước
    if MAX_ITERATIONS < 4:
        print(f"⚠️ CẢNH BÁO: MAX_ITERATIONS = {MAX_ITERATIONS} là quá thấp. "
              f"Case multi-step cần tối thiểu 4 bước ➔ Role 3 đặt lại thành 6 "
              f"(xem docs/INTERFACE_CONTRACT.md).")

    # --- MỐC 2: Chạy Chatbot Baseline trên toàn bộ bộ đề ---
    print("\n--- DEMO 1: CHATBOT BASELINE (1 LLM call mỗi câu, 0 lần gọi tool) ---")
    baseline_results = run_baseline_suite(tests, provider)

    # --- MỐC 3: Chạy ReAct Agent trên cùng bộ đề để so sánh công bằng ---
    print(f"\n\n--- DEMO 2: REACT AGENT (Thought -> Action -> Observation) ---")
    react_results = run_react_suite(tests, provider)

    export_baseline_markdown(baseline_results)
    export_react_markdown(react_results)

    # --- Bảng so sánh nhanh Chatbot vs Agent ---
    print(f"\n{'=' * 60}")
    print("📊 SO SÁNH NHANH: BASELINE vs REACT AGENT")
    print(f"{'=' * 60}")
    print(f"{'Case':<6}{'Baseline tool_calls':<22}{'Agent tool_calls':<20}{'Agent steps':<14}{'Guardrail'}")
    for base, react in zip(baseline_results, react_results):
        print(f"#{base['id']:<5}{base['tool_calls']:<22}{react['tool_calls']:<20}"
              f"{str(react['steps']) + '/' + str(MAX_ITERATIONS):<14}"
              f"{'CÓ' if react['stopped_by_guardrail'] else '-'}")
