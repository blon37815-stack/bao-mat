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
trực tiếp lên Internet: bản đầu chưa có đăng nhập hoặc giới hạn tần suất truy cập.

Chế độ **Mô phỏng** không gọi AI, chỉ xác minh luồng và lưu dữ liệu.
Để dùng **AI thật**, cấp `OPENAI_API_KEY` qua biến môi trường an toàn trước
khi chạy máy chủ. Không đưa khóa vào Git hay giao diện. `BOT_MODEL` mặc định
là `gpt-4.1-mini`; tài khoản cần có quyền dùng mô hình. Ba bước gọi mô hình
riêng và có thể phát sinh phí. Chế độ này chỉ tạo văn bản, chưa chạy lệnh.
Không nhập dữ liệu nhạy cảm nếu chưa chấp nhận gửi tới nhà cung cấp mô hình.

`PORT` đổi cổng, `BOT_DB` đổi đường dẫn SQLite (mặc định `data/tasks.sqlite3`).
Lịch sử giữ lại qua lần khởi động; nhiệm vụ đang chạy bị đánh dấu gián đoạn
và không tự chạy lại. Giao diện tìm kiếm toàn bộ lịch sử, phân trang 50 nhiệm vụ.

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
Với nhiệm vụ thất bại, bị gián đoạn, đã hủy hoặc cần người xem, nút **Chạy
lại từ đầu** tạo lượt mới và giữ kết quả cũ; chế độ AI có thể tính phí lần nữa. Không tự động
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

## Hàng đợi và lưu trữ

Trong một tiến trình app, nhiệm vụ mới và nhiệm vụ chạy lại dùng chung hàng
đợi FIFO và một worker. Chỉ một nhiệm vụ được xử lý tại một thời điểm (cả ba
bước); các nhiệm vụ khác giữ trạng thái Chờ. Không mở nhiều tiến trình app
cùng dùng một cơ sở dữ liệu. Hàng đợi giới hạn 10 việc chờ; khi đóng
app, việc chờ/đang chạy được đánh dấu gián đoạn ở lần khởi động tiếp theo,
không tự chạy lại. SQLite bật WAL và busy_timeout 30 giây để giảm tranh chấp
đọc/ghi; vẫn cần sao lưu đúng cả dữ liệu WAL khi app đang mở.

Bộ lọc suy nghĩ chỉ xử lý khối `<think>` ở đầu phản hồi. Với dữ liệu Qwen cũ
thiếu thẻ mở, chỉ lọc khi có lời mở đầu suy nghĩ tiếng Anh được nhận diện và
`</think>` nằm riêng một dòng. Thẻ được nhắc giữa câu hoặc trong khối mã được
giữ nguyên. Đây là quy tắc nhận diện có giới hạn, chưa phân biệt hoàn hảo mọi
trường hợp văn bản trích dẫn và suy nghĩ thiếu định dạng.

## Nhấp đúp để chạy trên Windows

Sau khi tải mã về, nhấp đúp **cai-dat.bat** để tạo môi trường Python 3.12 và
cài phụ thuộc (cần Internet). Nếu đã cài thủ công, có thể bỏ qua bước này.
Sau đó nhấp đúp **chay.bat**. Khi thấy `Bot team listening`, mở địa chỉ
hiển thị trong cửa sổ bằng trình duyệt. Giữ cửa sổ mở và giữ Ollama chạy nền.
Không mở nhiều bản app cùng lúc. Tệp BAT dùng thông báo không dấu để tránh
lỗi bảng mã Windows; giao diện web vẫn dùng tiếng Việt có dấu.

Các tệp BAT tự chuyển đến thư mục dự án kể cả khi đường dẫn có khoảng trắng.
Không cần quyền quản trị hay thay đổi execution policy. Sau khi cập nhật có
thay đổi requirements.txt, chạy lại cai-dat.bat trước khi khởi động.

## Kiểm thử tự động trên GitHub

