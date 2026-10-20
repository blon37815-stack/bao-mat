# Bao Mat — Đội bot

Ứng dụng web tiếng Việt chạy cục bộ: giao việc, theo dõi **Điều phối → Thực
hiện → Kiểm tra**, giữ lịch sử và tải sản phẩm. LangGraph điều phối các vai
trò; SQLite lưu dữ liệu. Ollama mặc định dùng `qwen3:4b` trên cùng máy.

Nhiệm vụ mới có thể dùng một chuyên gia cấp trên thích ứng từ ECC để giao
việc cho ba vai trò. Bộ quản lý phân công và giới hạn lượt gọi do mã thực
thi; bảng tài nguyên đọc CPU/RAM và GPU nếu có hỗ trợ. ECC không tự cung
cấp mô hình mạnh hơn: từng vai trò dùng hồ sơ model bạn chọn cho chế độ
Ollama hoặc OpenAI, mặc định dùng chung model.

Đây là công cụ tạo nội dung và bộ tệp. Có kiểm thử unittest Python trong
Docker khi chủ động bật hoặc bấm chạy; chưa chạy web/backend tương tác,
tự sửa mã ứng dụng đang chạy hoặc triển khai sản phẩm.
CrewAI, Letta và OpenHands chưa được tích hợp.

Hiện trạng và thiết kế để mở rộng bot/model, tách workspace và cập nhật có
phục hồi được lưu trong [Nền tảng bot](docs/NEN_TANG_BOT.md). Tài liệu phân
biệt chức năng đã có với các phần cần xây, kèm tiêu chí kiểm chứng từng đợt.
Hướng dẫn phần đã triển khai trong bản `0.2.0-dev`:
[Dự án, model, Docker và phục hồi](docs/CAP_NHAT_0_2.md).

## Cài, chạy và cập nhật trên Windows

Cài Python 3.12 và Python Launcher, Git, Ollama. Tải mô hình một lần:

```powershell
ollama run qwen3:4b
```

Khi trò chuyện được, nhập `/bye` để thoát phiên chat và giữ Ollama chạy nền.
Lần đầu tải mã (nếu đã clone thì dùng thư mục có sẵn):

```powershell
git clone --branch feat/bot-team-dashboard https://github.com/blon37815-stack/bao-mat.git
cd bao-mat
.\cai-dat.bat
.\chay.bat
```

Có thể nhấp đúp các tệp BAT. Chờ dòng `Bot team listening`, mở
`http://127.0.0.1:8000`, giữ cửa sổ app mở. Không cần activate venv, quyền
quản trị hoặc đổi execution policy PowerShell. BAT dùng thông báo không dấu;
web dùng UTF-8 tiếng Việt có dấu.

Cập nhật: dừng app bằng **Ctrl+C**, nhập **Y** nếu Windows hỏi dừng batch,
mở **cap-nhat.bat**, chọn Y để chạy lại và **Ctrl+F5** trên trình duyệt.
Updater fetch và fast-forward nhánh hiện tại (`main` hoặc
`feat/bot-team-dashboard`); dừng nếu có thay đổi/tệp chưa được quản lý.
Requirements đổi thì chuẩn bị môi trường riêng trước khi đổi mã. Nếu chuẩn
bị thất bại, giữ bản hiện tại; xem thông báo và gói phục hồi trước khi thử lại.

Nếu nhánh feature bị xóa, chỉ tự chuyển main khi HEAD là tổ tiên của
origin/main. Gộp bằng **Create a merge commit** để giữ quan hệ này; squash/
rebase có thể khiến updater dừng để kiểm tra. Updater mới tự lưu gói mã +
SQLite trước khi thay mã, thử import/khởi tạo đồ thị và migration trên bản
sao dữ liệu. Phụ thuộc đổi được cài vào môi trường riêng, giữ `.venv` cũ.
`phuc-hoi.bat` tạo bản phục hồi ở thư mục mới; không tự chuyển về bản cũ.
Không tự reset/xóa thay đổi cục bộ hoặc xóa dữ liệu trong data. Lần đầu kéo
bản mới bằng updater cũ vẫn cần sao lưu thủ công trước khi cập nhật.

