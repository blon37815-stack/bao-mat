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

## Chạy trên Windows với Ollama (không cần khóa API)

Cài Python 3.12 từ python.org (chọn thêm Python vào PATH), Git và Ollama.
Mở Ollama và chạy `ollama run qwen3:4b` ít nhất một lần để tải mô hình.
Khi đã trò chuyện được, nhập `/bye` để thoát phiên trò chuyện; giữ ứng dụng
Ollama chạy nền. Mở PowerShell mới:

```powershell
git clone --branch feat/bot-team-dashboard https://github.com/blon37815-stack/bao-mat.git
cd bao-mat
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Nếu đã clone dự án, vào đúng thư mục và chạy `git pull --ff-only` thay vì
clone lần nữa (đảm bảo đang ở nhánh `feat/bot-team-dashboard`). Không cần
activate môi trường ảo hay thay đổi execution policy PowerShell.

Trong trình duyệt trên máy Windows, truy cập `http://127.0.0.1:8000`, chọn
**Ollama · AI trên máy**, nhập nhiệm vụ ngắn và bấm **Giao nhiệm vụ**. Mỗi nhiệm
vụ gọi mô hình ba lần; chạy bằng CPU có thể mất vài phút. Nếu lỗi, kiểm tra
`ollama list` có `qwen3:4b` rồi dùng nút chạy lại.

Mặc định kết nối `http://127.0.0.1:11434`, mô hình `qwen3:4b`. Có thể đổi
`OLLAMA_MODEL` và `OLLAMA_BASE_URL` trong môi trường trước khi chạy, ví dụ
`$env:OLLAMA_MODEL = 'qwen3:4b'`. Chỉ dùng máy chủ Ollama bạn tin cậy; nội dung
nhiệm vụ được gửi đến máy chủ đó. Ứng dụng không tự chuyển sang OpenAI khi
Ollama lỗi và không cần OPENAI_API_KEY ở chế độ này.

Máy chủ Codex trên đám mây không kết nối được Ollama qua loopback của máy
Windows; cả app và Ollama cần chạy trên cùng máy theo hướng dẫn trên.

## Tải sản phẩm

Mở nhiệm vụ có kết quả và bấm **Tải toàn bộ báo cáo (.md)**, hoặc mở chi tiết
để tải riêng kế hoạch, kết quả hay báo cáo kiểm tra. Tệp Markdown UTF-8 giữ
nguyên tiếng Việt, gồm yêu cầu và trạng thái nhiệm vụ. Báo cáo mô phỏng và
kết quả một phần được đánh dấu rõ. Phần suy nghĩ trong thẻ think được loại bỏ
như trên giao diện. Tải xuống không gọi mô hình và không phát sinh phí API.

API: `GET /api/tasks/{id}/export/{all|plan|result|review}`. Trả về 409 khi
chưa có nội dung cho phần được yêu cầu, 404 khi không tìm thấy. Bản này xuất
nội dung văn bản thành Markdown, chưa tạo và thực thi dự án mã nguồn.

## Bộ nhớ dự án

Điền mục tiêu, yêu cầu và quyết định chung vào **Bộ nhớ dự án**, bấm **Lưu bộ
nhớ** rồi giao nhiệm vụ. Giới hạn 8000 ký tự, lưu trong cùng SQLite nên giữ
lại khi đóng app. Không lưu mật khẩu, khóa API hay thông tin nhạy cảm.
Bộ nhớ được gửi kèm cả ba bước đến nhà cung cấp bạn chọn; Ollama mặc định
chạy trên máy bạn. Đây là thông tin chung do bạn nhập, chưa tự học từ lịch sử.

Mỗi nhiệm vụ mới giữ một bản sao bộ nhớ lúc tạo. Xem bản sao trong chi tiết
hoặc báo cáo Markdown. Sửa bộ nhớ chung chỉ ảnh hưởng nhiệm vụ mới; chạy lại
nhiệm vụ dùng bản sao cũ. Nhiệm vụ tạo trước phiên bản này có bộ nhớ trống.
Để xóa bộ nhớ chung, để trống và lưu; các bản sao trong lịch sử vẫn được giữ.
Bản đầu hỗ trợ một bộ nhớ chung, chưa phân tách nhiều dự án.

API: `GET /api/memory`, `POST /api/memory` với JSON `{"content":"..."}`.

## Bảo vệ yêu cầu cục bộ

Máy chủ chỉ nhận Host `127.0.0.1:<cổng>` hoặc `localhost:<cổng>`.
Yêu cầu có Origin phải khớp chính xác địa chỉ trang ứng dụng; Origin `null`
và Fetch Metadata `cross-site` bị từ chối. Mọi POST yêu cầu
`Content-Type: application/json` và `X-CSRF-Token` lấy từ `GET /api/session`.
Giao diện tự lấy token; token đổi khi khởi động app nên cần tải lại trang.
API client bên ngoài cũng cần lấy và gửi token. Đây là bảo vệ trước yêu cầu
web chéo nguồn, không thay thế đăng nhập hoặc ngăn phần mềm độc hại trên máy.
Ứng dụng vẫn chỉ dành cho sử dụng cá nhân trên loopback.
