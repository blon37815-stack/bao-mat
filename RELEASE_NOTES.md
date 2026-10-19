# Đợt nâng cấp sử dụng hằng ngày

## Tính năng đi cùng nhau

- Tạm dừng/tiếp tục hàng đợi. Công việc đã bắt đầu tiếp tục; công việc đang
  chờ chỉ được lấy khi tiếp tục. Vẫn giữ giới hạn 10 việc chờ, một worker.
- Lưu lịch sử mỗi bước điều phối/thực hiện/kiểm tra và từng lượt sửa, gồm
  trạng thái, thời điểm bắt đầu/kết thúc và nội dung đã tạo. Kết quả cũ của
  vòng sửa không còn bị mất khi có kết quả mới.
- Hiển thị số bước đã xong và thời gian trên thẻ nhiệm vụ. Không ước lượng
  phần trăm hoàn thành hoặc thời gian còn lại khi chưa có cơ sở.
- Giữ yêu cầu đang soạn, chế độ AI, lựa chọn tạo sản phẩm và phiên bản gốc
  trong localStorage. Chỉ xóa nháp đã giao thành công; lỗi API giữ nháp.
- Mặc định Ollama cho lần đầu, ghi nhớ lựa chọn sau đó. Nếu OpenAI chưa có
  khóa thì chuyển sang mô phỏng có thông báo, không tự gọi nhà cung cấp phí.
- Giao diện co giãn, phần bộ nhớ/kết nối thu gọn; kết quả không bị dựng lại
  mỗi lần polling khi dữ liệu chưa đổi, giữ trạng thái đang đọc.
- Đóng kết nối SQLite khi rời context; lịch sử và thời gian được sao lưu
  cùng cơ sở dữ liệu hiện tại.

## Cập nhật

Dừng app đang chạy, mở cap-nhat.bat, chọn Y để mở lại, rồi Ctrl+F5 trên trình
 duyệt. Không cần cài thêm thư viện để sử dụng ứng dụng. Node/npm/Playwright
chỉ dành cho người phát triển chạy kiểm thử trình duyệt.

SQLite tự bổ sung các bảng task_timing và task_steps, không xóa dữ liệu
cũ. Nhiệm vụ cũ chưa có lịch sử từng bước vẫn giữ kết quả hiện có; không tự
tạo dữ liệu lịch sử giả. Tạm dừng không được giữ sau khi tắt tiến trình;
các việc chờ/dang dở vẫn được đánh dấu gián đoạn khi mở app lại.

## Kiểm chứng và giới hạn

Đã kiểm tra cục bộ: 62 unittest Python và 5 luồng Chromium trên Linux.
Luồng trình duyệt dùng ứng dụng thật với SQLite tạm và chế độ mô phỏng,
không gọi mô hình trả phí hoặc suy luận Ollama thật. CI được bổ sung kiểm
thử Chromium trên Windows/Ubuntu; chưa đồng nghĩa CI đã chạy xanh.

Lịch sử dùng thời gian UTC; trình duyệt hiển thị theo máy người dùng. Việc
bị dừng đột ngột được chốt thời gian lúc khôi phục, có thể gồm cả thời gian
app không chạy. Đây là thời gian trôi qua, không phải thời gian CPU/GPU.
Lịch sử nhiều vòng làm dữ liệu tăng; có thể tải bản sao lưu trước khi dọn.
Nháp chỉ ở trình duyệt hiện tại, chưa đồng bộ sang máy/trình duyệt khác;
không phải phần của ZIP sao lưu SQLite. Không nhập thông tin bí mật vào nháp.