## Giao việc và chọn mẫu

Thanh bên chia ứng dụng thành các khu riêng:

| Khu | Dùng để làm gì |
|---|---|
| Trao đổi | Soạn yêu cầu và đọc một kết quả đang chọn, có thể đóng khung xem |
| Công việc | Danh sách riêng, tìm/lọc/phân trang, mở kết quả, tải và xóa từng việc |
| Đội bot | Xem đủ 9 thành phần, vai trò, việc đang làm và thiết lập từng bot |
| Tài liệu | Nhập, sửa, tìm, xóa tài liệu; quản lý bộ nhớ dự án chung |
| Tài nguyên | Xem CPU/RAM/GPU và đặt giới hạn lượt gọi, số việc chờ |
| Thiết lập | Kiểm tra kết nối, tải bản sao lưu và dọn dữ liệu cũ |

Trong Công việc, bấm Mở kết quả để đọc kế hoạch, sản phẩm và nhận xét ở
khu Trao đổi. Xem bộ tệp mở cây tệp và trình soạn thảo; có thể mở rộng hoặc
đóng khung bên phải. Biểu tượng bot mở thiết lập; ô thống kê mở bộ lọc việc.
Chuyên gia/lượt gọi/tài liệu đính kèm nằm trong phần tùy chọn thu gọn.

Danh sách chỉ tải khi mở Công việc, 20 dòng mỗi trang. Không gửi kết quả
dài, bộ nhớ hoặc hướng dẫn riêng của bot trong phản hồi danh sách. Kết quả
đầy đủ chỉ tải cho công việc bạn mở; tự cập nhật khi việc đang chạy và khu
Trao đổi đang hiển thị. Đổi khu dừng tải danh sách/số đo không cần thiết;
đóng kết quả xóa cây tệp, nội dung và iframe khỏi khung xem. Các dòng
không đổi được giữ khi lọc/tự làm mới, không dựng lại toàn bộ danh sách.

Xóa công việc nằm cạnh phần tải trong danh sách và khung kết quả. Chỉ xóa
việc đã kết thúc; việc đang chờ/chạy cần hoàn tất hoặc hủy và đợi luồng
dừng hẳn. Hộp xác nhận nêu nội dung và liên kết liên quan. Máy chủ lưu bản
sao SQLite nhất quán và fsync trước khi xóa, kiểm tra lại dữ liệu trước
commit; sao lưu lỗi hoặc việc đổi thì giữ công việc. Bản xem trước hết hạn
sau 5 phút, có token và cần cùng phiên CSRF.

Xóa chỉ bỏ dữ liệu riêng của việc được chọn, không xóa phiên bản khác,
thư viện hoặc thiết lập chung. Phiên bản sửa vẫn so sánh được bằng bản
chụp nguồn dù bản gốc đã xóa. Chỉ giữ mã/tên ngắn cho liên kết còn lại;
không có nút mở nội dung bản đã xóa. Lượt chạy lại đã xóa có thể được tạo
lại từ công việc trước nếu trạng thái cho phép. ZIP trước xóa nằm trong
data/backups và có nút tải. Xóa giúp nhẹ danh sách; bản sao vẫn chiếm chỗ,
SQLite có thể giữ trang trống để tái sử dụng, không tự thu nhỏ tệp.

- **Mô phỏng:** không gọi mô hình; sản phẩm chỉ là README mô phỏng.
- **Ollama:** gọi AI trên máy, không phí API; không tự chuyển sang OpenAI.
- **OpenAI:** cần OPENAI_API_KEY, có thể tính phí; giao diện vô hiệu hóa khi
  chưa cấu hình khóa. Đường kết nối tồn tại nhưng cần kiểm chứng riêng bằng
  tài khoản/mô hình thật.

Tạo sản phẩm theo mẫu: chọn **Bắt đầu từ mẫu** và giữ yêu cầu mẫu tự điền.
Kiểm tra dòng tệp thực tế bắt buộc trước khi bấm Giao nhiệm vụ. Chỉ gõ
"Mẫu dữ liệu JSON" vào ô yêu cầu không gắn bộ tiêu chí của mẫu.

