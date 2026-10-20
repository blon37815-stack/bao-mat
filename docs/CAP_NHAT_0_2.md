# Dự án, hồ sơ model, kiểm thử Docker và phục hồi — 0.2.0-dev

Đây là hướng dẫn các phần đã triển khai. Nền giao diện vẫn giữ các khu cũ; không tạo thêm tiến trình model cho mỗi tên bot. Bản này chưa có toàn bộ agent/lệnh ECC hoặc tự nâng cấp ứng dụng.

## Cập nhật và bắt đầu

1. Dừng app, giữ Ollama mở. Với lần đầu kéo bản này bằng updater cũ, tải bản sao lưu trong Thiết lập trước.
2. Chạy `cap-nhat.bat`, rồi `chay.bat` nếu chưa mở lại. Làm mới trang. Bản mới dùng launcher để chọn đúng môi trường phụ thuộc.
3. Vào **Thiết lập → Nền tảng bot, model và dự án**. Tạo dự án hoặc hồ sơ model khi cần; giữ mặc định nếu chưa muốn thay đổi.

Không cần thêm thư viện chạy app so với bản trước. Docker chỉ cần cho kiểm thử chức năng Python, không cần để dùng giao diện/sinh sản phẩm.

Các nút điều hướng và giao việc chỉ bật sau khi tải đủ mã giao diện. Nếu một tệp JavaScript tải thất bại, trang báo rõ **Chưa tải đủ giao diện** và hướng dẫn Ctrl+F5. Kết nối đọc được tái sử dụng để giảm số socket khi làm mới nhiều lần trên Windows.

## Hồ sơ model và từng bot

- Một hồ sơ có ID, tên hiển thị, nhà cung cấp, tên model, thời hạn mỗi lần gọi, giới hạn đầu vào theo ký tự và đầu ra theo token. Context Ollama bằng 0 giữ mặc định dịch vụ; giá trị khác chuyển thành `num_ctx`.
- Tạo hồ sơ xong, vào **Đội bot → Thiết lập bot**, chọn riêng hồ sơ dùng khi nhiệm vụ ở chế độ Ollama và khi ở chế độ OpenAI. Không tự chuyển giữa hai nhà cung cấp.
- Nhiều bot có thể trỏ cùng hồ sơ, dùng chung dịch vụ Ollama. Vẫn chỉ một nhiệm vụ chạy mỗi lúc; không tự tải/nạp nhiều model hoặc tự tối ưu RAM/VRAM.
- Lưu lại hồ sơ làm tăng revision. Nhiệm vụ mới chụp toàn bộ cấu hình; việc đã giao và lượt chạy lại giữ cấu hình đã chụp. Model mặc định từ môi trường cũng được chụp theo tên/thời hạn lúc giao.
- Không cho xóa hồ sơ riêng đang được bot sử dụng; gỡ phân công trước. Xóa hồ sơ không thay đổi cấu hình nhiệm vụ cũ. Không cho đổi nhà cung cấp của hồ sơ đang được gắn ở chế độ khác.
- Mỗi hồ sơ là thiết lập, chưa phải bằng chứng model đã tải, đáp ứng mọi khả năng hoặc đạt chất lượng. Địa chỉ dịch vụ Ollama và khóa OpenAI vẫn do môi trường máy chủ quản lý; khóa không nằm trong hồ sơ/bản chụp.

Các nguồn ECC của chuyên gia được kiểm hash theo `PROVENANCE.json`, lưu bản tham khảo đầy đủ vào nhiệm vụ và gửi bước chỉ đạo. Không nạp hook, MCP hoặc quyền shell. Tên bot có thể đổi nhưng vai trò, quyền và hạn mức vẫn do ứng dụng kiểm soát.

Git được cấu hình giữ nguyên byte cho nguồn ECC. Với checkout Windows cũ đã đổi LF thành CRLF, app kiểm hash sau khi chuẩn hóa xuống dòng và ghi cả hash checkout; thay đổi nội dung khác vẫn bị từ chối.

## Dự án và workspace

