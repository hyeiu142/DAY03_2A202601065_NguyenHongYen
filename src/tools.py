"""
Tool registry cho đề tài "Trợ Lý Tra Cứu Đơn Hàng & Xử Lý Đổi Trả".

Phạm vi Role 2 theo ba mốc đầu:

Mốc 1 - Danh sách công cụ
    1. ``get_order_status``: tra cứu trạng thái và sản phẩm trong đơn.
    2. ``check_return_eligibility``: kiểm tra một sản phẩm có đủ điều kiện
       đổi/trả hay không.
    3. ``create_return_request``: tạo yêu cầu đổi hàng hoặc hoàn tiền sau khi
       người dùng xác nhận.

Mốc 2 - Tool contract
    Mỗi tool có docstring đầy đủ và ``TOOL_SPECS`` để Prompt Engineer/Core
    Integrator có thể đưa schema cho LLM.

Mốc 3 - An toàn cho ReAct loop
    Tool luôn trả về chuỗi JSON. Lỗi input, lỗi nghiệp vụ và lỗi ngoài dự kiến
    đều trở thành Observation có ``ok=false`` thay vì làm ứng dụng bị crash.

Dữ liệu trong bài lab là dữ liệu giả lập, deterministic và không gọi mạng.
Trong production, thay các dictionary bên dưới bằng API/DB adapter nhưng giữ
nguyên contract để Agent không phải thay đổi.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any


RETURN_WINDOW_DAYS = 7
DEFAULT_REQUEST_DATE = "2026-07-28"
ALLOWED_REASONS = {
    "damaged": "Sản phẩm bị hư hỏng",
    "wrong_item": "Giao sai sản phẩm",
    "not_as_described": "Sản phẩm không đúng mô tả",
    "changed_mind": "Thay đổi nhu cầu",
}
ALLOWED_RESOLUTIONS = {
    "exchange": "Đổi sản phẩm",
    "refund": "Hoàn tiền",
}

# Kho dữ liệu giả lập phục vụ demo/test offline.
_ORDERS: dict[str, dict[str, Any]] = {
    "DH1001": {
        "customer_phone_last4": "6789",
        "status": "delivered",
        "status_label": "Đã giao",
        "created_at": "2026-07-23",
        "delivered_at": "2026-07-25",
        "tracking_code": "VNPOST-1001",
        "estimated_delivery": None,
        "items": [
            {
                "item_id": "SP001",
                "name": "Giày chạy bộ AirFlex",
                "quantity": 1,
                "unit_price_vnd": 850_000,
                "returnable": True,
            },
            {
                "item_id": "SP002",
                "name": "Tất thể thao",
                "quantity": 2,
                "unit_price_vnd": 90_000,
                "returnable": True,
            },
        ],
    },
    "DH10023": {
        "customer_phone_last4": "6789",
        "status": "delivered",
        "status_label": "Đã giao",
        "created_at": "2026-07-23",
        "delivered_at": "2026-07-25",
        "tracking_code": "VNPOST-10023",
        "estimated_delivery": None,
        "items": [
            {
                "item_id": "SP002",
                "name": "Áo khoác gió",
                "quantity": 1,
                "unit_price_vnd": 450_000,
                "returnable": True,
            }
        ],
    },
    "DH1002": {
        "customer_phone_last4": "2468",
        "status": "shipping",
        "status_label": "Đang giao",
        "created_at": "2026-07-27",
        "delivered_at": None,
        "tracking_code": "GHN-1002",
        "estimated_delivery": "2026-07-30",
        "items": [
            {
                "item_id": "SP003",
                "name": "Balo Urban 20L",
                "quantity": 1,
                "unit_price_vnd": 620_000,
                "returnable": True,
            }
        ],
    },
    "DH1003": {
        "customer_phone_last4": "1357",
        "status": "delivered",
        "status_label": "Đã giao",
        "created_at": "2026-07-05",
        "delivered_at": "2026-07-10",
        "tracking_code": "JNT-1003",
        "estimated_delivery": None,
        "items": [
            {
                "item_id": "SP004",
                "name": "Áo khoác chống nắng",
                "quantity": 1,
                "unit_price_vnd": 390_000,
                "returnable": True,
            }
        ],
    },
    "DH1004": {
        "customer_phone_last4": "1122",
        "status": "delivered",
        "status_label": "Đã giao",
        "created_at": "2026-07-25",
        "delivered_at": "2026-07-27",
        "tracking_code": "SPX-1004",
        "estimated_delivery": None,
        "items": [
            {
                "item_id": "SP005",
                "name": "Tai nghe Bluetooth Sonic",
                "quantity": 1,
                "unit_price_vnd": 1_290_000,
                "returnable": True,
            },
            {
                "item_id": "SP006",
                "name": "Khẩu trang cá nhân",
                "quantity": 1,
                "unit_price_vnd": 45_000,
                "returnable": False,
            },
        ],
    },
}

_RETURN_REQUESTS: dict[str, dict[str, Any]] = {}


def _response(
    ok: bool,
    tool: str,
    *,
    data: dict[str, Any] | None = None,
    error_code: str | None = None,
    message: str,
) -> str:
    """Tạo Observation JSON có cấu trúc nhất quán cho Agent."""
    payload: dict[str, Any] = {"ok": ok, "tool": tool, "message": message}
    if data is not None:
        payload["data"] = data
    if error_code is not None:
        payload["error"] = {"code": error_code, "message": message}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _clean_required(value: Any, field_name: str) -> tuple[str | None, str | None]:
    """Chuẩn hóa một input string bắt buộc mà không phát sinh exception."""
    if not isinstance(value, str):
        return None, f"Tham số '{field_name}' phải là chuỗi."
    cleaned = value.strip()
    if not cleaned:
        return None, f"Tham số '{field_name}' không được để trống."
    if len(cleaned) > 100:
        return None, f"Tham số '{field_name}' vượt quá 100 ký tự."
    return cleaned, None


def _validate_identity(
    order_id: Any, phone_last4: Any = None, tool: str = ""
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Xác thực mã đơn hàng."""
    clean_order_id, error = _clean_required(order_id, "order_id")
    if error:
        return None, None, _response(
            False, tool, error_code="INVALID_INPUT", message=error
        )
    clean_order_id = clean_order_id.upper()

    order = _ORDERS.get(clean_order_id)
    if order is None:
        return None, None, _response(
            False,
            tool,
            error_code="ORDER_NOT_FOUND",
            message=f"Không tìm thấy đơn hàng {clean_order_id} trong hệ thống.",
        )
    return clean_order_id, order, None