Chọn Chuyên gia cấp trên (mặc định Tự chọn theo mẫu) và giới hạn lượt gọi
riêng cho nhiệm vụ. Đội cơ bản bỏ bước chuyên gia và giữ ba vai trò cũ.

| Mẫu | Tệp bắt buộc |
|---|---|
| Dữ liệu JSON | notes.json, config.json, README.md |
| Python | main.py, tests/test_main.py, README.md |
| Web | index.html, style.css, app.js, README.md |
| Kế hoạch | Văn bản, không tạo ZIP |

Mẫu sản phẩm khóa bật chế độ tạo bộ tệp cả ở giao diện và máy chủ. Tự nhập
yêu cầu có thể chọn văn bản hoặc bộ tệp tùy ý. Mỗi lần giao việc tạo mã mới.
Nút Chạy lại từ đầu giữ tiêu chí cũ; để chuyển nhiệm vụ cũ chưa gắn mẫu sang
mẫu mới, tạo nhiệm vụ độc lập từ dropdown.

## Sinh từng tệp và sửa đúng tệp

Với mẫu có required_files, bước thực hiện gọi mô hình riêng cho từng tệp.
Mô hình trả nội dung nguyên văn; Python ghép thành cấu trúc files để lưu và
tải ZIP. Hỗ trợ bỏ một hàng rào Markdown bao ngoài; không giải mã lại escape
trong mã nguồn. Nếu mô hình vẫn trả files envelope, chỉ lấy đúng tệp đang
yêu cầu. README hướng dẫn tạo notes.json không thay thế notes.json thực tế.

Lượt đầu sinh các tệp bắt buộc. Khi sửa phiên bản, các tệp bổ sung đã có ở
bản gốc cũng tham gia manifest và được giữ. Mẫu mới có manifest cố định;
yêu cầu số tệp khác dùng nhiệm vụ tùy chỉnh. Nhiệm vụ tùy chỉnh chưa có
manifest vẫn dùng cách sinh cả bộ JSON trong một phản hồi.

Thiếu tệp, tệp rỗng, lỗi lược đồ JSON, lỗi liên kết HTML hoặc lỗi cú pháp
được gắn với đường dẫn cụ thể. Lượt sửa chỉ gọi các tệp đó và giữ nguyên
nội dung tệp khác. AI có thể trả file_issues để chỉ rõ tệp cần sửa; nhận xét
chung hoặc đường dẫn không xác định khiến toàn bộ manifest được sửa lại.
Tệp đã sinh được lưu từng bước trong kết quả hiện tại; hủy/lỗi ở tệp sau
vẫn giữ phần đã tạo. Không tự tiếp tục từ tệp đang dở khi mở app lại.

Tối đa 2 vòng sửa, tương đương tối đa 3 lượt thực hiện. Số lần gọi không còn
cố định 3–7: mẫu 3 tệp cần 5 lần ở lượt đạt đầu, tối đa 13 nếu mọi tệp đều
phải sửa hai lần; mẫu web 4 tệp cần 6, tối đa 16. Bản gốc có thêm tệp sẽ cần
thêm lần gọi. Giao diện/báo cáo ghi cách sinh và số yêu cầu mô hình đã thử;
đây không phải số token, hóa đơn hoặc phần trăm tiến độ.
Số này đếm lượt gọi từ ứng dụng; OpenAI SDK có thể thử lại HTTP bên trong.
Chuyên gia thêm một lần gọi trước ba vai trò: mẫu JSON/Python thường cần
6 lượt ở lần đạt đầu, web 7; tối đa 14/17 nếu mọi tệp đều sửa hai vòng và
chưa chạm giới hạn riêng. Mặc định là 20 lượt cho toàn bộ một nhiệm vụ.

## Kiểm tra chất lượng và giới hạn

- **Python:** compile trong tiến trình riêng, không execute hoặc import mã
  sản phẩm, không cài phụ thuộc và không ghi bytecode.
- **JSON:** kiểm tra cú pháp chuẩn. Mẫu JSON còn yêu cầu đúng 3 ghi chú, id
  duy nhất, title/content không rỗng, created_at ISO 8601; config là object.