Workflow `.github/workflows/tests.yml` chạy trên push và pull request, dùng
Python 3.12 trên Ubuntu và Windows. Gồm cài phụ thuộc, pip check và unittest.
Không dùng khóa API, không tải mô hình Ollama; kết nối mô hình được giả lập
trong kiểm thử. Xem trạng thái thực tế trong tab Actions sau khi push; việc
có workflow không có nghĩa là một lượt chạy trên GitHub đã đạt.


## Kiểm tra có cấu trúc và tự sửa

Ở chế độ Ollama/OpenAI, bot kiểm tra phải trả JSON với `passed` (boolean)
và `issues` (danh sách lỗi). Nếu chưa đạt, bước thực hiện nhận lỗi và sửa,
sau đó kiểm tra lại. Tối đa hai lần sửa, tức tối đa ba bản kết quả và bảy
lần gọi mô hình cho một nhiệm vụ. OpenAI có thể tốn thêm phí; Ollama có thể
chạy lâu hơn. Luồng tự sửa giữ hàng đợi cho đến khi xong nhiệm vụ hiện tại.

Nếu vẫn chưa đạt hoặc mô hình trả sai định dạng, nhiệm vụ dừng ở **Cần bạn
xem**; kết quả vẫn xem và tải được. Không coi JSON sai là đạt. Khi đạt,
trạng thái ghi rõ đây là đánh giá của AI, chưa phải kiểm chứng bên ngoài.
Bản đầu chỉ giữ kết quả và nhận xét mới nhất, chưa lưu lịch sử các vòng sửa.
Chế độ mô phỏng không chạy vòng sửa. Nút duyệt và hủy chưa được triển khai.

## Duyệt và hủy nhiệm vụ

- **Hủy nhiệm vụ** áp dụng cho việc đang chờ hoặc đang xử lý. Việc chờ bị
  bỏ qua khi worker lấy khỏi hàng đợi. Với việc đang gọi mô hình, phản hồi
  trả về bị bỏ qua và không chạy bước tiếp theo; kết quả các bước trước vẫn
  được giữ. Chưa có khả năng ngắt ngay phép tính bên trong Ollama/OpenAI.
  Worker tiếp tục chờ yêu cầu hiện tại kết thúc hoặc timeout rồi mới lấy
  việc tiếp theo. Phí OpenAI của yêu cầu đã gửi có thể vẫn phát sinh.
- **Duyệt kết quả** chỉ áp dụng cho nhiệm vụ AI đã chạy xong hoặc cần người
  xem và có kết quả. Trạng thái chuyển thành **Bạn đã duyệt**, giữ nguyên nội
  dung và nhận xét kiểm tra. Việc duyệt không thực thi hay triển khai mã;
  mô phỏng không được duyệt. Bản đầu chưa có thao tác thu hồi duyệt hoặc chạy
  lại nhiệm vụ đã hủy; có thể tạo nhiệm vụ mới.

API: `POST /api/tasks/{id}/cancel`, `POST /api/tasks/{id}/approve`, dùng JSON
Content-Type và token phiên như các API ghi khác. Trả 200 khi thành công,
409 khi trạng thái không cho phép, 404 khi không tìm thấy.

## Tạo bộ mã nguồn và tải ZIP

Đánh dấu **Tạo bộ mã nguồn có thể tải ZIP**, chọn Ollama hoặc OpenAI và mô tả
một sản phẩm nhỏ, ví dụ: "Tạo trang ghi chú bằng HTML/CSS/JavaScript thuần,
lưu localStorage, kèm README hướng dẫn mở trang". Giữ yêu cầu nhỏ khi dùng
qwen3:4b. Trong chế độ mô phỏng, sản phẩm chỉ có README được ghi rõ mô phỏng.

Mô hình trả JSON `{"files":[{"path":"README.md","content":"..."}]}`.
Các tệp được lưu trong kết quả SQLite, không ghi vào cây thư mục máy chủ.
Khi nhiệm vụ kết thúc, bấm **Xem bộ tệp** để chọn và đọc nội dung, hoặc
**Tải mã nguồn ZIP**. ZIP được tạo trong bộ nhớ từ dữ liệu đã kiểm tra. Chưa
có tự chạy, cài phụ thuộc hoặc xác minh sản phẩm hoạt động; AI đánh giá đạt
không bảo đảm mã an toàn hay chạy đúng. Đọc mã trước khi dùng và chạy mã chưa
tin cậy trong môi trường cô lập. Chạy lại nhiệm vụ tạo lượt mới và giữ kết quả cũ; nên tải ZIP nếu cần bản sao riêng.

