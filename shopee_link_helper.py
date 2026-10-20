# -*- coding: utf-8 -*-
"""
shopee_link_helper.py - Import link Shopee cho AutoPromt Veo3Go.

Chức năng:
  * extract_links(text): lọc các link Shopee (kể cả link rút gọn shp.ee / s.shopee.vn) từ văn bản.
  * parse_link(url): đoán thị trường + shop_id + item_id từ link (không cần mạng).
  * fetch_product(url): lấy tên SP, mô tả, URL ảnh (og:image) từ trang sản phẩm - gọi khi tới lượt chạy.
  * download_image(url, path): tải ảnh về ổ đĩa (dự phòng khi urllib thường bị chặn).

Cách cào (xem _attempts): thử lần lượt dấu vân TLS trình duyệt thật của curl_cffi, UA WhatsApp,
rồi UA Facebook (cách cũ của AutoSeedvis, nay Shopee đã chặn 403), dừng khi lấy được thẻ Open Graph.
"""

import os
import re
import html as html_mod
import urllib.request
import urllib.error
import urllib.parse

try:  # curl_cffi giúp vượt kiểm tra TLS của Shopee; không bắt buộc
    from curl_cffi import requests as _cffi
except Exception:  # pragma: no cover
    _cffi = None

FACEBOOK_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
WHATSAPP_UA = "WhatsApp/2.23.20.0"
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Link Shopee: shopee.vn/..., s.shopee.vn/..., vn.shp.ee/..., shope.ee/... (có hoặc không có http)
RE_LINK = re.compile(
    r"(?:https?://)?(?:[a-z0-9-]+\.)*(?:shopee\.[a-z]{2,3}(?:\.[a-z]{2})?|shp\.ee|shope\.ee)/[^\s\"'<>]+",
    re.IGNORECASE,
)

RE_DASH_I = re.compile(r"-i\.(\d+)\.(\d+)")
RE_PRODUCT = re.compile(r"product/(\d+)/(\d+)")

DOMAIN_MARKET = {
    "shopee.vn": "VN",
    "shopee.ph": "PH",
    "shopee.co.id": "ID",
    "shopee.co.th": "TH",
    "shopee.com.my": "MY",
    "shopee.sg": "SG",
    "shopee.tw": "TW",
}

