# Gói mã để rà soát

Đọc README.md như mô tả thống nhất hiện tại; RELEASE_NOTES.md ghi thay đổi,
EVALUATION.md giải thích cách đo. Gói ZIP chỉ chứa tệp được Git quản lý,
không có data, .env, .venv, node_modules hay .git. SOURCE_VERSION.json trong
gói ghi commit và SHA-256 từng tệp để đối chiếu; file này không cần cài đặt.

## Phần mới cần xem

Đợt `0.3.0-dev`: xem `docs/CAP_NHAT_0_3.md`. `bot_tools.py` kiểm quyền ở
luồng thực tế, giữ grants theo lượt/thu hồi hiện tại và audit có hạn mức,
không lưu nội dung hay lỗi provider. `governance_api.py` tách các route quản trị. `upgrade_proposals.py` tạo bản sao
base/candidate, patch, hash và bundle trong SQLite; duyệt chỉ ghi quyết định.
Không có API thực thi shell hay áp dụng patch vào ứng dụng. Schema 2 giữ
dữ liệu cũ; test mới trong `test_bot_tools.py`, `test_upgrade_proposals.py`
và ba luồng Chromium cuối. Các phần dưới là lịch sử triển khai trước đó.

Đợt nền tảng `0.2.0-dev`: xem `docs/CAP_NHAT_0_2.md`. `platform_config.py`
lưu hồ sơ model/revision, dự án và task_runtime; `platform_ui.js` giữ nền
giao diện và thêm thiết lập. `product_runner.py`/`sandbox_worker.py` chỉ
chạy sản phẩm trong Docker có giới hạn, không fallback host. `release_support.py`,
`launch_app.py`, `restore_app.py` chuẩn bị bản đích trên dữ liệu sao chép,
sao lưu mã/SQLite và phục hồi sang thư mục mới. `task_commands.py` chỉ nối
6 lệnh công khai, không giả lập toàn bộ ECC. Các đoạn dưới mô tả đợt trước;
README và hướng dẫn 0.3 ở trên là hiện trạng mới hơn.

Đợt tách Công việc: task_deletion.py/app.py lưu ZIP trước xóa, so fingerprint
trước/sau sao lưu và xóa một việc trong transaction. Phiên bản khác giữ
bản chụp nguồn; deleted_tasks chỉ đánh dấu liên kết còn lại. Danh sách mới
GET /api/tasks?compact=1 trả 20 dòng, không có output/project_memory/
bot_preferences; API cũ vẫn giữ 50 dòng và nội dung để tương thích. UI chỉ
tải danh sách khi mở Công việc, tách khỏi khu Trao đổi, giữ node không đổi
và dừng polling không cần thiết. Xem tests/test_task_deletion.py và các
luồng trình duyệt xóa/liên kết/biểu tượng; ZIP trước xóa vẫn chứa dữ liệu.

Đợt mới nhất: index.html/styles.css và workspace_ui.js chia 5 khu, 9 thẻ
bot, trình soạn thảo và preview. workspace_data.py lưu thư viện/hướng dẫn
bot và bản chụp theo nhiệm vụ; app.py thêm API JSON có token. Xóa tài liệu
giữ bản đã gửi; lưu tệp tạo phiên bản needs_review không gọi mô hình.
web_preview.py chỉ ghép HTML/CSS tĩnh đã lọc, đặt CSP; iframe sandbox ở UI
không allow-scripts/allow-same-origin. tests/test_workspace.py và 4 luồng
Chromium mới kiểm tra các ranh giới này. Chưa có đọc PDF/Word, chạy JS của
sản phẩm hoặc chạy Python. Xem RELEASE_NOTES.md cho số kiểm thử hiện tại.

