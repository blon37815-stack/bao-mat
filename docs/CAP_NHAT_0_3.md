# 0.3 — Quyền công cụ, nhật ký và đề xuất nâng cấp

Bản này giữ các khu **Trao đổi, Công việc, Đội bot, Tài liệu, Tài nguyên, Thiết lập**. Model, tài liệu và công việc cũ tiếp tục được giữ; không cần tải lại model Ollama.

## Cập nhật trên Windows

1. Tải một bản sao dữ liệu từ Thiết lập trước lần cập nhật đầu tiên. Giữ ZIP ở ngoài thư mục dự án.
2. Dừng cửa sổ app bằng **Ctrl+C**, nhập **Y** nếu Windows hỏi dừng batch.
3. Mở **cap-nhat.bat**, chọn **Y** để chạy lại. Giữ Ollama đang mở.
4. Mở `http://127.0.0.1:8000/#workspace`, nhấn **Ctrl+F5**. Phiên bản hiển thị là `0.3.0-dev`.

Bộ cập nhật hiện có sao lưu mã/SQLite và thử migration trên bản sao. Lần mở app mới chuyển schema 0/1 lên **2**. App cũ không mở được dữ liệu schema 2: nếu cần quay lại, dùng **phuc-hoi.bat** với gói trước cập nhật, phục hồi sang thư mục mới. Không chép mã cũ đè lên dữ liệu mới.

## Xem và chỉnh quyền bot

Vào **Đội bot → Công cụ và phạm vi**, hoặc **Thiết lập bot**:

- Chuyên gia ECC và Điều phối: đọc dữ liệu trong công việc và gọi model.
- Thực hiện: thêm quyền lưu bộ tệp và soạn đề xuất nâng cấp.
- Kiểm tra: thêm kiểm tra cú pháp và chạy unittest Python trong Docker.
- Quản lý tài nguyên: chạy bằng mã, giữ hàng đợi và hạn mức; không gọi AI.

Chỉ bật/tắt trong danh sách công cụ đã triển khai của vai trò. Không cấp shell tùy ý, quyền đọc tệp máy chủ hoặc quyền tự ghi vào mã ứng dụng. Các hướng dẫn ECC/tài liệu/model không thay đổi được danh sách quyền.

Quyền được kiểm tra trong dispatcher trước thao tác. Công việc mới giữ bản chụp quyền; bật quyền sau đó không mở thêm quyền cho việc đã giao. Tắt quyền sẽ chặn lần dùng tiếp theo, kể cả việc cũ, nhưng không cưỡng bức dừng một công cụ đã chạy. Việc bị chặn giữ kết quả trước đó và chuyển sang **Cần bạn xem**. Bản cũ được chuyển đổi có bộ quyền mặc định được chụp riêng, không gán ngược model lịch sử.

Model và giới hạn vẫn dùng hồ sơ trong Thiết lập. Đây là các vai trò được điều phối, chưa phải mỗi thẻ bot có một tiến trình/model độc lập hoặc vòng tool calling tự do. Chất lượng model trên máy bạn vẫn cần đo riêng.

## Nhật ký thao tác

Vào **Tài nguyên → Nhật ký thao tác và quyền công cụ**, hoặc mở công việc → **Cấu hình và kiểm thử → Xem nhật ký thao tác**.

- Lọc công việc đang xem, quyết định hoặc chuyển trang 50 sự kiện.
- Mỗi sự kiện ghi vai trò, công cụ, đường dẫn, thời điểm, thời lượng, quyết định và kết quả.
- **Được phép** chỉ có nghĩa quyền đã được kiểm tra. Phải đọc kết quả bên cạnh: đã hoàn tất, kiểm tra đạt, chưa đạt, chưa hỗ trợ, bị gián đoạn hoặc hết hạn mức.
- Không ghi prompt, nội dung tệp, phản hồi model, khóa hoặc chuỗi lỗi provider vào nhật ký công cụ. Tên đường dẫn vẫn được lưu.
- Tối đa **500 sự kiện/công việc**, **5000 sự kiện toàn ứng dụng**; sự kiện cũ tự được bỏ. Không phải nhật ký chống chỉnh sửa hay lưu giữ vĩnh viễn.
- Xóa một công việc cũng xóa nhật ký riêng của việc đó, sau bước sao lưu có sẵn. Nhật ký từ chối/duyệt đề xuất ở cấp ứng dụng được giữ theo hạn mức chung.

