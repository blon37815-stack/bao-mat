# 0.2.0-dev — Nền cấu hình, workspace và cập nhật

- Hồ sơ model có revision, giới hạn đầu vào/đầu ra/thời hạn; phân công theo
  từng vai trò và chế độ Ollama/OpenAI, không tự chuyển nhà cung cấp.
- Dự án và bộ nhớ riêng, lọc công việc theo dự án. Snapshot lưu model,
  hướng dẫn bot, nguồn ECC, phiên bản ứng dụng và chế độ kiểm thử; chạy lại
  giữ cấu hình đã chụp. Việc cũ ghi rõ thiếu metadata, không gán ngược model.
- Nạp bản tham khảo ECC đầy đủ cho chuyên gia được chọn sau khi kiểm hash;
  không chạy hook/script. Có bộ xử lý `/plan`, `/python`, `/web`, `/data`,
  `/code-review`, `/verify`; các lệnh khác báo chưa hỗ trợ.
- Runner unittest Python trong Docker: mạng tắt, không root, nguồn/root
  chỉ đọc, 256 MiB RAM, 1 CPU, 64 PID, thời hạn và đầu ra có giới hạn.
  Chạy riêng hoặc bật cho nhiệm vụ mới; lỗi được đưa vào vòng sửa. Thiếu
  Docker/test hoặc loại tệp chưa hỗ trợ không được ghi là kiểm thử đạt.
- Workspace logic theo nhiệm vụ/vai trò trong SQLite, báo cáo thực thi và
  cấu hình ngay trong khung sản phẩm. Vẫn dùng nền giao diện và điều hướng cũ.
- Updater khóa cùng app, lưu mã/SQLite trước cập nhật, thử bản đích và
  migration trên bản sao trước fast-forward. Dependency đổi được chuẩn bị
  trong môi trường riêng; launcher giữ `.venv` cũ. Có `phuc-hoi.bat` tạo
  thư mục phục hồi mới và BAT khởi động dùng đúng dữ liệu của bản phục hồi.
- Tương thích Git Windows: giữ nguyên nguồn ECC, chấp nhận chuyển đổi
  CRLF/LF đã kiểm hash và ghi nhận hash checkout; sửa nội dung vẫn bị chặn.
- Nháp chỉnh sửa được lưu trước khi kiểm tra nguồn qua mạng, tránh mất
  liên kết bản gốc khi người dùng gõ và làm mới trang ngay sau khi bấm sửa.
- Đối chiếu dependency chuẩn hóa LF/CRLF giữa updater và launcher; đổi
  xuống dòng không tạo lại môi trường hoặc làm cấu hình môi trường lệch hash.
- Ctrl+C tạm dừng hàng đợi, phát tín hiệu hủy việc và giữ trạng thái gián
  đoạn để chạy lại; asset/API no-store giảm việc dùng nhầm giao diện cũ.

Kiểm chứng cục bộ ngày 20/10/2026: **144 unittest đạt** với LangGraph thật,
trong đó 4 ca thực thi Docker thật và các ca provider giả lập; **19 luồng
Chromium đạt** trên Linux. Đã thử hủy vòng lặp vô hạn, chặn mạng/ghi nguồn,
stdout quá lớn, không có test, model đổi khi việc chờ, migration trên bản
sao, mã đích hỏng và khôi phục source/SQLite; đã thử tạo môi trường riêng
khi requirements đổi. `pip check`, cú pháp Python/JavaScript và Prettier đạt.
Thêm job CI Ubuntu cho Docker; chưa xác nhận kết quả CI từ xa hoặc chạy
Windows/Ollama thật, chưa gộp PR.

Chưa có toàn bộ ECC, runner web, thư mục bền vững/công cụ shell cho từng
bot, tự tối ưu RAM/VRAM của Ollama, dọn môi trường cũ theo dung lượng hoặc
rollback tự động. Hướng dẫn: [docs/CAP_NHAT_0_2.md](docs/CAP_NHAT_0_2.md).

Các ghi chú dưới đây mô tả những đợt trước.

# Đợt tách công việc và xóa từng việc

- Công việc có mục/biểu tượng riêng trên thanh bên, không đặt danh sách
  hoặc ô thống kê trong khu Trao đổi. Giao việc mới mở kết quả đang xử lý.
- Ô thống kê mở bộ lọc; biểu tượng bot mở thiết lập; biểu tượng mở rộng và
  đóng khung kết quả có thao tác thực. Không hiện nút đóng/mở rộng khi trống.
- Danh sách 20 dòng, chỉ tải khi mở, không kèm kết quả dài/bộ nhớ/hướng dẫn
  bot. Giữ dòng không đổi khi lọc/làm mới. Số đo/bot không polling liên tục
  khi khu tương ứng bị ẩn; chỉ tự tải kết quả của việc đang xem còn chạy.
- Nút Xóa cạnh phần tải ở dòng công việc và khung kết quả. Có xem trước,
  xác nhận, bản sao SQLite lưu trước xóa và kiểm tra dữ liệu lại trong
  transaction. Chặn việc đang chạy/chờ hoặc luồng hủy chưa dừng hẳn.