- **JavaScript:** nếu có Node.js, dùng node --check (.js/.mjs dạng module,
  .cjs CommonJS). Thiếu Node ghi rõ bỏ qua.
- **Web:** đọc thẻ link/script trong index.html để kiểm tra liên kết tới
  style.css/app.js. Chữ trong chú thích, URL ngoài hoặc script text/plain
  không thay thế liên kết thực. Đây không phải kiểm thử giao diện/DOM/CSS.

Bộ kiểm tra cú pháp có thời hạn tổng 8 giây. Lỗi được đưa vào vòng sửa kể
cả AI tự đánh giá đạt. Không có tệp được hỗ trợ hoặc checker không hoàn tất
thì cần người xem. Kiểm tra tĩnh không xác minh chức năng, import/dependency,
tính an toàn, JSX/TypeScript hoặc HTML/CSS đầy đủ. Runner Docker tùy chọn
chạy unittest Python và đưa lỗi vào vòng sửa; không có test hoặc thiếu
Docker thì ghi rõ chưa kiểm thử. Chưa có runner trình duyệt cho web.

AI review dùng passed (boolean), issues (danh sách); file_issues theo tệp là
tùy chọn. Nhận xét cũ không được biến thành quy tắc mới của reviewer. Sai
định dạng hoặc hết vòng sửa thì dừng Cần bạn xem. Người dùng có thể duyệt
kết quả; thiếu tệp/tiêu chí mẫu hoặc bộ tệp sai cấu trúc bị chặn. Duyệt không
chạy mã và không chứng minh chức năng đúng; có thể vẫn còn lỗi cú pháp mà
người dùng chủ động chấp nhận.

## Hàng đợi, hủy và lịch sử

Một tiến trình app chạy một nhiệm vụ mỗi lúc, tối đa 10 việc chờ. Đầy hàng
đợi trả 429 mà không tạo nhiệm vụ thừa. Tạm dừng chỉ ngăn lấy việc tiếp theo,
không ngắt việc đã chạy; trạng thái tạm dừng không giữ sau khi tắt app.
Giới hạn việc chờ có thể hạ xuống 1–10 trong Phân công và tài nguyên; thiết
lập được giữ sau khởi động lại. Không cho hạ thấp hơn số việc đang chờ.

Hủy việc chờ giải phóng chỗ ngay. Hủy Ollama đóng tiến trình HTTP do app
quản lý và giải phóng worker, kể cả khi stream bị kẹt. Điều đó chưa chứng
minh CPU/GPU trên máy chủ Ollama đã dừng; cần quan sát thực tế. OpenAI gọi
đồng bộ nên việc đang gọi có thể còn chờ; yêu cầu đã gửi vẫn có thể tính phí.

Chạy lại áp dụng cho failed/interrupted/cancelled/needs_review, tạo mã mới,
giữ lịch sử và bản sao yêu cầu/bộ nhớ/nguồn. Mỗi nguồn có một lượt chạy lại
trực tiếp để tránh bấm trùng; nếu lượt sau lỗi có thể chạy tiếp từ lượt đó.

Lưu thời gian, nội dung từng bước và từng lượt sửa; hiển thị số bước đã
xong và thời gian trôi qua. Đây không phải thời gian CPU hoặc dự báo còn
lại. Khi khởi động, việc dang dở chuyển gián đoạn và không tự chạy lại.

## Sản phẩm, phiên bản và báo cáo

Xem bộ tệp, tải riêng hoặc tải ZIP khi sản phẩm kết thúc. Bộ tệp tối đa 30
tệp văn bản, mỗi tệp 100 KB, tổng 1 MB UTF-8. Từ chối đường dẫn tuyệt đối,
.., ký tự/tên thiết bị Windows không hợp lệ, đường dẫn trùng/xung đột và
thư mục .git/.venv. Đây là bảo vệ đường dẫn, chưa kiểm tra an toàn nội dung.
Tệp sản phẩm được lưu trong SQLite, không ghi vào cây mã nguồn máy chủ.