- Tạo ID/tên dự án và bộ nhớ riêng trong Thiết lập. Chọn dự án trong khung giao việc. Dự án chung tương thích với ô bộ nhớ chung cũ.
- Danh sách Công việc có bộ lọc dự án. Phiên bản sửa giữ dự án của bản gốc; chạy lại giữ cấu hình cũ. Nhiệm vụ cũ chưa có metadata được xếp vào dự án chung.
- Workspace hiện là không gian logic theo dự án/nhiệm vụ/vai trò trong SQLite: đầu vào, thiết lập, tệp, các bước và kết quả kiểm thử. Chưa tạo thư mục làm việc bền vững và bộ công cụ shell riêng cho mỗi bot.
- Khung sản phẩm có **Cấu hình và kiểm thử của công việc**, hiển thị model/revision thực tế được cấu hình và báo cáo kiểm thử. API `/api/tasks/<id>/workspace` trả metadata, lịch sử trạng thái theo vai trò và các báo cáo.
- Thư viện tài liệu vẫn dùng chung và chỉ gửi tài liệu được chọn. Dự án không phải cơ chế phân quyền nhiều người dùng. Nhiệm vụ cũ chưa lưu model được ghi rõ là chưa có dữ liệu, không suy đoán model lịch sử.

## Những lệnh đã có bộ xử lý

```text
/plan Lên kế hoạch ứng dụng ghi chú
/python Tạo CLI ghi chú dùng thư viện chuẩn và unittest
/web Tạo trang ghi chú HTML/CSS/JavaScript
/data Tạo dữ liệu ghi chú tiếng Việt
/code-review <mã-nhiệm-vụ>
/verify <mã-nhiệm-vụ>
```

`/code-review` tạo báo cáo AI từ bộ tệp đã lưu, không tạo lại bộ sản phẩm và không chạy mã. `/verify` kiểm thử sản phẩm Python đã kết thúc trong Docker và lưu báo cáo vào nhiệm vụ đó. Chế độ/nội dung của các lệnh tạo việc vẫn cần được chọn rõ trên giao diện. Lệnh không hỗ trợ như `/tdd` sẽ báo lỗi; không gửi ngầm như thể đã chạy đầy đủ quy trình ECC. Danh mục: `GET /api/commands`.

## Kiểm thử Python trong Docker

Docker Desktop trên Windows cần chế độ Linux containers/WSL2. Sau khi Docker hoạt động, tải image một lần, chủ động trên máy dùng app:

```powershell
docker pull python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
```

Trong Thiết lập, bấm **Kiểm tra Docker**. Có hai cách chạy:

- Bấm **Chạy kiểm thử Python (Docker)** trong khung công việc hoặc dùng `/verify <id>`.
- Bật tự kiểm thử trong Thiết lập rồi giao nhiệm vụ mới. Thay đổi này không ảnh hưởng việc đã giao. Lỗi unittest được chuyển về bước sửa, vẫn tối đa 2 vòng và chịu hạn mức gọi model.

Runner có các ranh giới:

- Chỉ nhận bộ tệp văn bản đã qua bảo vệ đường dẫn, không chạy mã sản phẩm trên host.
- Mạng `none`, root filesystem và source chỉ đọc, user `65534:65534`, bỏ capabilities, `no-new-privileges`.
- 1 CPU, RAM/swap tổng 256 MiB, 64 PID; vùng ghi tmpfs riêng. Đây là hạn mức container kiểm thử, không phải hạn mức CPU/RAM/GPU của Ollama.
- Thử unittest tối đa 25 giây, toàn lệnh Docker tối đa 40 giây; hủy nhiệm vụ tự đóng container. Đầu ra sản phẩm/báo cáo được giới hạn; không để stdout/stderr làm tăng bộ nhớ host vô hạn.
- Sao chép source vào vùng ghi tạm trong container; xóa môi trường tạm sau khi dừng container. Không chia sẻ thư mục ứng dụng, tài liệu khác, khóa API, Docker socket hoặc model với mã sản phẩm.
- Chưa tự cài dependency của sản phẩm; image chuẩn chỉ có thư viện Python đi kèm. Không tự pull/build image hoặc mở mạng để cài gói. `BOT_SANDBOX_IMAGE` có thể chọn image Linux đã chuẩn bị riêng; người vận hành chịu trách nhiệm chuẩn bị image tương thích.

Hiện hỗ trợ unittest ở thư mục `tests/`, hoặc thư mục gốc nếu không có `tests/`. Không tìm thấy test, 0 test, thiếu Docker/image hoặc loại web chưa hỗ trợ đều không được tính là kiểm thử đạt. Giới hạn 20 báo cáo kiểm thử mỗi nhiệm vụ; tạo phiên bản mới để kiểm tra tiếp.