1. expert_team.py/app.py: bản chỉ đạo của một chuyên gia thích ứng từ ECC
   truyền tới ba vai trò, cùng mô hình đã chọn. task_assignment giữ hồ sơ,
   commit nguồn và giới hạn riêng. model_reply đặt chỗ lượt gọi nguyên tử
   trước provider; hết mức giữ kết quả từng phần, chạy lại cần người dùng
   chọn hạn mức. resource_policy lưu mặc định/hàng đợi; API ghi vẫn cần
   token. resource_monitor.py/resource_ui.js đọc số đo máy chủ, không đặt
   hạn mức phần cứng. third_party/ecc giữ 5 định nghĩa gốc, MIT và hash;
   không chạy hook hoặc plugin. Xem tests/test_expert_team.py và
   tests/test_resource_monitor.py cho các trường hợp lỗi/đồng thời.
2. file_generation.py và app.py: mẫu cố định sinh nội dung từng tệp; ứng
   dụng ghép files. Sửa theo lỗi đường dẫn; lỗi AI chung sửa cả manifest.
   Giữ phần đã tạo khi hủy/lỗi, giới hạn 30 tệp/100 KB/tệp/1 MB tổng.
3. task_requirements.py: tiêu chí JSON, liên kết HTML và ánh xạ lỗi về tệp.
   parse_review nhận file_issues tùy chọn, kiểm tra kiểu và tính nhất quán.
4. evaluate.py/evaluation_cases.py: 9 ca, SQLite tạm, đo trước/sau sửa, số lần
   gọi, thời gian, checkpoint và mục tiêu JSON >=8/10 chỉ sau đủ lượt.
5. runtime_version.py: chụp commit/dirty/hash tại startup, endpoint version,
   hiển thị footer và commit của ứng dụng xuất báo cáo.
6. Các phần từ bản trước cần rà lại: data_cleanup.py (preview/hash, backup
   trước xóa, transaction), maintenance.py (backup SQLite/WAL),
   ollama_transport.py (stream subprocess, hủy/deadline), update_app.py
   (fast-forward, chuyển main theo ancestry), Prettier và CI Windows/Linux.

## Ranh giới và hạn chế

- Không chạy mã sinh ra; Python compile và node --check chỉ phân tích cú
  pháp. Chưa có sandbox Docker, functional tests hoặc quyền chạy shell.
- Sinh từng tệp chỉ cho nhiệm vụ có required_files; nhiệm vụ tự nhập vẫn
  dùng JSON bundle. Không đoán mẫu từ tên yêu cầu. Nhiệm vụ cũ không tự đổi.
- Số lần gọi tăng so với một bundle; context có thể lớn. Mô hình vẫn có thể
  sinh nội dung kém hoặc sai ngữ nghĩa. Tiêu chí tĩnh không chứng minh app
  hoạt động hoặc an toàn. Chưa ép Ollama JSON schema, chưa đo mô hình 7B.
- Chuyên gia là hướng dẫn vai trò được thích ứng, không phải toàn bộ đội
  ECC chạy nguyên bản hoặc mô hình Opus/Sonnet. Mỗi nhiệm vụ chỉ dùng một
  chuyên gia; chưa đo lợi ích chất lượng. Giới hạn lượt gọi từ app không
  phải giới hạn token/tiền hoặc HTTP retry bên trong SDK. CPU/RAM là toàn
  máy chủ app, GPU chỉ NVIDIA nếu đọc được; không giới hạn cứng phần cứng.
- Hủy đóng tiến trình HTTP của app, chưa chứng minh Ollama giải phóng CPU/
  GPU. OpenAI đang gọi vẫn đồng bộ. Số yêu cầu không phải hóa đơn/token.
- Dọn dữ liệu yêu cầu preview và DỌN; tự sao lưu trước. Chưa VACUUM hoặc tự
  quản lý dung lượng ZIP cũ. Updater chưa tự backup trước cập nhật.
- Chưa có đăng nhập/nhiều người dùng, nhiều dự án/FTS5, Letta, OpenHands,
  CrewAI hoặc tự nâng cấp ứng dụng. App chỉ dùng cục bộ.
- Chưa xác nhận ngưỡng chất lượng Ollama 8/10, CI remote Windows/Ubuntu
  hoặc khôi phục bản dữ liệu thật trên Windows; không gộp PR trong đợt này.

Xem số kiểm thử cục bộ ở RELEASE_NOTES.md. Không mô tả fake provider là
Ollama thật; không giả lập LangGraph trong các kiểm thử luồng của bản này.
