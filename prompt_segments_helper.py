# -*- coding: utf-8 -*-
"""
Helper module for multi-segment video prompt generation and FFmpeg concatenation.
Designed for Veo3go / AutoPromt to support 16s (2 segments) and 24s (3 segments).
"""

import os
import sys
import time
import random
import shutil
import tempfile
import subprocess

# ==================== LANGUAGE DEFINITIONS ====================

_LANG_MAP = {
    "ph": {
        "instruction": "The model speaks Filipino",
        "country_en": "Filipino",
        "country_vi": "Philippines"
    },
    "vi": {
        "instruction": "Người mẫu nói tiếng Việt",
        "country_en": "Vietnamese",
        "country_vi": "Việt Nam"
    },
    "id": {
        "instruction": "The model speaks Indonesian",
        "country_en": "Indonesian",
        "country_vi": "Indonesia"
    },
    "my": {
        "instruction": "The model speaks Malay",
        "country_en": "Malaysian",
        "country_vi": "Malaysia"
    },
    "en": {
        "instruction": "The model speaks English",
        "country_en": "American",
        "country_vi": "Mỹ"
    }
}

DURATION_MAP = {
    8: [0],
    16: [0, 1],
    24: [2, 3, 4]
}

# ==================== CHARACTER POOLS ====================

_HAIR_POOL_EN = [
    "long straight black hair",
    "shoulder-length wavy brown hair",
    "short bob cut with dark hair",
    "long curly dark brown hair",
    "medium-length straight hair with subtle highlights",
    "ponytail with bangs, dark hair",
    "long flowing hair with soft waves",
    "elegant updo hairstyle with loose strands",
]

_HAIR_POOL_VI = [
    "tóc đen dài thẳng",
    "tóc nâu ngang vai hơi xoăn",
    "tóc ngắn kiểu bob đen",
    "tóc nâu đen dài xoăn tự nhiên",
    "tóc thẳng dài vừa có highlight nhẹ",
    "tóc buộc đuôi ngựa với mái trước, tóc đen",
    "tóc dài bồng bềnh xoăn sóng nhẹ",
    "tóc búi cao thanh lịch với vài lọn rơi",
]

_OUTFIT_POOL_EN = [
    "a crisp white blouse tucked into high-waisted beige trousers",
    "a soft pastel pink knit sweater with dark jeans",
    "a light blue button-down shirt with rolled sleeves and cream skirt",
    "a classic striped navy-and-white top with tailored pants",
    "an elegant sage green midi dress with subtle floral pattern",
    "a warm beige turtleneck with a brown corduroy skirt",
    "a lavender cardigan over a white camisole with light gray trousers",
    "a chic camel blazer over a black turtleneck with dark slacks",
]

_OUTFIT_POOL_VI = [
    "áo sơ mi trắng bỏ trong quần tây beige cạp cao",
    "áo len hồng pastel nhẹ nhàng phối quần jeans đen",
    "áo sơ mi xanh nhạt xắn tay phối chân váy kem",
    "áo kẻ sọc xanh navy-trắng cổ điển phối quần tây",
    "váy midi xanh lá nhạt thanh lịch có họa tiết hoa nhẹ",
    "áo cổ lọ beige ấm áp phối chân váy nhung nâu",
    "áo cardigan tím lavender khoác ngoài áo hai dây trắng phối quần xám nhạt",
    "áo blazer camel lịch lãm khoác ngoài áo cổ lọ đen phối quần tây đen",
]

_MY_MALE_HAIR_POOL = [
    "short neat black hair with clean side part, well-groomed",
    "medium-length wavy dark hair, well-groomed and professional",
    "short cropped hair with subtle fade, clean and tidy",
    "neatly styled dark hair, professional and fresh look",
    "short classic taper hairstyle, dark hair, very neat and clean",
]

_MY_MALE_OUTFIT_POOL = [
    "a clean white long-sleeve button-down shirt with dark trousers",
    "a navy blue long-sleeve polo shirt with beige chinos",
    "a smart casual light blue long-sleeve oxford shirt with dark pants",
    "a modern olive green long-sleeve shirt with dark trousers",
    "a minimalist charcoal gray long-sleeve shirt with khaki pants",
    "a light gray modest kurta-style long-sleeve shirt with dark trousers",
]

# ==================== TTS DIALOGUE POOLS ====================

TTS_MIDDLES_EN = [
    "It is incredibly designed with premium materials, making it feel very high-quality.",
    "The overall build is sturdy and highly functional, perfect for daily usage.",
    "It exceeded all my expectations with its outstanding design and usability.",
    "This product is a game-changer for me and has solved so many of my problems.",
    "The shape is elegant and the color is gorgeous, absolutely no flaws to complain about.",
    "Even when inspected closely, there are no defects whatsoever, 10 out of 10.",
    "It is lightweight yet very durable, making it highly portable and convenient.",
    "I highly recommend this to everyone looking for a reliable and stylish solution."
]