- Xóa đúng một việc và dữ liệu riêng, giữ các phiên bản khác, tài liệu và
  thiết lập chung. Bản sửa vẫn có diff bằng nguồn đã chụp; liên kết gốc đã
  xóa được ghi rõ. Có thể tạo lượt chạy lại mới nếu lượt cũ đã xóa.
- Đóng/xóa kết quả đang xem giải phóng nội dung và iframe. Xóa không tự
  thu nhỏ tệp SQLite hoặc xóa bản sao lưu; các bản sao vẫn chiếm dung lượng.

Kiểm chứng cục bộ: 117 unittest Python và 16 luồng Chromium trên Linux,
provider giả lập, LangGraph thật. Kiểm tra lỗi sao lưu/fsync, dữ liệu đổi
trong lúc sao lưu, thời hạn/token, xóa việc liên kết, khôi phục ZIP, giữ
thư viện, phân trang nhẹ, bấm trực tiếp biểu tượng và bố cục điện thoại.
Chưa kiểm chứng Ollama thật trên Windows hoặc CI remote xanh; chưa gộp PR.
Cập nhật bằng cap-nhat.bat rồi Ctrl+F5. Không thêm phụ thuộc chạy app.

# Đợt giao diện không gian làm việc trước đó

- Thay trang dài bằng thanh bên với 5 khu: Làm việc, Đội bot, Tài liệu,
  Tài nguyên, Thiết lập. Tổng quan nhiệm vụ và hàng đợi lấy số liệu thật.
- Hiển thị đầy đủ 9 thành phần hiện có, nhiệm vụ đang xử lý và vai trò;
  cho đổi tên/hướng dẫn riêng của 5 chuyên gia và 3 bot thực thi. Thiết
  lập được giữ trong SQLite, chụp cho nhiệm vụ mới; chạy lại giữ bản cũ.
- Khung sản phẩm bên phải: đọc kết quả, duyệt tệp, sửa văn bản, bỏ tệp
  khỏi bản sửa và lưu phiên bản mới. Giữ bản gốc, 0 lượt AI cho lưu thủ
  công, luôn Cần bạn xem. Không chạy mã hoặc tự duyệt phiên bản mới.
- Xem trước HTML/CSS tĩnh có khổ điện thoại, CSS liên kết trong bộ tệp,
  iframe sandbox không quyền và CSP chặn mạng; lọc nội dung chủ động và
  URL ngoài. Chưa chạy JS/backend hoặc xác minh chức năng sản phẩm.
- Thư viện tài liệu: nhập TXT/Markdown/JSON UTF-8, thêm/sửa/tìm/xóa có xác
  nhận. Chọn tài liệu khi giao việc; giữ bản nội dung lúc gửi trong lịch
  sử. Có nút xóa bộ nhớ chung; không xóa bản đã gửi hoặc bản sao lưu.
- Bản sao lưu SQLite chứa thư viện, thiết lập bot và bản chụp theo nhiệm
  vụ. Dọn nhiệm vụ cũ xóa các bản chụp riêng, giữ thư viện/thiết lập chung.

Kiểm chứng cục bộ: 110 unittest Python và 12 luồng Chromium trên Linux,
provider giả lập, LangGraph thật. Đã thử nhập/đính kèm/xóa tài liệu, lưu
thiết lập qua reload, chỉnh tệp qua polling, giữ bản gốc, preview không
chạy script/không gọi URL ngoài và bố cục 390px không tràn ngang. Đã xem
ảnh bố cục desktop. Chưa thử Ollama thật trên Windows hoặc xác nhận CI
remote xanh. Chưa gộp PR. Không thêm phụ thuộc chạy app trong đợt này.

Cập nhật một lần bằng cap-nhat.bat, mở lại và Ctrl+F5. Các bảng mới tự thêm
vào SQLite; nhiệm vụ, sản phẩm và bộ nhớ cũ được giữ.

# Đợt chuyên gia ECC, phân công và tài nguyên

- Thêm 5 hồ sơ chuyên gia thích ứng từ ECC: lập kế hoạch, kiến trúc,
  Python, web và dữ liệu JSON. Một chuyên gia tạo bản giao việc cho ba
  vai trò cũ; lưu chỉ đạo trong kết quả, lịch sử và báo cáo. Có thể chọn
  đội cơ bản. Không thay đổi mô hình đang dùng hoặc chạy plugin ECC.
- Giữ nguồn vai trò ở third_party/ecc, ghim commit và SHA-256 từng tệp,
  kèm LICENSE MIT. App dùng bản hướng dẫn tiếng Việt đã điều chỉnh;
  không tự nạp hook, MCP hoặc quyền công cụ của kho upstream.
- Giới hạn riêng 1–100 lượt gọi/nhiệm vụ, mặc định 20, tính cả chuyên gia
  và vòng sửa. SQLite chặn nguyên tử trước lời gọi; hết mức chuyển Cần
  bạn xem, giữ kết quả từng phần và giải phóng worker. Chạy lại cho nhập
  giới hạn mới, không sửa lịch sử hoặc tự nâng mức.
