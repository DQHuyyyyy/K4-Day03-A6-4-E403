"""
🚀 CẤP ĐỘ 4: AUTONOMOUS AGENT (BONUS +10%)
Tự chia nhỏ mục tiêu (Planning) ➔ Thực thi ➔ Ghi nhớ (Memory) ➔ Tự đánh giá (Reflection).

KHÁC BIỆT SO VỚI REACT AGENT (CẤP 3):
    | Tiêu chí        | Cấp 3 — ReAct              | Cấp 4 — Autonomous              |
    | Đầu vào         | 1 câu hỏi                  | 1 MỤC TIÊU dài hạn              |
    | Kế hoạch        | Không có, ứng biến từng bước| Lập kế hoạch TRƯỚC khi hành động|
    | Bộ nhớ          | Chỉ trong 1 lượt hội thoại | Bền qua nhiều bước con          |
    | Điều kiện dừng  | MAX_ITERATIONS             | Tự đánh giá mục tiêu đã đạt chưa|
    | Phạm vi         | 1 đối tượng                | Nhiều đối tượng cùng lúc        |

Bài toán demo được chọn có chủ đích: *"xếp lịch cho MỌI ứng viên đạt chuẩn"* — với 4
ứng viên và 2 lần đặt lịch, ReAct Cấp 3 sẽ cháy hết MAX_ITERATIONS = 6 trước khi xong.
"""

import re
import sys

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass


PLANNER_PROMPT = """Bạn là Planner của hệ thống tuyển dụng tự động.

Nhiệm vụ: chia MỤC TIÊU của người dùng thành các BƯỚC CON độc lập, mỗi bước là một
chỉ thị ngắn gọn có thể giao cho một trợ lý thực thi bằng công cụ.

Các công cụ mà trợ lý thực thi có: search_candidates, get_candidate_profile,
score_candidate, check_interview_slots, book_interview.

QUY TẮC:
- Tối đa 3 bước, mỗi bước một dòng, đánh số "1." "2." "3.".
- Mỗi bước phải là một MỆNH LỆNH hành động cụ thể, không phải tên hàm trần trụi.
- ⚠️ search_candidates ĐÃ trả kèm điểm khớp của từng ứng viên. TUYỆT ĐỐI không tạo
  bước "chấm điểm cho tất cả ứng viên" — đó là gọi tool lặp thừa và sẽ cháy ngân sách.
- Bước 1 thu thập danh sách ứng viên. Bước 2 tra khung giờ trống.
  Bước 3 thực hiện đặt lịch cho những ứng viên đủ điều kiện.
- Không giải thích gì thêm, chỉ xuất danh sách bước.

MỤC TIÊU: """


REFLECTION_PROMPT = """Bạn là bộ phận Tự Đánh Giá của một Agent tự chủ.

Đọc MỤC TIÊU, TRẠNG THÁI THẬT và NHẬT KÝ BỘ NHỚ dưới đây, rồi trả lời DUY NHẤT một
trong hai dạng:

HOÀN THÀNH: <tóm tắt ngắn kết quả đã đạt được>
TIẾP TỤC: <việc cụ thể còn thiếu>

⚠️ QUY TẮC SỐNG CÒN: chỉ được kết luận HOÀN THÀNH khi TRẠNG THÁI THẬT xác nhận điều đó.
Trạng thái thật do hệ thống kiểm chứng, không phải lời kể trong nhật ký. Nếu mục tiêu
yêu cầu đặt lịch mà danh sách lịch đã đặt còn rỗng thì BẮT BUỘC trả lời TIẾP TỤC.

Không viết gì khác ngoài một dòng đó.
"""


def _parse_plan(raw: str) -> list:
    """Tách danh sách bước đánh số từ output của Planner."""
    steps = []
    for line in raw.splitlines():
        match = re.match(r"\s*(\d+)[.)]\s*(.+)", line.strip())
        if match:
            step = match.group(2).strip()
            if step:
                steps.append(step)
    return steps[:4]   # chốt trần 4 bước để không chạy lan man