TTS_ENDINGS_EN = [
    "You definitely need this, I put the purchase link in the bottom left corner.",
    "Don't miss this opportunity, grab yours now before the sale ends.",
    "Click the yellow cart below to checkout right now, you won't regret it.",
    "It is very affordable yet high quality, limited stock, so buy it now.",
    "There is also free shipping available, checkout immediately to save big."
]

TTS_MIDDLES_PH = [
    "Napakaganda ng disenyo, napakapino ng mga detalye, at napakasarap hawakan.",
    "Napakaganda ng kalidad ng materyal, premium ang pakiramdam kapag hinawakan.",
    "Nang subukan ko, mas maganda at advanced ang mga feature kaysa sa nakikita sa ad.",
    "Eksakto ang sukat, parehong-pareho ang kulay sa larawan, napakasiya ko.",
    "Kapag tiningnan nang malapitan, makikitang pulido ang pagkakagawa sa bawat detalye."
]

TTS_ENDINGS_PH = [
    "Sa pangkalahatan, sulit na sulit! I-click na ang dilaw na cart ngayon.",
    "Huwag nang mag-atubili, ang link ng produkto ay nasa ibabang kaliwang bahagi.",
    "May malaking flash sale ngayon, mag-checkout na bago maubusan.",
    "Dapat itong bilhin! 100 points, i-click ang icon ng cart.",
    "Magugustuhan mo kapag hinawakan mo, i-click ang dilaw na cart.",
    "Kailangan ito ng lahat, inilagay ko ang link sa ibabang kaliwa.",
    "Maniwala ka sa akin, bilhin mo na ngayon, hindi ka magsisi.",
    "May libreng shipping din ang shop, i-checkout na ang order mo."
]

TTS_MIDDLES_VI = [
    "Thiết kế của sản phẩm này thực sự rất tỉ mỉ, cầm trên tay cảm giác đầm và chắc chắn.",
    "Chất liệu cao cấp vượt ngoài mong đợi của mình, sờ vào rất thích tay và mịn màng.",
    "Công năng của nó phải nói là quá tiện lợi, giải quyết ngay vấn đề bấy lâu nay của mình.",
    "Màu sắc bên ngoài đẹp hơn cả trong ảnh, đường nét tinh tế không một điểm chê.",
    "Từ ngày có em này thì cuộc sống tiện hơn hẳn, tiết kiệm được bao nhiêu thời gian.",
    "Độ hoàn thiện cực kỳ xuất sắc, từng chi tiết nhỏ đều được gia công sắc nét.",
    "Nhìn sang trọng và hiện đại cực kỳ, bạn bè ai tới nhà cũng hỏi mua ở đâu."
]

TTS_ENDINGS_VI = [
    "Túm lại là nên mua! Xứng đáng 100 điểm, ấn ngay biểu tượng giỏ hàng nhé.",
    "Cầm trên tay là ưng ngay, các tình yêu ấn ngay vào giỏ vàng nha.",
    "Ai cũng cần một em như này, tôi gắn link giỏ hàng bên dưới góc trái rồi đó.",
    "Nghe mị đi, bấm mua liền đi, chắc chắn sẽ không làm bạn thất vọng đâu.",
    "Shop đang hỗ trợ freeship nữa, ngại gì không nhấp vào giỏ hàng chốt đơn.",
    "Quá ngon bổ rẻ, hàng hiếm đó! Múc lẹ múc lẹ kẻo cháy hàng mấy bà ơi.",
    "Đừng lăn tăn nữa, ấn ngay giỏ hàng xách liền một em về dùng thử xem."
]

TTS_MIDDLES_ID = [
    "Desainnya sangat mulus, detailnya rapi, dan nyaman digenggam.",
    "Bahannya sangat berkualitas, terasa premium saat disentuh.",
    "Setelah mencoba, ternyata fiturnya jauh lebih canggih daripada iklannya.",
    "Sangat presisi, warnanya persis seperti di foto, sangat memuaskan.",
    "Dilihat dari dekat pun tidak ada cacat, kualitasnya bintang sepuluh."
]

TTS_ENDINGS_ID = [
    "Kesimpulannya ini sangat menguntungkan! Buruan klik keranjang kuning ya.",
    "Jangan sampai menyesal, link pembelian ada di sudut kiri bawah layar.",
    "Toko lagi ada flash sale besar, langsung checkout sebelum kehabisan.",
    "Sangat direkomendasikan! Nilai 100, klik ikon keranjang sekarang."
]

TTS_MIDDLES_MY = [
    "Reka bentuknya sangat kemas, perinciannya halus dan selesa dipegang.",
    "Kualiti bahannya memang terbaik, rasa sangat premium bila disentuh.",
    "Bila cuba sendiri, baru tahu fungsinya jauh lebih hebat daripada iklan.",
    "Saiznya sangat tepat, warna sebiji macam dalam gambar, memang puas hati.",
    "Tengok dari dekat pun tiada kecacatan, kemasan dia bagi 10 per 10."
]