Yêu cầu chỉnh sửa tạo phiên bản mới từ bản sao bất biến của sản phẩm gốc;
không ghi đè bản gốc. So sánh phiên bản hiển thị thêm/sửa/xóa. Nguồn sửa giới
hạn 80 KB JSON UTF-8, chuỗi yêu cầu gốc 12000 ký tự để hạn chế ngữ cảnh.

Xuất toàn bộ hoặc từng phần kế hoạch/kết quả/kiểm tra thành Markdown UTF-8;
không gọi AI khi tải. Báo cáo nêu trạng thái, loại nhiệm vụ, tiêu chí mẫu,
nguồn phiên bản, bộ nhớ lúc giao việc và cách sinh nếu lượt mới đã ghi lại.
Nhiệm vụ cũ không được tự gán mẫu hoặc lịch sử giả.

Footer và GET /api/version hiển thị phiên bản, commit, mã băm nguồn và thời
điểm khởi động. Metadata được chụp lúc khởi động, không đọc lại commit sau
khi git pull; vì vậy cần dừng/chạy lại app sau cập nhật. Báo cáo ghi commit
của ứng dụng xuất báo cáo, không khẳng định nhiệm vụ cũ được sinh bởi commit
đó. ZIP rà soát không chứa .git có thể hiển thị commit unknown.

## Bộ nhớ, tìm kiếm và bản nháp

Đội bot hiển thị đúng 1 bộ quản lý bằng mã, 5 hồ sơ chuyên gia và 3 bot
thực thi đang có. Không giả lập thêm agent ECC chưa tích hợp. Thiết lập
bot cho đổi tên hiển thị và hướng dẫn riêng tối đa 1500 ký tự; quản lý
giới hạn chuyển tới khu Tài nguyên. Không đổi mô hình, quyền công cụ hoặc
hạn mức bằng lời nhắc. Thiết lập được chụp lúc giao nhiệm vụ; sửa thiết
lập sau đó không đổi việc đã giao. Chạy lại giữ bản thiết lập cũ.

Thư viện nhận văn bản gõ/dán hoặc tệp TXT/Markdown/JSON UTF-8. Tối đa 30
tài liệu, 20000 ký tự mỗi tài liệu, 500 KB toàn thư viện. Khi giao việc,
chọn tối đa 5 tài liệu, tổng 16000 ký tự; không tự gửi toàn thư viện cho AI.
Các bản tài liệu lúc gửi được lưu trong nhiệm vụ và báo cáo. Xóa tài liệu
cần xác nhận và chỉ xóa khỏi thư viện; bản đã gửi và các bản sao lưu vẫn
giữ nội dung. Chưa đọc PDF/Word, tìm kiếm ngữ nghĩa hoặc đồng bộ thư mục.

Khung sản phẩm có ba chế độ: Kết quả, Tệp & chỉnh sửa, Xem trước. Xem
trước HTML/CSS chỉ dựng tĩnh trong iframe sandbox không quyền; lọc script,
iframe, trình xử lý sự kiện và URL ngoài, kèm CSP chặn mạng. CSS liên kết
trong bộ tệp được ghép để hiển thị. Chưa chạy JavaScript, tài nguyên ngoài,
backend Python hoặc kiểm thử chức năng. JSON/văn bản hiển thị nội dung.

Sửa tệp hoặc bỏ một tệp khỏi bộ sản phẩm chỉ thay bản nháp trong khung.
Bấm Lưu thành phiên bản mới để lưu; không ghi đè bản gốc, không gọi AI,
không thực thi mã. Phiên bản mới luôn Cần bạn xem, có diff và tải ZIP;
tiêu chí tệp bắt buộc cũ vẫn giữ. Không cho bỏ hết tệp hoặc thoát đường
dẫn. Nhờ bot chỉnh tiếp dùng phiên bản đã lưu, chưa gửi phần sửa chưa lưu.
Bản sửa tệp và tài liệu chưa lưu chỉ ở bộ nhớ tab, không tự lưu qua reload;
trình duyệt có nhắc khi rời trang. Khung web không phải môi trường chạy app.

