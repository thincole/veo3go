# -*- coding: utf-8 -*-
"""
shopee_db_helper.py - Module tích hợp Shopee Database Server & Thuật toán Prompt TVC
cho Veo3Go 1.5.5 / AutoPromt.py.
Trích xuất và chuẩn hóa từ hệ thống Seedvis (E:\\0 - Seedvis).
"""

import os
import re
import json
import time
import random
import urllib.request
import urllib.error

# Cấu hình mặc định từ Seedvis
DEFAULT_SETTINGS = {
    "sv_server_url": "http://100.79.170.67:3000",
    "sv_api_key": "shopee_secret_2026",
    "sv_client_id": "XEON-CT2A_822d66_veo3go",
    "seedvis_market": "PH",
    "seedvis_claim_limit": "100",
    "seedvis_sort_by": "Số bán cao nhất",
    "seedvis_min_item_id": "40000000000",
    "seedvis_min_commission": "1",
    "seedvis_min_sold": "0",
    "seedvis_min_price": "0",
    "seedvis_max_price": "",
    "seedvis_scene": "🎲 Random",
    "seedvis_review_style": "🎲 Random",
    "seedvis_ai_prompt": "Template TVC (Mặc định)",
    "gemini_keys": ["AIzaSyBJfdDS5rA7SgioCya26Fa-AZLKsG5AzEI"]
}

SETTINGS_FILE = "shopee_db_settings.json"
SEEDVIS_SETTINGS_BACKUP = r"E:\0 - Seedvis\seedvis_settings.json"

# ==================== KHUNG CẢNH PRESET ====================
SCENES = [
    ("🎲 Random", "", ""),
    ("📦 Tổng kho hàng hóa",
     "in a large organized warehouse with neatly stacked product shelves behind, bright industrial lighting",
     "trong nhà kho lớn ngăn nắp với các kệ sản phẩm xếp gọn phía sau, ánh sáng công nghiệp sáng rõ"),
    ("🛒 Siêu thị hiện đại",
     "inside a bright modern supermarket with shiny product displays, spacious shopping environment",
     "bên trong siêu thị hiện đại sáng sủa với các gian hàng trưng bày sản phẩm bóng loáng, không gian mua sắm rộng rãi"),
    ("🎥 Phòng review chuyên nghiệp",
     "in a professional product review studio with clean white background and softbox lighting setup",
     "trong phòng quay đánh giá sản phẩm chuyên nghiệp với phông nền trắng sạch và hệ thống đèn softbox"),
    ("🛋 Phòng khách sang trọng",
     "in a luxurious modern living room with leather sofa, warm golden ambient lighting, elegant decor",
     "trong phòng khách hiện đại sang trọng với sofa da, ánh sáng vàng ấm áp, nội thất thanh lịch"),
    ("💼 Văn phòng hiện đại",
     "in a stylish modern office with glass desk, ergonomic chair, minimalist decor and green plants",
     "trong văn phòng hiện đại phong cách với bàn kính, ghế công thái học, trang trí tối giản và cây xanh"),
    ("🌳 Ngoài trời công viên",
     "outdoors in a beautiful green park with natural sunlight filtering through tree canopy",
     "ngoài trời trong công viên xanh mát với ánh nắng tự nhiên xuyên qua tán cây"),
    ("📸 Studio chụp ảnh",
     "in a professional photo studio with grey backdrop, ring light, clean minimal setup",
     "trong studio chụp ảnh chuyên nghiệp với phông nền xám, đèn ring light, bố trí gọn gàng tối giản"),
    ("🏬 Showroom trưng bày",
     "in an upscale product showroom with glass display shelves and LED spotlight illumination",
     "trong showroom trưng bày sản phẩm cao cấp với kệ kính và đèn LED chiếu điểm"),
    ("☕ Quán café hiện đại",
     "in a stylish modern cafe with wooden table, warm ambient light, cozy relaxing atmosphere",
     "trong quán café hiện đại phong cách với bàn gỗ, ánh sáng ấm áp, không gian thư giãn ấm cúng"),
    ("📦 Bàn unboxing",
     "at a clean unboxing desk with brown kraft paper, scissors, and packaging materials, bright overhead lighting",
     "tại bàn unboxing gọn gàng với giấy kraft nâu, kéo và vật liệu đóng gói, ánh sáng trên đầu sáng rõ"),
    ("⚖ Bàn so sánh sản phẩm",
     "at a product comparison table with clean white surface, multiple items neatly arranged side by side, professional overhead lighting",
     "tại bàn so sánh sản phẩm với mặt bàn trắng sạch, nhiều sản phẩm xếp gọn cạnh nhau, ánh sáng chuyên nghiệp từ trên"),
    ("📱 Studio livestream",
     "in a professional livestream studio with ring light, camera tripod, colorful LED backdrop, and product display shelf",
     "trong studio livestream chuyên nghiệp với đèn ring light, chân tripod camera, phông nền LED nhiều màu, và kệ trưng bày sản phẩm"),
    ("🏭 Nhà máy sản xuất",
     "inside the actual modern manufacturing factory where this product is produced with clean high-tech equipment",
     "bên trong nhà máy sản xuất hiện đại nơi sản phẩm này được gia công với trang thiết bị công nghệ cao")
]

