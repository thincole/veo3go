# AutoPromt Veo3Go — Nhật ký thay đổi & Hướng dẫn vận hành

Cập nhật: 28/09/2026

Tài liệu này ghi lại toàn bộ thay đổi trong ngày, cách vận hành phần mềm, và những vấn đề
đã gặp kèm cách xử lý. Dùng để tra cứu khi cài máy mới hoặc khi gặp lại lỗi cũ.

---

## 1. Tổng quan phần mềm

App desktop PySide6 tạo video TVC hàng loạt cho sản phẩm Shopee:

1. Nhận lô sản phẩm từ Shopee Database Server (REST API)
2. Tải ảnh sản phẩm và sinh prompt TVC theo thị trường (on-demand khi tới lượt chạy)
3. Gửi ảnh + prompt lên server Veo3 qua WebSocket (`wss://ws.nhungoc.me/`)
4. Tải video về, xóa logo, ghép ảnh outro 12s bằng ffmpeg
5. Báo trạng thái về Shopee Database

### File trong thư mục

| File | Vai trò |
|---|---|
| `AutoPromt.py` | Chương trình chính |
| `shopee_db_helper.py` | Client Shopee DB, sinh prompt TVC, danh sách khung cảnh/kiểu review |
| `run_AutoPromt.bat` | Khởi chạy phần mềm |
| `install.bat` | Cài đặt + kiểm tra môi trường |
| `bin/ffmpeg.exe` | Xóa logo, ghép ảnh 12s — **bắt buộc** |
| `resources/brand.txt` | Xác định brand khi xác thực license |
| `shopee_db_settings.json` | Toàn bộ cài đặt giao diện |
| `veo3_accounts.json` | License key |
| `veo3_session.json` | Hàng chờ sản phẩm |
| `logs.txt` | Nhật ký, **bị xóa mỗi lần khởi động app** |
| `crash_log.txt` | Traceback khi app lỗi nặng |

Chỉ cần 2 thư viện ngoài: **PySide6** và **websockets**.

---

## 2. Các thay đổi đã thực hiện

### 2.1 Sửa lỗi app không mở được

Hai đoạn code bị dán nhầm chỗ khiến app chết ngay khi khởi động:

- `class ShopeeReleaseWorker` nằm chen giữa `VeoLiteApp`, làm mọi method từ đó trở đi
  (gồm `setup_tab_i2v`, `start_queue`, `load_session`) thành method của class sai
  → `AttributeError: 'VeoLiteApp' object has no attribute '_do_append_log'`
- `WorkerThread.__init__` thiếu phần khởi tạo `accounts_pool`, đoạn thiếu lại nằm nhầm
  trong `report_shopee_status` → bấm Chạy là lỗi

Đã chuyển về đúng vị trí. Phần khởi tạo pool tách thành `_init_accounts_pool()`.

### 2.2 Bắt lỗi toàn cục

Trước đây app lỗi thì cửa sổ cmd nháy rồi tắt, không thấy nguyên nhân.

Giờ có `sys.excepthook`:
- Ghi traceback vào `crash_log.txt`
- Lỗi lúc khởi động → hiện hộp thoại
- Lỗi khi đang chạy → ghi vào khung log, không bật hộp thoại liên tục
- App tự `os.chdir` về thư mục chứa file, chạy từ đâu cũng đọc đúng file dữ liệu

### 2.3 Gỡ bỏ phần lách bản quyền

Đã xóa hoàn toàn (người dùng có gói Unlimited 5 hợp lệ):

| Đã xóa | Nội dung |
|---|---|
| `activate_email_sync()` | Xin license mới bằng phần cứng ngẫu nhiên |
| `generate_random_email()` | Sinh email ngẫu nhiên để đăng ký |
| `derive_device_credentials()` | Bịa CPU ID / mainboard UUID từ license key |
| `add_current_account_to_pool()` | Phụ thuộc auto-activate |
| Hạn mức 5 video/ngày | Cơ chế xoay vòng tài khoản dùng thử |
| Cooldown 15–20s sau mỗi video | Né rate limit của tài khoản dùng thử |
| `AccountCreator.py` | Công cụ tạo tài khoản hàng loạt |