Bộ nhớ chung tối đa 8000 ký tự, gửi kèm các bước đến nhà cung cấp được chọn.
Mỗi nhiệm vụ giữ bản sao lúc tạo. Sửa bộ nhớ chỉ ảnh hưởng việc mới; để
trống rồi lưu để xóa bộ nhớ chung. Thiết lập → Nền tảng cho tạo dự án với
bộ nhớ riêng; chọn dự án khi giao việc và lọc trong Công việc. Tệp, lịch sử
và workspace logic lưu theo mã nhiệm vụ trong SQLite. Thư viện tài liệu
vẫn dùng chung, chỉ gửi tài liệu được chọn. Chưa tự học hoặc tìm kiến thức
bằng FTS5. Không nhập khóa/mật khẩu vào bộ nhớ.

Tìm theo yêu cầu/mã trên toàn bộ SQLite, kết hợp bộ lọc trạng thái, phân
trang 50. Không phân biệt hoa thường; vẫn phân biệt dấu tiếng Việt; chưa
tìm trong toàn bộ nội dung kết quả. Các thông tin danh sách lấy bằng JOIN
trong một kết nối; kết nối được đóng khi ra khỏi context.

Bản nháp lưu yêu cầu, chế độ, mẫu và nguồn phiên bản trong localStorage.
Giao lỗi giữ nháp; giao thành công mới xóa nháp tương ứng. Nháp chỉ ở trình
duyệt hiện tại, không thuộc bản sao lưu SQLite. Polling giữ phần kết quả
đang mở khi dữ liệu chưa đổi. Kiểm tra Ollama chỉ gọi api/tags, không suy
luận; có mô hình chưa chứng minh suy luận sẽ thành công.

## Sao lưu, khôi phục và dọn dữ liệu

Kết nối và dữ liệu → Tải bản sao lưu: ZIP gồm tasks.sqlite3 và KHOI-PHUC.txt.
SQLite backup API chụp nhất quán cả khi WAL đang mở. Có lịch sử, sản phẩm,
bộ nhớ, tiêu chí và số lần gọi mô hình; không gồm mã app, .env, venv, mô hình
Ollama hoặc nháp trình duyệt. ZIP dùng RAM, phù hợp dữ liệu cá nhân nhỏ.

Khôi phục: dừng app hoàn toàn, giữ nguyên thư mục data cũ ở nơi riêng, tạo
data mới và chép tasks.sqlite3 từ ZIP vào đó. Không ghép với -wal/-shm cũ.
Nếu dùng BOT_DB, khôi phục đúng đường dẫn đó. Thử trên bản dự án riêng và
đối chiếu số nhiệm vụ/bộ nhớ trước khi dùng làm dữ liệu chính. Việc dang dở
trong bản sao sẽ được đánh dấu gián đoạn khi app mở. Chưa có nút khôi phục.

Dọn dữ liệu: chọn lịch sử từng lượt hoặc nhiệm vụ độc lập, giữ 1–3650 ngày
(mặc định 30), xem trước rồi nhập DỌN. Xem trước có hiệu lực 5 phút; dữ liệu
đổi phải xem lại. Chỉ dọn khi không còn việc chạy/chờ hoặc yêu cầu đang hủy.
App ghi và flush bản ZIP vào data/backups (hoặc backups cạnh BOT_DB), sau
đó mới xóa trong giao dịch SQLite. Không lưu được bản sao thì không dọn.

Dọn lịch sử giữ kết quả cuối/thời gian/trạng thái. Dọn nhiệm vụ giữ cả hai
đầu của liên kết phiên bản/chạy lại; bộ nhớ chung luôn được giữ. Nội dung đã
dọn được ghi rõ trong lịch sử. Không tự dọn theo lịch; SQLite giữ trang
trống tái sử dụng, chưa tự VACUUM. Các ZIP sao lưu vẫn chiếm chỗ và chưa tự
xóa, có thể chứa dữ liệu riêng tư đã dọn khỏi app. Giữ chúng ngoài Git.
Phân công chuyên gia/giới hạn riêng và chính sách mặc định cũng được sao
lưu trong SQLite. Dọn nhiệm vụ xóa phân công riêng; không xóa chính sách chung.

## Chuyên gia ECC và quản lý tài nguyên