TTS_ENDINGS_MY = [
    "Pendek kata memang berbaloi! Cepat tekan beg kuning sekarang ya.",
    "Jangan sampai terlepas, pautan ada di sudut bawah kiri skrin.",
    "Kedai tengah ada jualan kilat hebat, cepat checkout sebelum habis.",
    "Sangat disyorkan! Memang 100 markah, klik ikon beg sekarang."
]


def generate_tts_script(product_name, segment_index, total_segments, lang="en"):
    """Sinh kịch bản thoại (Voiceover) tự nhiên theo từng phân đoạn."""
    seed_val = sum(ord(c) for c in str(product_name))
    rng = random.Random(seed_val + segment_index * 13)

    lang_l = str(lang).lower()
    if lang_l == "vi":
        middles_pool = TTS_MIDDLES_VI
        endings_pool = TTS_ENDINGS_VI
        prefix_format = "Đối với {name}, "
        prefix_format_24s = "Về {name}, "
    elif lang_l == "id":
        middles_pool = TTS_MIDDLES_ID
        endings_pool = TTS_ENDINGS_ID
        prefix_format = "Untuk {name}, "
        prefix_format_24s = "Mengenai {name}, "
    elif lang_l in ("my", "ms"):
        middles_pool = TTS_MIDDLES_MY
        endings_pool = TTS_ENDINGS_MY
        prefix_format = "Untuk {name}, "
        prefix_format_24s = "Mengenai {name}, "
    elif lang_l == "ph":
        middles_pool = TTS_MIDDLES_PH
        endings_pool = TTS_ENDINGS_PH
        prefix_format = "Para sa {name}, "
        prefix_format_24s = "Tungkol sa {name}, "
    else:
        middles_pool = TTS_MIDDLES_EN
        endings_pool = TTS_ENDINGS_EN
        prefix_format = "For {name}, "
        prefix_format_24s = "About {name}, "

    middles = rng.sample(middles_pool, min(2, len(middles_pool)))
    ending = rng.choice(endings_pool)

    if total_segments == 2:
        if segment_index == 0:
            feat1 = middles[0]
            prefix = prefix_format.format(name=product_name)
            return prefix + feat1[0].lower() + feat1[1:]
        else:
            feat2 = middles[-1]
            return feat2 + " " + ending
    else:
        if segment_index == 0:
            feat1 = middles[0]
            prefix = prefix_format_24s.format(name=product_name)
            return prefix + feat1[0].lower() + feat1[1:]
        elif segment_index == 1:
            return middles[-1]
        else:
            return ending


# ==================== PROMPT TEMPLATES ====================

_CONT_FALLBACK_EN = (
    "=== SECTION 1: GENERAL RULES & NEGATIVE CONSTRAINTS ===\n"
    "[DIRECTIVES & PROMPT LOCKS]\n"
    "- The video structure must strictly follow the Timeline Action descriptions with clean continuity.\n"
    "- Ensure perfect temporal consistency - the presenter's face, body, clothing, and the product must remain 100% identical and stable across all frames with no morphing, no identity drift, and no sudden changes.\n"
    "- The product in the reference image is the primary focal point: It must remain clearly visible, properly framed, and in sharp focus throughout the entire video. Maintain its real-world proportions, colors, textures, and details.\n"
    "- FRAMING LOCK: Generate a full-frame vertical 9:16 portrait video. The reference image must fill the entire frame edge-to-edge with NO letterboxing, NO pillarboxing, NO black bars, NO white borders, NO frame-within-frame effect, and NO empty side margins.\n"
    "- PRODUCT CONSISTENCY LOCK: The product shown in frame 1 must be the EXACT SAME product in every subsequent frame. Its color, shape, size, material texture, and all distinguishing features must NOT change, swap, or gradually transform at any point in the video - especially in the final 1-2 seconds.\n"
    "- REALISTIC PRODUCT SIZE (CRITICAL): The product MUST have its REAL-LIFE, NATURAL size proportional to the human body. DO NOT enlarge or exaggerate product size - small items (cosmetics, phone, bottle) should be naturally small in hands, NOT oversized.\n"
    "- ITEM PERSISTENCE & HAND LOCK: Any object the presenter holds or wears at the start must remain naturally present throughout. The presenter has exactly TWO normal human hands with five fingers each. Do NOT generate extra hands, extra arms, extra fingers, or limb deformations.\n"
    "\n"
    "[NEGATIVE PROMPTS]\n"
    "- No chaotic morphing or unnatural transformation.\n"
    "- ABSOLUTELY NO text, NO letters, NO numbers, NO subtitles, NO captions, NO titles, NO watermarks, NO logo overlays, NO HUD, NO UI graphics.\n"
    "- No letterbox, no black bars, no white borders.\n"
    "- No cartoon, anime, illustration, 3D CGI render, or deepfake look. Live-action real camera footage only.\n"
    "- Color grading is strictly natural, true-to-life, clean white balance.\n"
    "- No anatomical anomalies, no extra limbs, no deformed hands, no missing fingers.\n"
    "\n"
    "=== SECTION 2: PRODUCT TO ADVERTISE ===\n"
    "- Product: {name}\n"
    "- The product matches the reference image exactly in appearance, color, and packaging.\n"
    "\n"
    "=== SECTION 3: SUBJECT & CHARACTER CONSISTENCY ===\n"
    "- Presenter: A cheerful and friendly 22-year-old {country_en} woman, natural makeup, warm welcoming smile.\n"
    "- Hair: {hair}.\n"
    "- Outfit: {outfit}.\n"
    "- CRITICAL IDENTITY & OUTFIT LOCK: The presenter MUST have the EXACT SAME face, facial features, skin tone, hairstyle ({hair}), and outfit ({outfit}) throughout ALL segments - DO NOT change her identity or clothing across clips.\n"
    "\n"
    "=== SECTION 4: SCENE & ACTION SEQUENCE ===\n"
    "- Environment: {scene}\n"
)