def _memory_to_context(memory: dict) -> str:
    """Chuyển bộ nhớ thành đoạn ngữ cảnh nhét vào bước con kế tiếp."""
    if not memory["facts"]:
        return "(chưa có dữ liệu nào)"

    lines = []
    for i, fact in enumerate(memory["facts"], 1):
        lines.append(f"[Bước {i}] {fact['step']}")
        for obs in fact["observations"]:
            lines.append(f"   • Dữ liệu thật thu được: {obs}")
    if memory["booked"]:
        lines.append(f"⚠️ ĐÃ đặt lịch cho: {', '.join(memory['booked'])} — đừng đặt lại.")
    return "\n".join(lines)


def run_autonomous_agent(goal: str, provider, react_runner, booked_registry,
                         max_cycles: int = 4) -> dict:
    """
    Chạy Agent tự chủ theo chu trình Planning ➔ Execution ➔ Memory ➔ Reflection.

    Args:
        goal: Mục tiêu dài hạn của người dùng.
        provider: LLM provider.
        react_runner: Hàm ``run_react_agent`` của src/app.py — Cấp 4 tái sử dụng
            nguyên vẹn vòng lặp ReAct Cấp 3 làm "cánh tay" thực thi từng bước con.
        booked_registry: ``tools.BOOKED_INTERVIEWS`` — trạng thái THẬT của thế giới,
            dùng để đối chiếu với những gì Agent tưởng là mình đã làm.
        max_cycles: Trần số bước con, tránh Agent tự chủ chạy vô hạn.

    Returns:
        dict gồm plan, memory và nhật ký đánh giá — để Role 5 đưa vào báo cáo.
    """
    print("\n" + "=" * 60)
    print("🚀 [AUTONOMOUS AGENT — CẤP ĐỘ 4]")
    print(f"🎯 Mục tiêu: {goal}")
    print("=" * 60)

    memory = {
        "facts": [],        # kết quả từng bước con
        "done": [],         # các bước đã thực hiện
        "booked": [],       # ứng viên đã xếp lịch (theo trạng thái THẬT)
        "reflections": [],  # nhật ký tự đánh giá
    }

    # Mục tiêu có yêu cầu ghi dữ liệu không? Dùng để chốt chặn lời tự nhận hoàn thành.
    needs_booking = "đặt lịch" in goal.lower() or "xếp lịch" in goal.lower()

    # ---------- PHA 1: PLANNING (tự chia nhỏ mục tiêu) ----------
    print("\n📋 [PHA 1 — PLANNING] Agent tự lập kế hoạch...")
    raw_plan = provider.generate(goal, system_prompt=PLANNER_PROMPT)
    plan = _parse_plan(raw_plan)

    if not plan:
        # Kế hoạch dự phòng nếu Planner trả về định dạng lạ
        plan = [
            "Liệt kê toàn bộ ứng viên đang ứng tuyển JD-001 kèm điểm khớp",
            "Kiểm tra các khung giờ phỏng vấn còn trống ngày 2026-07-29",
            "Đặt lịch phỏng vấn cho ứng viên đạt từ 70 điểm trở lên",
        ]
        print("⚠️ Không parse được kế hoạch từ LLM — dùng kế hoạch dự phòng.")

    for i, step in enumerate(plan, 1):
        print(f"   {i}. {step}")

    # ---------- PHA 2: EXECUTION + MEMORY + REFLECTION ----------
    completed = False

    for cycle, step in enumerate(plan[:max_cycles], 1):
        print(f"\n{'─' * 60}")
        print(f"⚙️ [PHA 2 — CHU KỲ {cycle}/{min(len(plan), max_cycles)}] {step}")
        print(f"{'─' * 60}")

        # Nhét bộ nhớ vào bước con ➔ đây chính là thứ Cấp 3 không có.
        # Phải nói rõ "bộ nhớ chỉ để tham khảo": nếu không, trợ lý thực thi sẽ thấy
        # dữ liệu có sẵn rồi trả lời luôn từ bộ nhớ mà KHÔNG gọi tool nào cả.
        sub_query = (
            f"NHIỆM VỤ CỦA BƯỚC NÀY: {step}\n\n"
            f"Bạn PHẢI thực hiện nhiệm vụ trên bằng cách gọi tool. Dữ liệu trong bộ nhớ "
            f"dưới đây chỉ để tham khảo tránh tra lại, KHÔNG thay thế được cho hành động. "
            f"Nếu nhiệm vụ là đặt lịch, hãy gọi book_interview cho TỪNG ứng viên đủ điều "
            f"kiện, mỗi người một khung giờ khác nhau.\n\n"
            f"[BỘ NHỚ - dữ liệu các bước trước đã thu được]\n"
            f"{_memory_to_context(memory)}"
        )

        # Tái sử dụng nguyên vòng lặp ReAct Cấp 3, KHÔNG reset trạng thái
        # để lịch đã đặt ở chu kỳ trước vẫn còn hiệu lực.
        outcome = react_runner(sub_query, provider, auto_confirm=True, reset=False)

        memory["done"].append(step)
        # Ghi nhớ cả Observation THẬT chứ không chỉ câu tóm tắt của LLM — bộ nhớ phải
        # là bằng chứng từ tool, nếu chỉ lưu lời kể lại thì sai sót sẽ nhân lên qua các bước.
        observations = [
            e["observation"] for e in outcome["trace"]
            if e["observation"] and not e["observation"].startswith("LỖI:")
        ]
        memory["facts"].append({
            "step": step,
            "observations": observations,
            "summary": outcome["final_answer"],
            "trace": outcome["trace"],   # giữ nguyên trace để giao diện web vẽ lại
        })
        memory["booked"] = [b["candidate_id"] for b in booked_registry]

        print(f"\n💾 [MEMORY] Đã lưu {len(memory['facts'])} kết quả · "
              f"Ứng viên đã xếp lịch (trạng thái thật): "
              f"{memory['booked'] if memory['booked'] else 'chưa có'}")

        # ---------- PHA 3: REFLECTION (tự đánh giá tiến độ) ----------
        review_input = (
            f"MỤC TIÊU: {goal}\n\n"
            f"TRẠNG THÁI THẬT (do hệ thống kiểm chứng):\n"
            f"- Lịch đã đặt thành công: "
            f"{booked_registry if booked_registry else 'CHƯA CÓ LỊCH NÀO'}\n\n"
            f"NHẬT KÝ BỘ NHỚ:\n{_memory_to_context(memory)}"
        )
        verdict = provider.generate(review_input, system_prompt=REFLECTION_PROMPT).strip()

        # 🛡️ CHỐT CHẶN KIỂM CHỨNG — bài học đắt nhất của Cấp độ 4:
        # bộ Tự Đánh Giá từng tuyên bố "HOÀN THÀNH: đã đặt lịch cho CAND-001 và CAND-005"
        # trong khi thực tế chưa có lịch nào được đặt. Không bao giờ tin lời tự khai của
        # LLM về trạng thái thế giới — phải đối chiếu với trạng thái thật do code nắm giữ.
        if verdict.upper().startswith("HOÀN THÀNH") and needs_booking and not booked_registry:
            print(f"🚨 [KIỂM CHỨNG] Bác bỏ lời tự nhận HOÀN THÀNH: \"{verdict[:80]}...\"")
            print("   Lý do: mục tiêu yêu cầu đặt lịch nhưng hệ thống chưa ghi nhận lịch nào.")
            verdict = ("TIẾP TỤC: (bị chốt chặn kiểm chứng bác bỏ — chưa có lịch nào "
                       "được đặt thật, phải thực hiện book_interview)")

        memory["reflections"].append({"cycle": cycle, "verdict": verdict})
        print(f"🔎 [REFLECTION] {verdict}")

        if verdict.upper().startswith("HOÀN THÀNH"):
            completed = True
            print("🎯 Agent tự kết luận mục tiêu đã đạt — dừng sớm, không chạy nốt kế hoạch.")
            break

    # ---------- TỔNG KẾT ----------
    print(f"\n{'=' * 60}")
    print("🏁 [KẾT QUẢ AUTONOMOUS AGENT]")
    print(f"{'=' * 60}")
    print(f"📋 Kế hoạch tự sinh : {len(plan)} bước")
    print(f"⚙️ Đã thực thi       : {len(memory['done'])} bước")
    print(f"💾 Bộ nhớ tích luỹ   : {len(memory['facts'])} kết quả")
    print(f"📅 Lịch đã đặt thật  : {booked_registry if booked_registry else 'không có'}")
    print(f"🎯 Tự đánh giá       : {'HOÀN THÀNH' if completed else 'CHƯA XONG (hết ngân sách bước)'}")

    return {
        "goal": goal,
        "plan": plan,
        "memory": memory,
        "completed": completed,
        "bookings": list(booked_registry),
    }