REVIEW_STYLES = [
    "🎲 Random",
    "Review tự nhiên",
    "Ngồi Review",
    "POV (Góc nhìn thứ nhất)",
    "Unboxing",
    "UGC Authentic",
    "Demo Công Dụng",
    "So Sánh/Đánh Giá"
]

MARKETS = ["PH", "VN", "ID", "TH", "MY", "SG", "TW"]

MARKET_LANG_MAP = {
    "PH": ("en", "Filipino"),
    "VN": ("vi", "tiếng Việt"),
    "ID": ("id", "tiếng Indonesia"),
    "MY": ("my", "tiếng Malaysia (Bahasa Melayu)"),
    "TH": ("th", "Thai"),
    "SG": ("en", "English"),
    "TW": ("zh", "Traditional Chinese")
}

def load_settings():
    """Tải cài đặt, ưu tiên shopee_db_settings.json, sau đó seedvis_settings.json, cuối cùng DEFAULT."""
    settings = dict(DEFAULT_SETTINGS)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings.update(json.load(f))
            return settings
        except Exception:
            pass
    if os.path.exists(SEEDVIS_SETTINGS_BACKUP):
        try:
            with open(SEEDVIS_SETTINGS_BACKUP, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k in DEFAULT_SETTINGS:
                    if k in data:
                        settings[k] = data[k]
            save_settings(settings)
            return settings
        except Exception:
            pass
    return settings

def save_settings(settings):
    """Lưu cài đặt vào file shopee_db_settings.json."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print("Lỗi lưu cấu hình:", e)
        return False

def clean_product_title(name):
    """Làm sạch tiêu đề Shopee để prompt TVC súc tích, tránh từ nhạy cảm và spam keyword."""
    if not name:
        return "featured product"
    s = str(name).strip()
    s = re.sub(r"[\【\[\(].*?[\】\]\)]", " ", s)
    s = re.sub(r"[^\w\s-]", " ", s)
    
    policy_risk_words = [
        "100%", "chính hãng", "chinh hang", "đặc trị", "dac tri", "chữa khỏi", "chua khoi",
        "dứt điểm", "dut diem", "phục hồi", "phuc hoi", "thần tốc", "than toc", "cam kết",
        "cam ket", "bao hành", "bao hanh", "replica", "fake", "super fake",
        "bra", "underwear", "panties", "bikini", "crop top", "lace", "breast", "nude",
        "sexy", "erotic", "lingerie", "magsafe", "iphone", "apple", "nike", "adidas",
        "bluetooth", "scratch", "remover", "jump starter", "compressor", "gold", "silver",
        "medicine", "cure", "medical", "treatment", "pill", "cream", "whitening", "slim",
        "slimming", "weight loss", "gun", "knife", "blade", "bomb", "chemical", "poison",
        "cod", "free shipping", "ready stock", "hot sale"
    ]
    for w in policy_risk_words:
        s = re.sub(r"\b" + re.escape(w) + r"\b", " ", s, flags=re.IGNORECASE)
    
    words = [w.strip() for w in s.split() if len(w.strip()) > 1]
    clean_str = " ".join(words[:5]).strip()
    return clean_str if clean_str else "featured product"

def pick_scene(choice="🎲 Random", lang="en"):
    """Chọn mô tả bối cảnh theo ngôn ngữ."""
    if choice == "🎲 Random" or not choice:
        cand = [s for s in SCENES if s[0] != "🎲 Random"]
        chosen = random.choice(cand)
        return chosen[1] if lang == "en" else chosen[2]
    for s in SCENES:
        if s[0] == choice:
            return s[1] if lang == "en" else s[2]
    return "in a professional product review studio with soft lighting"

def build_tvc_prompt(product_name, market="PH", review_style="🎲 Random", scene_choice="🎲 Random"):
    """Sinh prompt TVC Image-to-Video chuẩn Veo 3 / 1.5.5 cho sản phẩm Shopee.
    Bao gồm Anatomy Lock, Framing Lock 9:16, Camera movement và Voiceover.
    """
    clean_name = clean_product_title(product_name)
    short_name = (clean_name or "featured product")[:70].strip()

    lang_code, spoken_lang = MARKET_LANG_MAP.get(market.upper(), ("en", "English"))
    scene_en = pick_scene(scene_choice, lang="en")

    style = review_style
    if style in ("🎲 Random", "Random") or not style:
        style = random.choice([
            "Review tự nhiên", "Ngồi Review", "POV (Góc nhìn thứ nhất)",
            "Unboxing", "UGC Authentic", "Demo Công Dụng", "So Sánh/Đánh Giá"
        ])

    style_lower = style.lower()
    is_pov = any(k in style_lower for k in ("pov", "góc nhìn thứ nhất"))
    is_unbox = any(k in style_lower for k in ("unbox", "đập hộp"))
    is_demo = any(k in style_lower for k in ("demo", "công dụng", "feature"))

    # Ràng buộc âm bản và khóa chống lỗi tay / hình ảnh
    constraints = (
        "FRAMING & ANATOMY LOCK: Full-frame vertical 9:16 portrait video, edge-to-edge camera footage, NO letterbox, NO black borders. "
        "Strictly TWO natural human hands with exactly 5 fingers each, realistic skin tone, no extra fingers, no limb deformations. "
        "Product must remain 100% consistent with the reference image without morphing or disappearing. "
        "NO text, NO subtitles, NO captions, NO logos overlay on screen. 4K UHD, 30fps commercial quality."
    )

    if is_pov:
        prompt = (
            f'Create a high-end commercial video (TVC) reviewing the product "{short_name}". '
            f'First-person point of view (POV) angle looking down at a clean tabletop surface {scene_en}. '
            f'ABSOLUTELY NO human face, NO head, NO presenter body shown. '
            f'Only two natural, well-manicured hands are smoothly holding, rotating, and presenting "{short_name}" with clear tactile interaction. '
            f'Voiceover speaks in {spoken_lang} explaining key product benefits immediately. '
            f'{constraints}'
        )
        return prompt, "POV"

    if is_unbox:
        prompt = (
            f'Create an unboxing product commercial video (TVC) for "{short_name}". '
            f'Top-down camera view looking at a clean desk {scene_en}. '
            f'ABSOLUTELY NO human face or body visible. '
            f'Only two realistic hands carefully open packaging, unboxing, and proudly revealing "{short_name}" with gentle movements. '
            f'Voiceover in {spoken_lang} introducing the authentic product details. '
            f'{constraints}'
        )
        return prompt, "Unboxing"

    if is_demo:
        prompt = (
            f'Create a professional product feature demonstration video (TVC) for "{short_name}". '
            f'Extreme close-up macro cinematography focusing 100% on the functionality, texture, and durability of "{short_name}". '
            f'ABSOLUTELY NO human face visible. Only clean hands operating and demonstrating the key utility of "{short_name}" on a clean surface. '
            f'Voiceover in {spoken_lang} highlights its exceptional quality. '
            f'{constraints}'
        )
        return prompt, "Demo Công Dụng"

    if market.upper() == "MY":
        # Malaysia: Mẫu nam hoặc sản phẩm lịch sự an toàn chính sách
        prompt = (
            f'Create a commercial review video (TVC) for "{short_name}". '
            f'A handsome 25-year-old Malay male presenter in smart casual outfit holds "{short_name}" {scene_en}. '
            f'He speaks {spoken_lang} naturally with a confident smile, introducing key advantages. '
            f'Steady medium shot, cinematic depth of field, sharp focus on "{short_name}". '
            f'{constraints}'
        )
        return prompt, "Mẫu Nam (MY)"
    else:
        nationality_map = {
            "PH": "Filipino",
            "VN": "Vietnamese",
            "ID": "Indonesian",
            "TH": "Thai",
            "SG": "Asian",
            "TW": "Taiwanese"
        }
        nat = nationality_map.get(market.upper(), "Asian")
        prompt = (
            f'Create a commercial review video (TVC) for "{short_name}". '
            f'A cheerful and elegant 22-year-old {nat} female presenter holds "{short_name}" {scene_en}. '
            f'She speaks {spoken_lang} naturally with a welcoming smile, introducing its outstanding benefits. '
            f'Camera smoothly pans in medium framing, sharp focus on "{short_name}", modest elegant clothing. '
            f'{constraints}'
        )
        return prompt, f"Review ({nat})"


def check_existing_shopee_video(item_id, output_dir=None):
    """Kiểm tra xem video của sản phẩm Shopee đã tồn tại trong thư mục xuất (output_dir) của máy này chưa."""
    if not item_id or not output_dir:
        return None
    if not os.path.exists(output_dir):
        return None
    s_id = str(item_id).strip()
    for cand_name in (f"{s_id}.mp4", f"{s_id}_12s.mp4"):
        cand_path = os.path.join(output_dir, cand_name)
        if os.path.exists(cand_path) and os.path.getsize(cand_path) > 10240:
            return cand_path
    return None


class ShopeeDatabaseClient:
    """Client giao tiếp với Server Database PostgreSQL Shopee qua REST API."""

    def __init__(self, server_url=None, api_key=None):
        self.server_url = (server_url or DEFAULT_SETTINGS["sv_server_url"]).rstrip("/")
        self.api_key = api_key or DEFAULT_SETTINGS["sv_api_key"]

    def _request(self, method, path, data=None, timeout=25):
        url = self.server_url + path
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "AutoPromt-Veo3Go/1.5.5"
        }
        if method == "GET":
            req = urllib.request.Request(url, headers=headers)
        else:
            body = json.dumps(data or {}).encode("utf-8")
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content)

    def claim_jobs(self, market="PH", client_id=None, limit=100,
                   sort_by="sold", min_item_id=40000000000, min_commission=1.0,
                   min_sold=0, min_price=0.0, max_price=None, tool="veo3go"):
        """Claim sản phẩm từ Server Database."""
        if not client_id:
            try:
                client_id = load_settings().get("sv_client_id", "XEON-CT2A_822d66_veo3go")
            except Exception:
                client_id = "XEON-CT2A_822d66_veo3go"

        try:
            min_item_id = int(re.sub(r"\D", "", str(min_item_id)) or "0")
        except Exception:
            min_item_id = 0

        try:
            min_commission = float(str(min_commission).replace("%", "").strip() or "0.0")
        except Exception:
            min_commission = 0.0

        try:
            min_sold = int(min_sold)
        except Exception:
            min_sold = 0

        try:
            min_price = float(min_price)
        except Exception:
            min_price = 0.0

        payload = {
            "market": market,
            "clientId": client_id,
            "limit": int(limit),
            "tool": tool,
            "sortBy": "commission" if "hoa hồng" in str(sort_by).lower() or sort_by == "commission" else "sold",
            "min_item_id": min_item_id,
            "min_commission": min_commission,
            "minItemId": min_item_id,
            "minCommission": min_commission,
            "min_sold": min_sold,
            "minSold": min_sold,
            "min_price": min_price,
            "minPrice": min_price
        }
        if max_price is not None and str(max_price).strip():
            try:
                mp = float(max_price)
                payload["max_price"] = mp
                payload["maxPrice"] = mp
            except Exception:
                pass

        res = self._request("POST", "/api/thinaptm/claim-jobs", payload)
        raw_products = res.get("products", [])
        
        # Chuẩn hóa dữ liệu trả về
        products = []
        for p in raw_products:
            iid_str = str(p.get("item_id", "0"))
            try:
                iid = int(re.sub(r"\D", "", iid_str))
            except Exception:
                iid = 0
            if min_item_id > 0 and iid < min_item_id:
                continue

            try:
                comm = float(p.get("commission_rate", 0) or 0)
                if 0 < comm <= 1.0:
                    comm = comm * 100.0
                p["commission_rate"] = comm
            except Exception:
                comm = 0.0

            if comm < min_commission:
                continue

            img = p.get("image_url") or p.get("image") or ""
            p["image_url"] = img
            products.append(p)

        return products

    def complete_job(self, item_id, status="completed", video_path="", extra=None, retries=3, tool="veo3go"):
        """Báo cáo trạng thái video (completed, failed, vi phạm cs) về Server Database."""
        payload = {
            "itemId": str(item_id),
            "status": status,
            "tool": tool
        }
        if video_path:
            payload["video_path"] = os.path.basename(video_path)
            payload["full_path"] = video_path
        if extra and isinstance(extra, dict):
            payload.update(extra)

        for attempt in range(retries):
            try:
                self._request("POST", "/api/thinaptm/complete-job", payload)
                return True
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
        return False

    def release_jobs(self, client_id=None):
        """Giải phóng các sản phẩm đang kẹt (processing) của client_id này."""
        if not client_id:
            try:
                client_id = load_settings().get("sv_client_id", "XEON-CT2A_822d66_veo3go")
            except Exception:
                client_id = "XEON-CT2A_822d66_veo3go"

        released = 0
        try:
            r1 = self._request("POST", "/api/thinaptm/release-jobs", {"clientId": client_id})
            released += r1.get("released", 0) if isinstance(r1, dict) else 0
        except Exception:
            pass
        return released

    def release_single_job(self, item_id):
        """Trả 1 sản phẩm về trạng thái pending khi gặp lỗi tạm thời phía máy chủ Veo."""
        if not item_id:
            return False
        try:
            r = self._request("POST", "/api/thinaptm/release-single-job", {"itemId": str(item_id)})
            return r.get("success", False) if isinstance(r, dict) else False
        except Exception:
            return False


    @staticmethod
    def download_image(image_url, save_path, retries=3):
        """Tải ảnh Shopee CDN về thư mục cục bộ với retry khi chập chờn."""
        if not image_url:
            return False
        
        # Đảm bảo URL có scheme
        if image_url.startswith("//"):
            image_url = "https:" + image_url
        elif not image_url.startswith("http://") and not image_url.startswith("https://"):
            image_url = "https://" + image_url

        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://shopee.ph/"
        }
        for attempt in range(retries):
            try:
                req = urllib.request.Request(image_url, headers=headers)
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = resp.read()
                    if data and len(data) > 500:
                        with open(save_path, "wb") as f:
                            f.write(data)
                        return True
            except Exception:
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
        return False


def generate_gemini_prompt(product_name, market="PH", review_style="🎲 Random", scene_choice="🎲 Random", gemini_keys=None):
    """Sinh prompt TVC chi tiết bằng Google Gemini Flash (nếu có API Key).
    Tự động fallback về build_tvc_prompt nếu lỗi mạng hoặc hết quota."""
    if not gemini_keys or not isinstance(gemini_keys, (list, tuple)) or not gemini_keys[0]:
        prompt, label = build_tvc_prompt(product_name, market, review_style, scene_choice)
        return prompt, label

    lang_code, spoken_lang = MARKET_LANG_MAP.get(market.upper(), ("en", "English"))
    scene_en = pick_scene(scene_choice, lang="en")
    clean_name = clean_product_title(product_name)

    system_prompt = (
        f"You are a professional prompt engineer for Google Veo 3 / Veo 3.1 image-to-video AI.\n"
        f"Write EXACTLY 1 video prompt (about 80-120 words) for an e-commerce commercial TVC reviewing: \"{clean_name}\".\n"
        f"Settings: Market {market}, Spoken Language: {spoken_lang}, Scene: {scene_en}, Style: {review_style}.\n"
        f"Mandatory constraints:\n"
        f"- Full-frame vertical 9:16 portrait video, edge-to-edge camera framing, no black bars, no borders.\n"
        f"- Two natural normal hands with 5 fingers each, realistic skin tone, no extra fingers, no limb deformations.\n"
        f"- The product is the central hero item, perfectly consistent with reference image.\n"
        f"- Absolutely NO text, NO watermarks, NO subtitles on screen.\n"
        f"- Voiceover speaks in {spoken_lang}.\n"
        f"Output ONLY the prompt text, no explanations, no numbering."
    )

    models = ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3-flash-preview", "gemini-3.5-flash"]
    for key in gemini_keys:
        k = str(key).strip()
        if not k:
            continue
        for m in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={k}"
                body = json.dumps({
                    "contents": [{"parts": [{"text": system_prompt}]}],
                    "generationConfig": {"temperature": 0.8, "maxOutputTokens": 300}
                }).encode("utf-8")
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    text = ""
                    for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                        text += part.get("text", "")
                    prompt_out = text.strip().replace("\n", " ")
                    if len(prompt_out) > 30:
                        return prompt_out, "Gemini AI"
            except Exception:
                continue

    # Fallback
    return build_tvc_prompt(product_name, market, review_style, scene_choice)


try:
    from PySide6.QtCore import QThread, Signal
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False


if PYSIDE_AVAILABLE:
    class ShopeeClaimWorker(QThread):
        """Thread chạy nền xử lý claim sản phẩm, tải ảnh và sinh prompt TVC."""
        progress_signal = Signal(int, int, str) # current, total, text
        log_signal = Signal(str)
        finished_signal = Signal(list) # list of items
        error_signal = Signal(str)

        def __init__(self, client, market, client_id, limit, sort_by, min_item_id, min_commission,
                     review_style, scene_choice, prompt_mode="Template TVC (Mặc định)", gemini_keys=None):
            super().__init__()
            self.client = client
            self.market = market
            self.client_id = client_id
            self.limit = limit
            self.sort_by = sort_by
            self.min_item_id = min_item_id
            self.min_commission = min_commission
            self.review_style = review_style
            self.scene_choice = scene_choice
            self.prompt_mode = prompt_mode
            self.gemini_keys = gemini_keys if gemini_keys else []
            self.is_running = True

        def stop(self):
            self.is_running = False

        def run(self):
            try:
                self.log_signal.emit(f"📥 Đang gửi yêu cầu nhận {self.limit} sản phẩm từ Server Shopee Database (Market: {self.market})...")
                products = self.client.claim_jobs(
                    market=self.market,
                    client_id=self.client_id,
                    limit=self.limit,
                    sort_by=self.sort_by,
                    min_item_id=self.min_item_id,
                    min_commission=self.min_commission
                )
                if not products:
                    self.error_signal.emit("Không có sản phẩm nào được trả về từ Server (hoặc không khớp điều kiện lọc).")
                    return

                total = len(products)
                self.log_signal.emit(f"✅ Đã nhận {total} sản phẩm từ Server Shopee Database! Đang nạp vào danh sách hàng chờ...")

                valid_items = []
                for p in products:
                    if not self.is_running:
                        break
                    item_id = str(p.get("item_id", "0"))
                    name = p.get("name", "Product")
                    img_url = p.get("image_url", "")
                    valid_items.append({
                        "item_id": item_id,
                        "market": self.market,
                        "name": name,
                        "image_url": img_url,
                        "price": p.get("price", 0),
                        "sold": p.get("sold", 0),
                        "commission": p.get("commission_rate", 0)
                    })

                self.finished_signal.emit(valid_items)

            except Exception as e:
                self.error_signal.emit(f"Lỗi nhận SP: {str(e)}")
