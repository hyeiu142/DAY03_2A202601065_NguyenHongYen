# 📊 BÁO CÁO GIÁM SÁT & ĐÁNH GIÁ (OBSERVABILITY TRACE LOGS)
*Dành cho Role 5: Observability & Reviewer*
*Chủ đề nhóm: 🛒 Trợ Lý Tra Cứu Đơn Hàng & Xử Lý Đổi Trả (Đề tài số 5)*

---

## 🎯 1. BẢNG CHẤM ĐIỂM AGENTIC FIT (SCORING MATRIX)

| Tiêu chí | Điểm (1-5) | Lý do đánh giá |
| :--- | :---: | :--- |
| 🧠 **Multi-step Reasoning** | `4/5` | Cần suy luận nhiều bước: tra cứu đơn hàng → kiểm tra điều kiện đổi trả → tính số tiền hoàn. |
| 🛠️ **Tool Interaction** | `5/5` | Bắt buộc phải gọi hệ thống tra cứu đơn hàng thực tế (mã đơn, trạng thái, ngày mua...); LLM không thể tự biết dữ liệu riêng của từng khách hàng. |
| 🔀 **Dynamic Decision** | `5/5` | Kết quả tra cứu (đơn còn hạn hay đã quá hạn, sản phẩm có lỗi hay không) quyết định trực tiếp bước xử lý tiếp theo (được đổi trả hay bị từ chối). |
| ⏳ **Long Horizon** | `3/5` | Quy trình xử lý một yêu cầu đổi trả thường chỉ gồm 2-3 bước tra cứu/tính toán, chưa cần lập kế hoạch dài hạn. |
| **TỔNG ĐIỂM FIT** | **17/20** | **KẾT LUẬN: BÀI TOÁN RẤT NÊN DÙNG REACT AGENT!** Chatbot thường sẽ không thể tra cứu trạng thái đơn hàng thật hoặc sẽ "ảo giác" (hallucinate) ra số tiền hoàn. |

---

## 🔍 2. SO SÁNH PHẢN HỒI (TEST CASE #4)

**Câu hỏi**: *"Áo khoác trong đơn hàng DH10023 của tôi bị lỗi đường may, tôi có được đổi trả không và nếu được thì hoàn lại bao nhiêu tiền?"*

### 🤖 Chatbot Baseline:
* **Phản hồi**: *"Tôi không có quyền truy cập vào hệ thống đơn hàng của bạn nên không thể xác nhận tình trạng đơn DH10023 hay số tiền hoàn cụ thể. Bạn vui lòng liên hệ tổng đài để được kiểm tra."*
* **Nhận xét**: An toàn (không bịa số liệu) nhưng không giải quyết được nhu cầu thực tế — khách hàng vẫn phải tự đi tra cứu ở nơi khác.

### 🧠 ReAct Agent:
* **Thought 1**: Cần xác minh đơn hàng DH10023 có đủ điều kiện đổi trả (còn hạn, sản phẩm đúng diện lỗi) hay không.
* **Action 1**: `check_return_eligibility['DH10023']`
* **Observation 1**: `Đơn DH10023: mua ngày 10/07/2026, còn trong hạn đổi trả (7 ngày), sản phẩm "Áo khoác" đủ điều kiện đổi trả do lỗi nhà sản xuất.`
* **Thought 2**: Đơn hàng đủ điều kiện đổi trả, tiếp theo cần tính số tiền hoàn lại cho khách.
* **Action 2**: `calculate_refund['DH10023']`
* **Observation 2**: `Số tiền hoàn dự kiến cho đơn DH10023: 850,000 VNĐ (hoàn 100% vì lỗi từ nhà sản xuất).`
* **Thought 3**: Đã có đủ thông tin điều kiện đổi trả và số tiền hoàn, có thể tổng hợp câu trả lời cuối cùng.
* **Final Answer**: *"Đơn hàng DH10023 của bạn vẫn còn trong hạn đổi trả và áo khoác bị lỗi đường may đủ điều kiện đổi trả 100% do lỗi nhà sản xuất. Bạn sẽ được hoàn lại 850,000 VNĐ sau khi shop nhận lại sản phẩm."*
* **Nhận xét**: Hoàn thành xuất sắc nhờ kết hợp 2 Tool liên tiếp (Dynamic Decision: kết quả Tool 1 xác nhận đủ điều kiện mới cho phép gọi Tool 2).

---

## 🛡️ 3. TRACE LOG GUARDRAIL (TEST CASE #5 - EDGE CASE)

**Câu hỏi**: *"Tôi muốn đổi trả đơn hàng mã DH00000 mua từ cách đây 3 năm, khi nào shop chuyển tiền hoàn cho tôi?"*

* **Thought 1**: Cần kiểm tra đơn hàng DH00000 có tồn tại và còn hạn đổi trả không.
* **Action 1**: `check_return_eligibility['DH00000']`
* **Observation 1**: `LỖI: Không tìm thấy mã đơn hàng 'DH00000' trong hệ thống.`
* **Thought 2**: Tool báo lỗi không tìm thấy đơn hàng, tôi thử tra cứu lại trạng thái đơn để chắc chắn trước khi kết luận.
* **Action 2**: `check_order_status['DH00000']`
* **Observation 2**: `LỖI: Không tìm thấy dữ liệu đơn hàng cho mã 'DH00000'.`
* **Thought 3 (Step = MAX_ITERATIONS = 3)**: Đã 2 lần tra cứu đều báo lỗi, không được tiếp tục lặp vô hạn.
* **🛡️ GUARDRAIL TRIGGERED**: Đạt giới hạn `MAX_ITERATIONS = 3`, hệ thống tự động ngắt vòng lặp.
* **Final Answer (Fallback)**: *"Xin lỗi, tôi không tìm thấy đơn hàng với mã DH00000 trong hệ thống nên không thể xác nhận thời gian hoàn tiền. Bạn vui lòng kiểm tra lại mã đơn hoặc liên hệ tổng đài CSKH để được hỗ trợ."*
* **Nhận xét**: Agent KHÔNG bịa ra số tiền hoàn hay ngày chuyển tiền dù bị hỏi dồn; Guardrail hoạt động đúng, tránh lặp vô tận và trả lời có kiểm soát.