Giới hạn: 30 tệp văn bản, 100 KB mỗi tệp, tổng 1 MB nội dung UTF-8; không có
tệp nhị phân. Từ chối đường dẫn tuyệt đối, `..`, dấu gạch chéo ngược, ký tự
đặc biệt Windows, tên thiết bị dành riêng, đường dẫn trùng không phân biệt
hoa/thường, xung đột tệp/thư mục, thư mục .git và .venv. Nếu bộ tệp không hợp
lệ, vòng kiểm tra yêu cầu sửa tối đa hai lần; vẫn lỗi thì không tải hoặc duyệt
được bộ mã. Các quy tắc đường dẫn không phải kiểm tra độ an toàn nội dung mã.

API thêm: `GET /api/tasks/{id}/files` trả danh sách tệp; `GET
/api/tasks/{id}/artifact.zip` tải ZIP. Chỉ dùng khi nhiệm vụ sản phẩm đã kết
thúc ở completed/needs_review/approved. Khi tạo nhiệm vụ, đặt `product:true`
trong JSON; mặc định false để giữ quy trình văn bản cũ.

## Chỉnh sửa sản phẩm qua nhiều phiên bản

Ở nhiệm vụ có bộ mã hợp lệ, bấm **Yêu cầu chỉnh sửa**. Giao diện chọn bản gốc
và đưa bạn về ô giao việc; nhập thay đổi mong muốn, chẳng hạn "Thêm tìm kiếm,
giữ các tính năng cũ", rồi giao nhiệm vụ. Đây là nhiệm vụ mới, không ghi đè
sản phẩm gốc. Có thể bấm **Bỏ chọn bản gốc** để trở lại tạo sản phẩm độc lập.

Nhiệm vụ mới giữ bản sao bất biến của toàn bộ tệp gốc cùng chuỗi yêu cầu
trước đó, đồng thời dùng bộ nhớ dự án hiện tại lúc giao việc. Bot phải trả
lại toàn bộ bộ tệp, bao gồm tệp không đổi. Xem **So sánh với bản gốc** để biết
tệp thêm/sửa/xóa, đọc diff và kiểm tra mô hình có vô tình bỏ tệp hay không.
Việc duyệt vẫn do bạn thực hiện; so sánh không xác minh chức năng chạy đúng.
Mỗi nhiệm vụ ghi mã bản gốc trong chi tiết và báo cáo Markdown. Các bản vẫn được lưu trong SQLite và có thể tìm theo mã nhiệm vụ.

Trong **Xem bộ tệp**, chọn một tệp và bấm **Tải [tên tệp]** để tải riêng; mã
được tải như tệp đính kèm, không được thực thi hoặc hiển thị như trang HTML
trên máy chủ. Tải ZIP vẫn giữ nguyên cấu trúc thư mục.

Để giữ ngữ cảnh vừa phải, bản đầu chỉ nhận chỉnh sửa bộ mã gốc tối đa 80 KB
JSON UTF-8 và chuỗi yêu cầu trước đó tối đa 12000 ký tự. Mô hình nhỏ vẫn có
thể không giữ hết nội dung; ưu tiên sản phẩm nhỏ và kiểm tra diff sau mỗi
lần sửa. Giới hạn này không phải cam kết về dung lượng ngữ cảnh mô hình.

API: khi `POST /api/tasks`, thêm `parent_id` của nhiệm vụ sản phẩm đã kết
thúc và có bộ tệp hợp lệ; server tự bật `product:true`. Nguồn sai trả 404/409,
nguồn quá lớn trả 413. `GET /api/tasks/{id}/diff` trả thay đổi so với bản sao
gốc; `GET /api/tasks/{id}/file/{index}` tải một tệp trong danh sách files.