_CONT_FALLBACK_VI = (
    "=== SECTION 1: GENERAL RULES & NEGATIVE CONSTRAINTS ===\n"
    "[CHỈ THỊ CỐT LÕI & CÁC KHÓA BẢO VỆ]\n"
    "- Cấu trúc video phải tuân thủ nghiêm ngặt mô tả Timeline Action với sự tiếp nối liền mạch.\n"
    "- ĐỒNG BỘ THỜI GIAN TUYỆT ĐỐI: Khuôn mặt, vóc dáng, trang phục của người dẫn và sản phẩm phải giữ nguyên vẹn 100% qua mọi khung hình, không bị trôi danh tính hay biến dạng.\n"
    "- SẢN PHẨM LÀ TRỌNG TÂM: Sản phẩm trong ảnh tham chiếu phải luôn hiển thị rõ ràng, đúng tỷ lệ thực tế, màu sắc và chất liệu nguyên bản.\n"
    "- KHÓA KHUNG HÌNH 9:16: Toàn khung hình dọc 9:16 portrait, KHÔNG viền đen, KHÔNG viền trắng hai bên.\n"
    "- KHÓA TAY TỰ NHIÊN: Người dẫn có chính xác HAI bàn tay người bình thường, mỗi bàn tay 5 ngón. TUYỆT ĐỐI KHÔNG tạo thừa ngón, thừa tay, tay dị tật.\n"
    "\n"
    "[PROMPT PHỦ ĐỊNH]\n"
    "- TUYỆT ĐỐI KHÔNG chữ, KHÔNG phụ đề, KHÔNG logo, KHÔNG watermark trên màn hình.\n"
    "- KHÔNG hoạt hình, anime, 3D CGI render. Phải là cảnh quay thực tế người thật chân thực.\n"
    "- Màu sắc chuẩn trung tính, sáng đẹp tự nhiên.\n"
    "\n"
    "=== SECTION 2: SẢN PHẨM QUẢNG CÁO ===\n"
    "- Sản phẩm: {name}\n"
    "- Sản phẩm khớp hoàn toàn với ảnh tham chiếu về kiểu dáng, màu sắc và chi tiết bao bì.\n"
    "\n"
    "=== SECTION 3: ĐỒNG NHẤT NHÂN VẬT & TRANG PHỤC ===\n"
    "- Người dẫn: Nữ 22 tuổi người {country_vi}, gương mặt rạng rỡ tươi tắn, nụ cười thân thiện.\n"
    "- Kiểu tóc: {hair}.\n"
    "- Trang phục: {outfit}.\n"
    "- KHÓA DANH TÍNH TUYỆT ĐỐI: Người dẫn PHẢI CÙNG khuôn mặt, CÙNG kiểu tóc ({hair}), CÙNG trang phục ({outfit}) qua TẤT CẢ các phân đoạn.\n"
    "\n"
    "=== SECTION 4: BỐI CẢNH & HÀNH ĐỘNG ===\n"
    "- Bối cảnh: {scene}\n"
)

