"""
🚀 CORE AGENT APP (Role 4: Core Agent Developer / Integrator)
File chính ghép nối tất cả các thành phần: Tools + Prompts + Test Cases + Multi-Provider.

Điểm khác biệt so với bản demo hardcode ban đầu:
- ReAct loop THẬT: LLM tự sinh Thought/Action ở mỗi bước, không hardcode sẵn.
- Action được gọi theo JSON args (vì tool giờ nhận nhiều tham số có tên,
  không phải 1 chuỗi đơn như tool_name['param'] kiểu cũ).
- Tool luôn trả JSON (theo hợp đồng trong tools.py), lỗi parse/parse tool
  không làm crash app mà được đưa lại cho LLM dưới dạng Observation lỗi,
  để LLM có cơ hội tự sửa (self-correction) hoặc dừng an toàn.
"""

import json
import os
import re
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from tools import AVAILABLE_TOOLS, TOOL_SPECS
from prompts import (
    CHATBOT_BASELINE_PROMPT,
    REACT_SYSTEM_PROMPT,
    MAX_ITERATIONS,
    GUARDRAIL_TRIGGERED_MESSAGE,
)
from providers import get_llm_provider

# Dùng ĐÚNG format của Role 3: Action: tool_name[val1, val2, ...]
# (tham số theo VỊ TRÍ, không phải JSON có tên). Thứ tự dưới đây phải khớp
# CHÍNH XÁC với thứ tự Role 3 liệt kê trong REACT_SYSTEM_PROMPT. Nếu Role 3
# đổi thứ tự tham số trong prompt, phải sửa lại dict này cho khớp.
POSITIONAL_PARAMS = {
    "get_order_status": ["order_id", "phone_last4"],
    "check_return_eligibility": ["order_id", "item_id", "reason", "phone_last4"],
    "create_return_request": [
        "order_id", "item_id", "reason", "resolution", "phone_last4", "confirmed",
    ],
}

load_dotenv()


def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    if not os.path.exists(config_path):
        config_path = os.path.join(base_dir, "..", "config", "test_cases.json")
    if not os.path.exists(config_path):
        config_path = "test_cases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_tool_spec(tool_name: str):
    """Tìm spec của 1 tool trong TOOL_SPECS theo tên, dùng để validate required params."""
    for spec in TOOL_SPECS:
        if spec["name"] == tool_name:
            return spec
    return None


ACTION_PATTERN = re.compile(
    r"Action:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[(.*)\]",
    re.IGNORECASE | re.DOTALL,
)
FINAL_ANSWER_PATTERN = re.compile(r"Final Answer:\s*(.*)", re.IGNORECASE | re.DOTALL)


def _coerce_value(tool_name: str, param_name: str, raw_value: str):
    """
    Chuyển 1 giá trị thô (chuỗi trong ngoặc vuông) sang đúng kiểu Python.
    - Bỏ dấu nháy đơn/kép nếu LLM tự thêm (ví dụ 'DH1001' -> DH1001).
    - Tham số 'confirmed' (bool) parse từ true/false/1/0 (không phân biệt hoa thường).
    """
    value = raw_value.strip()
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        value = value[1:-1].strip()

    if param_name == "confirmed":
        return value.lower() in ("true", "1", "yes", "có", "co")
    return value


def parse_positional_args(tool_name: str, raw_args: str):
    """
    Parse Action: tool_name[v1, v2, ...] theo đúng thứ tự tham số của Role 3.
    Trả về (args_dict, error_message). error_message None nếu parse OK.
    """
    param_names = POSITIONAL_PARAMS.get(tool_name)
    if param_names is None:
        return None, (
            f"Không rõ thứ tự tham số cho tool '{tool_name}' "
            f"(chưa khai báo trong POSITIONAL_PARAMS)."
        )

    parts = [p for p in raw_args.split(",")] if raw_args.strip() else []
    parts = [p.strip() for p in parts]

    if len(parts) > len(param_names):
        return None, (
            f"Tool '{tool_name}' chỉ nhận tối đa {len(param_names)} tham số "
            f"({', '.join(param_names)}), nhưng nhận được {len(parts)} giá trị."
        )

    args = {}
    for name, raw_val in zip(param_names, parts):
        args[name] = _coerce_value(tool_name, name, raw_val)

    # Validate đủ tham số bắt buộc theo TOOL_SPECS (không chỉ dựa vào vị trí đã điền).
    spec = get_tool_spec(tool_name)
    if spec:
        required = spec.get("parameters", {}).get("required", [])
        missing = [r for r in required if r not in args]
        if missing:
            return None, (
                f"Tool '{tool_name}' thiếu tham số bắt buộc: {', '.join(missing)}. "
                f"Thứ tự tham số đúng là: {', '.join(param_names)}."
            )

    return args, None