## Nhấp đúp để cập nhật

Dừng app bằng Ctrl+C (nhập Y nếu Windows hỏi dừng batch), rồi nhấp đúp
**cap-nhat.bat**. Tệp chạy `git pull --ff-only` trên nhánh
`feat/bot-team-dashboard`, dừng nếu có thay đổi/tệp chưa được Git quản lý,
không tự reset hoặc xóa tệp. Dữ liệu data, khóa .env và .venv được Git bỏ qua.
Nếu requirements.txt đổi, tự cập nhật phụ thuộc bằng Python trong .venv.
Nếu cài thư viện thất bại, mã có thể đã được cập nhật; chạy cai-dat.bat để
khắc phục trước khi mở app. Cuối cùng chọn Y để mở đội bot hoặc N để đóng.
Giữ Ollama chạy nền, tải lại trình duyệt bằng Ctrl+F5 sau khi khởi động app.

## Tìm kiếm, kết nối và sao lưu

- **Tìm nhiệm vụ:** tìm trong yêu cầu hoặc mã nhiệm vụ trên toàn bộ SQLite,
  kết hợp bộ lọc trạng thái. Không phân biệt hoa/thường, vẫn phân biệt dấu
  tiếng Việt; không tìm trong nội dung kết quả. Phân trang 50 việc mỗi trang.
- **Kiểm tra Ollama:** chạy khi mở trang hoặc bấm nút, gọi `/api/tags` (không
  sinh nội dung) để kiểm tra dịch vụ đang phản hồi và đã tải mô hình cấu hình.
  Có mô hình không chứng minh một yêu cầu suy luận sẽ thành công. Kiểm tra
  không thử khóa OpenAI; API chỉ cho biết khóa đã được cấu hình hay chưa.
- **Tải bản sao lưu:** tạo ZIP gồm tasks.sqlite3 và hướng dẫn khôi phục. Dùng
  SQLite backup API để có ảnh chụp nhất quán kể cả khi đang bật WAL. Chứa tất
  cả lịch sử, bộ nhớ, sản phẩm và bản gốc của các phiên bản sửa; không chứa
  mã ứng dụng, .env, môi trường ảo hoặc mô hình Ollama. Không gửi bản sao lưu
  cho người khác nếu bên trong có dữ liệu riêng tư.

Khôi phục thủ công: dừng app hoàn toàn, giữ lại cả thư mục data cũ ở nơi an
 toàn, tạo thư mục data mới rồi giải nén tasks.sqlite3 vào đó. Không ghép cơ
sở dữ liệu khôi phục với -wal/-shm từ bản cũ. Nếu đặt BOT_DB riêng, dùng đúng
đường dẫn đó. Khởi động lại; nhiệm vụ chờ/đang xử lý trong bản sao sẽ được
đánh dấu gián đoạn. Bản đầu chưa có nút khôi phục hoặc sao lưu định kỳ.

API: `GET /api/tasks?q=...&status=all&offset=0` trả tasks, total, limit=50,
offset. `GET /api/health` kiểm tra kết nối; `POST /api/backup` tải ZIP, yêu
cầu Content-Type JSON và token phiên. Bản sao được tạo ở thư mục tạm rồi
xóa; dữ liệu ZIP được giữ trong RAM lúc tải, phù hợp cơ sở dữ liệu cá nhân
nhỏ. Nhiệm vụ hoàn thành sau thời điểm chụp sẽ cần bản sao lưu tiếp theo.

## Mẫu nhiệm vụ và kiểm tra cú pháp sản phẩm

Chọn một mẫu ở ô giao việc: kế hoạch sản phẩm, trang ghi chú web, ứng dụng
Python dòng lệnh hoặc bộ dữ liệu JSON. Mẫu chỉ điền yêu cầu và chọn chế độ
tạo bộ mã, không tự giao việc hay đổi nhà cung cấp AI. Nếu đang có yêu cầu
hoặc bản gốc được chọn, giao diện hỏi trước khi thay thế.