Kiểm thử thiếu Docker hoặc loại chưa hỗ trợ ghi **Cần chú ý**, không ghi kiểm thử đạt. Khi khởi động lại, thao tác chưa kết thúc được đánh dấu gián đoạn. Bản sửa tệp thủ công ghi người thực hiện là **Bạn** và vẫn tạo phiên bản riêng.

## Đề xuất nâng cấp để duyệt

Vào **Thiết lập → Đề xuất nâng cấp ứng dụng**. Có thể mở từ khung kết quả bằng **Đề xuất nâng cấp từ bộ tệp này**.

1. Chọn mã công việc đã có bộ tệp sửa ứng dụng, nhập tên rồi bấm **Tạo bản sao và đề xuất**. Không dùng mô phỏng. Tệp đề xuất phải là mã nguồn gốc, `tests/`, `docs/` hoặc `requirements.txt`; không dùng đường dẫn thoát thư mục, `.env`, `data/`, `.git` hoặc nguồn ECC.
2. Hệ thống tạo bản **base/** và **candidate/**, ghép các tệp được đề xuất vào bản ứng viên, lưu patch và kết quả kiểm tra cú pháp. Tệp không được đề xuất giữ nguyên; hiện chưa đề xuất xóa/đổi tên tệp.
3. Bấm **Xem thay đổi**, đọc diff và kết quả. Kiểm tra cú pháp chưa đạt hoặc mã nguồn gốc đã đổi thì chưa được duyệt. Có thể từ chối hoặc tạo bản đề xuất mới.
4. **Duyệt** chỉ lưu quyết định. Không áp dụng patch, cài thư viện, chạy mã hay triển khai ứng dụng mới. Đây chưa phải bot tự sửa và tự nâng cấp hoàn toàn.
5. Tải ZIP có bản gốc, bản ứng viên và patch; kiểm thử trong checkout/môi trường cô lập riêng. Khi bản mới đã được kiểm chứng và đưa vào nhánh cập nhật, dùng quy trình sao lưu/cap-nhat hiện có để cài.

Bản sao chỉ gồm mã nguồn được chọn, không có dữ liệu người dùng, `.env`, môi trường Python, node_modules, trọng số model hoặc Git history. Bản gốc giới hạn 500 tệp/16 MB; tối đa 10 đề xuất. **Xóa bản đề xuất** xóa dữ liệu bản sao của nó, giữ công việc và ứng dụng đang chạy.

ZIP nguồn đầy đủ được giữ trong SQLite; thư mục `data/proposals/<id>/` là bản dựng lại để đối chiếu. Vì vậy bản sao SQLite và gói phục hồi hiện có chứa cả đề xuất; sau phục hồi có thể dựng lại thư mục này. Kiểm tra hash phát hiện tệp bản sao bị sửa. Hạn mức không thay thế theo dõi dung lượng ổ đĩa; xóa không tự thu nhỏ tệp SQLite ngay.

## Kiểm chứng và giới hạn

Các ca tự động kiểm tra chặn sai vai trò, thu hồi quyền, bản chụp bất biến, giới hạn lượt gọi, log không lưu nội dung/khóa, migration giữ dữ liệu, bản sao/patch, từ chối cú pháp sai/mã gốc cũ, sửa bản sao bị phát hiện, khôi phục đề xuất từ backup và quy trình giao diện. Xem RELEASE_NOTES.md để biết kết quả thực tế của bản bàn giao.

Kiểm tra cú pháp của đề xuất không phải toàn bộ kiểm thử ứng dụng ứng viên. Kết quả Docker của công việc gốc được lưu tham khảo, không được coi là kiểm thử đã chạy trên toàn bộ bản ứng viên. Chưa có áp dụng patch tự động, PR do bot tự tạo, runner web, rollback tự động hoặc toàn bộ ECC. Chưa xác nhận chất lượng Ollama và thao tác nâng cấp trên máy Windows của bạn.