SEGMENT_POOL_FALLBACK_EN = [
    # 0: CLIP 1 — HOOK + DEMO (0-8s)
    (
        _CONT_FALLBACK_EN +
        "- Timeline Action for Segment 1 (0-8 seconds):\n"
        "  * HOOK + DEMO: Eye-catching opening with product demonstration. The presenter reveals '{name}' (from reference image) with an excited expression and 'wow' reaction.\n"
        "  * Camera executes dynamic push-in on the product for an impressive reveal moment.\n"
        "  * Then she smoothly demonstrates how '{name}' works with clear hand movements, showing genuine satisfaction.\n"
        "  * ENDING POSE (CRITICAL HANDOFF): The clip MUST END with the woman holding '{name}' with BOTH HANDS at CHEST LEVEL, facing the camera, smiling — this exact pose will be the starting point of the next segment.\n"
        "  * Seconds 7-8: Freeze into static pose with zero movement drift.\n"
        "\n"
        "=== SECTION 5: CAMERA & TECHNICAL SPECIFICATIONS ===\n"
        "- Camera: Dynamic push-in on reveal, then medium shot, 35mm lens feel, punchy cinematic daylight.\n"
        "- Color & Grading: Neutral color calibration, natural skin tones, ultra sharp focus on product.\n"
        "\n"
        "=== SECTION 6: DIALOGUE & SPOKEN SCRIPT ===\n"
        "- [{lang_instruction} naturally. The presenter speaks this exact dialogue: \"{dialogue}\"]\n\n"
    ),
    # 1: CLIP 2 — BENEFIT + CTA (8-16s)
    (
        _CONT_FALLBACK_EN +
        "- Timeline Action for Segment 2 (8-16 seconds):\n"
        "  * BENEFIT + CTA: Seamless continuation. CRITICAL: NO greeting or introduction.\n"
        "  * STARTING POSE (MUST MATCH): The SAME presenter (SAME face, SAME hair, SAME outfit) is ALREADY holding '{name}' with BOTH HANDS at CHEST LEVEL — continuing from where she left off.\n"
        "  * She holds '{name}' close to camera, pointing at key features with an impressed nod.\n"
        "  * Camera zooms into tight close-up showing product details, then she holds '{name}' up next to her face with a confident smile and thumbs-up.\n"
        "\n"
        "=== SECTION 5: CAMERA & TECHNICAL SPECIFICATIONS ===\n"
        "- Camera: Macro close-up then slow cinematic zoom out to medium shot, warm trustworthy lighting.\n"
        "- Color & Grading: Clean white balance, sharp subject separation, professional commercial finish.\n"
        "\n"
        "=== SECTION 6: DIALOGUE & SPOKEN SCRIPT ===\n"
        "- [{lang_instruction} naturally. The presenter speaks this exact dialogue: \"{dialogue}\"]\n\n"
    ),
    # 2: 24s CLIP 1 — REVIEW (0-8s)
    (
        _CONT_FALLBACK_EN +
        "- Timeline Action for Segment 1 of 3 (0-8 seconds):\n"
        "  * Product review opening. CRITICAL: DO NOT start with greeting or waving. Start DIRECTLY with product.\n"
        "  * The presenter is ALREADY holding '{name}' (from reference image) with both hands at chest level and carefully inspecting build quality and surface texture.\n"
        "  * She looks at camera and begins sharing honest first impressions naturally.\n"
        "  * ENDING POSE (CRITICAL HANDOFF): The clip MUST END with the woman holding '{name}' with BOTH HANDS at CHEST LEVEL, facing camera, mouth slightly open as if mid-sentence.\n"
        "  * Seconds 7-8: Freeze into static pose with zero movement drift.\n"
        "\n"
        "=== SECTION 5: CAMERA & TECHNICAL SPECIFICATIONS ===\n"
        "- Camera: Steady medium shot (waist-up), gentle subtle orbit, 35mm lens feel, natural warm lighting.\n"
        "- Color & Grading: Neutral calibration, natural skin tones, product clearly visible.\n"
        "\n"
        "=== SECTION 6: DIALOGUE & SPOKEN SCRIPT ===\n"
        "- [{lang_instruction} naturally. The presenter speaks this exact dialogue: \"{dialogue}\"]\n\n"
    ),
    # 3: 24s CLIP 2 — DEMO HANDS-ON (8-16s)
    (
        _CONT_FALLBACK_EN +
        "- Timeline Action for Segment 2 of 3 (8-16 seconds):\n"
        "  * Hands-on product demo — seamless continuation. CRITICAL: NO greeting or introduction.\n"
        "  * STARTING POSE (MUST MATCH): The SAME presenter is ALREADY holding '{name}' with BOTH HANDS at CHEST LEVEL, mid-sentence — continuing directly from where she left off.\n"
        "  * She actively demonstrates '{name}' in action: showing sides, pressing buttons, bringing it close to camera for macro view.\n"
        "  * ENDING POSE (CRITICAL HANDOFF): The clip MUST END with the woman holding '{name}' UP with ONE HAND near FACE level, the other hand pointing at the product.\n"
        "  * Seconds 15-16: Freeze into static pose with zero movement drift.\n"
        "\n"
        "=== SECTION 5: CAMERA & TECHNICAL SPECIFICATIONS ===\n"
        "- Camera: Smooth push-in for tight close-ups of product details and craftsmanship, 50mm lens.\n"
        "- Color & Grading: Consistent warm daylight matching segment 1.\n"
        "\n"
        "=== SECTION 6: DIALOGUE & SPOKEN SCRIPT ===\n"
        "- [{lang_instruction} naturally. The presenter speaks this exact dialogue: \"{dialogue}\"]\n\n"
    ),
    # 4: 24s CLIP 3 — TARGET + CTA (16-24s)
    (
        _CONT_FALLBACK_EN +
        "- Timeline Action for Segment 3 of 3 (16-24 seconds):\n"
        "  * Call to action — seamless continuation. CRITICAL: NO greeting or waving.\n"
        "  * STARTING POSE (MUST MATCH): The SAME presenter is ALREADY holding '{name}' UP with ONE HAND near FACE level — continuing directly from where she left off.\n"
        "  * She speaks with a warm engaging tone, holding '{name}' proudly with both hands, nodding enthusiastically.\n"
        "  * Confident smile with double thumbs-up, giving clear recommendation to buy.\n"
        "\n"
        "=== SECTION 5: CAMERA & TECHNICAL SPECIFICATIONS ===\n"
        "- Camera: Medium shot with slow zoom out to wide shot, bright inviting lighting.\n"
        "- Color & Grading: Clean white balance, sharp focus, professional finish.\n"
        "\n"
        "=== SECTION 6: DIALOGUE & SPOKEN SCRIPT ===\n"
        "- [{lang_instruction} naturally. The presenter speaks this exact dialogue: \"{dialogue}\"]\n\n"
    )
]