def parse_llm_response(text: str):
    """
    Phân tích output của LLM thành 1 trong 3 dạng:
    - ("action", tool_name, args_dict)
    - ("final", answer_text)
    - ("invalid", raw_text)   -> LLM không tuân thủ định dạng hoặc args sai

    Để app vẫn chạy ổn khi provider trả về phản hồi tự nhiên/không đúng format,
    trường hợp không khớp cấu trúc sẽ được coi là câu trả lời cuối cùng thay vì
    bị kẹt trong guardrail.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return ("invalid", "")

    final_match = FINAL_ANSWER_PATTERN.search(cleaned)
    action_match = ACTION_PATTERN.search(cleaned)

    if action_match and (not final_match or action_match.start() < final_match.start()):
        tool_name = action_match.group(1)
        raw_args = action_match.group(2).strip()
        args, error = parse_positional_args(tool_name, raw_args)
        if error:
            return ("invalid", error)
        return ("action", tool_name, args)

    if final_match:
        return ("final", final_match.group(1).strip())

    return ("final", cleaned)


def call_tool(tool_name: str, args: dict) -> str:
    """Gọi tool theo tên + args JSON; luôn trả về chuỗi Observation, không raise."""
    if tool_name not in AVAILABLE_TOOLS:
        return json.dumps({
            "ok": False,
            "tool": tool_name,
            "error": {"code": "UNKNOWN_TOOL", "message": f"Không tồn tại tool '{tool_name}'."},
            "message": f"Không tồn tại tool '{tool_name}'. Các tool hợp lệ: {list(AVAILABLE_TOOLS.keys())}",
        }, ensure_ascii=False)

    func = AVAILABLE_TOOLS[tool_name]
    try:
        return func(**args)
    except TypeError as e:
        # Sai tên/thiếu tham số bắt buộc -> trả Observation lỗi, không crash app.
        return json.dumps({
            "ok": False,
            "tool": tool_name,
            "error": {"code": "BAD_ARGUMENTS", "message": str(e)},
            "message": f"Gọi tool '{tool_name}' sai tham số: {e}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "ok": False,
            "tool": tool_name,
            "error": {"code": "TOOL_CRASHED", "message": str(e)},
            "message": f"Tool '{tool_name}' gặp lỗi không mong muốn: {e}",
        }, ensure_ascii=False)


def run_baseline_chatbot(user_query: str, provider):
    """Chatbot gốc, không có tool, dễ bị ảo giác/không có dữ liệu thực tế."""
    print(f"\n💬 [CHATBOT BASELINE] Câu hỏi: {user_query}")
    print(f"⚙️ System Prompt: {CHATBOT_BASELINE_PROMPT.strip()}")
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"🤖 Chatbot trả lời:\n{response}")


def run_react_agent(user_query: str, provider):
    """
    Vòng lặp ReAct THẬT:
    - Mỗi bước gửi lại toàn bộ "scratchpad" (Thought/Action/Observation
      từ các bước trước) cho LLM, vì provider.generate() không tự giữ
      lịch sử hội thoại (interface chỉ nhận 1 prompt string).
    - Dừng khi có Final Answer, hoặc khi chạm MAX_ITERATIONS (guardrail).
    """
    print(f"\n🤖 [REACT AGENT] Câu hỏi: {user_query}")
    system_prompt = REACT_SYSTEM_PROMPT

    scratchpad = f"Câu hỏi của người dùng: {user_query}\n"
    step = 0

    while step < MAX_ITERATIONS:
        step += 1
        print(f"\n--- 🔄 Vòng lặp ReAct (Step {step}/{MAX_ITERATIONS}) ---")

        raw_response = provider.generate(scratchpad, system_prompt=system_prompt)
        parsed = parse_llm_response(raw_response)

        if parsed[0] == "invalid":
            print(f"⚠️ LLM trả về không đúng định dạng:\n{raw_response}")
            print("🧠 Dùng phản hồi thô như câu trả lời cuối cùng để tránh bị kẹt guardrail.")
            return raw_response.strip() or "Xin lỗi, tôi chưa có câu trả lời phù hợp."

        if parsed[0] == "final":
            answer = parsed[1]
            print(f"🧠 Thought/Final: {raw_response.strip()}")
            print(f"🏁 Final Answer: {answer}")
            return answer

        # parsed[0] == "action"
        _, tool_name, args = parsed
        print(f"🧠 (LLM output thô):\n{raw_response.strip()}")
        param_order = POSITIONAL_PARAMS.get(tool_name, list(args.keys()))
        args_display = ", ".join(str(args.get(p, "")) for p in param_order)
        print(f"🛠️ Action: {tool_name}[{args_display}]")

        observation = call_tool(tool_name, args)
        print(f"👁️ Observation: {observation}")

        scratchpad += (
            f"\n{raw_response.strip()}\n"
            f"Observation: {observation}\n"
        )

    print(GUARDRAIL_TRIGGERED_MESSAGE)
    return None


if __name__ == "__main__":
    print("==================================================")
    print("🏫 ĐẠI HỌC VINUNI - BÀI LAB 3: CHATBOT VS REACT AGENT")
    print("==================================================")

    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"🔌 LLM Provider đang hoạt động: {provider.__class__.__name__} (Model: {model_name})")

    tests = load_test_cases()
    print(f"✅ Đã tải thành công {len(tests)} Test Cases từ config/test_cases.json\n")

    sample_query = tests[0]["question"] if isinstance(tests[0], dict) else tests[0]

    print("--- DEMO 1: CHẠY TRÊN CHATBOT BASELINE ---")
    run_baseline_chatbot(sample_query, provider)

    print("\n--- DEMO 2: CHẠY TRÊN REACT AGENT ---")
    run_react_agent(sample_query, provider)