Luồng: **bạn → quản lý phân công/giới hạn → một chuyên gia ECC → Điều phối
→ Thực hiện → Kiểm tra**. Chuyên gia tạo bản giao việc văn bản, được lưu và
gửi cho các bước cấp dưới. Requirements, kiểm tra tĩnh và giới hạn do mã
quy định; chỉ đạo AI không thể tăng lượt gọi hoặc cấp công cụ.

Có 5 hồ sơ: lập kế hoạch, kiến trúc, Python, web, dữ liệu JSON. Auto chọn
Python/web/JSON theo mẫu, còn lại dùng lập kế hoạch. Chỉ một chuyên gia tham
gia mỗi nhiệm vụ; các lời gọi tuần tự trên một worker. Đây là hướng dẫn vai
trò đã điều chỉnh, không phải chạy 71 agent hoặc plugin/runtime ECC nguyên
bản. Không tự dùng Opus/Sonnet, không cài hook/MCP hoặc bật quyền chạy shell.

Nguồn ECC ghim commit 76aaa77df6adc5b889e689007bf99b9a4f74af34. Giữ 5 bản
định nghĩa gốc, LICENSE MIT, hash và nguồn trong third_party/ecc. App dùng
bản thích ứng tiếng Việt ở expert_team.py và bản tham khảo đầy đủ của đúng
vai trò đã chọn. Khi giao việc, xác minh hash, chụp nội dung/commit nguồn
vào task_runtime rồi gửi bước chuyên gia; không thực thi hook/script hay
cấp công cụ từ Markdown. Chạy lại giữ bản tham khảo đã chụp. Chỉ đạo được
yêu cầu ngắn; quá 6000 ký tự sẽ rút gọn và đánh dấu. Nhiệm vụ cũ chưa có
bản chụp vẫn dùng luồng tương thích cũ, không gán ngược nguồn/model giả.

Ngân sách do SQLite chặn nguyên tử trước mỗi lượt gọi. Tính cả chuyên gia,
lập kế hoạch, sinh từng tệp và kiểm tra, kể cả yêu cầu lỗi đã bắt đầu. Khi
hết lượt, dừng Cần bạn xem, giữ phần đã sinh và giải phóng worker. Không tự
tăng giới hạn. Chạy lại cho nhập mức mới 1–100, giữ lượt cũ và số đã dùng.
Đây là lượt gọi từ app, không phải giới hạn token/tiền hoặc mọi HTTP retry.

Mặc định 20 lượt và 10 việc chờ; sửa trong Phân công và tài nguyên. Ngân
sách riêng đã gắn nhiệm vụ không đổi khi sửa mặc định. Ô giới hạn từng
nhiệm vụ được ưu tiên, kể cả giá trị được khôi phục từ bản nháp. Việc cũ
chưa có chuyên gia giữ đội cơ bản; không tự đổi nội dung đã tạo.

Bảng CPU/RAM là số đo toàn máy chủ app, không phải máy đang mở trình duyệt
nếu truy cập từ xa. RAM riêng app không gồm Ollama. CPU cần hai lần lấy mẫu
đầu tiên và được cache 2 giây. GPU chỉ đọc NVIDIA qua nvidia-smi có trên
PATH, timeout 1 giây và cache 5 giây; AMD/Intel hoặc thiếu công cụ ghi rõ
chưa đọc được, không giả là 0%. Không gửi số đo tới bên thứ ba.

Các số đo chỉ để quan sát; app không đặt giới hạn cứng CPU/RAM/GPU, tự hạ
xung hoặc kết thúc tiến trình khác. Muốn hạn mức phần cứng khi chạy mã sinh
ra dùng runner Docker tùy chọn của bản này; hạn mức đó không áp dụng lên
Ollama. API: GET /api/experts, GET /api/resources;
POST /api/resource-policy nhận default_call_limit và max_waiting, cần token.
POST /api/tasks nhận expert (auto/none hoặc id hồ sơ) và call_limit;
POST /api/tasks/{id}/retry có thể nhận call_limit mới.

## Cấu hình và phạm vi sử dụng