def _parse_iso_date(value: Any, field_name: str) -> tuple[date | None, str | None]:
    """Parse ngày ISO YYYY-MM-DD và chuyển lỗi parser thành thông báo nghiệp vụ."""
    cleaned, error = _clean_required(value, field_name)
    if error:
        return None, error
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date(), None
    except (TypeError, ValueError):
        return None, f"'{field_name}' phải là ngày hợp lệ theo định dạng YYYY-MM-DD."


def _find_item(order: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    """Tìm sản phẩm trong đơn theo item_id đã chuẩn hóa."""
    return next(
        (item for item in order["items"] if item["item_id"] == item_id), None
    )


def get_order_status(order_id: str, phone_last4: str = "") -> str:
    """
    Tra cứu trạng thái giao hàng và danh sách sản phẩm của một đơn.

    Purpose:
        Dùng khi người dùng hỏi đơn đang ở đâu, khi nào giao, hoặc cần biết
        ``item_id`` trước khi đổi/trả. Đây là tool read-only.
    Input schema:
        ``order_id`` (str, required): Mã đơn, ví dụ ``"DH1001"``.
        ``phone_last4`` (str, required): 4 số cuối SĐT đặt hàng để xác thực.
    Output schema:
        Chuỗi JSON. Thành công có ``ok=true`` và ``data`` gồm trạng thái,
        tracking, ngày dự kiến/ngày đã giao và sản phẩm. Không trả PII đầy đủ.
    Error semantics:
        ``INVALID_INPUT``, ``ORDER_NOT_FOUND_OR_UNAUTHORIZED`` hoặc
        ``INTERNAL_ERROR``; luôn trả JSON, không raise.
    Side effect:
        Không.
    Example:
        ``get_order_status("DH1001", "6789")``.
    """
    tool = "get_order_status"
    try:
        clean_order_id, order, error_response = _validate_identity(
            order_id, phone_last4, tool
        )
        if error_response:
            return error_response
        assert clean_order_id is not None and order is not None

        public_items = [
            {
                "item_id": item["item_id"],
                "name": item["name"],
                "quantity": item["quantity"],
                "unit_price_vnd": item["unit_price_vnd"],
            }
            for item in order["items"]
        ]
        return _response(
            True,
            tool,
            message=f"Tra cứu đơn {clean_order_id} thành công.",
            data={
                "order_id": clean_order_id,
                "status": order["status"],
                "status_label": order["status_label"],
                "created_at": order["created_at"],
                "delivered_at": order["delivered_at"],
                "estimated_delivery": order["estimated_delivery"],
                "tracking_code": order["tracking_code"],
                "items": public_items,
            },
        )
    except Exception:
        return _response(
            False,
            tool,
            error_code="INTERNAL_ERROR",
            message="Không thể tra cứu đơn lúc này. Vui lòng thử lại sau.",
        )


def check_return_eligibility(
    order_id: str,
    item_id: str,
    reason: str,
    phone_last4: str = "",
    request_date: str = DEFAULT_REQUEST_DATE,
) -> str:
    """
    Kiểm tra điều kiện đổi/trả cho một sản phẩm, chưa tạo yêu cầu.

    Purpose:
        Gọi sau ``get_order_status`` và trước ``create_return_request``. Tool
        kiểm tra trạng thái giao, hạn 7 ngày, loại sản phẩm và lý do.
    Input schema:
        ``order_id`` (str, required): Mã đơn.
        ``item_id`` (str, required): Mã sản phẩm nằm trong đơn.
        ``reason`` (str, required): Một trong ``damaged``, ``wrong_item``,
        ``not_as_described``, ``changed_mind``.
        ``phone_last4`` (str, required): 4 số cuối SĐT đặt hàng.
        ``request_date`` (str, optional): Ngày yêu cầu dạng YYYY-MM-DD;
        mặc định ``2026-07-28`` để bài lab chạy deterministic.
    Output schema:
        Chuỗi JSON với ``eligible`` (bool), lý do quyết định, hạn cuối và các
        hình thức xử lý hợp lệ.
    Error semantics:
        Input/hệ thống sai trả ``ok=false``. Trường hợp không đủ điều kiện là
        kết quả nghiệp vụ hợp lệ: ``ok=true`` và ``eligible=false``.
    Side effect:
        Không.
    Example:
        ``check_return_eligibility("DH1001", "SP001", "damaged", "6789")``.
    """
    tool = "check_return_eligibility"
    try:
        clean_order_id, order, error_response = _validate_identity(
            order_id, phone_last4, tool
        )
        if error_response:
            return error_response
        assert clean_order_id is not None and order is not None

        clean_item_id, error = _clean_required(item_id, "item_id")
        if error:
            return _response(
                False, tool, error_code="INVALID_INPUT", message=error
            )
        clean_item_id = clean_item_id.upper()

        clean_reason, error = _clean_required(reason, "reason")
        if error:
            return _response(
                False, tool, error_code="INVALID_INPUT", message=error
            )
        clean_reason = clean_reason.lower()
        if clean_reason not in ALLOWED_REASONS:
            return _response(
                False,
                tool,
                error_code="INVALID_REASON",
                message=(
                    "Lý do không hợp lệ. Giá trị cho phép: "
                    + ", ".join(sorted(ALLOWED_REASONS))
                    + "."
                ),
            )

        parsed_request_date, error = _parse_iso_date(request_date, "request_date")
        if error:
            return _response(
                False, tool, error_code="INVALID_DATE", message=error
            )
        assert parsed_request_date is not None

        item = _find_item(order, clean_item_id)
        if item is None:
            return _response(
                False,
                tool,
                error_code="ITEM_NOT_IN_ORDER",
                message=f"Không tìm thấy sản phẩm {clean_item_id} trong đơn.",
            )

        base_data = {
            "order_id": clean_order_id,
            "item_id": clean_item_id,
            "item_name": item["name"],
            "reason": clean_reason,
            "reason_label": ALLOWED_REASONS[clean_reason],
            "request_date": parsed_request_date.isoformat(),
        }
        if order["status"] != "delivered" or not order["delivered_at"]:
            return _response(
                True,
                tool,
                message="Đơn chưa giao thành công nên chưa thể tạo yêu cầu đổi/trả.",
                data={**base_data, "eligible": False, "decision": "NOT_DELIVERED"},
            )
        if not item["returnable"]:
            return _response(
                True,
                tool,
                message="Sản phẩm thuộc nhóm không hỗ trợ đổi/trả.",
                data={
                    **base_data,
                    "eligible": False,
                    "decision": "NON_RETURNABLE_ITEM",
                },
            )

        delivered_date = date.fromisoformat(order["delivered_at"])
        deadline = delivered_date.fromordinal(
            delivered_date.toordinal() + RETURN_WINDOW_DAYS
        )
        days_since_delivery = (parsed_request_date - delivered_date).days
        if days_since_delivery < 0:
            return _response(
                False,
                tool,
                error_code="INVALID_DATE",
                message="Ngày yêu cầu không thể trước ngày giao hàng.",
            )
        if parsed_request_date > deadline:
            return _response(
                True,
                tool,
                message=f"Đã quá hạn đổi/trả {RETURN_WINDOW_DAYS} ngày.",
                data={
                    **base_data,
                    "eligible": False,
                    "decision": "RETURN_WINDOW_EXPIRED",
                    "delivered_at": delivered_date.isoformat(),
                    "return_deadline": deadline.isoformat(),
                },
            )

        resolutions = ["exchange", "refund"]
        if clean_reason == "changed_mind":
            resolutions = ["exchange"]
        return _response(
            True,
            tool,
            message="Sản phẩm đủ điều kiện đổi/trả.",
            data={
                **base_data,
                "eligible": True,
                "decision": "ELIGIBLE",
                "delivered_at": delivered_date.isoformat(),
                "return_deadline": deadline.isoformat(),
                "allowed_resolutions": resolutions,
            },
        )
    except Exception:
        return _response(
            False,
            tool,
            error_code="INTERNAL_ERROR",
            message="Không thể kiểm tra điều kiện đổi/trả lúc này.",
        )


def create_return_request(
    order_id: str,
    item_id: str,
    reason: str,
    resolution: str,
    phone_last4: str = "",
    confirmed: bool = False,
    request_date: str = DEFAULT_REQUEST_DATE,
) -> str:
    """
    Tạo yêu cầu đổi hàng/hoàn tiền sau khi kiểm tra điều kiện và xác nhận.

    Purpose:
        Chỉ gọi sau khi người dùng đã xem kết quả eligibility và xác nhận rõ
        muốn tạo yêu cầu. Đây là tool có side effect.
    Input schema:
        ``order_id``, ``item_id``, ``reason``, ``phone_last4`` và
        ``request_date`` có ý nghĩa như ``check_return_eligibility``.
        ``resolution`` (str, required): ``exchange`` hoặc ``refund``.
        ``confirmed`` (bool, required để ghi): Phải là ``True``; không tự suy
        diễn sự đồng ý từ tin nhắn mơ hồ.
    Output schema:
        Chuỗi JSON chứa ``request_id``, trạng thái và bước tiếp theo.
    Error semantics:
        Không xác nhận trả ``CONFIRMATION_REQUIRED``; không đủ điều kiện trả
        ``NOT_ELIGIBLE``; yêu cầu trùng trả lại request cũ (idempotent).
        Mọi trường hợp đều trả JSON và không raise.
    Side effect:
        Có: ghi một yêu cầu vào kho giả lập trong bộ nhớ khi hợp lệ.
    Example:
        ``create_return_request("DH1001", "SP001", "damaged", "refund",
        "6789", True)``.
    """
    tool = "create_return_request"
    try:
        if not isinstance(confirmed, bool):
            return _response(
                False,
                tool,
                error_code="INVALID_INPUT",
                message="'confirmed' phải là giá trị boolean true/false.",
            )
        if not confirmed:
            return _response(
                False,
                tool,
                error_code="CONFIRMATION_REQUIRED",
                message=(
                    "Chưa tạo yêu cầu. Hãy trình bày phương án cho người dùng "
                    "và chỉ gọi lại với confirmed=true sau khi họ xác nhận."
                ),
            )

        clean_resolution, error = _clean_required(resolution, "resolution")
        if error:
            return _response(
                False, tool, error_code="INVALID_INPUT", message=error
            )
        clean_resolution = clean_resolution.lower()
        if clean_resolution not in ALLOWED_RESOLUTIONS:
            return _response(
                False,
                tool,
                error_code="INVALID_RESOLUTION",
                message=(
                    "Phương án không hợp lệ. Giá trị cho phép: "
                    + ", ".join(sorted(ALLOWED_RESOLUTIONS))
                    + "."
                ),
            )

        eligibility_json = check_return_eligibility(
            order_id, item_id, reason, phone_last4, request_date
        )
        eligibility = json.loads(eligibility_json)
        if not eligibility["ok"]:
            return _response(
                False,
                tool,
                error_code=eligibility["error"]["code"],
                message=eligibility["message"],
            )
        eligibility_data = eligibility["data"]
        if not eligibility_data["eligible"]:
            return _response(
                False,
                tool,
                error_code="NOT_ELIGIBLE",
                message=eligibility["message"],
                data={
                    "decision": eligibility_data["decision"],
                    "order_id": eligibility_data["order_id"],
                    "item_id": eligibility_data["item_id"],
                },
            )
        if clean_resolution not in eligibility_data["allowed_resolutions"]:
            return _response(
                False,
                tool,
                error_code="RESOLUTION_NOT_ALLOWED",
                message=(
                    f"Phương án '{clean_resolution}' không áp dụng cho lý do "
                    f"'{eligibility_data['reason']}'."
                ),
                data={
                    "allowed_resolutions": eligibility_data["allowed_resolutions"]
                },
            )

        key = "|".join(
            [
                eligibility_data["order_id"],
                eligibility_data["item_id"],
                eligibility_data["reason"],
                clean_resolution,
            ]
        )
        if key in _RETURN_REQUESTS:
            existing = _RETURN_REQUESTS[key]
            return _response(
                True,
                tool,
                message="Yêu cầu đã tồn tại; không tạo bản ghi trùng.",
                data={**existing, "duplicate": True},
            )

        request_id = f"RT{len(_RETURN_REQUESTS) + 1:04d}"
        request_record = {
            "request_id": request_id,
            "order_id": eligibility_data["order_id"],
            "item_id": eligibility_data["item_id"],
            "reason": eligibility_data["reason"],
            "resolution": clean_resolution,
            "resolution_label": ALLOWED_RESOLUTIONS[clean_resolution],
            "status": "pending_review",
            "created_at": eligibility_data["request_date"],
            "next_step": (
                "Đóng gói sản phẩm; mã gửi trả sẽ được cấp sau khi duyệt."
            ),
            "duplicate": False,
        }
        _RETURN_REQUESTS[key] = request_record
        return _response(
            True,
            tool,
            message=f"Đã tạo yêu cầu đổi/trả {request_id}.",
            data=request_record,
        )
    except Exception:
        return _response(
            False,
            tool,
            error_code="INTERNAL_ERROR",
            message="Không thể tạo yêu cầu đổi/trả lúc này. Chưa có thay đổi nào.",
        )


# Schema machine-readable để Prompt Engineer/Core Integrator đưa cho LLM.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_order_status",
        "description": (
            "Tra cứu trạng thái và item_id trong đơn. Chỉ đọc, không thay đổi đơn."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Mã đơn, VD DH1001"},
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_return_eligibility",
        "description": (
            "Kiểm tra điều kiện đổi/trả; chỉ đánh giá, chưa tạo yêu cầu."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "item_id": {"type": "string"},
                "reason": {"type": "string", "enum": sorted(ALLOWED_REASONS)},
                "request_date": {
                    "type": "string",
                    "format": "date",
                    "default": DEFAULT_REQUEST_DATE,
                },
            },
            "required": ["order_id", "item_id", "reason"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_return_request",
        "description": (
            "Tạo yêu cầu đổi/hoàn sau khi đủ điều kiện và người dùng xác nhận. "
            "Có side effect, không gọi với confirmed=true nếu chưa được đồng ý."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "item_id": {"type": "string"},
                "reason": {"type": "string", "enum": sorted(ALLOWED_REASONS)},
                "resolution": {
                    "type": "string",
                    "enum": sorted(ALLOWED_RESOLUTIONS),
                },
                "confirmed": {"type": "boolean", "const": True},
                "request_date": {
                    "type": "string",
                    "format": "date",
                    "default": DEFAULT_REQUEST_DATE,
                },
            },
            "required": [
                "order_id",
                "item_id",
                "reason",
                "resolution",
                "confirmed",
            ],
            "additionalProperties": False,
        },
    },
]


# Registry bắt buộc theo rubric; Core Integrator có thể dispatch bằng tên Action.
AVAILABLE_TOOLS = {
    "get_order_status": get_order_status,
    "check_return_eligibility": check_return_eligibility,
    "create_return_request": create_return_request,
}