Test do model tạo có thể chưa bao phủ đúng yêu cầu. “Đạt unittest” không có nghĩa đạt mọi chức năng hoặc an toàn. Chưa có runner chạy JavaScript/trình duyệt/backend tương tác của sản phẩm; xem trước web vẫn là HTML/CSS tĩnh.

## Cập nhật và phục hồi

Bộ cập nhật mới:

1. Khóa cùng dữ liệu với tiến trình app, từ chối khi app đang mở hoặc checkout có thay đổi.
2. Fetch, kiểm tra nhánh/fast-forward và quan hệ feature/main.
3. Lưu gói `data/backups/update-*.zip` (hoặc backups cạnh `BOT_DB`). Có mã theo commit, SQLite nhất quán, hash và metadata; không có `.env`, model, `.venv` hoặc Git history.
4. Giải nén mã đích ở khu thử. Nếu dependency đổi, tạo `.runtime-envs/<id>/`, cài requirements và kiểm tra gói ở đó; không sửa môi trường đang dùng.
5. Thử import, khởi tạo đồ thị và mở/migration trên bản sao SQLite. Nếu lỗi, dừng trước fast-forward, giữ mã và dữ liệu hiện tại.
6. Fast-forward mã; launcher trỏ đến môi trường đã chuẩn bị khi dependency đổi. Ghi thông tin bản trước/sau và gói phục hồi trong `data/updates/last-update.json` (hoặc updates cạnh `BOT_DB`).

Updater và launcher cùng tính hash `requirements.txt` sau khi chuẩn hóa CRLF thành LF. Git đổi kiểu xuống dòng không bị coi là thay thư viện hoặc làm môi trường đã chuẩn bị mất hiệu lực; nội dung dependency đổi vẫn được kiểm tra.

Khởi động app cập nhật schema từ 0 lên 1 bằng các bảng mới, giữ bảng/dữ liệu cũ. App từ chối cơ sở dữ liệu có `user_version` cao hơn phiên bản hỗ trợ. Thử migration trước không thay thế sao lưu hoặc kiểm thử nâng cấp thực tế.

Nếu cần phục hồi: dừng app, chạy **phuc-hoi.bat**, nhập ZIP `update-...` và một đường dẫn thư mục mới. Công cụ kiểm hash rồi khôi phục mã + SQLite vào đó; không ghi đè thư mục đang dùng. Chạy `cai-dat.bat`, rồi **chay-phuc-hoi.bat** trong bản phục hồi. BAT này đặt đúng `BOT_DB` của bản phục hồi, kể cả khi máy đang có biến trỏ tới dữ liệu cũ. Cấu hình lại bí mật qua môi trường khi cần. Bản phục hồi không có `.git`; không dùng `cap-nhat.bat` ở đó.

Phục hồi hiện có thao tác của người dùng; chưa có chuyển bản/rollback tự động hoặc cập nhật nóng. Các môi trường phụ thuộc cũ và gói phục hồi được giữ, chưa tự dọn theo dung lượng. Không sao chép model cho mỗi bot. Cần quản lý dung lượng backup và các môi trường cũ trước khi cập nhật nhiều phiên bản.

## Kiểm chứng và phần còn lại

Kiểm thử bao gồm cấu hình model bất biến, phân tách bộ nhớ/lọc dự án, nguồn ECC, hạn mức, đường dẫn, Docker không mạng/không root/chỉ đọc, hủy tác vụ vô hạn, đầu ra quá lớn, bản đích hỏng trước khi thay mã, migration trên bản sao và phục hồi nguyên vẹn vào thư mục khác. Kiểm thử trình duyệt dùng provider giả lập; không chứng minh chất lượng Ollama thật.

Cần xác nhận riêng trên Windows/Ollama thật và CI từ xa. Còn thiếu: toàn bộ agent/skill ECC, tool calling tùy ý, runner web, workspace thư mục bền vững theo bot, đánh giá model trên phần cứng đích, giới hạn tài nguyên Ollama, dọn môi trường/backup theo dung lượng và rollback tự động. Xem `NEN_TANG_BOT.md` để đối chiếu lộ trình.
