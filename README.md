# Bao Mat — Đội bot

Bản đầu của bảng điều hành tiếng Việt: giao nhiệm vụ, theo dõi luồng
**Điều phối → Thực hiện → Kiểm tra**, lưu lịch sử bằng SQLite.
LangGraph điều khiển ba bước. Chưa tích hợp CrewAI, Letta hoặc OpenHands;
chưa có thực thi mã, truy cập tệp hay triển khai tự động.

## Cài và chạy (Python 3.12)

```sh
cd /workspace/bao-mat
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python app.py
```

Máy chủ chỉ lắng nghe trên loopback, cổng 8000. Dùng trình duyệt trên máy
chạy ứng dụng hoặc đường hầm được quản lý để truy cập. Không đưa máy chủ này
trực tiếp lên Internet: bản đầu chưa có đăng nhập hay giới hạn số nhiệm vụ.

Chế độ **Mô phỏng** không gọi AI, chỉ xác minh luồng và lưu dữ liệu.
Để dùng **AI thật**, cấp `OPENAI_API_KEY` qua biến môi trường an toàn trước
khi chạy máy chủ. Không đưa khóa vào Git hay giao diện. `BOT_MODEL` mặc định
là `gpt-4.1-mini`; tài khoản cần có quyền dùng mô hình. Ba bước gọi mô hình
riêng và có thể phát sinh phí. Chế độ này chỉ tạo văn bản, chưa chạy lệnh.
Không nhập dữ liệu nhạy cảm nếu chưa chấp nhận gửi tới nhà cung cấp mô hình.

`PORT` đổi cổng, `BOT_DB` đổi đường dẫn SQLite (mặc định `data/tasks.sqlite3`).
Lịch sử giữ lại qua lần khởi động; nhiệm vụ đang chạy bị đánh dấu gián đoạn
và không tự chạy lại. Giao diện hiển thị 100 nhiệm vụ gần nhất.

## Kiến trúc dự kiến

- Hiện tại: LangGraph + SQLite + OpenAI SDK, ba vai trò văn bản.
- Tiếp theo: môi trường cô lập cho bot lập trình, quyền duyệt thao tác,
  xác thực người dùng và giới hạn chi phí trước khi mở cho nhiều người.
- Chỉ thêm Letta khi cần bộ nhớ agent dài hạn; đánh giá OpenHands như dịch vụ
  lập trình riêng. CrewAI là lựa chọn thay thế để tổ chức đội, chưa cần xếp
  thêm lên LangGraph ở bản đầu.

## Quản lý nhiệm vụ

Bảng điều hành hiển thị số nhiệm vụ đang xử lý ở từng vai trò và tổng số
nhiệm vụ theo trạng thái. Có bộ lọc và mục chi tiết cho từng nhiệm vụ.
Với nhiệm vụ thất bại hoặc bị gián đoạn, nút **Chạy lại từ đầu** xóa kết quả
cũ và chạy lại cả ba bước; chế độ AI có thể tính phí lần nữa. Không tự động
chạy lại sau lỗi hoặc khởi động lại để tránh phát sinh chi phí ngoài ý muốn.

API bổ sung: `GET /api/team`, `GET /api/tasks/{id}` và
`POST /api/tasks/{id}/retry`. Chạy lại trả về 202 khi được nhận, 409 khi
trạng thái không phù hợp, 404 khi không tìm thấy nhiệm vụ.
