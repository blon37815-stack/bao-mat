"""Nine fixed prompts. These cases test static acceptance, not program execution."""
CASES = [
    {'id':'data_basic','template':'data','prompt':'Tạo dữ liệu mẫu cho ứng dụng ghi chú: notes.json chứa đúng 3 ghi chú với id, title, content, created_at ISO 8601; config.json chứa theme và language; README.md giải thích từng trường bằng tiếng Việt.'},
    {'id':'data_unicode','template':'data','prompt':'Tạo 3 ghi chú tiếng Việt có dấu về học tập, công việc và gia đình trong notes.json; mỗi ghi chú có id, title, content, created_at ISO 8601. Kèm config.json và README.md tiếng Việt.','unicode_notes':True},
    {'id':'data_escaping','template':'data','prompt':'Tạo notes.json với đúng 3 ghi chú (id, title, content, created_at ISO 8601). Ít nhất một content có xuống dòng thật và dấu ngoặc kép trong chuỗi. Dùng JSON escaping đúng. Kèm config.json và README.md tiếng Việt.','escaped_notes':True},
    {'id':'python_basic','template':'python','prompt':'Tạo chương trình việc cần làm bằng Python 3.12 thư viện chuẩn: thêm, liệt kê và hoàn thành công việc. Trả main.py, tests/test_main.py dùng unittest và README.md tiếng Việt.'},
    {'id':'python_persistence','template':'python','prompt':'Tạo chương trình quản lý việc cần làm bằng Python 3.12, lưu JSON trong thư mục người dùng chọn, không tự xóa tệp. Trả main.py, tests/test_main.py với unittest và README.md tiếng Việt.'},
    {'id':'python_unicode','template':'python','prompt':'Tạo chương trình việc cần làm Python 3.12 hỗ trợ tên công việc tiếng Việt có dấu, lưu JSON UTF-8. Trả main.py, tests/test_main.py và README.md tiếng Việt; chỉ dùng thư viện chuẩn.'},
    {'id':'web_notes','template':'web','prompt':'Tạo ứng dụng ghi chú HTML/CSS/JavaScript thuần với thêm, sửa, xóa và lưu localStorage. Trả index.html liên kết style.css và app.js, cùng README.md tiếng Việt.'},
    {'id':'web_mobile','template':'web','prompt':'Tạo trang ghi chú dùng được ở màn hình điện thoại, có thêm và xóa ghi chú, lưu localStorage. Trả index.html, style.css, app.js, README.md. Không dùng thư viện ngoài; giao diện tiếng Việt.'},
    {'id':'web_search','template':'web','prompt':'Tạo trang ghi chú có tìm kiếm theo tiêu đề và nội dung, thêm/sửa/xóa và localStorage. Trả index.html liên kết style.css và app.js, cùng README.md tiếng Việt. Không dùng dịch vụ ngoài.'},
]
