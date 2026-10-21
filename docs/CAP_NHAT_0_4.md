# 0.4 — Tạo đủ tệp và xem bằng chứng

Đợt này tập trung vào lỗi sản phẩm chỉ có README. Giữ các khu giao diện và
quyền/hàng đợi/model cũ; không tự tải model, tăng lượt gọi hoặc bật Docker.
API vẫn là 1, dữ liệu vẫn schema 2; không cần tạo lại dữ liệu.

## Cập nhật một lần trên Windows

1. Tải bản sao dữ liệu trong Thiết lập và giữ ZIP ngoài thư mục dự án.
2. Dừng cửa sổ app bằng **Ctrl+C**, nhập **Y** nếu được hỏi.
3. Mở **cap-nhat.bat**, chọn **Y** để chạy lại. Giữ Ollama mở.
4. Vào `http://127.0.0.1:8000/#workspace`, nhấn **Ctrl+F5**. Kiểm tra góc
   dưới thanh bên có phiên bản **0.4.0-dev**.

Các thư viện không đổi. Nếu cần quay lại, dùng gói sao lưu trước cập nhật
và **phuc-hoi.bat**, phục hồi sang thư mục mới như hướng dẫn 0.2/0.3.

## Yêu cầu tự nhập có danh sách tệp

Bật **Tạo bộ mã nguồn có thể tải ZIP**, mở **Bộ tệp và tiêu chí bàn giao**:

- **Ứng dụng:** phải có mã nguồn thực tế ngoài tài liệu và kiểm thử.
- **Dữ liệu:** phải có tệp dữ liệu như JSON/CSV, không chỉ hướng dẫn.
- **Tài liệu:** cho phép sản phẩm chỉ có Markdown khi bạn chủ động chọn.

Bạn có thể nhập tệp bắt buộc, mỗi dòng một đường dẫn tương đối. Ví dụ cho
công cụ Excel tùy chỉnh:

```text
src/main.py
requirements.txt
tests/test_main.py
README.md
```

Các tệp này bắt buộc phải tồn tại và có nội dung. Tệp requirements.txt cho
dự án không có thư viện ngoài có thể ghi chú bằng một dòng bắt đầu với `#`.
Mô hình nhận nội dung từng tệp riêng; mã trong README không thay thế tệp.
Tên tệp và dung lượng vẫn chịu giới hạn Windows/an toàn có sẵn.

Nếu để trống, Điều phối phải trả kế hoạch và danh sách tối đa 12 tệp. Ứng
dụng kiểm danh sách, cho lập lại một lần khi sai, rồi chốt vào nhiệm vụ.
Danh sách không hợp lệ sau hai lần sẽ dừng ở **Cần bạn xem**, chưa gọi bước
sinh tệp. Danh sách do người dùng chỉ định có tối đa 30 tệp.

Mẫu web/Python/JSON giữ các tệp bắt buộc của mẫu; tệp bạn nhập chỉ bổ sung.
Phiên bản sửa không được loại bỏ tiêu chí gốc hay đổi loại sản phẩm đã biết.
Để đổi loại hoặc mẫu, tạo nhiệm vụ độc lập. Việc cũ chưa lưu loại/danh sách
được ghi chưa xác minh; khi sửa, bạn có thể chọn loại và bổ sung danh sách.
Không gán ngược kết quả kiểm chứng mới vào lịch sử.

Ước tính lượt đầu gồm kế hoạch, từng tệp, kiểm tra và chuyên gia nếu có.
Đây là ước tính, không phải số token/chi phí; lập lại kế hoạch và các vòng
sửa cần thêm lượt. Hết ngân sách thì dừng và giữ phần đã có, không tự tăng.

## Bằng chứng trên bàn làm việc

Mở một sản phẩm đã dừng, xem **Chất lượng bộ tệp**:

1. **Bộ tệp:** có đủ tệp bắt buộc, không rỗng, đúng các tiêu chí mẫu được hỗ trợ.
2. **Cú pháp:** Python/JSON/JavaScript khi có Node; ghi rõ tệp bỏ qua.
3. **Chức năng:** chỉ ghi đã chạy khi có báo cáo unittest Docker tương ứng
   với chính bộ tệp đó và có ít nhất một ca thực sự chạy.

Ý kiến AI được hiển thị riêng. Đủ tệp hoặc đạt cú pháp không chứng minh
chương trình đáp ứng mọi yêu cầu. `completed` vẫn có thể là kết thúc luồng
AI + kiểm tra tĩnh; đọc dòng **chưa kiểm thử chức năng** nếu Docker chưa chạy.

Nút **Kiểm tra lại** chỉ kiểm tra tĩnh; không chạy sản phẩm. Chạy Docker
bằng nút trong **Cấu hình và kiểm thử của công việc**, hoặc chủ động bật tự
kiểm thử trong Thiết lập trước khi giao nhiệm vụ mới. Không cài thư viện
ngoài trong container, không tải image và không chạy mã trên máy thật khi
Docker thiếu. Dự án cần openpyxl/pandas có thể chưa chạy được bằng image
Python chuẩn hiện tại; báo cáo sẽ nêu lỗi, không tự cài thư viện qua mạng.

**Tải bằng chứng (.json)** chứa danh sách, kết quả, thời điểm, nguồn ứng
dụng và SHA-256 bộ tệp. Báo cáo Docker cũ thiếu hash hoặc không khớp nội
dung không được dùng để xác nhận bản hiện tại. ZIP chưa đạt vẫn tải được
để bạn kiểm tra, nhưng được ghi **Tải bộ tệp chưa đạt**; tải được ZIP không
có nghĩa sản phẩm hoàn thành.

Duyệt kết quả không được bỏ qua tệp thiếu, tệp bắt buộc rỗng, lỗi cú pháp
đã phát hiện hoặc báo cáo Docker thất bại gắn đúng bộ tệp. Duyệt thủ công
vẫn chỉ là quyết định của bạn, không biến phần chưa kiểm thử thành đã đạt.

## Bổ sung tệp thiếu mà giữ bản gốc

Nếu danh sách có tệp thiếu/rỗng, bấm **Nhờ bot bổ sung tệp thiếu**. Ứng dụng
điền yêu cầu cho phiên bản mới; bạn xem rồi bấm **Giao nhiệm vụ**. Nhiệm vụ
mới giữ bản chụp các tệp cũ, sinh các tệp thiếu và kiểm tra toàn bộ bộ tệp.
Các tệp đã có không bị sinh lại trong chế độ này, kể cả khi AI muốn sửa
tệp khác. Khi cần thay đổi ngoài phạm vi, luồng dừng để bạn dùng **Nhờ bot
chỉnh tiếp** hoặc **Yêu cầu chỉnh sửa** đầy đủ. Không ghi đè bản gốc.

## Đo chất lượng trên Ollama thật

Bộ đánh giá có 12 ca, thêm yêu cầu tự nhập tự lập danh sách và danh sách do
người dùng chỉ định. Mặc định chỉ liệt kê; dùng SQLite tạm, không sửa dữ
liệu app. Xem [EVALUATION.md](../EVALUATION.md). Ví dụ:

```powershell
.\.venv\Scripts\python.exe evaluate.py --suite custom
.\.venv\Scripts\python.exe evaluate.py --case custom_cli_auto --repeat 10 --run
.\.venv\Scripts\python.exe evaluate.py --suite python --run --sandbox
```

Dòng cuối yêu cầu Docker/image đã sẵn sàng. Không dùng tỷ lệ kiểm thử ứng
dụng với provider giả lập để suy ra tỷ lệ thành công của qwen3:4b. Chưa có
số đo Ollama thật cho bản này; model nhỏ vẫn có thể viết sai chức năng dù
đã đủ tệp. Web chưa có runner trình duyệt cho sản phẩm sinh ra; unittest
do chính mô hình tạo cũng chưa thay thế bộ nghiệm thu độc lập từ yêu cầu.