**Giữ lại** (hợp lệ theo gói đã mua): `get_real_hardware_info()` đọc phần cứng thật,
`verify_license()` xác thực với server, pool tài khoản + 5 slot song song
(số slot lấy từ `veo3_unlimited_threads` server trả về), cooldown khi server bận.

### 2.4 Tối ưu hiệu năng

- **Tra cứu dòng theo task_id**: trước đây quét toàn bộ ~5000 dòng mỗi lần cập nhật
  tiến độ. Thêm cache `_task_row_cache`. Đo được: 250 lần quét kiểu cũ mất 1,56 giây
  trên luồng giao diện; 2000 lần tra kiểu mới mất 0,014 giây.
- **Ghi log**: giữ file mở sẵn thay vì mở lại cho từng dòng. Khung log đổi sang
  `QPlainTextEdit`.
- **Bấm Chạy**: 1 dòng thiếu ảnh không còn chặn cả hàng chờ; dòng đó bị bỏ qua và
  đánh dấu lỗi, các dòng còn lại vẫn chạy.
- **Tắt app**: lệnh giải phóng SP kẹt chạy nền, chờ tối đa 5 giây, không làm treo app.

### 2.5 Hiện đúng mã lỗi của Veo

Trước đây mọi lỗi đều gộp thành "Lỗi: Không tìm thấy dữ liệu video". Server thực ra
trả về mã lỗi rõ ràng trong `data["error"]`.

Thêm `classify_veo_error()` với bảng `VEO_CONTENT_ERRORS`:

| Mã lỗi Veo | Nhãn hiển thị | Ý nghĩa |
|---|---|---|
| `PUBLIC_ERROR_IP_INPUT_IMAGE` | Lỗi Bản Quyền | Ảnh chứa nội dung có bản quyền |
| `PUBLIC_ERROR_PROMINENT_PEOPLE_FILTER_FAILED` | Lỗi Bản Quyền | Có người nổi tiếng |
| `PUBLIC_ERROR_RECITATION` | Lỗi Bản Quyền | |
| `PUBLIC_ERROR_UNSAFE_GENERATION` | Lỗi Bộ lọc nội dung | Bộ lọc an toàn chặn |
| `PUBLIC_ERROR_DANGER_FILTER` | Lỗi Bộ lọc nội dung | |

Mã lạ chưa biết thì hiện nguyên văn thay vì câu chung chung.

Các trạng thái này báo về Shopee DB là `vi phạm cs` thay vì `failed`, nên không bị
claim lại và chạy lại vô ích. Nút "Xóa SP bị từ chối (bản quyền / bộ lọc)" dọn cả 2 loại.

### 2.6 Lưu cài đặt cho phiên sau

Trước đây hầu hết cài đặt chỉ được **đọc** mà không bao giờ **ghi** lại. Hàm
`save_shopee_settings_gui` là code chết: không nút nào gọi, và gọi vào sẽ crash vì
tham chiếu 5 widget không tồn tại.

Giờ lưu đủ **18 cài đặt**: tỉ lệ, khung cảnh, độ dài, ngôn ngữ, kiểu review, AI Prompt,
cách đặt tên, xóa ảnh, ghép ảnh 12s, thư mục lưu, số luồng, xóa logo, thị trường,
ưu tiên, số lượng, ItemID từ, hoa hồng từ, SL bán từ.

Lưu vào `shopee_db_settings.json` khi: bấm nút **💾 Lưu cài đặt**, tắt app, hoặc bấm Chạy.

`veo3_session.json` giờ chỉ giữ hàng chờ, không còn ghi 8 khóa Shopee luôn sai như trước.

### 2.7 Tương thích thư viện websockets

Lỗi trên máy khác: `'ClientConnection' object has no attribute 'closed'`

| | websockets < 14 | websockets >= 14 |
|---|---|---|
| `connect()` trả về | `WebSocketClientProtocol` | `ClientConnection` |
| Có `.closed` | Có | **Không**, chỉ có `.state` |