Ở bộ sản phẩm, bấm **Kiểm tra cú pháp** để xem từng tệp đạt/lỗi/bỏ qua.
Hỗ trợ `.py` theo phiên bản Python đang chạy và `.json` theo JSON chuẩn.
HTML/CSS/JavaScript cùng các loại khác được ghi rõ chưa hỗ trợ. Tệp Python
được compile thành code object trong một tiến trình Python riêng, không
execute, không import module của sản phẩm, không cài phụ thuộc hay viết
bytecode. Có timeout 8 giây; nếu bộ kiểm tra lỗi hoặc quá hạn thì không
kết luận đạt. Đây là kiểm tra cú pháp, không phải sandbox để chạy mã, kiểm
thử chức năng, kiểm tra bảo mật hoặc bảo đảm sản phẩm hoạt động.

Trong bước kiểm tra của luồng tạo/sửa sản phẩm, lỗi cú pháp Python/JSON được
đưa vào danh sách lỗi để bot sửa (vẫn tối đa hai lần). Kết luận AI "đạt"
không ghi đè lỗi cú pháp do bộ kiểm tra phát hiện. Nếu bộ kiểm tra không
hoàn tất, nhiệm vụ cần người xem. Tải mã lỗi vẫn được phép để bạn kiểm tra;
người dùng vẫn có thể chủ động duyệt kết quả, việc duyệt không tự sửa lỗi.

API: `GET /api/tasks/{id}/checks` trả status, checked, skipped và findings.
Các trạng thái gồm passed (chỉ các tệp được hỗ trợ), failed, not_supported
(không có tệp được hỗ trợ), unavailable (không kiểm tra được). Kết quả kiểm
tra được tính lại khi bấm nút; chưa lưu lịch sử báo cáo kiểm tra.


## Cập nhật xử lý hủy, nhánh và mức kiểm chứng

**Hủy Ollama:** dùng API streaming trong một tiến trình HTTP riêng do app
quản lý. Khi hủy, app kết thúc tiến trình yêu cầu, đóng kết nối và giải
phóng worker để lấy việc tiếp theo, kể cả lúc stream chưa có dòng hoàn
chỉnh. Không chạy mã do mô hình sinh ra trong tiến trình đó. Đóng kết nối
không phải bằng chứng máy chủ Ollama đã ngừng tính hoặc giải phóng GPU; còn
phụ thuộc Ollama. OpenAI vẫn dùng lệnh gọi đồng bộ và chưa có hủy tức thì.

**Cập nhật nhánh:** cap-nhat.bat hỗ trợ main và feat/bot-team-dashboard.
Fetch rồi fast-forward từ nhánh origin tương ứng. Nếu nhánh feature bị xóa,
chỉ tự chuyển main khi kiểm chứng được HEAD hiện tại là tổ tiên của
origin/main. Trường hợp squash/rebase chưa chứng minh được bằng phép kiểm
tra này thì dừng và giữ mã, không reset hay xóa nhánh để ép cập nhật.

**JavaScript:** nếu có Node.js trên PATH, nút Kiểm tra cú pháp và vòng sửa
sẽ dùng `node --check` cho .js/.mjs (module) và .cjs (CommonJS). Mã chỉ được
phân tích, không thực thi, không cài npm hay nạp phụ thuộc dự án. Thiếu Node
thì ghi rõ bỏ qua. HTML/CSS, JSX/TypeScript và kiểm thử chức năng vẫn chưa
được hỗ trợ. Có thể cài Node.js LTS từ nodejs.org rồi mở lại app để bật kiểm
tra JS. Kiểm tra cú pháp đạt không chứng minh DOM, CSS, import, tương tác,
lưu trữ hay logic chương trình hoạt động.

Nếu sản phẩm không có tệp nào được kiểm tra cú pháp độc lập, AI đánh giá đạt
vẫn dừng ở Cần bạn xem. Nếu có kiểm tra, trạng thái ghi số tệp đã kiểm tra
và bỏ qua, cùng giới hạn chưa kiểm thử chức năng. Người dùng có thể xem và
chủ động duyệt; chưa có tự chạy test của sản phẩm trong sandbox.


