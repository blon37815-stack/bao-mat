# 0.4.1 — Timeout kết nối và văn bản dài

## Log timeout sau GET thành công

Trình duyệt giữ kết nối HTTP/1.1 để dùng lại. Nếu chưa gửi yêu cầu tiếp theo
trong 15 giây, máy chủ đóng kết nối. Trước bản vá, thư viện HTTP chuẩn ghi
`Request timed out: TimeoutError('timed out')` ngay cả khi chưa nhận yêu cầu
mới. Tab nền có thể gửi lại mỗi phút, khiến log 200 xen kẽ timeout.

Bản vá đóng yên lặng kết nối đang chờ mà chưa nhận byte đầu tiên, kể cả
khi trình duyệt hủy kết nối lúc chuyển trang (Windows có thể báo WinError
10053). Lỗi ngắt kết nối này không còn in traceback từ bước chờ.
Giữ giới hạn 15 giây và tái sử dụng kết nối GET. Yêu cầu đã gửi một phần
header/body hoặc timeout khi xử lý/ghi phản hồi vẫn đi qua bộ xử lý lỗi
chuẩn; không lọc mọi dòng timeout. Thời hạn gọi Ollama không bị thay đổi.

Có năm kiểm thử bằng socket thật: chờ kết nối trước yêu cầu, chờ sau phản
hồi keep-alive, reset kết nối, header bị gửi dở, body bị gửi dở. Trước vá
hai ca nhàn rỗi tái hiện log không mong muốn; ca reset cũng tái hiện lỗi
thoát ra bộ xử lý server trước khi bổ sung bản sửa. Sau vá cả năm đạt.

## Yêu cầu tối đa 4.000 ký tự

Ô yêu cầu có bộ đếm và cảnh báo khi chạm giới hạn, kể cả bản nháp được
khôi phục sau tải lại. Dán quá phần trống của ô sẽ được chặn và báo rõ;
giữ nguyên yêu cầu đang soạn, không lặng lẽ cắt đoạn dán. Thay một vùng đã
chọn bằng đoạn ngắn hơn vẫn được phép.

Văn bản dài nên đưa vào **Tài liệu**, lưu rồi chọn đính kèm khi giao việc.
Nút cạnh cảnh báo mở khu Tài liệu. Ô yêu cầu dùng để nói rõ hành động:

> Biên tập tài liệu đính kèm thành bản nháp hoàn chỉnh. Giữ các thông tin
> đã có, đánh dấu phần chưa có dữ liệu; không bịa kết quả hay tự thêm điều
> kiện nghiệm thu. Chỉ trả văn bản Markdown, không yêu cầu thực hiện thí
> nghiệm ngoài phạm vi biên tập.

Một báo cáo có yêu cầu dài đúng 4.000 ký tự và kết thúc giữa câu có thể
đã bị cắt ở lần dán trước. Bản vá không khôi phục được phần chưa từng được
gửi. Dùng lại tài liệu gốc đầy đủ thay vì suy đoán đoạn còn thiếu.

Hướng dẫn hệ thống của chuyên gia, kế hoạch, thực hiện và kiểm tra được
bổ sung để phân biệt yêu cầu bắt buộc với đề xuất mới. Ngưỡng/số mẫu/thời
lượng do mô hình gợi ý chưa được chốt không được tự dùng để đánh trượt bản
nháp. Phần chưa đo giữ là chưa xác minh, không bịa kết quả. Đây là điều
chỉnh lời nhắc; chưa có phép đo Ollama thật chứng minh mọi phản hồi đều
tuân thủ. Không tự chuyển một kết quả AI chưa đạt thành đã đạt.

## Cập nhật

Sao lưu dữ liệu; dừng cửa sổ app bằng **Ctrl+C** và **Y** nếu được hỏi.
Mở **cap-nhat.bat**, chọn **Y**, giữ Ollama mở, rồi **Ctrl+F5** trong trình
duyệt. Góc dưới thanh bên phải ghi **0.4.1-dev**. Nếu vừa tải mã mà chưa
khởi động lại app, tiến trình vẫn có thể dùng mã cũ.

Không có thư viện mới; API vẫn 1, schema vẫn 2. Nhiệm vụ và báo cáo cũ
không tự chạy lại hoặc được đánh giá lại. Xem cả phiên bản xuất báo cáo và
`runtime.executed_by` để phân biệt ứng dụng xuất với mã đã thực hiện nhiệm vụ.