Thêm `ws_is_open()` tự nhận biết API nào đang dùng. Cũng bỏ tham số `ssl` khi kết nối
vì cả 2 phiên bản đều tự bật TLS cho `wss://`, còn truyền tay `ssl=None` với `ws://`
sẽ gây `TypeError` trên bản mới.

**Không cần hạ cấp hay nâng cấp thư viện** — bản code mới chạy được trên mọi phiên bản.

### 2.8 Thư mục lưu video không tồn tại

Lỗi trên máy khác: `FileNotFoundError: [WinError 3] ... 'F:/'`

Do chép `shopee_db_settings.json` giữa 2 máy. Máy này có ổ `F:`, máy kia không.
`os.makedirs(default_out)` chạy không có lớp bảo vệ → app chết ngay khi khởi động.

Đã sửa 2 chỗ:
- **Lúc khởi động**: không tạo được thì tự chuyển về `Desktop\Veo3LiteOutput`,
  báo cho người dùng, app **vẫn mở lên**
- **Lúc bấm Chạy**: kiểm tra trước, không được thì báo lỗi rõ và không khởi động hàng chờ

### 2.9 Tính năng tự dừng khi chạm cap — ĐÃ GỠ BỎ

Đã từng làm rồi gỡ theo yêu cầu. Bản có tính năng này lưu tại
`AutoPromt.py.bak_co_tudung_cap` nếu muốn khôi phục.

**Hành vi hiện tại**: khi chạm cap, mỗi sản phẩm bị rút ra đều hỏng và báo `failed`
về Shopee DB. App chạy tiếp cho tới khi kết nối được làm mới.

Log vẫn ghi rõ nguyên nhân: `Lỗi: Quota exceeded. Session prompt cap: 199...`

---

## 3. Giới hạn cần biết

### Cap 199 prompt mỗi phiên kết nối

Server áp hạn mức **199 prompt cho mỗi phiên WebSocket**. Chạm cap thì mọi yêu cầu
tiếp theo đều bị từ chối với thông báo:

```
Quota exceeded. Session prompt cap: 199. Accepted: 199. New: 1.
```

Ghi nhận thực tế ngày 28/09: chạm cap lúc 07:59:38, **307 sản phẩm bị đốt trong 5 phút**,
tất cả báo `failed`. Đến 08:04:30 kết nối rớt rồi nối lại, app chạy tiếp.

**Muốn chạy 24/7 thì phải hỏi bên bán license** xem có hỗ trợ không, hoặc có gói /
endpoint nào cap cao hơn. Không nên tự tạo phiên mới để reset bộ đếm.

### Bộ lọc nội dung của Veo

Mỗi lần bị từ chối vẫn tốn 1 prompt trong 199. Tỉ lệ từ chối ảnh hưởng trực tiếp
tới sản lượng:

| Tỉ lệ từ chối | Video thu được / phiên |
|---|---|
| 20% | ~159 |
| 10% | ~179 |
| 5% | ~189 |

**Nhóm hàng hay bị từ chối** (ghi nhận thực tế): đồ chơi và đồ dùng trẻ em in hình
nhân vật hoạt hình — CARS RACING MCQUEEN, Minnie Mouse, Inside Out, Lilo & Stitch,
Disney Princess, cặp học sinh, ốp lưng in hình. Lô này từng lên tới **54% bị từ chối**.

**Nhóm an toàn**: mỹ phẩm, đồ gia dụng, phụ kiện bếp, dụng cụ, thực phẩm chức năng —
ảnh chụp sản phẩm thật, nền trơn. Tỉ lệ từ chối chỉ 7–8%.

### Số liệu tham khảo

| Chỉ số | Giá trị ghi nhận |
|---|---|
| Luồng song song | 5 (1 tài khoản × 5 slot) |
| Thời gian mỗi video | 136–447 giây, trung bình ~270 giây |
| Tốc độ | 0,76 – 1,81 video/phút tùy thời điểm |

---

## 4. Cài đặt trên máy mới

### File cần chép

```
AutoPromt.py
shopee_db_helper.py
run_AutoPromt.bat
install.bat
resources/brand.txt
bin/ffmpeg.exe
bin/ffprobe.exe      <- nhớ chép, xem mục cảnh báo bên dưới
```