## Giới hạn hàng đợi và lịch sử chạy lại

Tối đa 10 việc đang chờ ngoài một việc đang xử lý. Việc mới và chạy lại dùng
chung giới hạn; API trả 429 khi đầy, không tạo bản ghi nhiệm vụ thừa. Trên
bảng điều hành hiển thị số việc chờ/giới hạn và tạm khóa nút giao việc khi
đầy. Hủy việc chờ xóa ngay mục tương ứng khỏi hàng đợi để nhận việc khác.
Giới hạn áp dụng trong một tiến trình; không chạy nhiều app cùng dùng SQLite.

Chạy lại hỗ trợ failed/interrupted/cancelled/needs_review. Mỗi lần tạo mã
nhiệm vụ mới, sao chép yêu cầu, chế độ, bộ nhớ ban đầu và bản sao mã nguồn
nếu có; không xóa kết quả cũ. Một nguồn chỉ tạo một lượt chạy lại trực tiếp,
tránh bấm trùng; nếu lượt mới lại lỗi thì chạy tiếp từ lượt mới đó. Giao diện
có liên kết **Xem lượt trước** và **Xem lượt chạy lại**. Việc đã duyệt hoặc
hoàn thành không được chạy lại bằng nút này; dùng yêu cầu chỉnh sửa sản phẩm.

`POST /api/tasks/{id}/retry` trả 202 với id mới và retry_of; 409 nếu không
được phép hoặc đã tạo lượt, 429 khi đầy. Lượt cũ giữ trạng thái và dữ liệu
nguyên vẹn. Quan hệ lượt chạy được sao lưu trong SQLite. Danh sách nhiệm vụ
lấy bộ nhớ, sản phẩm và quan hệ phiên bản bằng JOIN trong một kết nối, không
mở thêm kết nối theo từng nhiệm vụ trên trang.

## Đợt nâng cấp dùng hằng ngày

Chi tiết ở [RELEASE_NOTES.md](RELEASE_NOTES.md). Giao diện được tách thành
index.html, app.js và styles.css; cả ba đều cần khi chạy app.

- **Tạm dừng hàng đợi / Tiếp tục hàng đợi:** chỉ tác động tới việc chưa được
  worker lấy; việc đã bắt đầu tiếp tục chạy. Tạm dừng không phải hủy hay lưu
  checkpoint giữa bước, không tự giữ sau khi tắt app.
- **Lịch sử từng bước:** chọn trên thẻ nhiệm vụ để xem các kết quả từng lượt
  và thời gian, kể cả bản kết quả trước khi sửa. Nhiệm vụ từ bản cũ có thể
  chưa có lịch sử, kết quả cuối vẫn được giữ.
- **Bản nháp:** tự lưu trên trình duyệt này, gồm yêu cầu, chế độ và bản gốc
  được chọn. Lỗi giao việc không xóa nháp. Xóa bằng nút Xóa bản nháp; dữ liệu
  đã giao không bị xóa. Nháp không nằm trong SQLite hay bản sao lưu dữ liệu.

API thêm: `POST /api/queue` với JSON `{"paused":true|false}`, yêu cầu token
phiên; `GET /api/tasks/{id}/history` trả steps và timing. Danh sách có thêm
started_at, finished_at và completed_steps. Các bảng mới được tạo tự động,
không cần reset dữ liệu.

### Kiểm thử giao diện cho người phát triển

Chạy unittest như trước. Để kiểm tra Chromium, cài Node.js 22+ và chạy:

```sh
npm ci --prefix tests/ui
cd tests/ui
npx playwright install chromium
npm test
```

Config mặc định dùng Python trong .venv. Có thể đặt BAO_TEST_PYTHON thành
đường dẫn Python đã cài phụ thuộc. Nếu có sẵn Chromium, đặt
PLAYWRIGHT_EXECUTABLE_PATH thành đường dẫn trình duyệt để không tải lại.
Máy chủ kiểm thử dùng SQLite tạm ở cổng 8989, không dùng dữ liệu app của bạn.
Dùng chế độ mô phỏng để kiểm tra giao việc, lịch sử, tải tệp và các thao tác
trình duyệt; các kiểm thử mô hình thật vẫn là kiểm tra riêng.