| Biến | Mặc định / ý nghĩa |
|---|---|
| PORT | 8000, chỉ nghe loopback |
| BOT_DB | data/tasks.sqlite3 |
| OLLAMA_MODEL | qwen3:4b |
| OLLAMA_BASE_URL | http://127.0.0.1:11434 |
| OLLAMA_TIMEOUT_SECONDS | 600; cho phép 1–7200 giây mỗi lần gọi |
| OPENAI_API_KEY | Khóa qua môi trường nếu chủ động dùng OpenAI |
| BOT_MODEL | gpt-4.1-mini cho OpenAI |

Đặt biến trước khi chạy app trong cùng PowerShell, ví dụ:

```powershell
$env:OLLAMA_TIMEOUT_SECONDS = '1200'
.\chay.bat
```

Ollama và app cần trên cùng máy nếu dùng loopback. Cloud không truy cập
được Ollama của máy Windows qua 127.0.0.1. Thời hạn trên áp dụng từng lần
gọi, không phải toàn bộ nhiệm vụ hoặc OpenAI/checker; giá trị sai làm yêu
cầu thất bại. Bộ lọc think chỉ bỏ khối suy nghĩ đầu câu, giữ thẻ trong nội
dung thông thường; quy tắc nhận diện không hoàn hảo với mọi phản hồi lỗi.

Host chỉ nhận localhost/127.0.0.1 đúng cổng; kiểm tra Origin/Fetch Metadata.
Mọi POST cần application/json và X-CSRF-Token từ GET /api/session. Token đổi
khi khởi động; giao diện tự lấy. API client cũng phải gửi token. Đây chưa
phải đăng nhập/phân quyền. Không mở ứng dụng trực tiếp ra Internet hoặc
chạy nhiều tiến trình app cùng một SQLite. WAL và busy_timeout 30 giây đã
bật; không thay thế sao lưu. Khóa, data, backups và venv được loại khỏi Git.

## Bộ đánh giá Ollama cố định

Xem EVALUATION.md. Có 9 ca (3 JSON, 3 Python, 3 web), không chạy mã sản phẩm.
Mặc định chỉ liệt kê, không gọi mô hình:

```powershell
.\.venv\Scripts\python.exe evaluate.py --suite data
```

Để đo mục tiêu JSON ít nhất 8/10 cho ca cơ bản, giữ Ollama mở, dừng app và
các phiên chat khác để tránh nhiễu, rồi chạy hoặc mở danh-gia.bat:

```powershell
.\.venv\Scripts\python.exe evaluate.py --case data_basic --repeat 10 --run
```

Báo cáo ở data/evaluations, dùng SQLite tạm riêng; không sửa/xóa dữ liệu app.
Ghi tỷ lệ đạt lượt đầu/cuối, thời gian, số yêu cầu và commit. Mốc 8/10 chưa
được xác nhận bằng mô hình thật trong môi trường cloud này.
CLI mặc định --expert auto --call-limit 20. Thêm --expert none để so sánh
đội cơ bản với tầng chuyên gia trên cùng ca/mô hình/máy.

## Phát triển và CI

Dùng checkout hiện có; mỗi cloud task đã cô lập, không cần tạo worktree mới.
Trên Linux:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python app.py
```

Kiểm thử giao diện (Node.js 22+ chỉ dành cho phát triển; Node cũng cần nếu
muốn kiểm tra cú pháp sản phẩm JavaScript):

```sh
npm ci --prefix tests/ui
cd tests/ui
npx playwright install chromium
npm test
npm run format:check
```

BAO_TEST_PYTHON đổi Python kiểm thử; PLAYWRIGHT_EXECUTABLE_PATH dùng Chromium
có sẵn. Bộ trình duyệt chạy app thật với SQLite tạm ở cổng 8989, mô phỏng
provider; LangGraph thật vẫn điều phối. Không dùng khóa API hoặc dữ liệu
người dùng. npm run format định dạng app.js/resource_ui.js/workspace_ui.js,
index.html và styles.css.

Actions cấu hình Python 3.12, unittest, Prettier và Chromium trên Windows/
Ubuntu; lưu trace khi lỗi. Có cấu hình không đồng nghĩa CI đã xanh. Xem
RELEASE_NOTES.md và REVIEW.md để biết kiểm chứng, giới hạn và phần cần rà.