SEGMENT_POOL_FALLBACK_VI = [
    # 0: CLIP 1 (0-8s)
    (
        _CONT_FALLBACK_VI +
        "- Timeline Action cho Đoạn 1 (0-8 giây):\n"
        "  * MỞ ĐẦU THU HÚT: Người dẫn bất ngờ giới thiệu '{name}' (từ ảnh tham chiếu) với biểu cảm thích thú và hào hứng.\n"
        "  * Camera lướt nhẹ cận cảnh sản phẩm tạo khoảnh khắc ấn tượng.\n"
        "  * Cô cầm sản phẩm trình diễn các thao tác sử dụng mượt mà, khuôn mặt toát lên sự hài lòng tự nhiên.\n"
        "  * TƯ THẾ KẾT THÚC (QUAN TRỌNG): Clip PHẢI KẾT THÚC với cô gái cầm '{name}' bằng HAI TAY ở tầm NGANG NGỰC, hướng nhìn camera, mỉm cười — đây chính là tư thế bắt đầu đoạn tiếp theo.\n"
        "  * Giây 7-8: Chốt lại tư thế tĩnh hoàn toàn, không trôi dạt chuyển động.\n"
        "\n"
        "=== SECTION 5: CAMERA & THÔNG SỐ KỸ THUẬT ===\n"
        "- Camera: Push-in mở đầu, sau đó chuyển medium shot góc máy điện ảnh 35mm.\n"
        "- Màu sắc: Chuẩn trung tính, màu da tự nhiên, lấy nét sắc sảo vào sản phẩm.\n"
        "\n"
        "=== SECTION 6: LỜI THOẠI & KỊCH BẢN ===\n"
        "- [{lang_instruction} tự nhiên. Người dẫn nói đúng câu thoại: \"{dialogue}\"]\n\n"
    ),
    # 1: CLIP 2 (8-16s)
    (
        _CONT_FALLBACK_VI +
        "- Timeline Action cho Đoạn 2 (8-16 giây):\n"
        "  * LỢI ÍCH & KÊU GỌI: Nối tiếp hoàn hảo từ đoạn trước. QUAN TRỌNG: TUYỆT ĐỐI KHÔNG chào hỏi lại từ đầu.\n"
        "  * TƯ THẾ BẮT ĐẦU (PHẢI KHỚP): CÙNG cô gái (CÙNG khuôn mặt, CÙNG kiểu tóc, CÙNG trang phục) ĐANG cầm '{name}' bằng HAI TAY ở tầm NGANG NGỰC — tiếp tục ngay tại điểm dừng.\n"
        "  * Cô đưa sản phẩm lại gần camera hơn, chỉ ngón tay vào tính năng nổi bật, gật đầu tâm đắc.\n"
        "  * Kết thúc bằng việc giơ '{name}' lên ngang mặt với nụ cười rạng rỡ và giơ ngón tay cái tán thưởng.\n"
        "\n"
        "=== SECTION 5: CAMERA & THÔNG SỐ KỸ THUẬT ===\n"
        "- Camera: Cận cảnh chi tiết rồi zoom ra medium shot, ánh sáng thương mại ấm áp.\n"
        "- Màu sắc: Tương phản mềm mại, hoàn thiện sắc nét cao cấp.\n"
        "\n"
        "=== SECTION 6: LỜI THOẠI & KỊCH BẢN ===\n"
        "- [{lang_instruction} tự nhiên. Người dẫn nói đúng câu thoại: \"{dialogue}\"]\n\n"
    ),
    # 2: 24s CLIP 1
    (
        _CONT_FALLBACK_VI +
        "- Timeline Action cho Đoạn 1 trên 3 (0-8 giây):\n"
        "  * Mở đầu đánh giá sản phẩm. QUAN TRỌNG: Bắt đầu TRỰC TIẾP với sản phẩm, không vẫy tay chào.\n"
        "  * Cô gái ĐANG cầm '{name}' bằng HAI TAY ở tầm NGANG NGỰC và chia sẻ cảm nhận ban đầu.\n"
        "  * TƯ THẾ KẾT THÚC: Clip kết thúc với cô gái cầm '{name}' bằng HAI TAY ở tầm NGANG NGỰC, hướng nhìn camera.\n"
        "  * Giây 7-8: Đóng băng chuyển động giữ nguyên tư thế.\n"
        "\n"
        "=== SECTION 5: CAMERA & THÔNG SỐ KỸ THUẬT ===\n"
        "- Camera: Medium shot ổn định, 35mm lens, ánh sáng tự nhiên.\n"
        "\n"
        "=== SECTION 6: LỜI THOẠI & KỊCH BẢN ===\n"
        "- [{lang_instruction} tự nhiên. Người dẫn nói câu thoại: \"{dialogue}\"]\n\n"
    ),
    # 3: 24s CLIP 2
    (
        _CONT_FALLBACK_VI +
        "- Timeline Action cho Đoạn 2 trên 3 (8-16 giây):\n"
        "  * Trình diễn chi tiết — tiếp nối liền mạch.\n"
        "  * TƯ THẾ BẮT ĐẦU: CÙNG cô gái ĐANG cầm '{name}' bằng HAI TAY ở tầm NGANG NGỰC.\n"
        "  * Cô thao tác chi tiết trên sản phẩm cho camera thấy rõ kết cấu.\n"
        "  * TƯ THẾ KẾT THÚC: Clip kết thúc với cô gái giơ '{name}' LÊN CAO bằng MỘT TAY gần tầm MẶT.\n"
        "  * Giây 15-16: Đóng băng chuyển động giữ nguyên tư thế.\n"
        "\n"
        "=== SECTION 5: CAMERA & THÔNG SỐ KỸ THUẬT ===\n"
        "- Camera: Push-in cận cảnh chi tiết rồi trở lại medium shot.\n"
        "\n"
        "=== SECTION 6: LỜI THOẠI & KỊCH BẢN ===\n"
        "- [{lang_instruction} tự nhiên. Người dẫn nói câu thoại: \"{dialogue}\"]\n\n"
    ),
    # 4: 24s CLIP 3
    (
        _CONT_FALLBACK_VI +
        "- Timeline Action cho Đoạn 3 trên 3 (16-24 giây):\n"
        "  * Kêu gọi hành động — tiếp nối liền mạch đến kết thúc.\n"
        "  * TƯ THẾ BẮT ĐẦU: CÙNG cô gái ĐANG giơ '{name}' LÊN CAO bằng MỘT TAY gần tầm MẶT.\n"
        "  * Cô giới thiệu nồng nhiệt tới người xem và kết thúc bằng nụ cười tự tin cùng hai ngón cái giơ lên.\n"
        "\n"
        "=== SECTION 5: CAMERA & THÔNG SỐ KỸ THUẬT ===\n"
        "- Camera: Medium shot nhẹ nhàng zoom ra toàn cảnh, ánh sáng thương mại đáng tin cậy.\n"
        "\n"
        "=== SECTION 6: LỜI THOẠI & KỊCH BẢN ===\n"
        "- [{lang_instruction} tự nhiên. Người dẫn nói câu thoại: \"{dialogue}\"]\n\n"
    )
]