- Lưu chính sách mặc định và số việc chờ 1–10; giữ sau khởi động và trong
  bản sao lưu. Thay mặc định không đổi hạn mức các nhiệm vụ đã giao.
- Bảng tài nguyên đọc CPU/RAM máy chủ và NVIDIA nếu có nvidia-smi, cache
  ngắn và thời hạn lấy GPU 1 giây. Thiếu số liệu ghi chưa đọc được; đây
  là quan sát, chưa áp hạn mức cứng CPU/RAM/GPU hoặc dừng Ollama.
- Bộ đánh giá mặc định dùng chuyên gia theo mẫu; --expert none cho phép
  so sánh với đội cơ bản. Chưa có số đo chất lượng mô hình thật để kết
  luận tầng chuyên gia giúp tăng tỷ lệ đạt.

Kiểm chứng cục bộ: 105 unittest Python và 8 luồng Chromium trên Linux,
LangGraph 1.2.16 thật, provider giả lập. Có kiểm tra giới hạn đồng thời,
hết lượt giữa bộ tệp, chạy lại với mức mới, chính sách sau nạp lại và bảo
vệ API. RAM Linux đọc được; trường hợp không có GPU hiển thị đúng. Chưa
kiểm chứng số đo phần cứng Windows/NVIDIA hoặc suy luận Ollama thật; chưa
xác nhận CI remote xanh, chưa gộp PR hoặc gắn thẻ.

Cập nhật: dừng app, chạy cap-nhat.bat, chọn Y mở lại và Ctrl+F5 trình
duyệt. Updater cài thêm psutil 7.2.2 từ requirements.txt. SQLite tự thêm
task_assignment/resource_policy; giữ nhiệm vụ cũ và bộ nhớ hiện có.

# Đợt sinh từng tệp và đánh giá chất lượng

- Mẫu JSON/Python/web sinh nội dung từng tệp; ứng dụng ghép bộ sản phẩm.
  Lỗi có đường dẫn chỉ sửa đúng tệp, giữ tệp khác. Nhận xét AI chung sửa
  cả manifest; tối đa hai vòng sửa. Nhiệm vụ tự nhập vẫn dùng bundle cũ.
- Lưu cách sinh và số yêu cầu mô hình; giữ kết quả đã sinh nếu hủy/lỗi ở
  tệp sau. Nhiều tệp có thể tăng số lần gọi và thời gian xử lý.
- Bộ đánh giá 9 ca cố định, SQLite tạm, tỷ lệ trước/sau sửa, thời gian và
  số yêu cầu. danh-gia.bat chạy data_basic 10 lần khi người dùng chọn Y.
  Mục tiêu JSON >=8/10 chưa được kiểm chứng bằng Ollama thật.
- Footer/API version chụp commit/dirty/hash lúc khởi động, giúp phân biệt
  app đang chạy với mã vừa tải. Báo cáo ghi commit của ứng dụng xuất báo cáo.
- README đã được viết lại thành mô tả hiện tại; EVALUATION.md hướng dẫn
  đo, REVIEW.md nêu phần cần rà soát và các giới hạn.

Kiểm chứng cục bộ: 94 unittest Python và 7 luồng Chromium trên Linux.
LangGraph 1.2.16 thật được dùng; provider được giả lập. Chưa có số đo Ollama
8/10, kiểm chứng suy luận/CPU Windows hoặc xác nhận CI remote xanh.
Chưa gộp PR, chưa gắn thẻ phát hành, chưa chạy mã trong Docker.

# Đợt ổn định web, thời hạn và dữ liệu trước đó

- Mẫu web kiểm tra liên kết HTML thực tới style.css/app.js; không tính chữ
  trong chú thích hoặc liên kết ngoài. Đây vẫn là kiểm tra tĩnh.
- OLLAMA_TIMEOUT_SECONDS đặt thời hạn tổng mỗi lượt, mặc định 600, phạm vi
  1–7200 giây. Hủy vẫn giải phóng tiến trình HTTP do app quản lý.
- Dọn nội dung lịch sử hoặc nhiệm vụ cũ độc lập: xem trước, nhập DỌN, tự
  lưu ZIP trước khi xóa; giữ phiên bản/chạy lại và bộ nhớ chung. Không tự
  dọn theo lịch; chưa thu nhỏ tệp SQLite, bản sao vẫn chiếm dung lượng.
- App.js, HTML và CSS được định dạng; bổ sung Prettier chỉ cho phát triển,
  có kiểm tra định dạng trên CI. Người dùng Windows không cần cài Node.

Kiểm chứng cục bộ: 80 unittest Python và 6 luồng Chromium trên Linux với
SQLite tạm. Có thử thời hạn bằng máy chủ streaming giả lập; chưa chạy
suy luận Ollama thật. Chưa xác nhận CI Windows/Ubuntu xanh hoặc CPU Ollama
giảm trên Windows sau hủy; chưa gộp PR. Khi gộp chọn Create a merge commit.
Chưa có chạy mã sản phẩm trong Docker/sandbox hoặc kiểm thử chức năng của
web do mô hình tạo.

# Đợt nâng cấp sử dụng hằng ngày trước đó

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