**Không nên chép** `shopee_db_settings.json` giữa 2 máy, vì nó chứa đường dẫn riêng
của từng máy (`seedvis_out_dir`). Nếu có chép thì nhớ sửa lại ô "Lưu Video".

### Các bước

1. Cài Python 3.12 trở lên, **bắt buộc tick "Add python.exe to PATH"**
2. Chạy `install.bat` — nó sẽ cài thư viện và kiểm tra đủ 6 mục
3. Chạy `run_AutoPromt.bat`
4. Vào **Quản lý Tài khoản** nhập license key
5. Bấm nút **Chọn** cạnh ô "Lưu Video" để trỏ đúng ổ đĩa trên máy đó
6. Bấm **💾 Lưu cài đặt**

`install.bat` kết luận 1 trong 3 mức: `DAY DU` / `CO THE CHAY DUOC - N canh bao` /
`CHUA DU DIEU KIEN CHAY - N muc bi thieu` (mã thoát 0 hoặc 1).

### Cảnh báo về ffprobe

`ffprobe` **không đi kèm** trong `bin/`. Thiếu nó thì chức năng ghép ảnh 12s vẫn chạy
nhưng **âm thầm sai**: giả định video là 1080×1920, 30fps và **không có tiếng**.
Không báo lỗi gì cả. Nhớ chép `ffprobe.exe` vào `bin/`.

---

## 5. Vận hành hằng ngày

### Quy trình

1. Mở app → bấm **🔄 Giải phóng SP kẹt** (trả lại SP đang treo `processing` từ lần trước)
2. Đặt số lượng claim — **nên 150–180 SP mỗi phiên**, đừng claim vài nghìn
3. Bấm **📥 Lấy SP từ Database & Sinh Prompt**
4. Bấm **Bắt đầu chạy queue**
5. Khi chạm cap, tắt và mở lại app để có phiên mới

Claim quá nhiều thì số dư bị giữ trạng thái `processing` trên server, phải bấm
"Giải phóng SP kẹt" mới trả lại được.

### Đọc log

| Dòng log | Ý nghĩa |
|---|---|
| `Đã lưu video thành công: ...` | Xong 1 video |
| `⛔ Veo từ chối tạo video: <mã> → <nhãn>` | Bộ lọc chặn, SP bị loại |
| `Lỗi: Quota exceeded. Session prompt cap: 199...` | Hết hạn mức phiên |
| `Server đang bận (Code 1013)` | Server quá tải, tự thử lại |
| `Kết nối WebSocket bị ngắt` | Tự thử lại sau 3 giây |
| `lỗi license (1008)` | Key sai / hết hạn / thiết bị không khớp |

`logs.txt` bị xóa mỗi lần khởi động app. File ngắn đi đột ngột nghĩa là app vừa khởi động lại.

---

## 6. Bản sao lưu

| File | Nội dung |
|---|---|
| `AutoPromt.py.bak_truoc_toiuu` | Bản gốc trước toàn bộ thay đổi ngày 28/09 |
| `AutoPromt.py.bak_co_tudung_cap` | Bản có tính năng tự dừng khi chạm cap |

---

## 7. Dọn dẹp đã thực hiện

Thư mục giảm từ **350 MB** xuống **159 MB**.

Đã xóa: runtime app Veo3Go gốc (`lib/` 183 MB, các file `.dll`, Qt plugins,
`Veo3Go_video_generator.exe`, `Veo3Updater.exe`), bộ cài `Veo3go 155.rar` 119 MB,
`resources/brands|icons|bin`, file ghi chú dịch ngược, pool tài khoản cũ,
`AccountCreator.py`, `__pycache__`.

Đã kiểm chứng trước khi xóa: PySide6 / websockets / PIL đều nạp từ Python hệ thống,
không phải từ `lib/`. Code chỉ đọc đúng 7 file: `brand.txt`, `ffmpeg.exe`, `logs.txt`,
`crash_log.txt`, `shopee_db_settings.json`, `veo3_accounts.json`, `veo3_session.json`.
