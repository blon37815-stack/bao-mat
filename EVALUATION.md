# Đánh giá chất lượng sinh sản phẩm

Từ 0.2, mỗi lượt đánh giá cũng chụp hồ sơ model và nguồn ECC như nhiệm vụ
mới, lưu metadata trong báo cáo. CLI vẫn dùng SQLite tạm và mặc định không
chạy sản phẩm; cấu hình Docker trong app không được tự lấy vào bộ đánh giá.
Runner Python trong ứng dụng được mô tả ở docs/CAP_NHAT_0_2.md.

Bộ đánh giá có 12 ca cố định trong evaluation_cases.py, gồm JSON cơ bản,
Unicode, escaping; Python cơ bản, lưu trữ, Unicode; web ghi chú, mobile,
tìm kiếm; thêm 3 ca yêu cầu tự nhập: CLI tự lập danh sách, CLI với danh sách
người dùng chỉ định và people.json. Các ca có tên tệp trong yêu cầu được đối
chiếu độc lập với danh sách AI đề xuất. Mặc định chỉ kiểm tra tĩnh; không
chứng minh các tính năng được mô tả hoạt động.

## Chạy và so sánh

Mặc định chỉ liệt kê, không gọi Ollama hoặc thay đổi dữ liệu người dùng:

```powershell
.\.venv\Scripts\python.exe evaluate.py
```

Chạy 10 lượt một ca để đo mục tiêu ít nhất 8 lượt đạt:

```powershell
.\.venv\Scripts\python.exe evaluate.py --case data_basic --repeat 10 --run
```

Chạy một lần cả 12 ca hoặc 10 lần mỗi ca JSON:

```powershell
.\.venv\Scripts\python.exe evaluate.py --suite all --run
.\.venv\Scripts\python.exe evaluate.py --suite data --repeat 10 --run
```

Lệnh thứ hai chạy 30 nhiệm vụ, không phải 10. Mỗi nhiệm vụ có nhiều lần gọi
mô hình và có thể cần hai vòng sửa. Giữ Ollama mở, dừng app/phiên chat khác
để giảm nhiễu. Không tự tải mô hình; cần Ollama/api/tags xác nhận mô hình
đã có. Web cần Node để kiểm tra JS, thiếu thì dừng trước khi suy luận.

Dùng cùng ca, số lượt và máy; đổi OLLAMA_MODEL trước khi đo mô hình khác.
Chỉ dùng mô hình đã tải và vừa RAM. Ví dụ qwen2.5-coder:7b là lựa chọn để
so sánh khi máy đủ tài nguyên, chưa được đo ở đây. Không tự chuyển sang
OpenAI hoặc gọi API trả phí.

Mặc định CLI dùng --expert auto và --call-limit 20, gồm lời gọi chuyên gia
ECC. Thêm --expert none để so sánh với đội cơ bản, hoặc chọn planner,
architect, python, web, data. Ngân sách được ghi trong báo cáo; hết mức là
chưa đạt chứ không tự tăng. Chuyên gia thêm một lời gọi nhưng vẫn dùng mô
hình bạn chọn. Các kiểm thử gọi helper trực tiếp có thể dùng đội cơ bản để
giữ điều kiện đối chiếu.

## Ý nghĩa kết quả

Từ 0.4 có thể dùng `--suite custom` để đo ba ca tự nhập. Muốn chạy unittest
Python trong Docker, thêm `--sandbox`, ví dụ:

```powershell
.\.venv\Scripts\python.exe evaluate.py --case custom_cli_auto --repeat 10 --run --sandbox
```

Docker Linux và image cấu hình phải có sẵn; CLI kiểm tra trước khi gọi mô
hình. Không tự cài thư viện trong image hoặc chạy mã trên máy thật. Khi
chọn `--sandbox`, lượt chỉ đạt nếu kiểm thử Docker thực sự đạt; JSON/web
không có unittest sẽ ghi chưa hỗ trợ và không đạt điều kiện đó.

Báo cáo JSON nằm trong data/evaluations (hoặc --output đường-dẫn-mới).
Không ghi đè báo cáo đã tồn tại. Mỗi lượt dùng nhiệm vụ/memory trống trong
SQLite tạm; app.DB được khôi phục sau khi đo. Không truy cập SQLite người
dùng. Chỉ `--sandbox` mới chạy chương trình sản phẩm trong Docker.

- passed: bộ tệp cuối đủ tiêu chí tĩnh, cú pháp được kiểm tra đạt và luồng
  kết thúc completed; khi chọn `--sandbox` còn cần Docker đạt. AI tự đánh
  giá đạt riêng không đủ.
- first_pass: bộ tệp ở lượt thực hiện đầu đã đạt tiêu chí tĩnh; không phải
  bảo đảm chức năng hay AI review đạt ngay.
- issues, checked, skipped: lỗi cuối và phạm vi kiểm tra.
- calls: số yêu cầu provider đã thử, có thể gồm yêu cầu lỗi/hủy; không phải
  số token hoặc chi phí.
- seconds: thời gian toàn lượt, gồm kiểm tra và các vòng sửa.
- requirements/content_sha256: danh sách cuối đã chốt và dấu nội dung bộ
  tệp; execution chứa báo cáo chạy nếu có. sandbox_requested ghi lựa chọn,
  functional_tests chỉ bật khi ít nhất một lượt thực sự chạy hơn 0 ca;
  đọc từng execution để biết ca nào đạt/chưa đạt.
- summary theo ca: số lượt, tỷ lệ cuối đạt, số lượt đầu đạt, thời gian trung
  vị. target_met chỉ có giá trị khi ca JSON có ít nhất 10 lượt; dưới 10 là
  null, không suy diễn đạt mục tiêu từ vài lần thử.

Hai ca JSON bổ sung kiểm tra chuỗi Unicode và content chứa cả xuống dòng
thật lẫn dấu ngoặc kép sau parse. Tiêu chí chuẩn vẫn gồm đủ 3 tệp, 3 ghi chú,
id duy nhất và các trường đúng định dạng. Không kiểm chứng mọi yêu cầu ngữ
nghĩa của prompt hoặc nội dung README, DOM/CSS, chức năng Python/web.

Checkpoint sau mỗi lượt; Ctrl+C đóng yêu cầu đang gọi và lưu báo cáo trạng
thái interrupted với kết quả đã có. Mã thoát 0 khi mọi lượt đạt, 1 khi có ca
chưa đạt, 130 khi ngắt; lỗi cấu hình/thiếu Ollama dùng lỗi CLI. Tỷ lệ 8/10
là ngưỡng nghiệm thu đề xuất, chưa phải số đo đã đạt trên qwen3:4b.

## Kiểm chứng trong repository

Unittest chạy LangGraph thật, giả lập phản hồi provider để kiểm tra ghép
tệp, chỉ sửa tệp lỗi, hủy giữa tệp, giữ escape, đếm yêu cầu và cô lập dữ liệu.
Chromium dùng app thật và provider fixture để tải bộ JSON đủ 3 tệp. Đây là
kiểm thử ứng dụng, không thay thế chạy evaluate.py với Ollama thật.