_META_RES = {
    "title": (
        re.compile(r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']*)["\']', re.I),
        re.compile(r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*property=["\']og:title["\']', re.I),
    ),
    "description": (
        re.compile(r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']*)["\']', re.I),
        re.compile(r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*property=["\']og:description["\']', re.I),
    ),
    "image": (
        re.compile(r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']*)["\']', re.I),
        re.compile(r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*property=["\']og:image["\']', re.I),
    ),
}


def extract_links(text):
    """Trả về danh sách link Shopee (giữ thứ tự, bỏ trùng) trong văn bản."""
    seen, out = set(), []
    for m in RE_LINK.finditer(text or ""):
        url = m.group(0).rstrip(".,;:!?)]}>\"'")
        if not re.match(r"https?://", url, re.I):
            url = "https://" + url
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _market_from_host(host):
    host = (host or "").lower()
    for dom, mk in DOMAIN_MARKET.items():
        if host == dom or host.endswith("." + dom):
            return mk
    return ""


def _find_ids(url):
    """Tìm (shop_id, item_id) trong URL; giải mã %-encode vì link đăng nhập hay bọc URL gốc trong ?next=."""
    s = url or ""
    for _ in range(3):
        m = RE_DASH_I.search(s) or RE_PRODUCT.search(s)
        if m:
            return m.group(1), m.group(2)
        decoded = urllib.parse.unquote(s)
        if decoded == s:
            break
        s = decoded
    return "", ""


def parse_link(url):
    """Phân tích link không cần mạng. Link rút gọn sẽ có item_id rỗng (xác định sau khi cào)."""
    host = urllib.parse.urlparse(url or "").netloc
    shop_id, item_id = _find_ids(url)
    return {"market": _market_from_host(host), "shop_id": shop_id, "item_id": item_id}


def _attempts():
    """Các cách truy cập trang SP, theo thứ tự thử. (impersonate, user-agent); impersonate=None => urllib.

    Thực tế kiểm tra: Shopee hiện chặn 403 với UA Facebook/Google/Twitter, nhưng cho qua
    khi dùng dấu vân TLS của trình duyệt thật (curl_cffi) không gắn UA riêng, hoặc UA WhatsApp.
    """
    atts = []
    if _cffi is not None:
        atts += [("chrome131", None), ("chrome124", WHATSAPP_UA), ("safari17_2_ios", None), ("chrome124", None)]
    atts += [(None, WHATSAPP_UA), (None, FACEBOOK_UA)]
    return atts


def _http_get(url, imp, ua, timeout):
    """Trả về (status, text, final_url)."""
    if imp and _cffi is not None:
        headers = {"User-Agent": ua} if ua else None
        resp = _cffi.get(url, impersonate=imp, headers=headers, timeout=timeout, allow_redirects=True)
        return resp.status_code, resp.text, str(resp.url)
    req = urllib.request.Request(url, headers={"User-Agent": ua or BROWSER_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body, resp.geturl()
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body, url


def _meta(html, key):
    for rx in _META_RES[key]:
        m = rx.search(html)
        if m:
            return html_mod.unescape(m.group(1)).strip()
    return ""


def fetch_product(url, timeout=15, retries=2):
    """Lấy thông tin SP từ link Shopee.

    Trả về dict: ok, error, title, description, image_url, market, shop_id, item_id.
    """
    result = {"ok": False, "error": "", "title": "", "description": "", "image_url": "",
              "market": "", "shop_id": "", "item_id": ""}
    pre = parse_link(url)
    result.update(market=pre["market"], shop_id=pre["shop_id"], item_id=pre["item_id"])

    fetch_url = url
    if pre["shop_id"] and pre["item_id"]:
        host = urllib.parse.urlparse(url).netloc or "shopee.vn"
        fetch_url = f"https://{host}/product/{pre['shop_id']}/{pre['item_id']}"

    last_err = ""
    for _ in range(max(1, retries)):
        for imp, ua in _attempts():
            label = f"{imp or 'urllib'}/{(ua or 'default')[:12]}"
            try:
                status, html, final_url = _http_get(fetch_url, imp, ua, timeout)
            except Exception as e:
                last_err = f"Lỗi kết nối ({label}): {e}"
                continue

            title = _meta(html, "title")
            for sep in (" | Shopee", " - Shopee"):
                idx = title.find(sep)
                if idx > 0:
                    title = title[:idx]
                    break
            img = _meta(html, "image")
            if "@resize" in img:
                img = img.split("@resize")[0]
            if img.startswith("//"):
                img = "https:" + img

            # Shopee trả trang xác minh chung / 403 khi nghi là bot => thử cách khác
            if not img or "Mua và Bán Trên Ứng Dụng" in title:
                last_err = f"Shopee chặn hoặc không có ảnh (HTTP {status})"
                continue

            # Link rút gọn: lấy ID / thị trường từ URL sau khi chuyển hướng
            if not result["item_id"]:
                sid, iid = _find_ids(final_url)
                if iid:
                    result.update(shop_id=sid, item_id=iid)
            if not result["market"]:
                result["market"] = _market_from_host(urllib.parse.urlparse(final_url).netloc)

            result.update(ok=True, title=title.strip(), description=_meta(html, "description"), image_url=img)
            return result

    result["error"] = last_err or "Không lấy được dữ liệu"
    return result


def download_image(url, save_path, timeout=20):
    """Tải ảnh về save_path. Trả True nếu thành công."""
    if not url:
        return False
    if url.startswith("//"):
        url = "https:" + url
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    try:
        if _cffi is not None:
            resp = _cffi.get(url, impersonate="chrome131", timeout=timeout)
            data = resp.content
        else:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Referer": "https://shopee.vn/"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
        if data and len(data) > 500:
            with open(save_path, "wb") as f:
                f.write(data)
            return True
    except Exception:
        pass
    return False