## Tiêu chí nghiệm thu của mẫu sản phẩm

Mẫu được chọn ở dropdown sẽ lưu bộ tiêu chí cùng nhiệm vụ, ngoài phần yêu
cầu văn bản. Mẫu dữ liệu JSON bắt buộc tạo notes.json, config.json và
README.md thành ba mục trong files; hướng dẫn sinh tệp hoặc mã nhúng trong
README không thay thế các tệp thực tế. notes.json phải chứa đúng 3 ghi chú,
id duy nhất (chuỗi/số nguyên), title/content không rỗng và created_at ISO
8601; config.json phải là đối tượng JSON. Trường bổ sung như priority được
phép. Nếu muốn cấu trúc khác, chọn tự nhập yêu cầu để tạo nhiệm vụ độc lập.

Mẫu web bắt buộc index.html, style.css, app.js, README.md; mẫu Python bắt
buộc main.py, tests/test_main.py, README.md. Đây là kiểm tra sự hiện diện và
cú pháp hỗ trợ, chưa thực thi hoặc chứng minh chức năng. Các lỗi tiêu chí
được đưa vào vòng sửa ngay cả khi mô hình tự đánh giá đạt. Thiếu tiêu chí
sau hai lần sửa thì dừng cần người xem và không cho duyệt như sản phẩm đủ.

Bộ tiêu chí hiện ở ô giao việc, chi tiết nhiệm vụ, báo cáo và mục kiểm tra.
Chạy lại sao chép bộ tiêu chí; chỉnh sửa sản phẩm kế thừa tiêu chí bản gốc
khi không chọn mẫu mới. Dữ liệu cũ không có template metadata không được tự
gán tiêu chí dựa trên phỏng đoán. Để kiểm chứng mẫu, tạo nhiệm vụ mới bằng
chọn mẫu ở dropdown; không chỉ gõ tên mẫu như một yêu cầu chung chung.
Chế độ mô phỏng không thực thi kiểm tra tiêu chí sản phẩm thật, được ghi rõ
skipped_demo trong báo cáo kiểm tra. Tiêu chí mẫu không phải sandbox hay
kiểm thử chức năng của ứng dụng.

Khi chọn mẫu JSON/web/Python, chế độ tạo bộ tệp được khóa bật ở giao diện
và bắt buộc ở máy chủ, kể cả client cũ gửi product=false. Muốn chỉ tạo văn
bản, chọn Tự nhập yêu cầu hoặc mẫu Lập kế hoạch. Trước nút giao việc và trên
thẻ nhiệm vụ đều có nhãn loại kết quả. Nhiệm vụ văn bản chỉ xuất báo cáo .md,
không có ZIP; việc cũ không tự chuyển thành nhiệm vụ sản phẩm sau cập nhật.

Báo cáo sản phẩm ghi rõ khi nhiệm vụ chưa có bộ tiêu chí mẫu. Nhiệm vụ
chỉnh sửa kế thừa cấu trúc cũ và tiêu chí cũ nếu có; không tự biến thành mẫu
mới chỉ vì nhập tên mẫu trong yêu cầu. Khi cần mẫu có files bắt buộc, tạo
nhiệm vụ độc lập bằng dropdown. Giao diện nhắc điều này khi chọn bản gốc.

Bot kiểm tra nhận bản result mới nhất, chính sách cho phép README.md và
bộ tiêu chí đã lưu. Không đưa nhận xét vòng trước vào prompt của chính bot
kiểm tra; bot thực hiện vẫn nhận nhận xét đó để sửa. Đây là hướng dẫn mô
hình, chưa phải bảo đảm loại bỏ mọi nhận xét sai; kiểm tra xác định vẫn giữ
vai trò phát hiện thiếu tệp/cú pháp/schema độc lập. Trạng thái needs_review
trong báo cáo được mô tả là luồng đã dừng cần người xem.