# ==================== MAIN BUILDER FUNCTIONS ====================

def clean_title(name):
    """Làm sạch tiêu đề sản phẩm."""
    if not name:
        return "featured product"
    s = str(name).strip()
    import re
    s = re.sub(r'\[.*?\]', '', s)
    s = re.sub(r'【.*?】', '', s)
    s = re.sub(r'[\(\)]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:75].strip() or "featured product"


def build_segment_prompts(product_name, market="PH", duration_sec=16,
                          review_style="🎲 Random", scene_choice="🎲 Random",
                          prompt_mode="Prompt A + B", gemini_keys=None):
    """
    Sinh danh sách Prompt theo từng Segment (phân đoạn) tương ứng với độ dài:
    - 8s  -> 1 prompt (TVC chuẩn)
    - 16s -> 2 prompts (Segment 1: Hook + Demo 8s, Segment 2: Benefit + CTA 8s)
    - 24s -> 3 prompts (Segment 1, 2, 3 x 8s)
    Có khóa tư thế Handoff pose & đồng nhất nhân vật / trang phục giữa các đoạn.
    """
    from shopee_db_helper import build_tvc_prompt, pick_scene

    dur = int(duration_sec or 8)
    if dur <= 8:
        p, _ = build_tvc_prompt(product_name, market=market, review_style=review_style, scene_choice=scene_choice)
        return [p]

    mkt = str(market or "PH").upper()
    lang_code = "ph" if mkt == "PH" else ("vi" if mkt == "VN" else ("id" if mkt == "ID" else ("my" if mkt == "MY" else "en")))
    lang_info = _LANG_MAP.get(lang_code, _LANG_MAP["en"])

    indices = DURATION_MAP.get(dur, DURATION_MAP[16])
    n_segments = len(indices)
    prod_clean = clean_title(product_name)
    scene_en = pick_scene(scene_choice, lang="en")

    # Thị trường Malaysia: ưu tiên mẫu nam lịch sự
    is_my = (mkt == "MY")
    if is_my:
        hair = random.choice(_MY_MALE_HAIR_POOL)
        outfit = random.choice(_MY_MALE_OUTFIT_POOL)
    else:
        hair_pool = _HAIR_POOL_VI if lang_code == "vi" else _HAIR_POOL_EN
        outfit_pool = _OUTFIT_POOL_VI if lang_code == "vi" else _OUTFIT_POOL_EN
        hair = random.choice(hair_pool)
        outfit = random.choice(outfit_pool)

    pool = SEGMENT_POOL_FALLBACK_VI if lang_code == "vi" else SEGMENT_POOL_FALLBACK_EN

    prompts = []
    for i, idx in enumerate(indices):
        dialogue = generate_tts_script(prod_clean, i, n_segments, lang=lang_code)
        seg_prompt = pool[idx].format(
            name=prod_clean,
            scene=scene_en,
            lang_instruction=lang_info["instruction"],
            country_en=lang_info["country_en"],
            country_vi=lang_info["country_vi"],
            hair=hair,
            outfit=outfit,
            dialogue=dialogue
        )

        if is_my:
            # Điều chỉnh ngôn từ cho mẫu nam Malaysia
            seg_prompt = seg_prompt.replace("A 22-year-old Malaysian woman", "A handsome 25-year-old Malay male presenter")
            seg_prompt = seg_prompt.replace("the woman", "the presenter")
            seg_prompt = seg_prompt.replace("she ", "he ")
            seg_prompt = seg_prompt.replace("She ", "He ")
            seg_prompt = seg_prompt.replace("her ", "his ")
            seg_prompt = seg_prompt.replace("Her ", "His ")

        prompts.append(seg_prompt.strip())

    return prompts


# ==================== FFMPEG VIDEO CONCATENATION ====================

def get_ffmpeg_bin():
    """Tìm file thực thi ffmpeg trên hệ thống."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "vanthe_155", "bin", "ffmpeg.exe"),
        os.path.join(script_dir, "bin", "ffmpeg.exe"),
        os.path.join(script_dir, "ffmpeg.exe"),
        shutil.which("ffmpeg")
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return "ffmpeg"


def concat_videos(clip_paths, output_path, log=None):
    """
    Ghép nối nhiều video clip thành 1 video hoàn chỉnh bằng FFmpeg demuxer.
    Ưu tiên dùng stream copy (-c copy) siêu nhanh (~0.5s).
    Nếu stream copy lỗi -> tự động fallback sang re-encode libx264 an toàn.
    """
    def _log(m):
        if log:
            try:
                log(m)
            except Exception:
                pass

    if not clip_paths:
        _log("❌ Không có clip nào để ghép!")
        return False

    valid_clips = [p for p in clip_paths if p and os.path.exists(p) and os.path.getsize(p) > 10240]
    if not valid_clips:
        _log("❌ Các file clip đầu vào đều rỗng hoặc không tồn tại!")
        return False

    if len(valid_clips) == 1:
        _log("ℹ Chỉ có 1 clip, tiến hành sao chép sang file đích...")
        shutil.copy2(valid_clips[0], output_path)
        return True

    ffmpeg_bin = get_ffmpeg_bin()
    tmp_dir = tempfile.gettempdir()
    list_file = os.path.join(tmp_dir, f"concat_{int(time.time())}_{random.randint(1000, 9999)}.txt")

    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for p in valid_clips:
                clean_p = p.replace(os.sep, "/")
                f.write(f"file '{clean_p}'\n")

        # Thử nghiệm 1: Stream copy (nhanh nhất, giữ nguyên chất lượng gốc)
        cmd_copy = [
            ffmpeg_bin, "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-movflags", "+faststart",
            output_path
        ]
        _log(f"🔧 Đang ghép nối {len(valid_clips)} clips bằng FFmpeg (stream copy)...")
        res = subprocess.run(cmd_copy, capture_output=True, text=True, timeout=180, creationflags=creation_flags)

        if res.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 10240:
            _log("⚠️ Stream copy không tương thích, chuyển sang chế độ re-encode...")
            cmd_reencode = [
                ffmpeg_bin, "-y",
                "-f", "concat", "-safe", "0",
                "-i", list_file,
                "-c:v", "libx264", "-preset", "superfast", "-crf", "23",
                "-threads", "2",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                output_path
            ]
            res = subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=300, creationflags=creation_flags)

        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 10240:
            size_kb = os.path.getsize(output_path) // 1024
            _log(f"✅ Ghép nối hoàn tất: {os.path.basename(output_path)} ({size_kb} KB)")
            return True
        else:
            err_snip = (res.stderr or "")[-300:].strip()
            _log(f"❌ FFmpeg ghép nối thất bại: {err_snip}")
            return False

    except subprocess.TimeoutExpired:
        _log("❌ FFmpeg ghép nối bị timeout!")
        return False
    except Exception as e:
        _log(f"❌ Lỗi ngoại lệ khi ghép video: {e}")
        return False
    finally:
        try:
            if os.path.exists(list_file):
                os.remove(list_file)
        except Exception:
            pass
