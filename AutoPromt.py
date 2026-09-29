import sys
import os
import json
import time
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
_main_window = None


def _handle_uncaught_exception(exc_type, exc_value, exc_tb):
    """Ghi lỗi ra crash_log.txt và báo cho người dùng, thay vì để cửa sổ cmd tự tắt mất lỗi."""
    detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    crash_path = os.path.join(APP_DIR, "crash_log.txt")
    try:
        with open(crash_path, "a", encoding="utf-8") as f:
            f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{detail}")
    except Exception:
        pass
    try:
        sys.__stderr__.write(detail)
    except Exception:
        pass

    # Khi app đã chạy: đưa lỗi vào khung log, không bật hộp thoại liên tục
    if _main_window is not None:
        try:
            _main_window.log(f"[Lỗi] {exc_type.__name__}: {exc_value} (chi tiết trong crash_log.txt)")
            return
        except Exception:
            pass

    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            f"{exc_type.__name__}: {exc_value}\n\nChi tiết đã ghi vào:\n{crash_path}",
            "AutoPromt - Lỗi",
            0x10
        )
    except Exception:
        pass


sys.excepthook = _handle_uncaught_exception

import uuid
import hmac
import hashlib
import winreg
import urllib.request
import urllib.parse
import asyncio
import websockets
import re
import shutil
import subprocess
from PySide6.QtCore import QThread, Signal, QObject, Qt, Slot, QRect, QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QFileDialog, QProgressBar, QTextEdit, QComboBox, QCheckBox,
                             QHeaderView, QMessageBox, QTabWidget, QSplitter, QFrame,
                             QSpinBox, QDialog, QPlainTextEdit, QStyle, QStyleOptionButton,
                             QGroupBox)
from PySide6.QtGui import QColor, QFont, QIcon

from shopee_db_helper import (
    load_settings as load_shopee_settings,
    save_settings as save_shopee_settings,
    clean_product_title,
    build_tvc_prompt,
    ShopeeDatabaseClient,
    ShopeeClaimWorker,
    SCENES as SHOPEE_SCENES,
    REVIEW_STYLES as SHOPEE_REVIEW_STYLES,
    MARKETS as SHOPEE_MARKETS,
    DEFAULT_SETTINGS as SHOPEE_DEFAULT_SETTINGS
)


import threading
_accounts_file_lock = threading.Lock()

def log_to_file(text):
    try:
        import time
        with open("logs.txt", "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")
    except Exception:
        pass


class CheckBoxHeader(QHeaderView):
    stateChanged = Signal(int)

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.isOn = False

    def paintSection(self, painter, rect, logicalIndex):
        painter.save()
        super().paintSection(painter, rect, logicalIndex)
        painter.restore()

        if logicalIndex == 0:
            option = QStyleOptionButton()
            option.rect = QRect(rect.x() + (rect.width() - 18) // 2, rect.y() + (rect.height() - 18) // 2, 18, 18)
            option.state = QStyle.State_Enabled | QStyle.State_Active
            if self.isOn:
                option.state |= QStyle.State_On
            else:
                option.state |= QStyle.State_Off
            self.style().drawControl(QStyle.CE_CheckBox, option, painter)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Qt6: pos() đã deprecated, dùng position() (QPointF) rồi đổi sang QPoint
            index = self.logicalIndexAt(event.position().toPoint())
            if index == 0:
                self.isOn = not self.isOn
                self.viewport().update()
                self.stateChanged.emit(2 if self.isOn else 0)
                return
        super().mousePressEvent(event)


DEFAULT_HUB_HTTP = "https://11labs.net"
DEFAULT_WSS = "wss://ws.nhungoc.me/"

STYLING = """
QMainWindow {
    background-color: #0F0F1A;
}
QWidget {
    color: #A0A5C0;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}
QLabel {
    color: #C0C5E0;
}
QLabel#titleLabel {
    color: #FFFFFF;
    font-size: 22px;
    font-weight: bold;
}
QLineEdit, QComboBox, QTextEdit {
    background-color: #191B2A;
    border: 1px solid #2F324D;
    border-radius: 6px;
    padding: 6px 10px;
    color: #FFFFFF;
}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #00F0FF;
}
QPushButton {
    background-color: #2F324D;
    border: none;
    border-radius: 6px;
    padding: 8px 15px;
    color: #FFFFFF;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3F436B;
}
QPushButton:pressed {
    background-color: #1F2133;
}
QPushButton#btnRun {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #BD00FF, stop:1 #00F0FF);
    color: #0F0F1A;
}
QPushButton#btnRun:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #D033FF, stop:1 #33F3FF);
}
QPushButton#btnStop {
    background-color: #E63946;
    color: #FFFFFF;
}
QPushButton#btnStop:hover {
    background-color: #FF4D5A;
}
QTableWidget {
    background-color: #131422;
    border: 1px solid #2F324D;
    gridline-color: #1F2135;
    border-radius: 8px;
    color: #FFFFFF;
}
QTableWidget::item {
    padding: 5px;
}
QTableWidget::item:selected {
    background-color: #2A2C42;
    color: #00F0FF;
}
QHeaderView::section {
    background-color: #191B2A;
    color: #FFFFFF;
    padding: 5px;
    border: none;
    border-bottom: 2px solid #BD00FF;
    font-weight: bold;
}
QProgressBar {
    background-color: #191B2A;
    border: 1px solid #2F324D;
    border-radius: 6px;
    text-align: center;
    color: #FF4D5A;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #00F0FF;
    border-radius: 5px;
}
QTabWidget::pane {
    border: 1px solid #2F324D;
    background-color: #131422;
    border-radius: 8px;
}
QTabBar::tab {
    background-color: #191B2A;
    border: 1px solid #2F324D;
    border-bottom-color: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 8px 16px;
    color: #A0A5C0;
}
QTabBar::tab:selected {
    background-color: #131422;
    border-bottom-color: #131422;
    color: #00F0FF;
    font-weight: bold;
}
QScrollBar:vertical {
    border: none;
    background-color: #131422;
    width: 10px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background-color: #2F324D;
    min-height: 20px;
    border-radius: 5px;
}
QScrollBar::handle:vertical:hover {
    background-color: #00F0FF;
}
QMessageBox {
    background-color: #161826;
}
QMessageBox QLabel {
    color: #FFFFFF;
}
QMessageBox QPushButton {
    background-color: #2F324D;
    color: #FFFFFF;
    font-weight: bold;
    border-radius: 6px;
    padding: 6px 12px;
}
QMessageBox QPushButton:hover {
    background-color: #3F436B;
}
"""

def get_real_hardware_info():
    """Lấy thông tin phần cứng chuẩn xác tương thích Veo3Go 1.5.5"""
    import subprocess
    import hashlib
    import winreg
    
    # 1. Đọc từ cache Registry (hệ sinh thái 1.5.5 lưu trữ)
    for reg_path in [
        r"Software\ElevenLabs\ElevenLabs TTS Client\system",
        r"Software\Veo3Go\Veo3 Go\system",
        r"Software\Veo3Go\Veo3 Go"
    ]:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path)
            try:
                hw, _ = winreg.QueryValueEx(k, "hardware_id")
            except OSError:
                hw = None
            try:
                cpu, _ = winreg.QueryValueEx(k, "cached_cpu_id")
            except OSError:
                cpu = None
            try:
                mb, _ = winreg.QueryValueEx(k, "cached_mainboard_uuid")
            except OSError:
                mb = None
            winreg.CloseKey(k)
            if hw and cpu and mb:
                return str(hw).strip(), str(cpu).strip(), str(mb).strip()
        except Exception:
            pass

    # 2. Truy vấn trực tiếp phần cứng qua WMIC (như hardware_info_veo3.py)
    cpu_id = ""
    try:
        out = subprocess.check_output("wmic cpu get ProcessorId", shell=True, text=True)
        lines = [line.strip() for line in out.strip().splitlines() if line.strip() and "ProcessorId" not in line]
        if lines:
            cpu_id = lines[0]
    except Exception:
        pass

    mb_uuid = ""
    try:
        out = subprocess.check_output("wmic csproduct get uuid", shell=True, text=True)
        lines = [line.strip() for line in out.strip().splitlines() if line.strip() and "UUID" not in line]
        if lines:
            mb_uuid = lines[0]
    except Exception:
        pass

    if not mb_uuid:
        try:
            out = subprocess.check_output("wmic baseboard get serialnumber", shell=True, text=True)
            lines = [line.strip() for line in out.strip().splitlines() if line.strip() and "SerialNumber" not in line]
            if lines:
                mb_uuid = lines[0]
        except Exception:
            pass

    if not cpu_id:
        cpu_id = "BFEBFBFF000906EA"
    if not mb_uuid:
        mb_uuid = "Default-MB-UUID"

    hw_id = hashlib.sha256(f"{cpu_id}|{mb_uuid}".encode()).hexdigest()
    return hw_id, cpu_id, mb_uuid

def get_registry_credentials():
    """Đọc thông tin bản quyền và phần cứng tương thích Veo3Go 1.5.5"""
    import winreg
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Xác định brand đang sử dụng
    brand = "vanthe"
    for b_path in [
        os.path.join(script_dir, "vanthe_155", "resources", "brand.txt"),
        os.path.join(script_dir, "resources", "brand.txt"),
        os.path.join(script_dir, "brand.txt")
    ]:
        if os.path.exists(b_path):
            try:
                with open(b_path, "r", encoding="utf-8") as f:
                    b_str = f.read().strip()
                    if b_str:
                        brand = b_str
                        break
            except Exception:
                pass

    hw_id, cpu_hash, board_hash = get_real_hardware_info()
    license_key = ""
    email = "Registry License Key"

    # Danh sách các khóa Registry theo thứ tự ưu tiên
    registry_candidates = [
        (r"Software\Veo3Go\Veo3 Go\license", "key", r"Software\Veo3Go\Veo3 Go", ["last_email_veo3", "activation/last_email"]),
        (r"Software\Nhungoc\Veo3 Client\license", "key", r"Software\Nhungoc\Veo3 Client\account", ["last_email", "email"]),
        (r"Software\Nhungoc\Nhungoc Video Generator\license", "key", r"Software\Nhungoc\Nhungoc Video Generator", ["last_email_veo3", "last_email"]),
        (r"Software\NhanLyVeo3Gen\NhanLy Veo3Gen\license", "key", r"Software\NhanLyVeo3Gen\NhanLy Veo3Gen", ["last_email_veo3"]),
        (r"Software\GKTech\Veo3HubClient", "api_key", r"Software\GKTech\Veo3HubClient", ["activation_email"])
    ]

    for lic_reg, lic_val_name, email_reg, email_val_names in registry_candidates:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, lic_reg)
            val, _ = winreg.QueryValueEx(k, lic_val_name)
            winreg.CloseKey(k)
            if val and str(val).strip():
                license_key = str(val).strip()
                # Thử đọc email
                try:
                    k_em = winreg.OpenKey(winreg.HKEY_CURRENT_USER, email_reg)
                    for em_name in email_val_names:
                        try:
                            em_val, _ = winreg.QueryValueEx(k_em, em_name)
                            if em_val and str(em_val).strip():
                                email = str(em_val).strip()
                                break
                        except OSError:
                            pass
                    winreg.CloseKey(k_em)
                except Exception:
                    pass
                break
        except Exception:
            pass

    return {
        "api_key": license_key,
        "activation_email": email if license_key else "Không có tài khoản Registry",
        "device_key": "",
        "hardware_id": hw_id,
        "cpu_id": cpu_hash,
        "mainboard_uuid": board_hash,
        "brand": brand
    }

def slugify(text):
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '_', text).strip('_')
    return text[:30]

def encode_image_base64(path):
    import base64
    try:
        with open(path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception:
        return ""

def strip_logo(video_path):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "vanthe_155", "bin", "ffmpeg.exe"),
        os.path.join(script_dir, "bin", "ffmpeg.exe"),
        os.path.join(script_dir, "ffmpeg.exe"),
        shutil.which("ffmpeg")
    ]
    ffmpeg_bin = None
    for c in candidates:
        if c and os.path.exists(c):
            ffmpeg_bin = c
            break

    if not ffmpeg_bin:
        return False, "Không tìm thấy ffmpeg.exe trong hệ thống"
            
    tmp_out = video_path.replace(".mp4", ".nologo.mp4")
    cmd = [
        ffmpeg_bin, "-y", "-i", video_path,
        "-map", "0:v:0", "-map", "0:a?",
        "-vf", "crop=iw*0.958:ih*0.928:0:0,scale=trunc(iw/0.958/2)*2:trunc(ih/0.928/2)*2",
        "-c:v", "libx264", "-crf", "22", "-preset", "superfast", "-threads", "4",
        "-c:a", "copy", tmp_out
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        if res.returncode != 0:
            cmd_fallback = [
                ffmpeg_bin, "-y", "-i", video_path,
                "-map", "0:v:0", "-map", "0:a?",
                "-vf", "crop=iw*0.958:ih*0.928:0:0,scale=trunc(iw/0.958/2)*2:trunc(ih/0.928/2)*2",
                "-c:v", "libx264", "-crf", "22", "-preset", "superfast", "-threads", "4",
                "-c:a", "aac", "-b:a", "192k", tmp_out
            ]
            res = subprocess.run(cmd_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            if res.returncode != 0:
                return False, f"Lỗi ffmpeg: {res.stderr}"
        
        os.replace(tmp_out, video_path)
        return True, "Đã xóa logo"
    except Exception as e:
        return False, str(e)

class VeoClient:
    def __init__(self, creds):
        self.api_key = creds.get("api_key", "")
        self.device_key = creds.get("device_key", "")
        self.hardware_id = creds.get("hardware_id", "")
        self.cpu_id = creds.get("cpu_id", "")
        self.mainboard_uuid = creds.get("mainboard_uuid", "")
        self.brand = creds.get("brand", "vanthe")

    def verify_license(self, email):
        url = f"{DEFAULT_HUB_HTTP}/api/license/verify_veo3.php"
        payload = {
            "license_key": self.api_key,
            "email": email,
            "hardware_id": self.hardware_id,
            "cpu_id": self.cpu_id,
            "mainboard_uuid": self.mainboard_uuid,
            "brand": self.brand,
            "current_version": "1.5.5"
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Veo3-Client/1.5.5"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {
                "success": False,
                "message": str(e)
            }

class DailyLimitExceeded(Exception):
    pass


# Mã lỗi bộ lọc nội dung của Veo. Server trả về event "video_result" kèm status="error"
# và mã lỗi ở đây; video KHÔNG được tạo ra nên không có link tải. Thử lại cũng bị từ chối,
# vì vậy các sản phẩm này cần được loại khỏi hàng chờ thay vì chạy lại.
VEO_CONTENT_ERRORS = {
    "PUBLIC_ERROR_IP_INPUT_IMAGE": "Lỗi Bản Quyền",
    "PROMINENT_PEOPLE": "Lỗi Bản Quyền",
    "FILTER_FAILED": "Lỗi Bản Quyền",
    "PUBLIC_ERROR_RECITATION": "Lỗi Bản Quyền",
    "PUBLIC_ERROR_UNSAFE_GENERATION": "Lỗi Bộ lọc nội dung",
    "PUBLIC_ERROR_DANGER_FILTER": "Lỗi Bộ lọc nội dung",
    "PUBLIC_ERROR_SAFETY_FILTER": "Lỗi Bộ lọc nội dung",
}

# Các trạng thái bị Veo từ chối hẳn: không chạy lại, xóa khỏi bảng khi xong hàng chờ
CONTENT_REJECT_LABELS = ("Lỗi Bản Quyền", "Lỗi Bộ lọc nội dung")


def classify_veo_error(data):
    """Dò mã lỗi bộ lọc của Veo trong payload trả về.

    Trả về (nhãn hiển thị, mã lỗi gốc), hoặc (None, "") nếu không nhận diện được.
    """
    try:
        blob = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    except Exception:
        blob = str(data)
    for code, label in VEO_CONTENT_ERRORS.items():
        if code in blob:
            return label, code
    return None, ""

def _run_ghep_anh_12s(video_path, image_path, output_path):
    """
    Ghép ảnh vào video tạo ra video 12s chuẩn Seedvis với hiệu ứng Zoom In 3.5s.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "vanthe_155", "bin", "ffmpeg.exe"),
        os.path.join(script_dir, "bin", "ffmpeg.exe"),
        os.path.join(script_dir, "ffmpeg.exe"),
        shutil.which("ffmpeg")
    ]
    ffmpeg_bin = None
    for c in candidates:
        if c and os.path.exists(c):
            ffmpeg_bin = c
            break
    if not ffmpeg_bin:
        ffmpeg_bin = "ffmpeg"

    ffprobe_bin = ffmpeg_bin.replace("ffmpeg", "ffprobe")
    if not os.path.exists(ffprobe_bin):
        ffprobe_bin = shutil.which("ffprobe") or "ffprobe"

    slow_factor = 1.05
    image_dur = 3.5
    total_dur = 12.0
    video_dur = total_dur - image_dur # 8.5s

    def check_has_audio(vp):
        cmd = [ffprobe_bin, '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1', vp]
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, startupinfo=startupinfo, creationflags=0x08000000)
            return len(result.stdout.strip()) > 0
        except Exception:
            return False

    def get_video_info(vp):
        cmd = [ffprobe_bin, '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate', '-of', 'json', vp]
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, startupinfo=startupinfo, creationflags=0x08000000)
            data = json.loads(result.stdout)
            stream = data['streams'][0]
            width = int(stream['width'])
            height = int(stream['height'])
            fps_str = stream['r_frame_rate']
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den)
            else:
                fps = float(fps_str)
            return width, height, fps
        except Exception:
            pass
        return 1080, 1920, 30.0

    try:
        has_audio = check_has_audio(video_path)
        width, height, fps = get_video_info(video_path)
        fps_int = int(round(fps))
        if fps_int <= 0:
            fps_int = 30

        total_image_frames = int(image_dur * fps_int)
        max_zoom = 1.3
        w_scale = int(width * max_zoom)
        if w_scale % 2 != 0: w_scale += 1
        h_scale = int(height * max_zoom)
        if h_scale % 2 != 0: h_scale += 1

        zoom_step = 0.3 / total_image_frames
        zoom_expr = f"min(zoom+{zoom_step:.6f},1.3)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

        video_filter = f"[0:v]setpts={slow_factor}*PTS,scale={width}:{height},fps={fps_int},tpad=stop_mode=clone:stop_duration={video_dur},trim=0:{video_dur},setpts=PTS-STARTPTS[v_part]"
        filter_parts = [video_filter]

        if has_audio:
            audio_slow_factor = 1.0 / slow_factor
            audio_filter = f"[0:a]atempo={audio_slow_factor},apad,atrim=0:{video_dur},asetpts=PTS-STARTPTS[a_part]"
            filter_parts.append(audio_filter)

        image_filter_base = (
            f"[1:v]scale={w_scale}:{h_scale}:force_original_aspect_ratio=increase,"
            f"crop={w_scale}:{h_scale},"
            f"zoompan=z='{zoom_expr}':d={total_image_frames}:x='{x_expr}':y='{y_expr}':s={width}x{height},"
            f"fps={fps_int},trim=0:{image_dur},setpts=PTS-STARTPTS[i_v]"
        )
        filter_parts.append(image_filter_base)
        image_audio_filter = f"anullsrc=r=48000:cl=stereo,atrim=0:{image_dur},asetpts=PTS-STARTPTS[i_a]"
        filter_parts.append(image_audio_filter)

        if has_audio:
            filter_parts.append("[v_part][a_part][i_v][i_a]concat=n=2:v=1:a=1[outv][outa]")
            map_args = ["-map", "[outv]", "-map", "[outa]"]
        else:
            filter_parts.append("[v_part][i_v]concat=n=2:v=1:a=0[outv]")
            map_args = ["-map", "[outv]"]

        filter_complex_str = "; ".join(filter_parts)

        tmp_out = output_path.replace(".mp4", "_12s_tmp.mp4")
        cmd = [
            ffmpeg_bin, "-y",
            "-filter_threads", "2", "-filter_complex_threads", "2",
            "-i", video_path,
            "-loop", "1", "-t", str(image_dur), "-i", image_path,
            "-filter_complex", filter_complex_str
        ]
        cmd.extend(map_args)
        cmd.extend(["-c:v", "libx264", "-preset", "superfast", "-crf", "22", "-threads", "2"])
        if has_audio:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
        cmd.append(tmp_out)

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, startupinfo=startupinfo, timeout=120, creationflags=0x08000000)
        if os.path.exists(tmp_out):
            if os.path.exists(output_path):
                os.remove(output_path)
            os.replace(tmp_out, output_path)
            return True, "Ghép ảnh 12s thành công"
        return False, "Không tạo được file video 12s"
    except Exception as e:
        return False, f"Lỗi ghép ảnh: {e}"


class AiKeysDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("🔑 Cài đặt AI Keys (Gemini & Groq)")
        self.setMinimumSize(640, 500)
        self.setStyleSheet("""
            QDialog { background-color: #12131C; color: #FFFFFF; }
            QLabel { color: #E2E8F0; font-size: 13px; }
            QPlainTextEdit {
                background-color: #0B0B12;
                border: 1px solid #232538;
                border-radius: 6px;
                color: #00F0FF;
                font-family: Consolas, monospace;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton {
                background-color: #1C1E30;
                color: #FFFFFF;
                border: 1px solid #2F3352;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2A2E4B; border-color: #00F0FF; }
        """)
        self.settings = settings or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("🔑 Quản lý API Key AI (Gemini & Groq)")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00F0FF;")
        layout.addWidget(title)

        desc = QLabel("Các key này được nạp tự động từ shopee_db_settings.json.\nKhi chọn AI Prompt là Gemini hoặc Groq, hệ thống sẽ xoay vòng các key này.")
        desc.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(desc)

        layout.addWidget(QLabel("💎 Gemini API Keys (1 key/dòng):"))
        self.txt_gemini = QPlainTextEdit()
        gem_keys = self.settings.get("gemini_keys", [])
        self.txt_gemini.setPlainText("\n".join(gem_keys))
        layout.addWidget(self.txt_gemini)

        layout.addWidget(QLabel("⚡ Groq API Keys (1 key/dòng):"))
        self.txt_groq = QPlainTextEdit()
        groq_keys = self.settings.get("groq_keys", [])
        self.txt_groq.setPlainText("\n".join(groq_keys))
        layout.addWidget(self.txt_groq)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Đóng")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Lưu API Keys")
        btn_save.setStyleSheet("background-color: #00F0FF; color: #0B0B12; font-weight: bold;")
        btn_save.clicked.connect(self.save_keys)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def save_keys(self):
        new_gem = [k.strip() for k in self.txt_gemini.toPlainText().splitlines() if k.strip()]
        new_groq = [k.strip() for k in self.txt_groq.toPlainText().splitlines() if k.strip()]
        self.settings["gemini_keys"] = new_gem
        self.settings["groq_keys"] = new_groq
        save_shopee_settings(self.settings)
        QMessageBox.information(self, "Thành công", f"Đã lưu:\n- {len(new_gem)} Gemini Key\n- {len(new_groq)} Groq Key")
        self.accept()


class TestPromptDialog(QDialog):
    def __init__(self, parent=None, product_name="", scene="🎲 Random", review_style="🎲 Random", lang="Tiếng Philippines", ai_mode="Prompt A + B", settings=None):
        super().__init__(parent)
        self.setWindowTitle(f"🧪 Test Prompt: {product_name[:35]}")
        self.setMinimumSize(720, 520)
        self.setStyleSheet("""
            QDialog { background-color: #12131C; color: #FFFFFF; }
            QLabel { color: #E2E8F0; font-size: 13px; }
            QTextEdit {
                background-color: #0B0B12;
                border: 1px solid #232538;
                border-radius: 6px;
                color: #00F0FF;
                font-family: Consolas, monospace;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton {
                background-color: #1C1E30;
                color: #FFFFFF;
                border: 1px solid #2F3352;
                border-radius: 5px;
                padding: 6px 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2A2E4B; border-color: #00F0FF; }
        """)
        self.product_name = product_name or "Serum Vitamin C Sáng Da Mờ Thâm Nám 30ml"
        self.scene = scene
        self.review_style = review_style
        self.lang = lang
        self.ai_mode = ai_mode
        self.settings = settings or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"📦 Sản phẩm: {self.product_name}")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00F0FF;")
        layout.addWidget(title)

        info = QLabel(f"⚙️ Chế độ: {self.ai_mode} | Khung cảnh: {self.scene} | Kiểu Review: {self.review_style} | Ngôn ngữ: {self.lang}")
        info.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(info)

        self.txt_prompt = QTextEdit()
        self.txt_prompt.setReadOnly(True)
        layout.addWidget(self.txt_prompt)

        btn_row = QHBoxLayout()
        btn_regen = QPushButton("🔄 Sinh lại Prompt")
        btn_regen.clicked.connect(self.generate_prompt)
        btn_row.addWidget(btn_regen)

        btn_copy = QPushButton("📋 Sao chép Prompt")
        btn_copy.clicked.connect(self.copy_prompt)
        btn_row.addWidget(btn_copy)

        btn_row.addStretch()

        btn_close = QPushButton("Đóng")
        btn_close.clicked.connect(self.reject)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

        self.generate_prompt()

    def generate_prompt(self):
        mkt_map = {
            "Tiếng Philippines": "PH",
            "Tiếng Việt": "VN",
            "Tiếng Thái": "TH",
            "Tiếng Indonesia": "ID",
            "Tiếng Malaysia": "MY",
            "Tiếng Anh": "SG"
        }
        mkt = mkt_map.get(self.lang, "PH")
        p, tag = build_tvc_prompt(self.product_name, market=mkt, review_style=self.review_style, scene_choice=self.scene)
        self.txt_prompt.setText(f"[Tag: {tag}]\n\n{p}")

    def copy_prompt(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.txt_prompt.toPlainText())
        QMessageBox.information(self, "Thông báo", "Đã sao chép Prompt vào clipboard!")

class ShopeeServerConfigDialog(QDialog):
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.setWindowTitle("⚙ Cấu hình Server Database Shopee")
        self.setMinimumSize(480, 260)
        self.setStyleSheet("""
            QDialog { background-color: #12131C; color: #FFFFFF; }
            QLabel { color: #E2E8F0; font-size: 13px; }
            QLineEdit {
                background-color: #0B0B12;
                border: 1px solid #232538;
                border-radius: 5px;
                color: #00F0FF;
                padding: 6px 10px;
                font-size: 12px;
            }
            QPushButton {
                background-color: #1C1E30;
                color: #FFFFFF;
                border: 1px solid #2F3352;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #2A2E4B; border-color: #00F0FF; }
        """)
        self.settings = settings or {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("⚙ CẤU HÌNH KẾT NỐI SERVER SHOPEE")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00F0FF;")
        layout.addWidget(title)

        form = QVBoxLayout()
        form.addWidget(QLabel("Server URL:"))
        self.txt_url = QLineEdit(self.settings.get("sv_server_url", "http://100.79.170.67:3000"))
        form.addWidget(self.txt_url)

        form.addWidget(QLabel("API Key:"))
        self.txt_key = QLineEdit(self.settings.get("sv_api_key", "shopee_secret_2026"))
        form.addWidget(self.txt_key)

        form.addWidget(QLabel("Client ID:"))
        self.txt_cid = QLineEdit(self.settings.get("sv_client_id", "XEON-CT2A_822d66"))
        form.addWidget(self.txt_cid)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("Đóng")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Lưu cấu hình")
        btn_save.setStyleSheet("background-color: #00F0FF; color: #0B0B12; font-weight: bold;")
        btn_save.clicked.connect(self.save)
        btn_row.addWidget(btn_save)
        layout.addLayout(btn_row)

    def save(self):
        self.settings["sv_server_url"] = self.txt_url.text().strip()
        self.settings["sv_api_key"] = self.txt_key.text().strip()
        self.settings["sv_client_id"] = self.txt_cid.text().strip()
        save_shopee_settings(self.settings)
        self.accept()


def ws_is_open(ws):
    """Kiểm tra WebSocket còn mở, tương thích mọi phiên bản thư viện websockets.

    - websockets < 14: connect() trả về WebSocketClientProtocol, có thuộc tính .closed
    - websockets >= 14: connect() trả về ClientConnection, KHÔNG có .closed, chỉ có .state
    """
    if ws is None:
        return False
    closed = getattr(ws, "closed", None)
    if closed is not None:
        return not closed
    state = getattr(ws, "state", None)
    if state is not None:
        return getattr(state, "name", str(state)).upper() == "OPEN"
    return True


class AccountWsSession:
    """Quản lý kết nối WebSocket duy nhất cho 1 tài khoản và chia sẻ N slot song song (VD: 5 slots cho Unlimited 5)."""
    def __init__(self, acc, log_signal, default_cpu_id=""):
        self.acc = acc
        self.log_signal = log_signal
        self.default_cpu_id = default_cpu_id
        self.ws = None
        self.lock = asyncio.Lock()
        self.send_lock = asyncio.Lock()
        self.listen_task = None
        self.task_events = {} # task_id -> asyncio.Queue()
        self.is_connected = False
        self.verified_info = {}
        
        # Số slots song song
        is_un = acc.get("is_unlimited", False) or "unlimited" in str(acc.get("plan", "")).lower() or ("5" in str(acc.get("plan", "")))
        self.max_slots = int(acc.get("max_slots") or acc.get("veo3_unlimited_threads") or (5 if is_un else 1))
        self.semaphore = asyncio.Semaphore(self.max_slots)

    async def ensure_connected(self):
        async with self.lock:
            if ws_is_open(self.ws):
                return self.ws

            # Không truyền ssl: thư viện tự bật TLS cho URI wss:// ở mọi phiên bản.
            # Truyền tay ssl=None với ws:// sẽ gây TypeError trên websockets >= 14.
            self.ws = await websockets.connect(
                DEFAULT_WSS,
                ping_interval=20,
                ping_timeout=40,
                max_size=104857600
            )
            # Register client
            cpu = self.acc.get("cpu_id") or self.default_cpu_id
            reg_msg = {
                "event": "register",
                "data": {
                    "license_key": self.acc["api_key"],
                    "cpu_id": cpu
                }
            }
            await self.ws.send(json.dumps(reg_msg))
            
            # Message 1: registered (pending verification)
            r1 = json.loads(await self.ws.recv())
            # Message 2: registered (verified with quota and thread count)
            r2 = json.loads(await self.ws.recv())
            
            if r2.get("event") == "registration_failed":
                err_data = r2.get("data", {})
                err_msg = err_data.get("error") if isinstance(err_data, dict) else str(err_data)
                raise Exception(f"Đăng ký thất bại: {err_msg}")
                
            if r2.get("event") == "registered":
                v_data = r2.get("data", {}).get("verification", {}).get("data", {})
                if v_data:
                    self.verified_info = v_data
                    un_threads = int(v_data.get("veo3_unlimited_threads", 0) or 0)
                    if un_threads > 0:
                        self.max_slots = un_threads
                        self.acc["max_slots"] = un_threads
                        self.acc["is_unlimited"] = True
                        self.semaphore = asyncio.Semaphore(un_threads)
            
            self.is_connected = True
            if self.listen_task and not self.listen_task.done():
                self.listen_task.cancel()
            self.listen_task = asyncio.create_task(self.listen_loop())
            return self.ws

    async def listen_loop(self):
        try:
            async for message in self.ws:
                try:
                    msg = json.loads(message)
                    event = msg.get("event")
                    data = msg.get("data", {})
                    if isinstance(data, dict):
                        tid = data.get("task_id")
                        if tid and tid in self.task_events:
                            await self.task_events[tid].put((event, data))
                        elif event == "video_batch_queued":
                            for r in data.get("batch_results", []):
                                r_tid = r.get("task_id")
                                if r_tid and r_tid in self.task_events:
                                    await self.task_events[r_tid].put(("video_queued", r))
                        elif event in ("error", "job_error", "server_busy", "registration_failed"):
                            for q in list(self.task_events.values()):
                                await q.put((event, data))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                tid = item.get("task_id")
                                if tid and tid in self.task_events:
                                    await self.task_events[tid].put((event, item))
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self.is_connected = False
            for tid, q in list(self.task_events.items()):
                try:
                    q.put_nowait(("ws_closed", {"error": "Kết nối WebSocket bị ngắt"}))
                except Exception:
                    pass

    async def send_json(self, payload):
        await self.ensure_connected()
        async with self.send_lock:
            if ws_is_open(self.ws):
                await self.ws.send(json.dumps(payload))
            else:
                raise Exception("Kết nối WebSocket chưa sẵn sàng hoặc đã đóng.")

    async def force_reconnect(self):
        """Đóng phiên WebSocket hiện tại và xóa mọi trạng thái.
        Lần gọi ensure_connected() tiếp theo sẽ mở kết nối mới — bộ đếm 199 prompt được reset."""
        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()
            try:
                await self.listen_task
            except BaseException:
                pass
        if ws_is_open(self.ws):
            try:
                await self.ws.close()
            except BaseException:
                pass
        self.ws = None
        self.is_connected = False
        self.listen_task = None

    async def close(self):
        if self.listen_task and not self.listen_task.done():
            self.listen_task.cancel()
            try:
                await self.listen_task
            except BaseException:
                pass
        if ws_is_open(self.ws):
            try:
                await self.ws.close()
            except BaseException:
                pass


class WorkerThread(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(str, int, str) # task_id, progress_percentage, status_text
    task_done_signal = Signal(str, str, str) # task_id, output_path, status_result
    finished_signal = Signal()
    account_created_signal = Signal()
    task_id_changed_signal = Signal(str, str) # old_task_id, new_task_id
    task_updated_signal = Signal(str, str, str) # task_id, image_path, prompt

    def __init__(self, client, tasks, output_dir, strip_logo_enabled, accounts_pool=None, max_workers=5, naming_mode="Tên ảnh đầu vào", ghep_anh_12s=False, del_img=False, shopee_client=None):
        super().__init__()
        self.client = client
        self.tasks = tasks # list of dict
        self.output_dir = output_dir
        self.strip_logo_enabled = strip_logo_enabled
        self.ghep_anh_12s = ghep_anh_12s
        self.del_img = del_img
        self.shopee_client = shopee_client
        self.is_running = True
        self.stop_requested = False
        self.max_workers = max_workers
        self.naming_mode = naming_mode
        self.account_sessions = {}
        self._init_accounts_pool(client, accounts_pool)

    async def report_shopee_status(self, task, result_text, output_path=""):
        item_id = task.get("shopee_item_id")
        if not self.shopee_client or not item_id:
            return
        status_map = {
            "Hoàn thành": "completed",
            "Lỗi Bản Quyền": "vi phạm cs",
            "Lỗi Bộ lọc nội dung": "vi phạm cs"
        }
        st_db = status_map.get(result_text, "failed")
        def do_report(iid, s, p):
            try:
                self.shopee_client.complete_job(str(iid), status=s, video_path=p)
                return True, None
            except Exception as e:
                return False, str(e)
        ok, err = await asyncio.to_thread(do_report, item_id, st_db, output_path)
        if ok:
            self.log_signal.emit(f"[Shopee DB] ✅ Đã báo cáo SP {item_id} -> '{st_db}' về Server")
        else:
            self.log_signal.emit(f"[Shopee DB] ⚠ Lỗi báo cáo SP {item_id}: {err}")

    def _init_accounts_pool(self, client, accounts_pool):
        self.default_hardware_id = client.hardware_id
        self.default_cpu_id = client.cpu_id
        self.default_mainboard_uuid = client.mainboard_uuid
        
        self.accounts_pool = accounts_pool if accounts_pool else []
        # Nếu chưa có pool, dùng license thật đọc từ Registry làm tài khoản mặc định
        if not self.accounts_pool and client.api_key:
            self.accounts_pool = [{
                "email": getattr(client, "activation_email", "Registry Default"),
                "api_key": client.api_key,
                "device_key": client.device_key,
                "hardware_id": client.hardware_id,
                "cpu_id": client.cpu_id,
                "mainboard_uuid": client.mainboard_uuid
            }]

        # Khởi tạo trạng thái slot cho toàn bộ tài khoản trong pool.
        # Số slot thực tế do License Server trả về khi kết nối (ensure_connected).
        for acc in self.accounts_pool:
            acc["is_unlimited"] = True
            acc["max_slots"] = int(acc.get("max_slots") or acc.get("veo3_unlimited_threads") or 5)
            if not acc.get("plan"):
                acc["plan"] = "Unlimited 5"
            acc["active_slots"] = 0
            acc["in_use"] = False

    def request_stop(self):
        self.stop_requested = True
        self.log_signal.emit("[Hệ thống] Nhận yêu cầu dừng: Không nhận thêm tác vụ mới, đang hoàn thành nốt các tác vụ đang chạy...")

    def stop(self):
        self.stop_requested = True
        self.is_running = False

    def get_or_create_session(self, acc):
        email = acc.get("email") or acc.get("api_key")
        if email not in self.account_sessions:
            self.account_sessions[email] = AccountWsSession(
                acc,
                self.log_signal,
                default_cpu_id=self.default_cpu_id
            )
        return self.account_sessions[email]

    async def reset_session_for_account(self, acc):
        """Đóng phiên WebSocket hiện tại của tài khoản và xóa khỏi cache.
        Lần xử lý tác vụ tiếp theo sẽ tạo phiên mới — bộ đếm 199 prompt phía server được reset."""
        email = acc.get("email") or acc.get("api_key")
        session = self.account_sessions.pop(email, None)
        if session:
            try:
                await session.force_reconnect()
            except BaseException:
                pass

    async def increment_busy_failures(self):
        async with self.lock:
            self.consecutive_busy_failures += 1
            self.log_signal.emit(f"[Hệ thống] Số luồng liên tiếp báo Server bận: {self.consecutive_busy_failures}/10")
            if self.consecutive_busy_failures >= 10:
                self.consecutive_busy_failures = 0
                self.pause_event.clear()
                self.log_signal.emit("[Hệ thống] Đã có 10 luồng liên tiếp báo Server bận. Tạm dừng tất cả các luồng để nghỉ 15 phút rồi chạy tiếp...")
                for _ in range(900):
                    if not self.is_running:
                        break
                    await asyncio.sleep(1)
                if self.is_running:
                    self.log_signal.emit("[Hệ thống] Hết thời gian nghỉ 15 phút. Tiếp tục xử lý tác vụ...")
                self.pause_event.set()

    def reset_busy_failures(self):
        self.consecutive_busy_failures = 0

    def run(self):
        try:
            asyncio.run(self.process_queue())
        except BaseException as e:
            self.log_signal.emit(f"[Lỗi tiến trình Worker] {e}")

    async def acquire_account(self):
        import time
        now = time.time()
        async with self.lock:
            # Lọc các ứng viên còn slot khả dụng
            candidates = []
            for acc in self.accounts_pool:
                # Bỏ qua tài khoản có license không hợp lệ
                if acc.get("permanent_exhausted"):
                    continue

                max_s = int(acc.get("max_slots") or acc.get("veo3_unlimited_threads") or 5)
                active_slots = int(acc.get("active_slots", 0))

                # Chỉ chờ nếu đang trong thời gian tạm hoãn do lỗi tạm thời (server bận / mất kết nối)
                if acc.get("cooldown_until", 0) > now:
                    continue

                # Còn slot trống để chạy
                if active_slots < max_s:
                    candidates.append((acc, active_slots, max_s))

            if not candidates:
                return None

            # Thuật toán San tải: chọn tài khoản có tỷ lệ sử dụng thấp nhất và dùng lâu nhất trước đó
            selected_acc, cur_slots, max_s = min(
                candidates, 
                key=lambda x: (x[1] / max(1, x[2]), x[1], x[0].get("last_used_time", 0))
            )
            selected_acc["active_slots"] = cur_slots + 1
            selected_acc["in_use"] = (selected_acc["active_slots"] >= max_s)
            selected_acc["last_used_time"] = now
            return selected_acc

    def release_account(self, acc, cooldown_seconds=0):
        import time
        now = time.time()
        max_s = int(acc.get("max_slots") or acc.get("veo3_unlimited_threads") or 5)

        acc["active_slots"] = max(0, int(acc.get("active_slots", 1)) - 1)
        acc["in_use"] = (acc["active_slots"] >= max_s)
        acc["last_used_time"] = now

        # cooldown chỉ dùng cho lỗi tạm thời (server bận / mất kết nối); mặc định slot rảnh nhận việc ngay
        acc["cooldown_until"] = now + cooldown_seconds if cooldown_seconds > 0 else 0

    def save_accounts_pool_to_disk(self):
        with _accounts_file_lock:
            try:
                temp_filepath = "veo3_accounts.json.tmp"
                with open(temp_filepath, "w", encoding="utf-8") as f:
                    json.dump(self.accounts_pool, f, ensure_ascii=False, indent=4)
                if os.path.exists("veo3_accounts.json"):
                    os.remove("veo3_accounts.json")
                os.rename(temp_filepath, "veo3_accounts.json")
            except Exception as e:
                print("Error saving accounts pool:", e)
        self.account_created_signal.emit()

    def mark_account_license_invalid(self, acc, reason="error"):
        """Đánh dấu license không hợp lệ (sai key / hết hạn / thiết bị không khớp) để ngừng dùng."""
        acc["in_use"] = False
        acc["permanent_exhausted"] = True
        acc["error_reason"] = reason
        acc["status"] = f"Lỗi license: {reason}"
        self.save_accounts_pool_to_disk()

    async def process_queue(self):
        if not self.tasks:
            self.log_signal.emit("Hàng chờ trống.")
            self.finished_signal.emit()
            return

        self.lock = asyncio.Lock()
        self.pause_event = asyncio.Event()
        self.pause_event.set()
        self.consecutive_busy_failures = 0
        self.stop_requested = False

        # Khởi tạo trạng thái slot cho toàn bộ tài khoản trong pool
        for acc in self.accounts_pool:
            acc["is_unlimited"] = True
            acc["max_slots"] = int(acc.get("max_slots") or acc.get("veo3_unlimited_threads") or 5)
            acc["active_slots"] = 0
            acc["in_use"] = False
            acc["cooldown_until"] = 0

        # Xác định số worker dựa trên tổng slot khả dụng từ pool
        available_accs = [acc for acc in self.accounts_pool if not acc.get("permanent_exhausted")]
        total_parallel_capacity = sum(int(acc.get("max_slots") or 5) for acc in available_accs)
        if total_parallel_capacity < 1:
            total_parallel_capacity = 1

        max_workers = min(self.max_workers, total_parallel_capacity)
        if max_workers < 1:
            max_workers = 1

        self.log_signal.emit(f"Bắt đầu chạy {len(self.tasks)} tác vụ với {max_workers} luồng song song ({len(available_accs)} tài khoản khả dụng trong Pool, tổng {total_parallel_capacity} slots)...")

        task_queue = asyncio.Queue()
        for task in self.tasks:
            await task_queue.put(task)

        # Khởi động các worker xử lý song song
        workers = []
        for i in range(max_workers):
            workers.append(asyncio.create_task(self.worker_loop(task_queue, worker_id=i)))

        try:
            await asyncio.gather(*workers)
        finally:
            # Dọn dẹp đóng các kết nối WebSocket session
            for sess in list(self.account_sessions.values()):
                try:
                    await sess.close()
                except Exception:
                    pass
            self.account_sessions.clear()
            self.finished_signal.emit()

    async def worker_loop(self, task_queue, worker_id=0):
        while not task_queue.empty() and not self.stop_requested and self.is_running:
            await self.pause_event.wait()
            task = await task_queue.get()
            task_id = task["task_id"]
            
            success = False
            retries = 0
            busy_count = 0
            max_retries = max(5, len(self.accounts_pool))
            
            while not success and retries < max_retries and self.is_running:
                acc = await self.acquire_account()
                if not acc:
                    available = [a for a in self.accounts_pool if not a.get("permanent_exhausted")]
                    if not available:
                        self.log_signal.emit(f"[{task_id}] Lỗi: Không còn tài khoản hợp lệ (license lỗi hoặc chưa nhập key).")
                        await self.report_shopee_status(task, "Lỗi: Hết tài khoản sử dụng.", "")
                        self.task_done_signal.emit(task_id, "", "Lỗi: Hết tài khoản sử dụng.")
                        break
                    else:
                        # Wait for in-use account to release
                        await asyncio.sleep(2)
                        continue

                # Tài khoản phải có license key hợp lệ (không tự tạo/kích hoạt)
                if not acc.get("api_key"):
                    self.log_signal.emit(f"[Lỗi] Tài khoản {acc['email']} thiếu license key. Vui lòng nhập key hợp lệ trong Quản lý tài khoản.")
                    self.mark_account_license_invalid(acc, reason="missing_key")
                    retries += 1
                    continue

                self.log_signal.emit(f"[{task_id}] Luồng sử dụng tài khoản: {acc['email']} (Slot {acc.get('active_slots', 1)}/{acc.get('max_slots', 5)})")

                # Kết nối / đảm bảo session WebSocket duy nhất cho tài khoản này
                # (Server tự xác thực license & trả số slot khi register trong ensure_connected)
                session = self.get_or_create_session(acc)
                try:
                    await session.ensure_connected()
                except Exception as e:
                    self.log_signal.emit(f"[{task_id}] Lỗi kết nối WebSocket cho {acc['email']}: {e}")
                    self.release_account(acc, cooldown_seconds=5)
                    await asyncio.sleep(3)
                    retries += 1
                    continue

                # On-demand tải ảnh & sinh Prompt TVC cho sản phẩm Shopee khi tới lượt chạy
                if task.get("is_lazy_shopee"):
                    s_id = str(task.get("shopee_item_id", ""))
                    s_mkt = task.get("shopee_market", "PH")
                    s_url = task.get("shopee_image_url", "")
                    s_name = task.get("shopee_name", "")

                    curr_dir = os.path.dirname(os.path.abspath(__file__))
                    out_dir = os.path.join(curr_dir, "downloads", "shopee_images")
                    os.makedirs(out_dir, exist_ok=True)
                    img_path = os.path.join(out_dir, f"{s_mkt}_{s_id}.jpg")

                    # 1. Tải ảnh nếu chưa có trên ổ đĩa
                    if not os.path.exists(img_path) or os.path.getsize(img_path) == 0:
                        self.progress_signal.emit(task_id, 2, "Đang tải ảnh SP...")
                        self.log_signal.emit(f"[{task_id}] [Shopee DB] Bắt đầu tải ảnh SP {s_id}...")
                        def do_download():
                            try:
                                req = urllib.request.Request(s_url, headers={"User-Agent": "Mozilla/5.0"})
                                with urllib.request.urlopen(req, timeout=25) as resp, open(img_path, "wb") as f_out:
                                    f_out.write(resp.read())
                                return True
                            except Exception as e:
                                return str(e)
                        dl_res = await asyncio.to_thread(do_download)
                        if dl_res is not True:
                            self.log_signal.emit(f"[{task_id}] ⚠ Không tải được ảnh SP {s_id}: {dl_res}")
                            await self.report_shopee_status(task, f"Lỗi tải ảnh: {dl_res}", "")
                            self.task_done_signal.emit(task_id, "", f"Lỗi tải ảnh: {dl_res}")
                            self.release_account(acc, cooldown_seconds=0)
                            break
                    task["start_image"] = img_path

                    # 2. Sinh Prompt TVC on-demand
                    if not task.get("prompt_ready"):
                        self.progress_signal.emit(task_id, 4, "Đang tạo Prompt TVC...")
                        scene_c = task.get("shopee_scene", "🎲 Random")
                        style_c = task.get("shopee_style", "🎲 Random")
                        
                        def do_prompt():
                            try:
                                p_res, _ = build_tvc_prompt(
                                    product_name=s_name,
                                    market=s_mkt,
                                    review_style=style_c,
                                    scene_choice=scene_c
                                )
                                return p_res
                            except Exception as e:
                                return str(e)
                        gen_prompt = await asyncio.to_thread(do_prompt)
                        task["prompt"] = gen_prompt
                        task["prompt_ready"] = True
                        self.log_signal.emit(f"[{task_id}] [Shopee DB] Đã tạo Prompt TVC: {gen_prompt[:65]}...")

                    # 3. Đồng bộ hóa đường dẫn ảnh & Prompt lên giao diện
                    self.task_updated_signal.emit(task_id, task["start_image"], task["prompt"])

                self.progress_signal.emit(task_id, 5, "Đang gửi dữ liệu...")
                try:
                    task_ok = await self.run_ws_task(session, task, worker_id=worker_id)
                    if task_ok:
                        # Unlimited 5: không cooldown, slot rảnh nhận việc tiếp ngay
                        acc["videos_today"] = acc.get("videos_today", 0) + 1
                        active_rem = max(0, int(acc.get("active_slots", 1)) - 1)
                        max_s = int(acc.get("max_slots") or 5)
                        self.log_signal.emit(f"[Hệ thống] [Unlimited 5] Tài khoản {acc['email']} hoàn thành (Tổng phiên: {acc['videos_today']} video). Đang chạy {active_rem}/{max_s} slots.")
                        self.release_account(acc, cooldown_seconds=0)
                        self.reset_busy_failures()
                    else:
                        self.release_account(acc, cooldown_seconds=0)

                    self.save_accounts_pool_to_disk()
                    success = True
                except DailyLimitExceeded:
                    self.log_signal.emit(
                        f"[Hệ thống] ⚠ Tài khoản {acc['email']} chạm cap 199 prompt/phiên! "
                        f"Đang reset phiên WebSocket để lấy kết nối mới với bộ đếm sạch..."
                    )
                    self.progress_signal.emit(task_id, 5, "Đang reset phiên WebSocket...")
                    self.release_account(acc, cooldown_seconds=0)
                    try:
                        # Đóng phiên cũ + xóa khỏi cache → lần kết nối tiếp theo mở phiên mới
                        await self.reset_session_for_account(acc)
                    except BaseException as reset_err:
                        self.log_signal.emit(f"[Hệ thống] ⚠ Lỗi khi reset phiên: {reset_err}")
                    self.log_signal.emit(f"[Hệ thống] ✅ Đã reset phiên. Đang thử lại tác vụ [{task_id}] trên phiên mới...")
                    retries += 1
                    continue
                except Exception as e:
                    err_str = str(e)
                    if "1013" in err_str or "busy" in err_str.lower():
                        import random
                        import uuid
                        
                        busy_count += 1
                        if busy_count >= 3:
                            self.log_signal.emit(f"[{task_id}] Server bận 3 lần liên tiếp. Bỏ qua tác vụ này và chuyển tác vụ khác.")
                            await self.report_shopee_status(task, "Lỗi: Server bận 3 lần liên tiếp", "")
                            self.task_done_signal.emit(task_id, "", "Lỗi: Server bận 3 lần liên tiếp")
                            self.release_account(acc, cooldown_seconds=5)
                            await self.increment_busy_failures()
                            break
                            
                        if busy_count == 1:
                            wait_sec = random.randint(15, 25)
                        else:
                            wait_sec = random.randint(30, 45)
                        
                        # Generate new task ID
                        new_task_id = str(uuid.uuid4())
                        self.task_id_changed_signal.emit(task_id, new_task_id)
                        
                        # Update task dict and local variables
                        task["task_id"] = new_task_id
                        task_id = new_task_id
                        
                        self.progress_signal.emit(task_id, 5, f"Server bận (Lần {busy_count}), chờ {wait_sec}s...")
                        self.log_signal.emit(f"[{task_id}] Server đang bận (Server busy / Code 1013 / Lần {busy_count}/3). Chờ {wait_sec}s để thử lại...")
                        self.release_account(acc, cooldown_seconds=wait_sec)
                        await asyncio.sleep(wait_sec)
                        retries += 1
                        continue
                    elif "1008" in err_str or "license_verification_failed" in err_str:
                        self.log_signal.emit(f"[{task_id}] Tài khoản {acc['email']} lỗi license (1008 / license_verification_failed). Kiểm tra lại key/gói cước.")
                        self.mark_account_license_invalid(acc, reason="license_error_1008")
                        retries += 1
                        continue
                    elif any(x in err_str.lower() for x in ["4001", "replaced by reconnect", "reconnect", "close frame", "connection closed", "closed", "timeout", "reset by peer", "502", "503", "bị ngắt", "ngắt", "websocket bị ngắt"]):
                        self.log_signal.emit(f"[{task_id}] Kết nối WebSocket bị ngắt ({err_str}). Đang thử lại tác vụ sau 3s...")
                        self.release_account(acc, cooldown_seconds=3)
                        await asyncio.sleep(3)
                        retries += 1
                        continue
                    
                    self.log_signal.emit(f"[{task_id}] Lỗi xử lý websocket: {e}")
                    await self.report_shopee_status(task, f"Lỗi WebSocket: {e}", "")
                    self.task_done_signal.emit(task_id, "", f"Lỗi WebSocket: {e}")
                    self.release_account(acc, cooldown_seconds=10)
                    break

    async def run_ws_task(self, session, task, worker_id=0):
        task_id = task["task_id"]
        await session.ensure_connected()

        # Tạo queue nhận message cho riêng task_id này
        q = asyncio.Queue()
        session.task_events[task_id] = q

        try:
            self.log_signal.emit(f"[{task_id}] Đang tải ảnh lên và gửi yêu cầu...")
            self.progress_signal.emit(task_id, 10, "Đang gửi dữ liệu...")
            
            # Prepare payload
            aspect_map = {
                "9:16": "VIDEO_ASPECT_RATIO_PORTRAIT",
                "16:9": "VIDEO_ASPECT_RATIO_LANDSCAPE"
            }
            mapped_ar = aspect_map.get(task.get("aspect_ratio", "9:16"), task.get("aspect_ratio", "VIDEO_ASPECT_RATIO_PORTRAIT"))
            dur_sec = task.get("duration_seconds") or task.get("duration_sec") or 8

            if task["mode"] == "image_to_video":
                s_b64 = await asyncio.to_thread(encode_image_base64, task["start_image"])
                if not s_b64:
                    self.task_done_signal.emit(task_id, "", "Lỗi đọc ảnh nguồn")
                    return False
                
                payload = {
                    "event": "submit_image_video_batch",
                    "data": [
                        {
                            "task_id": task_id,
                            "image_base64": s_b64,
                            "mime_type": "image/jpeg",
                            "prompt": task.get("prompt", ""),
                            "aspect_ratio": mapped_ar,
                            "seed": task.get("seed", 0),
                            "upscale_1080p": task.get("upscale_1080p", False),
                            "duration_seconds": dur_sec,
                            "allow_silent_video": task.get("allow_silent", True)
                        }
                    ]
                }
            else: # start_end
                s_b64 = await asyncio.to_thread(encode_image_base64, task["start_image"])
                e_b64 = await asyncio.to_thread(encode_image_base64, task["end_image"])
                if not s_b64 or not e_b64:
                    self.task_done_signal.emit(task_id, "", "Lỗi đọc ảnh đầu/cuối")
                    return False
                
                data_item = {
                    "task_id": task_id,
                    "start_image_base64": s_b64,
                    "end_image_base64": e_b64,
                    "mime_type": "image/jpeg",
                    "prompt": task.get("prompt", ""),
                    "aspect_ratio": mapped_ar,
                    "seed": task.get("seed", 0),
                    "upscale_1080p": task.get("upscale_1080p", False),
                    "duration_seconds": dur_sec,
                    "allow_silent_video": task.get("allow_silent", True)
                }
                if task.get("motion_prompt"):
                    data_item["motion_prompt"] = task["motion_prompt"]
                if task.get("camera_prompt"):
                    data_item["camera_prompt"] = task["camera_prompt"]
                    
                payload = {
                    "event": "submit_start_end_video_batch",
                    "data": [data_item]
                }

            await session.send_json(payload)
            self.log_signal.emit(f"[{task_id}] Đã gửi yêu cầu render (Thời lượng: {dur_sec}s).")
            self.progress_signal.emit(task_id, 15, "Đang xử lý ở hàng chờ...")

            # Vòng lặp nhận kết quả cho task này
            while self.is_running:
                try:
                    event, data = await asyncio.wait_for(q.get(), timeout=360)
                except asyncio.TimeoutError:
                    self.log_signal.emit(f"[{task_id}] Hết thời gian chờ phản hồi từ server (6 phút).")
                    await self.report_shopee_status(task, "Lỗi: Timeout chờ kết quả", "")
                    self.task_done_signal.emit(task_id, "", "Lỗi: Timeout chờ kết quả")
                    return False

                if event == "ws_closed":
                    raise Exception(data.get("error", "Kết nối WebSocket bị ngắt"))

                if event in ("video_queued", "queued"):
                    pos = data.get("queue_position", 1)
                    self.progress_signal.emit(task_id, 20, f"Hàng chờ: vị trí {pos}")
                    self.log_signal.emit(f"[{task_id}] Vị trí hàng chờ: {pos}")
                elif event in ("video_processing", "progress", "job_processing"):
                    progress_val = data.get("progress", 0)
                    pct = int(20 + (progress_val * 0.6))
                    self.progress_signal.emit(task_id, pct, f"Đang tạo video ({progress_val}%)")
                elif event == "video_retry":
                    self.progress_signal.emit(task_id, 35, "Server đang thử lại...")
                    self.log_signal.emit(f"[{task_id}] Server gửi sự kiện video_retry, đang sinh lại...")
                elif event == "video_upscaling":
                    self.progress_signal.emit(task_id, 85, "Đang upscale 1080p...")
                    self.log_signal.emit(f"[{task_id}] Đang nâng cấp lên 1080p...")
                elif event in ("video_result", "job_result"):
                    self.progress_signal.emit(task_id, 90, "Đang tải video kết quả...")
                    self.log_signal.emit(f"[{task_id}] Nhận kết quả từ server: {event}")
                    
                    # Gửi result_ack cho server
                    try:
                        await session.send_json({
                            "event": "result_ack",
                            "data": {
                                "task_id": task_id
                            }
                        })
                    except Exception:
                        pass

                    encoded_video = data.get("encoded_video") or data.get("inline_mp4")
                    video_url = None
                    
                    if not encoded_video:
                        res_raw = data.get("result")
                        if isinstance(res_raw, dict):
                            encoded_video = res_raw.get("encoded_video") or res_raw.get("inline_mp4")
                            video_url = res_raw.get("download_url") or res_raw.get("url") or res_raw.get("video_url")
                            if not video_url and res_raw.get("urls"):
                                video_url = res_raw["urls"][0]
                        elif isinstance(res_raw, list) and len(res_raw) > 0:
                            first_res = res_raw[0]
                            if isinstance(first_res, dict):
                                encoded_video = first_res.get("encoded_video") or first_res.get("inline_mp4")
                                video_url = first_res.get("download_url") or first_res.get("url") or first_res.get("video_url")
                                if not video_url and first_res.get("urls"):
                                    video_url = first_res["urls"][0]
                            elif isinstance(first_res, str):
                                video_url = first_res
                                
                        if not video_url and not encoded_video:
                            video_url = data.get("download_url") or data.get("url") or data.get("video_url")
                            if not video_url and data.get("urls"):
                                video_url = data["urls"][0]
                            
                    img_name = "result"
                    mode_str = str(getattr(self, "naming_mode", "Theo Item ID"))
                    item_id = task.get("shopee_item_id")
                    row_idx = task.get("row_index", 0) + 1
                    prompt_str = task.get("prompt", "").strip()

                    if ("Item ID" in mode_str) and item_id:
                        img_name = str(item_id)
                    elif ("15" in mode_str or "13" in mode_str) and prompt_str:
                        safe_prompt = re.sub(r'[\\/*?:"<>|]', '', prompt_str)
                        lim = 15 if "15" in mode_str else 13
                        img_name = safe_prompt[:lim].strip() or f"video_{task_id[:8]}"
                    elif "thứ tự" in mode_str:
                        img_name = f"{row_idx:03d}"
                    elif task.get("start_image"):
                        img_name = os.path.splitext(os.path.basename(task["start_image"]))[0]
                    elif prompt_str:
                        img_name = f"video_{slugify(prompt_str)[:20]}"
                    else:
                        img_name = f"video_{task_id[:8]}"
                        
                    out_path = os.path.join(self.output_dir, f"{img_name}.mp4")
                    counter = 1
                    while os.path.exists(out_path):
                        out_path = os.path.join(self.output_dir, f"{img_name}_{counter}.mp4")
                        counter += 1
                    
                    if encoded_video:
                        try:
                            import base64
                            video_bytes = base64.b64decode(encoded_video)
                            with open(out_path, "wb") as out_file:
                                out_file.write(video_bytes)
                            self.log_signal.emit(f"[{task_id}] Đã giải mã và lưu video thành công.")
                        except Exception as e:
                            await self.report_shopee_status(task, f"Lỗi giải mã base64: {e}", "")
                            self.task_done_signal.emit(task_id, "", f"Lỗi giải mã base64: {e}")
                            return False
                    elif video_url:
                        self.log_signal.emit(f"[{task_id}] Đang tải video từ: {video_url}")
                        try:
                            await asyncio.to_thread(self.download_file, video_url, out_path)
                        except Exception as e:
                            await self.report_shopee_status(task, f"Lỗi tải video: {e}", "")
                            self.task_done_signal.emit(task_id, "", f"Lỗi tải video: {e}")
                            return False
                    else:
                        # Kiểm tra xem có phải server báo chạm quota/cap không
                        raw_err = data.get("error") or data.get("code") or data.get("message") or ""
                        if any(x in str(raw_err).lower() for x in ["limit", "daily", "exceeded", "quota", "session prompt cap", "cap"]):
                            raise DailyLimitExceeded()

                        # Không có video: thường do Veo từ chối tạo (bộ lọc bản quyền / an toàn),
                        # mã lỗi thật nằm trong data["error"] hoặc data["code"]
                        res_lbl, code = classify_veo_error(data)
                        if res_lbl:
                            self.log_signal.emit(f"[{task_id}] ⛔ Veo từ chối tạo video: {code} → {res_lbl}. Sản phẩm này sẽ bị loại khỏi hàng chờ.")
                        else:
                            if raw_err:
                                res_lbl = f"Lỗi: {raw_err}"
                                self.log_signal.emit(f"[{task_id}] Server báo lỗi khi tạo video: {raw_err}")
                            else:
                                res_lbl = "Lỗi: Không tìm thấy dữ liệu video"
                                self.log_signal.emit(f"[{task_id}] Lỗi: Không tìm thấy dữ liệu video hoặc link tải. Data: {json.dumps(data)}")
                        await self.report_shopee_status(task, res_lbl, "")
                        self.task_done_signal.emit(task_id, "", res_lbl)
                        return False
                        
                    if self.strip_logo_enabled and task.get("strip_logo", True):
                        self.progress_signal.emit(task_id, 92, "Đang xóa logo...")
                        ok_logo, logo_reason = await asyncio.to_thread(strip_logo, out_path)
                        if ok_logo:
                            self.log_signal.emit(f"[{task_id}] Đã xóa logo thành công.")
                        else:
                            self.log_signal.emit(f"[{task_id}] Không thể xóa logo: {logo_reason}")

                    # 1. Ghép ảnh 12s nếu bật checkbox (chạy trên background thread, không đơ UI)
                    src_img = task.get("start_image")
                    if self.ghep_anh_12s and src_img and os.path.exists(src_img):
                        self.progress_signal.emit(task_id, 96, "Đang ghép ảnh 12s...")
                        self.log_signal.emit(f"[{task_id}] Đang ghép ảnh Outro tạo video 12s...")
                        ok_gh, gh_msg = await asyncio.to_thread(_run_ghep_anh_12s, out_path, src_img, out_path)
                        if ok_gh:
                            self.log_signal.emit(f"[{task_id}] ✅ Đã ghép ảnh 12s thành công.")
                        else:
                            self.log_signal.emit(f"[{task_id}] ⚠ Lỗi ghép ảnh 12s: {gh_msg}")

                    # 2. Xóa ảnh sản phẩm nếu bật checkbox
                    if self.del_img and src_img and os.path.exists(src_img):
                        try:
                            os.remove(src_img)
                            self.log_signal.emit(f"[{task_id}] 🗑 Đã xóa ảnh sản phẩm: {os.path.basename(src_img)}")
                        except Exception:
                            pass

                    # 3. Báo cáo trạng thái SP hoàn thành về Shopee Database Server
                    await self.report_shopee_status(task, "Hoàn thành", out_path)
                            
                    self.task_done_signal.emit(task_id, out_path, "Hoàn thành")
                    return True
                elif event in ("error", "job_error"):
                    err_msg = data.get("message") or data.get("detail") or data.get("reason") or data.get("error") or "Lỗi server không xác định"
                    if any(x in str(err_msg).lower() for x in ["limit", "daily", "exceeded", "quota", "session prompt cap", "cap"]):
                        raise DailyLimitExceeded()
                    
                    res_label, code = classify_veo_error(data)
                    if res_label:
                        self.log_signal.emit(f"[{task_id}] ⛔ Veo từ chối tạo video: {code} → {res_label}. Sản phẩm này sẽ bị loại khỏi hàng chờ.")
                    else:
                        res_label = f"Lỗi: {err_msg}"
                    await self.report_shopee_status(task, res_label, "")
                    self.task_done_signal.emit(task_id, "", res_label)
                    return False
            return False
        finally:
            session.task_events.pop(task_id, None)

    def download_file(self, url, path):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response, open(path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)


class AccountVerifyWorker(QThread):
    progress_signal = Signal(int, int, str) # current, total, text
    account_verified_signal = Signal(int, dict) # index, updated_acc
    finished_signal = Signal()

    def __init__(self, accounts):
        super().__init__()
        self.accounts = accounts
        self.is_running = True

    def stop(self):
        self.is_running = False

    def run(self):
        total = len(self.accounts)
        for i, acc in enumerate(self.accounts):
            if not self.is_running:
                break
            email = acc.get("email", "")
            key = acc.get("api_key", "")
            disp_name = email if email else key[:12] + "..."
            self.progress_signal.emit(i + 1, total, f"Đang kiểm tra: {disp_name}")

            client = VeoClient({
                "api_key": key,
                "device_key": acc.get("device_key", ""),
                "hardware_id": acc.get("hardware_id", ""),
                "cpu_id": acc.get("cpu_id", ""),
                "mainboard_uuid": acc.get("mainboard_uuid", "")
            })

            try:
                res = client.verify_license(email)
                if res.get("success"):
                    data_sec = res.get("data", {})
                    plan = str(data_sec.get("plan", "")).lower()
                    unlimited_threads = int(data_sec.get("veo3_unlimited_threads", 0) or 0)
                    unlimited_paid = data_sec.get("unlimited_paid_veo3") or data_sec.get("unlimited_paid")
                    buy_package = int(data_sec.get("veo3_buy_package", 0) or 0)
                    expiry_veo3 = str(data_sec.get("expiry_veo3", ""))
                    is_expired = data_sec.get("is_expired", False)
                    
                    is_un = (unlimited_threads > 0) or ("unlimited" in plan) or bool(unlimited_paid) or (buy_package == 1) or bool(expiry_veo3 and not is_expired)
                    acc["is_unlimited"] = is_un
                    acc["max_slots"] = unlimited_threads if unlimited_threads > 0 else (5 if is_un else 1)
                    if is_un:
                        acc["plan"] = "Tạo 5 video cùng lúc"
                        acc["status"] = "Sẵn sàng (999 tỷ video)"
                    else:
                        acc["plan"] = data_sec.get("plan") or "Basic / Trial"
                        acc["status"] = "Sẵn sàng"
                    acc["permanent_exhausted"] = False
                    acc["exhausted"] = False
                else:
                    err_msg = res.get("message", "Lỗi xác thực")
                    acc["status"] = f"Lỗi: {err_msg}"
                    if "1008" in str(err_msg) or "unauthorized" in str(err_msg).lower():
                        acc["permanent_exhausted"] = True
            except Exception as e:
                acc["status"] = f"Lỗi: {e}"

            self.account_verified_signal.emit(i, acc)
            time.sleep(0.15)

        self.finished_signal.emit()


class AccountBatchImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nhập hàng loạt tài khoản Unlimited 5")
        self.setMinimumSize(580, 430)
        self.setStyleSheet("""
            QDialog {
                background-color: #12131C;
                color: #FFFFFF;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 13px;
            }
            QPlainTextEdit {
                background-color: #0B0B12;
                border: 1px solid #232538;
                border-radius: 6px;
                color: #00F0FF;
                font-family: Consolas, monospace;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton {
                background-color: #1F2238;
                color: #FFFFFF;
                border: 1px solid #323656;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2D3154;
                border-color: #00F0FF;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        title_lbl = QLabel("📋 Dán danh sách tài khoản Unlimited 5 vào ô dưới đây:")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #00F0FF;")
        layout.addWidget(title_lbl)

        hint_lbl = QLabel("Định dạng hỗ trợ mỗi dòng:\n  • email|license_key  (ví dụ: user@gmail.com|ELV-xxx)\n  • email:license_key\n  • license_key        (hệ thống tự gán email)")
        hint_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(hint_lbl)

        self.txt_input = QPlainTextEdit()
        self.txt_input.setPlaceholderText("user1@gmail.com|ELV-7b4f0867-...\nuser2@gmail.com:ELV-9c2e1188-...\nELV-3d8a5566-...")
        layout.addWidget(self.txt_input)

        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Hủy")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_import = QPushButton("⚡ Nhập vào Pool")
        self.btn_import.setStyleSheet("background-color: #00F0FF; color: #000000; font-weight: bold;")
        self.btn_import.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_import)
        layout.addLayout(btn_layout)

    def get_imported_accounts(self):
        text = self.txt_input.toPlainText().strip()
        if not text:
            return []
        lines = text.split("\n")
        accounts = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            email = ""
            key = ""
            if "|" in line:
                parts = line.split("|", 1)
                email = parts[0].strip()
                key = parts[1].strip()
            elif ":" in line and not line.startswith("http"):
                parts = line.split(":", 1)
                email = parts[0].strip()
                key = parts[1].strip()
            else:
                key = line
                email = f"unlimited_{hashlib.md5(key.encode()).hexdigest()[:8]}@veo3.unlimited"

            if key:
                hw_id, cpu_h, board_h = get_real_hardware_info()
                accounts.append({
                    "email": email,
                    "api_key": key,
                    "device_key": "",
                    "hardware_id": hw_id,
                    "cpu_id": cpu_h,
                    "mainboard_uuid": board_h,
                    "is_unlimited": True,
                    "max_slots": 5,
                    "active_slots": 0,
                    "videos_today": 0,
                    "plan": "Unlimited 5",
                    "status": "Chờ kiểm tra",
                    "exhausted": False,
                    "permanent_exhausted": False,
                    "in_use": False,
                    "cooldown_until": 0
                })
        return accounts


class AccountManagerDialog(QDialog):
    def __init__(self, parent=None, accounts_pool=None, on_pool_updated=None):
        super().__init__(parent)
        self.setWindowTitle("👥 Quản lý Tài khoản (Pool Unlimited 5)")
        self.setMinimumSize(920, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #0F1019;
                color: #FFFFFF;
            }
            QLabel {
                color: #E2E8F0;
                font-size: 13px;
            }
            QTableWidget {
                background-color: #0B0B12;
                border: 1px solid #1E2133;
                border-radius: 6px;
                gridline-color: #1A1D2D;
                color: #E2E8F0;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #171827;
                color: #00F0FF;
                font-weight: bold;
                padding: 6px;
                border: 1px solid #1E2133;
            }
            QPushButton {
                background-color: #1C1E30;
                color: #FFFFFF;
                border: 1px solid #2F3352;
                border-radius: 5px;
                padding: 7px 14px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2A2E4B;
                border-color: #00F0FF;
            }
        """)

        self.accounts = [dict(acc) for acc in (accounts_pool or [])]
        self.on_pool_updated = on_pool_updated
        self.verify_worker = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # Header bar
        header_layout = QHBoxLayout()
        header_title = QLabel("👥 DANH SÁCH TÀI KHOẢN VEO3 (TỐI ƯU CHO GÓI UNLIMITED 5)")
        header_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #00F0FF;")
        header_layout.addWidget(header_title)
        header_layout.addStretch()

        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("font-size: 13px; font-weight: bold; color: #00FF66;")
        header_layout.addWidget(self.lbl_stats)
        layout.addLayout(header_layout)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "STT", "Email", "License Key", "Gói cước", "Slots tối đa", "Video hôm nay", "Trạng thái"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        # Progress / Verification indicator
        self.lbl_verify_status = QLabel("")
        self.lbl_verify_status.setStyleSheet("color: #FFB703; font-style: italic;")
        layout.addWidget(self.lbl_verify_status)

        # Control Toolbar
        btn_layout = QHBoxLayout()
        
        self.btn_load_reg = QPushButton("📥 Nạp TK Registry")
        self.btn_load_reg.setStyleSheet("background-color: #00F0FF; color: #0B0B12; font-weight: bold;")
        self.btn_load_reg.setToolTip("Tự động nạp tài khoản chính thức từ Windows Registry với License Key thật")
        self.btn_load_reg.clicked.connect(self.load_registry_account)
        btn_layout.addWidget(self.btn_load_reg)

        self.btn_add_manual = QPushButton("➕ Thêm 1 tài khoản")
        self.btn_add_manual.clicked.connect(self.add_manual_account)
        btn_layout.addWidget(self.btn_add_manual)

        self.btn_batch_import = QPushButton("📥 Nhập hàng loạt...")
        self.btn_batch_import.setStyleSheet("background-color: #2F3352; color: #00F0FF; font-weight: bold;")
        self.btn_batch_import.clicked.connect(self.open_batch_import)
        btn_layout.addWidget(self.btn_batch_import)

        self.btn_verify_all = QPushButton("🔍 Kiểm tra bản quyền (Verify All)")
        self.btn_verify_all.setStyleSheet("background-color: #00B4D8; color: #FFFFFF; font-weight: bold;")
        self.btn_verify_all.clicked.connect(self.verify_all_accounts)
        btn_layout.addWidget(self.btn_verify_all)

        self.btn_delete_selected = QPushButton("🗑️ Xóa đã chọn")
        self.btn_delete_selected.clicked.connect(self.delete_selected)
        btn_layout.addWidget(self.btn_delete_selected)

        self.btn_clear_all = QPushButton("⚠️ Xóa toàn bộ")
        self.btn_clear_all.clicked.connect(self.clear_all)
        btn_layout.addWidget(self.btn_clear_all)

        btn_layout.addStretch()

        self.btn_save = QPushButton("💾 Lưu & Áp dụng")
        self.btn_save.setStyleSheet("background-color: #00F0FF; color: #000000; font-weight: bold; font-size: 13px; padding: 8px 20px;")
        self.btn_save.clicked.connect(self.save_and_apply)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

        self.refresh_table()

    def refresh_table(self):
        self.table.setRowCount(len(self.accounts))
        unlimited_count = 0
        total_slots = 0

        for row, acc in enumerate(self.accounts):
            is_un = acc.get("is_unlimited", False) or "unlimited" in str(acc.get("plan", "")).lower() or int(acc.get("veo3_unlimited_threads", 0) or 0) > 0
            slots = int(acc.get("max_slots") or acc.get("veo3_unlimited_threads") or (5 if is_un else 1))
            if is_un:
                unlimited_count += 1
            if not acc.get("permanent_exhausted"):
                total_slots += slots

            item_stt = QTableWidgetItem(str(row + 1))
            item_stt.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_stt)

            item_email = QTableWidgetItem(acc.get("email", ""))
            self.table.setItem(row, 1, item_email)

            raw_key = acc.get("api_key", "")
            mask_key = f"{raw_key[:10]}...{raw_key[-6:]}" if len(raw_key) > 16 else raw_key
            item_key = QTableWidgetItem(mask_key)
            item_key.setToolTip(raw_key)
            item_key.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, item_key)

            plan_text = acc.get("plan") or ("Unlimited 5" if is_un else "Basic / Trial")
            item_plan = QTableWidgetItem(plan_text)
            item_plan.setTextAlignment(Qt.AlignCenter)
            if is_un:
                item_plan.setForeground(QColor("#00F0FF"))
                font = item_plan.font()
                font.setBold(True)
                item_plan.setFont(font)
            self.table.setItem(row, 3, item_plan)

            item_slots = QTableWidgetItem(f"{slots} slots")
            item_slots.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, item_slots)

            item_vids = QTableWidgetItem(str(acc.get("videos_today", 0)))
            item_vids.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 5, item_vids)

            status_text = acc.get("status") or ("Sẵn sàng" if not acc.get("permanent_exhausted") else "Bị khóa/Lỗi")
            item_status = QTableWidgetItem(status_text)
            item_status.setTextAlignment(Qt.AlignCenter)
            if "lỗi" in status_text.lower() or "khóa" in status_text.lower():
                item_status.setForeground(QColor("#FF3366"))
            elif is_un:
                item_status.setForeground(QColor("#00FF66"))
            self.table.setItem(row, 6, item_status)

        self.lbl_stats.setText(f"Tổng: {len(self.accounts)} tài khoản ({unlimited_count} Unlimited 5) | {total_slots} Slots song song")

    def load_registry_account(self):
        creds = get_registry_credentials()
        if not creds:
            QMessageBox.warning(self, "Lỗi", "Không đọc được tài khoản từ Windows Registry!")
            return
        email = creds.get("activation_email", "")
        api_key = creds.get("api_key", "")
        hw_id = creds.get("hardware_id", "")
        cpu_id = creds.get("cpu_id", "")
        board_id = creds.get("mainboard_uuid", "")

        if not email or email == "Không có tài khoản Registry":
            QMessageBox.warning(self, "Lỗi", "Registry chưa có tài khoản nào được kích hoạt!")
            return

        found = False
        for acc in self.accounts:
            if acc.get("email") == email:
                acc["api_key"] = api_key or acc.get("api_key", "")
                acc["hardware_id"] = hw_id or acc.get("hardware_id", "")
                acc["cpu_id"] = cpu_id or acc.get("cpu_id", "")
                acc["mainboard_uuid"] = board_id or acc.get("mainboard_uuid", "")
                acc["is_unlimited"] = True
                acc["max_slots"] = 5
                acc["plan"] = "Tạo 5 video cùng lúc"
                acc["status"] = "Sẵn sàng (999 tỷ video)"
                acc["permanent_exhausted"] = False
                found = True
                break

        if not found:
            self.accounts.insert(0, {
                "email": email,
                "api_key": api_key,
                "device_key": creds.get("device_key", ""),
                "hardware_id": hw_id,
                "cpu_id": cpu_id,
                "mainboard_uuid": board_id,
                "brand": "vanthe",
                "is_unlimited": True,
                "max_slots": 5,
                "active_slots": 0,
                "videos_today": 0,
                "plan": "Tạo 5 video cùng lúc",
                "status": "Sẵn sàng (999 tỷ video)",
                "exhausted": False,
                "permanent_exhausted": False,
                "in_use": False,
                "cooldown_until": 0
            })

        self.refresh_table()
        QMessageBox.information(
            self, 
            "Nạp thành công", 
            f"✅ Đã nạp tài khoản chính từ Registry:\n- Email: {email}\n- License Key: {api_key}\n- Gói cước: Tạo 5 video cùng lúc\n- Hạn mức: 999 tỷ video"
        )

    def add_manual_account(self):
        from PySide6.QtWidgets import QInputDialog
        key, ok1 = QInputDialog.getText(self, "Thêm tài khoản", "Nhập License Key (bắt buộc):")
        if not ok1 or not key.strip():
            return
        key = key.strip()

        email, ok2 = QInputDialog.getText(self, "Thêm tài khoản", "Nhập Email (để trống để tự tạo):")
        if not ok2 or not email.strip():
            email = f"unlimited_{hashlib.md5(key.encode()).hexdigest()[:8]}@veo3.unlimited"
        else:
            email = email.strip()

        hw_id, cpu_h, board_h = get_real_hardware_info()
        self.accounts.append({
            "email": email,
            "api_key": key,
            "device_key": "",
            "hardware_id": hw_id,
            "cpu_id": cpu_h,
            "mainboard_uuid": board_h,
            "is_unlimited": True,
            "max_slots": 5,
            "active_slots": 0,
            "videos_today": 0,
            "plan": "Unlimited 5",
            "status": "Chờ kiểm tra",
            "exhausted": False,
            "permanent_exhausted": False,
            "in_use": False,
            "cooldown_until": 0
        })
        self.refresh_table()

    def open_batch_import(self):
        dlg = AccountBatchImportDialog(self)
        if dlg.exec() == QDialog.Accepted:
            new_accs = dlg.get_imported_accounts()
            if new_accs:
                existing_keys = {acc.get("api_key") for acc in self.accounts}
                added_count = 0
                for acc in new_accs:
                    if acc.get("api_key") not in existing_keys:
                        self.accounts.append(acc)
                        existing_keys.add(acc.get("api_key"))
                        added_count += 1
                self.refresh_table()
                QMessageBox.information(self, "Thành công", f"Đã nhập thành công {added_count} tài khoản mới vào pool!")

    def verify_all_accounts(self):
        if not self.accounts:
            QMessageBox.warning(self, "Thông báo", "Danh sách tài khoản đang trống.")
            return

        self.btn_verify_all.setEnabled(False)
        self.btn_save.setEnabled(False)
        self.lbl_verify_status.setText("Đang khởi động kiểm tra bản quyền...")

        self.verify_worker = AccountVerifyWorker(self.accounts)
        self.verify_worker.progress_signal.connect(self.on_verify_progress)
        self.verify_worker.account_verified_signal.connect(self.on_account_verified)
        self.verify_worker.finished_signal.connect(self.on_verify_finished)
        self.verify_worker.start()

    def on_verify_progress(self, current, total, text):
        self.lbl_verify_status.setText(f"[{current}/{total}] {text}")

    def on_account_verified(self, idx, updated_acc):
        if 0 <= idx < len(self.accounts):
            self.accounts[idx] = updated_acc
            self.refresh_table()

    def on_verify_finished(self):
        self.btn_verify_all.setEnabled(True)
        self.btn_save.setEnabled(True)
        self.lbl_verify_status.setText("✅ Đã kiểm tra xong toàn bộ tài khoản!")
        self.refresh_table()

    def delete_selected(self):
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()), reverse=True)
        if not selected_rows:
            QMessageBox.warning(self, "Thông báo", "Vui lòng chọn ít nhất một dòng để xóa.")
            return
        for r in selected_rows:
            if 0 <= r < len(self.accounts):
                self.accounts.pop(r)
        self.refresh_table()

    def clear_all(self):
        reply = QMessageBox.warning(
            self, 
            "Xác nhận", 
            "Bạn có chắc muốn xóa TOÀN BỘ tài khoản trong pool?", 
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.accounts = []
            self.refresh_table()

    def save_and_apply(self):
        with _accounts_file_lock:
            try:
                temp_file = "veo3_accounts.json.tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(self.accounts, f, ensure_ascii=False, indent=4)
                if os.path.exists("veo3_accounts.json"):
                    os.remove("veo3_accounts.json")
                os.rename(temp_file, "veo3_accounts.json")
            except Exception as e:
                QMessageBox.critical(self, "Lỗi", f"Không thể lưu danh sách: {e}")
                return

        if self.on_pool_updated:
            self.on_pool_updated(self.accounts)

        QMessageBox.information(self, "Thành công", f"Đã lưu và áp dụng {len(self.accounts)} tài khoản vào hệ thống!")
        self.accept()


class PromptSourceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chọn nguồn nhập Prompt")
        self.setMinimumWidth(450)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        label = QLabel("Bạn có muốn thêm prompt cho danh sách ảnh vừa chọn không?\n(Mỗi prompt tương ứng với một ảnh theo thứ tự tên)")
        label.setWordWrap(True)
        label.setStyleSheet("font-size: 13px; color: #FFFFFF;")
        layout.addWidget(label)
        layout.addSpacing(5)
        
        self.btn_file = QPushButton("📁 Chọn file TXT...")
        self.btn_paste = QPushButton("📋 Nhập từ Clipboard / Dán văn bản...")
        self.btn_skip = QPushButton("❌ Bỏ qua (Tự động lấy tên ảnh làm prompt)")
        
        button_style = """
            QPushButton {
                background-color: #232336;
                color: #FFFFFF;
                border: 1px solid #3d3d5c;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #32324e;
                border-color: #00F0FF;
            }
            QPushButton:pressed {
                background-color: #1a1a2b;
            }
        """
        self.btn_file.setStyleSheet(button_style)
        self.btn_paste.setStyleSheet(button_style)
        self.btn_skip.setStyleSheet(button_style)
        
        layout.addWidget(self.btn_file)
        layout.addWidget(self.btn_paste)
        layout.addWidget(self.btn_skip)
        
        self.result_mode = None # "file", "paste", "skip"
        
        self.btn_file.clicked.connect(self.choose_file)
        self.btn_paste.clicked.connect(self.choose_paste)
        self.btn_skip.clicked.connect(self.choose_skip)
        
    def choose_file(self):
        self.result_mode = "file"
        self.accept()
        
    def choose_paste(self):
        self.result_mode = "paste"
        self.accept()
        
    def choose_skip(self):
        self.result_mode = "skip"
        self.accept()


class PastePromptDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dán danh sách Prompt")
        self.setMinimumSize(500, 400)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        label = QLabel("Dán danh sách prompt vào ô bên dưới (mỗi prompt một dòng):")
        label.setStyleSheet("font-size: 13px; color: #FFFFFF;")
        layout.addWidget(label)
        
        self.txt_edit = QPlainTextEdit()
        self.txt_edit.setPlaceholderText("Prompt cho ảnh 1\nPrompt cho ảnh 2\nPrompt cho ảnh 3...")
        self.txt_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #161624;
                color: #FFFFFF;
                border: 1px solid #3d3d5c;
                border-radius: 5px;
                font-family: Consolas, Monaco, monospace;
                font-size: 12px;
                padding: 5px;
            }
        """)
        
        # Try to pre-populate with clipboard content if it has text!
        clipboard = QApplication.clipboard()
        if clipboard.text():
            self.txt_edit.setPlainText(clipboard.text())
            
        layout.addWidget(self.txt_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_ok = QPushButton("Xác nhận")
        btn_cancel = QPushButton("Hủy")
        
        ok_style = """
            QPushButton {
                background-color: #00B4D8;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00F0FF;
            }
        """
        cancel_style = """
            QPushButton {
                background-color: #232336;
                color: #A0A0B0;
                border: 1px solid #3d3d5c;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #32324e;
                color: #FFFFFF;
            }
        """
        btn_ok.setStyleSheet(ok_style)
        btn_cancel.setStyleSheet(cancel_style)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
        
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        
    def get_prompts(self):
        text = self.txt_edit.toPlainText()
        return [line.strip() for line in text.split("\n") if line.strip()]


def parse_row_ranges(range_str, max_rows):
    """
    Parses a string like "1-3, 5, 7-9" or "1-3 or 3,6,7,8" and returns a set of 0-based row indices.
    """
    indices = set()
    if not range_str:
        return indices
    
    cleaned = range_str.lower()
    cleaned = cleaned.replace("or", ",").replace(";", ",")
    
    parts = cleaned.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            subparts = part.split("-")
            if len(subparts) == 2:
                try:
                    start = int(subparts[0].strip())
                    end = int(subparts[1].strip())
                    for r in range(start, end + 1):
                        if 1 <= r <= max_rows:
                            indices.add(r - 1)
                except ValueError:
                    pass
        else:
            try:
                r = int(part)
                if 1 <= r <= max_rows:
                    indices.add(r - 1)
            except ValueError:
                pass
    return indices


class CustomCheckDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom check")
        self.setMinimumWidth(300)
        self.setModal(True)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #0F0F1A;
                border: 2px solid #2F324D;
                border-radius: 8px;
            }
            QLabel {
                font-family: 'Segoe UI', Arial, sans-serif;
                color: #A0A5C0;
            }
            QLineEdit, QComboBox {
                background-color: #191B2A;
                border: 1px solid #2F324D;
                border-radius: 6px;
                padding: 6px 10px;
                color: #FFFFFF;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #00F0FF;
            }
            QPushButton {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 20px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        lbl_action = QLabel("Action:")
        lbl_action.setStyleSheet("font-size: 13px; color: #FFFFFF;")
        layout.addWidget(lbl_action)
        
        self.combo_action = QComboBox()
        self.combo_action.addItems(["Check", "Uncheck"])
        layout.addWidget(self.combo_action)
        
        lbl_rows = QLabel("Rows (e.g. 1-3 or 3,6,7,8):")
        lbl_rows.setStyleSheet("font-size: 13px; color: #FFFFFF;")
        layout.addWidget(lbl_rows)
        
        self.txt_rows = QLineEdit()
        self.txt_rows.setPlaceholderText("e.g. 1-3 or 3,6,7,8")
        layout.addWidget(self.txt_rows)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Cancel")
        
        ok_style = """
            QPushButton {
                background-color: #00B4D8;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00F0FF;
            }
        """
        cancel_style = """
            QPushButton {
                background-color: #232336;
                color: #A0A0B0;
                border: 1px solid #3d3d5c;
                border-radius: 4px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #32324e;
                color: #FFFFFF;
            }
        """
        self.btn_ok.setStyleSheet(ok_style)
        self.btn_cancel.setStyleSheet(cancel_style)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
        
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        
    def get_data(self):
        return self.combo_action.currentText(), self.txt_rows.text().strip()


class CountdownMessageBox(QDialog):
    def __init__(self, parent=None, timeout_seconds=20):
        super().__init__(parent)
        self.setWindowTitle("Hoàn thành - Chạy lại lỗi?")
        self.setMinimumWidth(400)
        self.setMinimumHeight(150)
        self.timeout_seconds = timeout_seconds
        
        self.setStyleSheet("""
            QDialog {
                background-color: #0F0F1A;
                border: 2px solid #2F324D;
                border-radius: 8px;
            }
            QLabel {
                font-family: 'Segoe UI', Arial, sans-serif;
                color: #A0A5C0;
            }
            QPushButton {
                font-family: 'Segoe UI', Arial, sans-serif;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 20px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        self.lbl_msg = QLabel("Đã xử lý xong hàng chờ.\nBạn có muốn chạy lại các lệnh bị lỗi không?")
        self.lbl_msg.setStyleSheet("font-size: 14px; color: #FFFFFF; font-weight: bold;")
        self.lbl_msg.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_msg)
        
        self.lbl_countdown = QLabel(f"Tự động chọn 'Có' sau {self.timeout_seconds} giây...")
        self.lbl_countdown.setStyleSheet("color: #FFC107; font-size: 13px; font-weight: bold;")
        self.lbl_countdown.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_countdown)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(15)
        
        self.btn_yes = QPushButton("Có (Yes)")
        self.btn_yes.setStyleSheet("""
            QPushButton {
                background-color: #00F0FF;
                color: #0F0F1A;
            }
            QPushButton:hover {
                background-color: #33F3FF;
            }
        """)
        self.btn_yes.clicked.connect(self.accept)
        
        self.btn_no = QPushButton("Không (No)")
        self.btn_no.setStyleSheet("""
            QPushButton {
                background-color: #2F324D;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #3F436B;
            }
        """)
        self.btn_no.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_yes)
        btn_layout.addWidget(self.btn_no)
        btn_layout.addStretch()
        
        layout.addLayout(btn_layout)
        
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        
    def tick(self):
        self.timeout_seconds -= 1
        if self.timeout_seconds <= 0:
            self.timer.stop()
            self.accept()
        else:
            self.lbl_countdown.setText(f"Tự động chọn 'Có' sau {self.timeout_seconds} giây...")

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)


class ShopeeReleaseWorker(QThread):
    finished_signal = Signal(int)
    error_signal = Signal(str)

    def __init__(self, client, client_id):
        super().__init__()
        self.client = client
        self.client_id = client_id

    def run(self):
        try:
            count = self.client.release_jobs(client_id=self.client_id)
            self.finished_signal.emit(count)
        except Exception as e:
            self.error_signal.emit(str(e))


class VeoLiteApp(QMainWindow):
    gui_log_signal = Signal(str)

    def __init__(self, creds):
        super().__init__()
        self.gui_log_signal.connect(self._do_append_log, Qt.QueuedConnection)
        self.creds = creds
        self.client = VeoClient(creds)
        self.worker = None
        self.total_tasks_count = 0
        self.completed_tasks_count = 0
        self.successful_tasks_count = 0
        self.queue_start_time = None
        self.completed_video_times = []
        self.metric_timer = QTimer(self)
        self.metric_timer.setInterval(1000)
        self.metric_timer.timeout.connect(self.update_avg_speed_metric)
        
        self.accounts_timer = QTimer(self)
        self.accounts_timer.setInterval(5000)
        self.accounts_timer.timeout.connect(self.update_accounts_label)
        self.accounts_timer.start()
        
        # Clear log file on startup, rồi giữ file mở (append, line-buffered) thay vì mở lại cho từng dòng log
        self._log_file = None
        try:
            with open("logs.txt", "w", encoding="utf-8") as f:
                f.write(f"=== AutoPromt Veo3go Started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            self._log_file = open("logs.txt", "a", encoding="utf-8", buffering=1)
        except Exception:
            pass

        # task_id -> (row, tab): tránh quét toàn bảng (hàng nghìn dòng) mỗi lần cập nhật tiến độ
        self._task_row_cache = {}

        # Cảnh báo phát sinh lúc dựng giao diện, ghi ra log sau khi khung log đã sẵn sàng
        self._startup_warnings = []

        # Shopee Database Integration
        self.shopee_settings = load_shopee_settings()
        self.shopee_client = ShopeeDatabaseClient(
            server_url=self.shopee_settings.get("sv_server_url"),
            api_key=self.shopee_settings.get("sv_api_key")
        )
        self.task_shopee_map = {}
        self.shopee_claim_worker = None

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("AutoPromt Veo3go - Version 1.5.5")
        self.resize(1100, 750)
        self.setStyleSheet(STYLING)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(12)

        # Header bar
        header_layout = QHBoxLayout()
        title_label = QLabel("AUTOPROMT VEO3GO v1.5.5")
        title_label.setObjectName("titleLabel")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # User Info Panel
        info_layout = QVBoxLayout()
        email_str = self.creds["activation_email"] if (self.creds and self.creds.get("activation_email") != "Không có tài khoản Registry") else "Chưa nhập license"
        user_label = QLabel(f"Tài khoản: <b>{email_str}</b>")
        if self.creds and self.creds.get("activation_email") != "Không có tài khoản Registry":
            status_label = QLabel("Gói cước: <font color='#00F0FF'><b>Unlimited 5 (bản quyền)</b></font>")
        else:
            status_label = QLabel("Gói cước: <font color='#FF9F1C'><b>Chưa có license — nhập key trong Quản lý tài khoản</b></font>")
        info_layout.addWidget(user_label)
        info_layout.addWidget(status_label)
        header_layout.addLayout(info_layout)
        
        main_layout.addLayout(header_layout)
        
        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background-color: #2F324D; max-height: 1px;")
        main_layout.addWidget(divider)
        
        # Settings Bar
        settings_layout = QHBoxLayout()
        
        # Max concurrent threads spinbox
        settings_layout.addWidget(QLabel("⚡ Số luồng song song (Unlimited 5):"))
        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 100)
        try:
            self.spin_threads.setValue(int(self.shopee_settings.get("seedvis_threads", 10)))
        except Exception:
            self.spin_threads.setValue(10)
        self.spin_threads.setFixedWidth(55)
        self.spin_threads.setToolTip("Số lượng tác vụ xử lý cùng một lúc (hỗ trợ tới 100 luồng cho các tài khoản Unlimited 5)")
        settings_layout.addWidget(self.spin_threads)

        self.btn_max_threads = QPushButton("⚡ Tối đa")
        self.btn_max_threads.setToolTip("Tự động đặt số luồng bằng tổng số slots của các tài khoản trong Pool")
        self.btn_max_threads.setStyleSheet("background-color: #7928CA; color: #FFFFFF; font-weight: bold; padding: 3px 8px; border-radius: 4px;")
        self.btn_max_threads.clicked.connect(self.set_max_threads_from_pool)
        settings_layout.addWidget(self.btn_max_threads)

        settings_layout.addWidget(QLabel(" | "))

        # Checkbox for logo stripping
        self.chk_strip_logo = QCheckBox("Tự động xóa logo (Yêu cầu ffmpeg)")
        script_dir = os.path.dirname(os.path.abspath(__file__))
        local_ffmpeg_exists = (
            os.path.exists(os.path.join(script_dir, "vanthe_155", "bin", "ffmpeg.exe")) or
            os.path.exists(os.path.join(script_dir, "bin", "ffmpeg.exe"))
        )
        has_ffmpeg = (
            shutil.which("ffmpeg") is not None or
            os.path.exists("ffmpeg.exe") or
            local_ffmpeg_exists
        )
        # Ưu tiên lựa chọn đã lưu; chưa có thì bật sẵn nếu máy có ffmpeg
        saved_strip = self.shopee_settings.get("seedvis_strip_logo")
        self.chk_strip_logo.setChecked(has_ffmpeg if saved_strip is None else bool(saved_strip))
        settings_layout.addWidget(self.chk_strip_logo)
        settings_layout.addStretch()

        self.btn_save_settings = QPushButton("💾 Lưu cài đặt")
        self.btn_save_settings.setToolTip("Lưu toàn bộ lựa chọn hiện tại để dùng cho các phiên làm việc sau")
        self.btn_save_settings.setStyleSheet("background-color: #00B4D8; color: #FFFFFF; font-weight: bold; padding: 4px 12px; border-radius: 4px;")
        self.btn_save_settings.clicked.connect(self.save_shopee_settings_gui)
        settings_layout.addWidget(self.btn_save_settings)
        
        main_layout.addLayout(settings_layout)
        
        # Accounts Pool Bar
        accounts_layout = QHBoxLayout()
        accounts_layout.addWidget(QLabel("Danh sách tài khoản (Pool):"))
        self.lbl_accounts_count = QLabel("0 tài khoản")
        self.lbl_accounts_count.setStyleSheet("color: #00F0FF; font-weight: bold;")
        accounts_layout.addWidget(self.lbl_accounts_count)
        
        self.btn_manage_accounts = QPushButton("👥 Quản lý Tài khoản (Unlimited Pool)")
        self.btn_manage_accounts.setStyleSheet("background-color: #00F0FF; color: #0B0B12; font-weight: bold; padding: 4px 12px; border-radius: 4px;")
        self.btn_manage_accounts.setToolTip("Mở bảng quản lý, kiểm tra bản quyền, nhập hàng loạt tài khoản Unlimited 5")
        self.btn_manage_accounts.clicked.connect(self.open_account_manager_dialog)
        accounts_layout.addWidget(self.btn_manage_accounts)
        
        btn_clear_acc = QPushButton("Xóa danh sách")
        btn_clear_acc.clicked.connect(self.clear_accounts_pool)
        accounts_layout.addWidget(btn_clear_acc)
        
        accounts_layout.addStretch()
        main_layout.addLayout(accounts_layout)

        # Tab widgets for Modes
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # Tab 1: Image to Video
        self.tab_i2v = QWidget()
        self.setup_tab_i2v()
        self.tabs.addTab(self.tab_i2v, "Ảnh to Video (Image to Video)")
        
        # Tab 2: Start/End (Hidden/Disabled)
        self.tab_se = QWidget()
        self.setup_tab_se()
        # self.tabs.addTab(self.tab_se, "Ảnh Đầu + Ảnh Cuối (Start/End)")
        
        # Hide tab bar as we only have 1 active mode tab now
        self.tabs.tabBar().hide()
        
        # Bottom controls and logs (using Splitter)
        bottom_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(bottom_splitter)
        
        # Console Log Panel
        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 5, 0, 0)
        log_header_layout = QHBoxLayout()
        log_header_label = QLabel("Nhật ký xử lý (Logs):")
        log_header_layout.addWidget(log_header_label)
        log_header_layout.addStretch()
        self.lbl_avg_speed = QLabel("Số Video trung bình/phút: --")
        self.lbl_avg_speed.setStyleSheet("color: #00E5FF; font-weight: bold;")
        log_header_layout.addWidget(self.lbl_avg_speed)
        log_layout.addLayout(log_header_layout)
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumBlockCount(2000)
        self.log_console.setStyleSheet("font-family: Consolas, monospace; background-color: #0B0B12; border: 1px solid #1F2135; color: #FFFFFF;")
        log_layout.addWidget(self.log_console)
        
        bottom_splitter.addWidget(log_panel)
        
        # Progress and Run Panel
        run_panel = QWidget()
        run_layout = QHBoxLayout(run_panel)
        run_layout.setContentsMargins(0, 5, 0, 0)
        
        self.progress_total = QProgressBar()
        self.progress_total.setValue(0)
        self.progress_total.setFormat("Tiến độ tổng: %p%")
        run_layout.addWidget(self.progress_total)
        
        self.btn_run = QPushButton("Bắt đầu chạy queue")
        self.btn_run.setObjectName("btnRun")
        self.btn_run.clicked.connect(self.start_queue)
        run_layout.addWidget(self.btn_run)
        
        self.btn_stop = QPushButton("Dừng lại")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_queue)
        run_layout.addWidget(self.btn_stop)
        
        main_layout.addWidget(run_panel)
        self.load_session()
        self.load_accounts_pool()

        # Báo các sự cố gặp lúc dựng giao diện (giờ khung log đã sẵn sàng)
        for w in self._startup_warnings:
            self.log(f"[Cảnh báo] ⚠ {w}")
        if self._startup_warnings:
            QMessageBox.warning(self, "Cảnh báo khởi động", "\n\n".join(self._startup_warnings))
            self._startup_warnings = []

    # ==================== LƯU / NẠP CÀI ĐẶT ====================
    def collect_ui_settings(self):
        """Gom toàn bộ lựa chọn đang có trên giao diện thành dict để ghi ra file."""
        s = {}

        def put(key, attr, getter):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    s[key] = getter(w)
                except Exception:
                    pass

        txt = lambda w: w.currentText()
        # Panel "Cài đặt Video"
        put("seedvis_aspect", "combo_aspect", txt)
        put("seedvis_scene", "combo_scene", txt)
        put("seedvis_total_dur", "combo_duration", txt)
        put("seedvis_lang", "combo_lang", txt)
        put("seedvis_review_style", "combo_review_style", txt)
        put("seedvis_ai_prompt", "combo_ai_prompt", txt)
        put("seedvis_naming", "combo_naming", txt)
        put("seedvis_del_img", "chk_del_img", lambda w: w.isChecked())
        put("seedvis_ghep_anh", "chk_ghep_anh", lambda w: w.isChecked())
        put("seedvis_out_dir", "txt_output", lambda w: w.text().strip())
        # Thanh cài đặt chung
        put("seedvis_threads", "spin_threads", lambda w: w.value())
        put("seedvis_strip_logo", "chk_strip_logo", lambda w: w.isChecked())
        # Panel "Nhận Lô Sản Phẩm từ Database"
        put("seedvis_market", "combo_shopee_market", txt)
        put("seedvis_sort_by", "combo_shopee_sort", txt)
        put("seedvis_claim_limit", "spin_shopee_limit", lambda w: str(w.value()))
        put("seedvis_min_item_id", "txt_shopee_min_id", lambda w: w.text().strip())
        put("seedvis_min_commission", "txt_shopee_min_comm", lambda w: w.text().strip())
        put("seedvis_min_sold", "txt_shopee_min_sold", lambda w: w.text().strip())
        return s

    def save_all_settings(self, quiet=True):
        """Ghi cài đặt hiện tại xuống shopee_db_settings.json để dùng cho phiên sau."""
        try:
            self.shopee_settings.update(self.collect_ui_settings())
            save_shopee_settings(self.shopee_settings)
            if not quiet:
                self.log("[Cài đặt] 💾 Đã lưu cài đặt. Lần mở phần mềm sau sẽ tự khôi phục.")
            return True
        except Exception as e:
            if not quiet:
                QMessageBox.critical(self, "Lỗi", f"Không thể lưu cài đặt: {e}")
            else:
                print("Lỗi lưu cài đặt:", e)
            return False

    def setup_video_settings_panel(self, parent_layout):
        cfg_box = QGroupBox("⚙ Cài đặt Video")
        cfg_box.setStyleSheet("""
            QGroupBox {
                border: 1px solid #00F0FF;
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: #00F0FF;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        cfg_layout = QVBoxLayout(cfg_box)
        cfg_layout.setContentsMargins(10, 8, 10, 8)
        cfg_layout.setSpacing(6)

        # Row 1: Tỉ lệ, Khung cảnh, Độ dài, Ngôn ngữ
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Tỉ lệ:"))
        self.combo_aspect = QComboBox()
        self.combo_aspect.addItems(["Dọc 9:16 (TikTok)", "Ngang 16:9", "Vuông 1:1"])
        self.combo_aspect.setCurrentText(self.shopee_settings.get("seedvis_aspect", "Dọc 9:16 (TikTok)"))
        self.combo_aspect.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        row1.addWidget(self.combo_aspect)

        row1.addWidget(QLabel("Khung cảnh:"))
        self.combo_scene = QComboBox()
        for s in SHOPEE_SCENES:
            self.combo_scene.addItem(s[0])
        self.combo_scene.setCurrentText(self.shopee_settings.get("seedvis_scene", "🎲 Random"))
        self.combo_scene.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        row1.addWidget(self.combo_scene, 1)

        row1.addWidget(QLabel("Độ dài:"))
        self.combo_duration = QComboBox()
        self.combo_duration.addItems(["8s (Chuẩn 1.5.5)", "16s", "24s", "5s"])
        self.combo_duration.setCurrentText(self.shopee_settings.get("seedvis_total_dur", "8s (Chuẩn 1.5.5)"))
        self.combo_duration.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        row1.addWidget(self.combo_duration)

        row1.addWidget(QLabel("Ngôn ngữ:"))
        self.combo_lang = QComboBox()
        self.combo_lang.addItems(["Tiếng Philippines", "Tiếng Việt", "Tiếng Thái", "Tiếng Indonesia", "Tiếng Malaysia", "Tiếng Anh"])
        self.combo_lang.setCurrentText(self.shopee_settings.get("seedvis_lang", "Tiếng Philippines"))
        self.combo_lang.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        row1.addWidget(self.combo_lang)

        cfg_layout.addLayout(row1)

        # Row 2: Kiểu Review, AI Prompt, Test Prompt, AI Keys, Xóa ảnh, Ghép ảnh
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Kiểu Review:"))
        self.combo_review_style = QComboBox()
        self.combo_review_style.addItems(SHOPEE_REVIEW_STYLES)
        self.combo_review_style.setCurrentText(self.shopee_settings.get("seedvis_review_style", "🎲 Random"))
        self.combo_review_style.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        row2.addWidget(self.combo_review_style, 1)

        row2.addWidget(QLabel("AI Prompt:"))
        self.combo_ai_prompt = QComboBox()
        self.combo_ai_prompt.addItems(["Prompt A + B", "Template (mặc định)", "Gemini", "Groq"])
        self.combo_ai_prompt.setCurrentText(self.shopee_settings.get("seedvis_ai_prompt", "Prompt A + B"))
        self.combo_ai_prompt.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        row2.addWidget(self.combo_ai_prompt)

        self.btn_test_prompt = QPushButton("🧪 Test Prompt")
        self.btn_test_prompt.setStyleSheet("background-color: #5f6368; color: #ffffff; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        self.btn_test_prompt.clicked.connect(self.open_test_prompt_dialog)
        row2.addWidget(self.btn_test_prompt)

        self.btn_ai_keys = QPushButton("🔑 AI Keys")
        self.btn_ai_keys.setStyleSheet("background-color: #1a73e8; color: #ffffff; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        self.btn_ai_keys.clicked.connect(self.open_ai_keys_dialog)
        row2.addWidget(self.btn_ai_keys)

        self.chk_del_img = QCheckBox("Xóa ảnh")
        self.chk_del_img.setChecked(self.shopee_settings.get("seedvis_del_img", True))
        self.chk_del_img.setToolTip("Tự động xóa ảnh tải về sau khi render video thành công")
        self.chk_del_img.setStyleSheet("color: #E2E8F0; font-size: 11px;")
        row2.addWidget(self.chk_del_img)

        self.chk_ghep_anh = QCheckBox("🎞 Ghép ảnh (12s)")
        self.chk_ghep_anh.setChecked(self.shopee_settings.get("seedvis_ghep_anh", False))
        self.chk_ghep_anh.setToolTip("Ghép thêm đoạn outro Zoom In 3.5s từ ảnh sản phẩm thành video 12s hoàn chỉnh")
        self.chk_ghep_anh.setStyleSheet("color: #00F0FF; font-weight: bold; font-size: 11px;")
        row2.addWidget(self.chk_ghep_anh)

        cfg_layout.addLayout(row2)

        # Row 3: Đặt tên video, Lưu Video
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Đặt tên video:"))
        self.combo_naming = QComboBox()
        self.combo_naming.addItems(["Theo Item ID", "15 ký tự đầu prompt", "Tên ảnh đầu vào", "Số thứ tự (001...)"])
        self.combo_naming.setCurrentText(self.shopee_settings.get("seedvis_naming", "Theo Item ID"))
        self.combo_naming.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        row3.addWidget(self.combo_naming)

        row3.addWidget(QLabel("Lưu Video:"))
        self.txt_output = QLineEdit()
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        fallback_out = os.path.join(desktop, "Veo3LiteOutput")
        default_out = self.shopee_settings.get("seedvis_out_dir") or fallback_out
        # Đường dẫn lưu từ máy khác có thể không tồn tại trên máy này (VD: ổ F:).
        # Không được để lỗi này làm sập app lúc khởi động.
        try:
            os.makedirs(default_out, exist_ok=True)
        except Exception as e:
            self._startup_warnings.append(
                f"Không dùng được thư mục lưu video đã lưu ({default_out}): {e}. "
                f"Đã chuyển tạm về: {fallback_out}"
            )
            default_out = fallback_out
            try:
                os.makedirs(default_out, exist_ok=True)
            except Exception:
                pass
        self.txt_output.setText(default_out)
        self.txt_output.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        row3.addWidget(self.txt_output, 2)

        btn_browse_out = QPushButton("Chọn")
        btn_browse_out.setStyleSheet("background-color: #2F324D; color: #ffffff; padding: 4px 12px; border-radius: 4px;")
        btn_browse_out.clicked.connect(self.browse_output_dir)
        row3.addWidget(btn_browse_out)

        cfg_layout.addLayout(row3)
        parent_layout.addWidget(cfg_box)

    def setup_shopee_db_panel(self, parent_layout):
        claim_card = QGroupBox("📦 Nhận Lô Sản Phẩm từ Database")
        claim_card.setStyleSheet("""
            QGroupBox {
                border: 1px solid #2F324D;
                border-radius: 6px;
                margin-top: 6px;
                font-weight: bold;
                color: #00F0FF;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        claim_layout = QVBoxLayout(claim_card)
        claim_layout.setContentsMargins(10, 8, 10, 8)
        claim_layout.setSpacing(6)

        # Row 1: Số lượng, Ưu tiên, Thị trường, ItemID từ, Hoa hồng từ, SL bán từ
        claim_row = QHBoxLayout()
        claim_row.addWidget(QLabel("Số lượng:"))
        self.spin_shopee_limit = QSpinBox()
        self.spin_shopee_limit.setRange(1, 999999999)
        default_lim = 20
        try:
            default_lim = int(self.shopee_settings.get("seedvis_claim_limit", "20"))
        except:
            pass
        self.spin_shopee_limit.setValue(default_lim)
        self.spin_shopee_limit.setFixedWidth(90)
        self.spin_shopee_limit.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        claim_row.addWidget(self.spin_shopee_limit)

        claim_row.addWidget(QLabel("Ưu tiên:"))
        self.combo_shopee_sort = QComboBox()
        self.combo_shopee_sort.addItems(["Số bán cao nhất", "Hoa hồng cao nhất"])
        self.combo_shopee_sort.setCurrentText(self.shopee_settings.get("seedvis_sort_by", "Số bán cao nhất"))
        self.combo_shopee_sort.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        claim_row.addWidget(self.combo_shopee_sort)

        claim_row.addWidget(QLabel("Thị trường:"))
        self.combo_shopee_market = QComboBox()
        self.combo_shopee_market.addItems(SHOPEE_MARKETS)
        self.combo_shopee_market.setCurrentText(self.shopee_settings.get("seedvis_market", "PH"))
        self.combo_shopee_market.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        claim_row.addWidget(self.combo_shopee_market)

        claim_row.addWidget(QLabel("ItemID từ:"))
        self.txt_shopee_min_id = QLineEdit()
        self.txt_shopee_min_id.setText(str(self.shopee_settings.get("seedvis_min_item_id", "40000000000")))
        self.txt_shopee_min_id.setFixedWidth(110)
        self.txt_shopee_min_id.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        claim_row.addWidget(self.txt_shopee_min_id)

        claim_row.addWidget(QLabel("Hoa hồng từ:"))
        self.txt_shopee_min_comm = QLineEdit()
        self.txt_shopee_min_comm.setText(str(self.shopee_settings.get("seedvis_min_commission", "1")))
        self.txt_shopee_min_comm.setFixedWidth(45)
        self.txt_shopee_min_comm.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        claim_row.addWidget(self.txt_shopee_min_comm)

        claim_row.addWidget(QLabel("SL bán (tổng) từ:"))
        self.txt_shopee_min_sold = QLineEdit()
        self.txt_shopee_min_sold.setText(str(self.shopee_settings.get("seedvis_min_sold", "0")))
        self.txt_shopee_min_sold.setFixedWidth(55)
        self.txt_shopee_min_sold.setStyleSheet("background-color: #1e1e2f; color: #ffffff; border: 1px solid #2F324D; border-radius: 4px; padding: 3px;")
        claim_row.addWidget(self.txt_shopee_min_sold)

        claim_row.addStretch()
        claim_layout.addLayout(claim_row)

        # Row 2: Nút hành động & Cấu hình Server
        act_row = QHBoxLayout()
        self.btn_shopee_claim = QPushButton("📥 Lấy SP từ Database & Sinh Prompt")
        self.btn_shopee_claim.setStyleSheet("background-color: #00F0FF; color: #0B0B12; font-weight: bold; padding: 6px 14px; font-size: 13px; border-radius: 4px;")
        self.btn_shopee_claim.clicked.connect(self.start_shopee_claim_gui)
        act_row.addWidget(self.btn_shopee_claim)

        self.btn_shopee_release = QPushButton("🔄 Giải phóng SP kẹt")
        self.btn_shopee_release.setStyleSheet("background-color: #FF9F1C; color: #0B0B12; font-weight: bold; padding: 6px 12px; border-radius: 4px;")
        self.btn_shopee_release.setToolTip("Giải phóng các sản phẩm đang ở trạng thái 'processing' của Client ID này trên Server")
        self.btn_shopee_release.clicked.connect(self.release_shopee_stuck_gui)
        act_row.addWidget(self.btn_shopee_release)

        self.btn_shopee_server_cfg = QPushButton("⚙ Cấu hình Server DB")
        self.btn_shopee_server_cfg.setStyleSheet("background-color: #2F324D; color: #ffffff; padding: 6px 12px; border-radius: 4px;")
        self.btn_shopee_server_cfg.clicked.connect(self.open_shopee_server_config_dialog)
        act_row.addWidget(self.btn_shopee_server_cfg)

        self.lbl_shopee_status = QLabel("Trạng thái: Sẵn sàng kết nối")
        self.lbl_shopee_status.setStyleSheet("color: #A0A5C0; font-style: italic; margin-left: 8px;")
        act_row.addWidget(self.lbl_shopee_status)

        act_row.addStretch()
        claim_layout.addLayout(act_row)

        parent_layout.addWidget(claim_card)

    def open_test_prompt_dialog(self):
        prod_name = "Serum Vitamin C Sáng Da Mờ Thâm Nám 30ml"
        if hasattr(self, 'tbl_i2v') and self.tbl_i2v.rowCount() > 0:
            it = self.tbl_i2v.item(0, 0)
            if it:
                meta = it.data(Qt.UserRole + 1)
                if isinstance(meta, dict) and meta.get("name"):
                    prod_name = meta["name"]

        dlg = TestPromptDialog(
            self,
            product_name=prod_name,
            scene=self.combo_scene.currentText(),
            review_style=self.combo_review_style.currentText(),
            lang=self.combo_lang.currentText(),
            ai_mode=self.combo_ai_prompt.currentText(),
            settings=self.shopee_settings
        )
        dlg.exec()

    def open_ai_keys_dialog(self):
        dlg = AiKeysDialog(self, settings=self.shopee_settings)
        if dlg.exec() == QDialog.Accepted:
            self.log(f"[AI Keys] Đã cập nhật AI Keys ({len(self.shopee_settings.get('gemini_keys', []))} Gemini, {len(self.shopee_settings.get('groq_keys', []))} Groq).")

    def open_shopee_server_config_dialog(self):
        dlg = ShopeeServerConfigDialog(self, settings=self.shopee_settings)
        if dlg.exec() == QDialog.Accepted:
            self.shopee_client.server_url = self.shopee_settings.get("sv_server_url", "").rstrip("/")
            self.shopee_client.api_key = self.shopee_settings.get("sv_api_key", "")
            self.lbl_shopee_status.setText("Đã cập nhật cấu hình Server.")
            self.log(f"[Shopee DB] Đã cập nhật Server: {self.shopee_client.server_url}")

    def start_shopee_claim_gui(self):
        url = self.shopee_settings.get("sv_server_url", "http://100.79.170.67:3000")
        key = self.shopee_settings.get("sv_api_key", "shopee_secret_2026")
        cid = self.shopee_settings.get("sv_client_id", "XEON-CT2A_822d66")
        mkt = self.combo_shopee_market.currentText()
        limit = self.spin_shopee_limit.value()
        sort_by = self.combo_shopee_sort.currentText()
        min_id = self.txt_shopee_min_id.text().strip()
        min_comm = self.txt_shopee_min_comm.text().strip()
        style = self.combo_review_style.currentText()
        scene = self.combo_scene.currentText()
        prompt_mode = self.combo_ai_prompt.currentText()

        self.shopee_client.server_url = url.rstrip("/")
        self.shopee_client.api_key = key

        self.btn_shopee_claim.setEnabled(False)
        self.btn_shopee_claim.setText("⏳ Đang nhận SP...")
        self.lbl_shopee_status.setText("Đang kết nối Server và gửi yêu cầu Claim...")
        self.log(f"[Shopee DB] Bắt đầu nhận {limit} SP (Market: {mkt}, Sort: {sort_by})...")

        gemini_keys = self.shopee_settings.get("gemini_keys", [])

        self.shopee_claim_worker = ShopeeClaimWorker(
            client=self.shopee_client,
            market=mkt,
            client_id=cid,
            limit=limit,
            sort_by=sort_by,
            min_item_id=min_id,
            min_commission=min_comm,
            review_style=style,
            scene_choice=scene,
            prompt_mode=prompt_mode,
            gemini_keys=gemini_keys
        )
        self.shopee_claim_worker.progress_signal.connect(self.on_shopee_claim_progress)
        self.shopee_claim_worker.log_signal.connect(self.log)
        self.shopee_claim_worker.finished_signal.connect(self.on_shopee_claim_finished)
        self.shopee_claim_worker.error_signal.connect(self.on_shopee_claim_error)
        self.shopee_claim_worker.start()

    @Slot(int, int, str)
    def on_shopee_claim_progress(self, cur, tot, text):
        pct = int((cur / tot) * 100) if tot > 0 else 0
        self.lbl_shopee_status.setText(f"{text} ({pct}%)")

    @Slot(list)
    def on_shopee_claim_finished(self, valid_items):
        self.btn_shopee_claim.setEnabled(True)
        self.btn_shopee_claim.setText("📥 Lấy SP từ Database & Sinh Prompt")
        self.lbl_shopee_status.setText(f"Hoàn tất: Đã nạp {len(valid_items)} sản phẩm!")

        if not valid_items:
            self.log("[Shopee DB] Không có sản phẩm nào hợp lệ để nạp.")
            return

        self.tbl_i2v.setUpdatesEnabled(False)
        self.tbl_i2v.setSortingEnabled(False)

        # Xóa dòng rỗng ban đầu nếu có
        if self.tbl_i2v.rowCount() == 1:
            item = self.tbl_i2v.item(0, 2)
            if not item or self.get_item_path(item) in ("", "Nháy đúp để chọn ảnh..."):
                self.tbl_i2v.setRowCount(0)

        start_row = self.tbl_i2v.rowCount()
        self.tbl_i2v.setRowCount(start_row + len(valid_items))

        for i, it in enumerate(valid_items):
            row = start_row + i
            item_select = QTableWidgetItem()
            item_select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item_select.setCheckState(Qt.Checked)
            # Lưu metadata Shopee vào item
            item_select.setData(Qt.UserRole + 1, {
                "item_id": it["item_id"],
                "market": it["market"],
                "name": it["name"],
                "image_url": it.get("image_url", ""),
                "is_lazy_shopee": True
            })
            self.tbl_i2v.setItem(row, 0, item_select)

            # Cột 1: STT
            self.tbl_i2v.setItem(row, 1, QTableWidgetItem(str(row + 1)))

            # Cột 2: Ảnh nguồn (hiển thị placeholder, tải on-demand khi chạy)
            expected_img_name = f"{it['market']}_{it['item_id']}.jpg"
            img_item = QTableWidgetItem(f"[Shopee] {expected_img_name}")
            img_item.setToolTip(f"URL: {it.get('image_url', '')}\n(Ảnh sẽ tự động tải khi tới lượt tạo video)")
            self.tbl_i2v.setItem(row, 2, img_item)

            # Cột 3: Prompt mô tả (hiển thị tên SP sạch, AI sinh prompt khi chạy)
            clean_title = clean_product_title(it["name"])
            prompt_item = QTableWidgetItem(f"[Shopee {it['market']}] {clean_title}")
            prompt_item.setToolTip(f"Tên gốc: {it['name']}\n(Prompt TVC chi tiết sẽ được AI tạo khi tới lượt chạy)")
            self.tbl_i2v.setItem(row, 3, prompt_item)

            # Cột 4: Tỷ lệ
            ar_choice = "9:16"
            if hasattr(self, 'combo_aspect'):
                txt_ar = self.combo_aspect.currentText()
                if "16:9" in txt_ar:
                    ar_choice = "16:9"
                elif "1:1" in txt_ar:
                    ar_choice = "1:1"
                else:
                    ar_choice = "9:16"
            self.tbl_i2v.setItem(row, 4, QTableWidgetItem(ar_choice))

            # Cột 5: Trạng thái
            self.tbl_i2v.setItem(row, 5, QTableWidgetItem("Chờ"))

            # Cột 6: Task ID
            new_task_id = str(uuid.uuid4())
            self.tbl_i2v.setItem(row, 6, QTableWidgetItem(new_task_id))

            # Lưu vào dictionary mapping
            self.task_shopee_map[new_task_id] = {
                "item_id": it["item_id"],
                "market": it["market"],
                "name": it["name"],
                "image_url": it.get("image_url", ""),
                "is_lazy_shopee": True
            }

        self.tbl_i2v.setUpdatesEnabled(True)
        self.log(f"[Shopee DB] 🎉 Đã nạp thành công {len(valid_items)} sản phẩm Shopee vào danh sách! (Ảnh & Prompt sẽ được tạo on-demand khi chạy)")

    @Slot(str)
    def on_shopee_claim_error(self, err_msg):
        self.btn_shopee_claim.setEnabled(True)
        self.btn_shopee_claim.setText("📥 Lấy SP từ Database & Sinh Prompt")
        self.lbl_shopee_status.setText(f"Lỗi: {err_msg}")
        self.log(f"[Shopee DB] ❌ {err_msg}")
        QMessageBox.warning(self, "Lỗi Shopee Database", err_msg)

    def release_shopee_stuck_gui(self):
        cid = self.shopee_settings.get("sv_client_id", "XEON-CT2A_822d66")
        if not cid:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng cấu hình Client ID.")
            return
        self.btn_shopee_release.setEnabled(False)
        self.btn_shopee_release.setText("Đang giải phóng...")
        self.log(f"[Shopee DB] Đang gửi yêu cầu giải phóng SP kẹt cho Client '{cid}'...")

        self.shopee_release_worker = ShopeeReleaseWorker(self.shopee_client, cid)

        def on_done(count):
            self.log(f"[Shopee DB] ✅ Đã giải phóng {count} SP kẹt thành công!")
            self.lbl_shopee_status.setText(f"Đã giải phóng {count} SP kẹt.")
            self.btn_shopee_release.setEnabled(True)
            self.btn_shopee_release.setText("🔄 Giải phóng SP kẹt")

        def on_err(err_msg):
            self.log(f"[Shopee DB] ❌ Lỗi giải phóng: {err_msg}")
            self.lbl_shopee_status.setText(f"Lỗi giải phóng: {err_msg}")
            self.btn_shopee_release.setEnabled(True)
            self.btn_shopee_release.setText("🔄 Giải phóng SP kẹt")

        self.shopee_release_worker.finished_signal.connect(on_done)
        self.shopee_release_worker.error_signal.connect(on_err)
        self.shopee_release_worker.start()

    def save_shopee_settings_gui(self):
        if self.save_all_settings(quiet=False):
            self.lbl_shopee_status.setText("Đã lưu cài đặt.")

    def setup_tab_i2v(self):
        layout = QVBoxLayout(self.tab_i2v)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 1. Panel Cài đặt Video (chuẩn Seedvis)
        self.setup_video_settings_panel(layout)

        # 2. Panel Nhận Lô Sản Phẩm từ Database (chuẩn Seedvis)
        self.setup_shopee_db_panel(layout)

        # Table
        self.tbl_i2v = QTableWidget()
        self.tbl_i2v.verticalHeader().setVisible(False)
        self.tbl_i2v.setColumnCount(7)
        self.header_checkbox = CheckBoxHeader(Qt.Horizontal, self.tbl_i2v)
        self.tbl_i2v.setHorizontalHeader(self.header_checkbox)
        self.tbl_i2v.setHorizontalHeaderLabels([
            "", "STT", "Ảnh nguồn (Start Image)", "Prompt mô tả", "Tỷ lệ", "Trạng thái", "Task ID"
        ])
        self.header_checkbox.stateChanged.connect(self.select_all_i2v_rows)
        
        self.tbl_i2v.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl_i2v.setColumnWidth(0, 30)
        self.tbl_i2v.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tbl_i2v.setColumnWidth(1, 70)
        self.tbl_i2v.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tbl_i2v.setColumnWidth(2, 130)
        self.tbl_i2v.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.tbl_i2v.setColumnWidth(3, 350)
        self.tbl_i2v.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.tbl_i2v.setColumnWidth(4, 60)
        self.tbl_i2v.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.tbl_i2v.setColumnWidth(5, 200)
        self.tbl_i2v.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.tbl_i2v.setColumnWidth(6, 100)
        self.tbl_i2v.horizontalHeader().setSectionResizeMode(6, QHeaderView.Interactive)
        self.tbl_i2v.cellDoubleClicked.connect(self.handle_i2v_double_click)
        layout.addWidget(self.tbl_i2v)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Thêm dòng")
        btn_add.clicked.connect(self.add_i2v_row)
        btn_layout.addWidget(btn_add)
        
        btn_del = QPushButton("Xóa dòng đã chọn")
        btn_del.clicked.connect(self.del_i2v_row)
        btn_layout.addWidget(btn_del)
        
        btn_del_success = QPushButton("Xóa thành công")
        btn_del_success.clicked.connect(self.del_i2v_success_rows)
        btn_layout.addWidget(btn_del_success)
        
        btn_del_copyright = QPushButton("Xóa SP bị từ chối (bản quyền / bộ lọc)")
        btn_del_copyright.clicked.connect(self.del_i2v_copyright_rows)
        btn_layout.addWidget(btn_del_copyright)
        
        btn_custom_check = QPushButton("Custom check")
        btn_custom_check.clicked.connect(self.custom_check_i2v)
        btn_layout.addWidget(btn_custom_check)

        btn_bulk = QPushButton("Nhập hàng loạt ảnh")
        btn_bulk.clicked.connect(self.import_i2v_batch_images)
        btn_layout.addWidget(btn_bulk)
        
        btn_csv = QPushButton("Nhập từ CSV/TXT")
        btn_csv.clicked.connect(self.import_i2v_csv)
        btn_layout.addWidget(btn_csv)
        
        btn_clear = QPushButton("Xóa tất cả")
        btn_clear.clicked.connect(self.clear_i2v_table)
        btn_layout.addWidget(btn_clear)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def setup_tab_se(self):
        layout = QVBoxLayout(self.tab_se)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Table
        self.tbl_se = QTableWidget()
        self.tbl_se.verticalHeader().setVisible(False)
        self.tbl_se.setColumnCount(11)
        self.tbl_se.setHorizontalHeaderLabels([
            "STT", "Ảnh đầu (Start)", "Ảnh cuối (End)", "Prompt mô tả", "Thời lượng (s)", "Motion", "Camera", "1080p", "Silent", "Trạng thái", "Task ID"
        ])
        self.tbl_se.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl_se.setColumnWidth(0, 70)
        self.tbl_se.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tbl_se.setColumnWidth(1, 130)
        self.tbl_se.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.tbl_se.setColumnWidth(2, 130)
        self.tbl_se.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.tbl_se.setColumnWidth(3, 350)
        self.tbl_se.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.tbl_se.setColumnWidth(4, 85)
        self.tbl_se.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.tbl_se.setColumnWidth(5, 60)
        self.tbl_se.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        self.tbl_se.setColumnWidth(6, 100)
        self.tbl_se.horizontalHeader().setSectionResizeMode(6, QHeaderView.Interactive)
        self.tbl_se.setColumnWidth(7, 60)
        self.tbl_se.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed)
        self.tbl_se.setColumnWidth(8, 60)
        self.tbl_se.horizontalHeader().setSectionResizeMode(8, QHeaderView.Fixed)
        self.tbl_se.horizontalHeader().setSectionResizeMode(9, QHeaderView.Stretch)
        self.tbl_se.setColumnWidth(10, 100)
        self.tbl_se.horizontalHeader().setSectionResizeMode(10, QHeaderView.Interactive)
        self.tbl_se.cellDoubleClicked.connect(self.handle_se_double_click)
        layout.addWidget(self.tbl_se)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_add = QPushButton("Thêm dòng")
        btn_add.clicked.connect(self.add_se_row)
        btn_layout.addWidget(btn_add)
        
        btn_del = QPushButton("Xóa dòng đã chọn")
        btn_del.clicked.connect(self.del_se_row)
        btn_layout.addWidget(btn_del)
        
        btn_browse_start = QPushButton("Duyệt ảnh đầu")
        btn_browse_start.clicked.connect(self.browse_se_start_image)
        btn_layout.addWidget(btn_browse_start)
        
        btn_browse_end = QPushButton("Duyệt ảnh cuối")
        btn_browse_end.clicked.connect(self.browse_se_end_image)
        btn_layout.addWidget(btn_browse_end)
        
        btn_csv = QPushButton("Nhập từ CSV/TXT")
        btn_csv.clicked.connect(self.import_se_csv)
        btn_layout.addWidget(btn_csv)
        
        btn_clear = QPushButton("Xóa tất cả")
        btn_clear.clicked.connect(self.clear_se_table)
        btn_layout.addWidget(btn_clear)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    # Browse Directory
    def browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Chọn thư mục đầu ra", self.txt_output.text())
        if path:
            self.txt_output.setText(path)

    # I2V operations
    def get_item_path(self, item):
        if not item:
            return ""
        user_data = item.data(Qt.UserRole)
        if user_data:
            return user_data
        return item.text()

    def make_path_item(self, path):
        if not path or path in ("Nháy đúp để chọn ảnh...", "Ảnh đầu...", "Ảnh cuối..."):
            item = QTableWidgetItem(path)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return item
            
        filename = os.path.basename(path)
        item = QTableWidgetItem(filename)
        item.setData(Qt.UserRole, path)
        item.setToolTip(path)
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return item

    def select_all_i2v_rows(self, state):
        self.tbl_i2v.setUpdatesEnabled(False)
        check_state = Qt.Checked if state == 2 else Qt.Unchecked
        for r in range(self.tbl_i2v.rowCount()):
            item = self.tbl_i2v.item(r, 0)
            if item:
                item.setCheckState(check_state)
        self.tbl_i2v.setUpdatesEnabled(True)

    def custom_check_i2v(self):
        dialog = CustomCheckDialog(self)
        if dialog.exec() == QDialog.Accepted:
            action, range_str = dialog.get_data()
            max_rows = self.tbl_i2v.rowCount()
            indices = parse_row_ranges(range_str, max_rows)
            
            check_state = Qt.Checked if action == "Check" else Qt.Unchecked
            
            self.tbl_i2v.setUpdatesEnabled(False)
            for r in range(max_rows):
                if r in indices:
                    item = self.tbl_i2v.item(r, 0)
                    if item:
                        item.setCheckState(check_state)
            self.tbl_i2v.setUpdatesEnabled(True)

    def add_i2v_row(self):
        row = self.tbl_i2v.rowCount()
        self.tbl_i2v.insertRow(row)
        
        item_select = QTableWidgetItem()
        item_select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item_select.setCheckState(Qt.Unchecked)
        self.tbl_i2v.setItem(row, 0, item_select)
        
        self.tbl_i2v.setItem(row, 1, QTableWidgetItem(str(row + 1)))
        self.tbl_i2v.setItem(row, 2, self.make_path_item("Nháy đúp để chọn ảnh..."))
        self.tbl_i2v.setItem(row, 3, QTableWidgetItem("A beautiful cinematic sunset over mountains"))
        
        self.tbl_i2v.setItem(row, 4, QTableWidgetItem("9:16"))
        
        self.tbl_i2v.setItem(row, 5, QTableWidgetItem("Chờ"))
        self.tbl_i2v.setItem(row, 6, QTableWidgetItem(str(uuid.uuid4())))

    def del_i2v_row(self):
        checked_rows = []
        for r in range(self.tbl_i2v.rowCount()):
            item = self.tbl_i2v.item(r, 0)
            if item and item.checkState() == Qt.Checked:
                checked_rows.append(r)
                
        if not checked_rows:
            curr = self.tbl_i2v.currentRow()
            if curr >= 0:
                checked_rows.append(curr)
                
        if checked_rows:
            checked_rows.sort(reverse=True)
            self.tbl_i2v.setUpdatesEnabled(False)
            for r in checked_rows:
                self.tbl_i2v.removeRow(r)
            for r in range(self.tbl_i2v.rowCount()):
                stt_item = self.tbl_i2v.item(r, 1)
                if stt_item:
                    stt_item.setText(str(r + 1))
            self.tbl_i2v.setUpdatesEnabled(True)

    def del_i2v_success_rows(self):
        self.tbl_i2v.setUpdatesEnabled(False)
        self.tbl_i2v.setSortingEnabled(False)
        for r in range(self.tbl_i2v.rowCount() - 1, -1, -1):
            status_item = self.tbl_i2v.item(r, 5)
            if status_item and status_item.text() == "Hoàn thành":
                self.tbl_i2v.removeRow(r)
        for r in range(self.tbl_i2v.rowCount()):
            stt_item = self.tbl_i2v.item(r, 1)
            if stt_item:
                stt_item.setText(str(r + 1))
        self.tbl_i2v.setUpdatesEnabled(True)

    def del_i2v_copyright_rows(self):
        """Xóa các dòng bị Veo từ chối hẳn (bản quyền / bộ lọc nội dung) — chạy lại cũng bị từ chối."""
        self.tbl_i2v.setUpdatesEnabled(False)
        self.tbl_i2v.setSortingEnabled(False)
        for r in range(self.tbl_i2v.rowCount() - 1, -1, -1):
            status_item = self.tbl_i2v.item(r, 5)
            if status_item and status_item.text() in CONTENT_REJECT_LABELS:
                self.tbl_i2v.removeRow(r)
        for r in range(self.tbl_i2v.rowCount()):
            stt_item = self.tbl_i2v.item(r, 1)
            if stt_item:
                stt_item.setText(str(r + 1))
        self.tbl_i2v.setUpdatesEnabled(True)

    def handle_i2v_double_click(self, row, col):
        if col == 2:
            self.browse_i2v_image_for_row(row)

    def browse_i2v_image(self):
        row = self.tbl_i2v.currentRow()
        if row >= 0:
            self.browse_i2v_image_for_row(row)
        else:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn một dòng trước!")

    def browse_i2v_image_for_row(self, row):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh nguồn", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if file_path:
            self.tbl_i2v.setItem(row, 2, self.make_path_item(file_path))

    # SE operations
    def add_se_row(self):
        row = self.tbl_se.rowCount()
        self.tbl_se.insertRow(row)
        
        self.tbl_se.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.tbl_se.setItem(row, 1, self.make_path_item("Ảnh đầu..."))
        self.tbl_se.setItem(row, 2, self.make_path_item("Ảnh cuối..."))
        self.tbl_se.setItem(row, 3, QTableWidgetItem("A futuristic city transformation"))
        self.tbl_se.setItem(row, 4, QTableWidgetItem("5"))
        self.tbl_se.setItem(row, 5, QTableWidgetItem(""))
        self.tbl_se.setItem(row, 6, QTableWidgetItem(""))
        
        item_up = QTableWidgetItem()
        item_up.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item_up.setCheckState(Qt.Unchecked)
        self.tbl_se.setItem(row, 7, item_up)
        
        item_silent = QTableWidgetItem()
        item_silent.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        item_silent.setCheckState(Qt.Checked)
        self.tbl_se.setItem(row, 8, item_silent)
        
        self.tbl_se.setItem(row, 9, QTableWidgetItem("Chờ"))
        self.tbl_se.setItem(row, 10, QTableWidgetItem(str(uuid.uuid4())))

    def del_se_row(self):
        curr = self.tbl_se.currentRow()
        if curr >= 0:
            self.tbl_se.removeRow(curr)
            for r in range(self.tbl_se.rowCount()):
                self.tbl_se.item(r, 0).setText(str(r + 1))

    def handle_se_double_click(self, row, col):
        if col == 1:
            self.browse_se_image_for_row(row, 1)
        elif col == 2:
            self.browse_se_image_for_row(row, 2)

    def browse_se_start_image(self):
        row = self.tbl_se.currentRow()
        if row >= 0:
            self.browse_se_image_for_row(row, 1)
        else:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn một dòng trước!")

    def browse_se_end_image(self):
        row = self.tbl_se.currentRow()
        if row >= 0:
            self.browse_se_image_for_row(row, 2)
        else:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn một dòng trước!")

    def browse_se_image_for_row(self, row, col):
        title = "Chọn ảnh đầu" if col == 1 else "Chọn ảnh cuối"
        file_path, _ = QFileDialog.getOpenFileName(self, title, "", "Images (*.png *.jpg *.jpeg *.webp)")
        if file_path:
            self.tbl_se.setItem(row, col, self.make_path_item(file_path))



    def import_i2v_batch_images(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa ảnh nguồn")
        if not dir_path:
            return
            
        exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
        file_paths = []
        try:
            for f in os.listdir(dir_path):
                if f.lower().endswith(exts):
                    file_paths.append(os.path.join(dir_path, f))
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể đọc thư mục: {e}")
            return
            
        if not file_paths:
            QMessageBox.warning(self, "Cảnh báo", "Không tìm thấy ảnh nào (.png, .jpg, .jpeg, .webp, .bmp) trong thư mục đã chọn.")
            return
            
        file_paths.sort()
        
        dialog = PromptSourceDialog(self)
        dialog.exec()
        
        prompts = []
        if dialog.result_mode == "file":
            prompt_file, _ = QFileDialog.getOpenFileName(self, "Chọn file prompt TXT", "", "Text files (*.txt)")
            if prompt_file:
                try:
                    with open(prompt_file, "r", encoding="utf-8") as f:
                        prompts = [line.strip() for line in f.readlines() if line.strip()]
                except Exception as e:
                    QMessageBox.warning(self, "Lỗi", f"Không thể đọc file prompt: {e}")
        elif dialog.result_mode == "paste":
            paste_dialog = PastePromptDialog(self)
            if paste_dialog.exec() == QDialog.Accepted:
                prompts = paste_dialog.get_prompts()
                    
        # Remove placeholder row if it is the only row before inserting imported images
        if self.tbl_i2v.rowCount() == 1:
            item = self.tbl_i2v.item(0, 2)
            if item and item.text() == "Nháy đúp để chọn ảnh...":
                self.tbl_i2v.setRowCount(0)

        self.tbl_i2v.setUpdatesEnabled(False)
        self.tbl_i2v.setSortingEnabled(False)
        
        start_row = self.tbl_i2v.rowCount()
        self.tbl_i2v.setRowCount(start_row + len(file_paths))
        
        for i, path in enumerate(file_paths):
            row = start_row + i
            item_select = QTableWidgetItem()
            item_select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item_select.setCheckState(Qt.Unchecked)
            self.tbl_i2v.setItem(row, 0, item_select)
            
            self.tbl_i2v.setItem(row, 1, QTableWidgetItem(str(row + 1)))
            self.tbl_i2v.setItem(row, 2, self.make_path_item(path))
            
            prompt = ""
            if i < len(prompts):
                prompt = prompts[i]
            else:
                base = os.path.basename(path)
                name, _ = os.path.splitext(base)
                prompt = name.replace("_", " ").replace("-", " ")
                
            self.tbl_i2v.setItem(row, 3, QTableWidgetItem(prompt))
            self.tbl_i2v.setItem(row, 4, QTableWidgetItem("9:16"))
            
            self.tbl_i2v.setItem(row, 5, QTableWidgetItem("Chờ"))
            self.tbl_i2v.setItem(row, 6, QTableWidgetItem(str(uuid.uuid4())))
            
        self.tbl_i2v.setUpdatesEnabled(True)
        QMessageBox.information(self, "Thành công", f"Đã nhập {len(file_paths)} dòng thành công.")
            
    def parse_line_path_prompt(self, line):
        line = line.strip()
        if not line:
            return None, None
            
        exts = [".png", ".jpg", ".jpeg", ".webp", ".bmp"]
        line_lower = line.lower()
        
        for ext in exts:
            if ext in line_lower:
                idx = line_lower.find(ext)
                end_idx = idx + len(ext)
                img_path = line[:end_idx].strip()
                
                remainder = line[end_idx:].strip()
                if remainder.startswith(",") or remainder.startswith(";") or remainder.startswith("|") or remainder.startswith("\t"):
                    remainder = remainder[1:].strip()
                return img_path, remainder
                
        for delim in ["|", ",", ";", "\t"]:
            if delim in line:
                parts = line.split(delim, 1)
                return parts[0].strip(), parts[1].strip()
                
        return line, ""

    def parse_line_start_end_prompt(self, line):
        line = line.strip()
        if not line:
            return None, None, None
            
        exts = [".png", ".jpg", ".jpeg", ".webp", ".bmp"]
        line_lower = line.lower()
        
        first_img = None
        second_img = None
        prompt = ""
        
        matches = []
        for ext in exts:
            pos = 0
            while True:
                pos = line_lower.find(ext, pos)
                if pos == -1:
                    break
                matches.append((pos, pos + len(ext)))
                pos += len(ext)
                
        matches.sort()
        
        if len(matches) >= 2:
            first_img = line[:matches[0][1]].strip()
            second_part = line[matches[0][1]:]
            if second_part.startswith(",") or second_part.startswith(";") or second_part.startswith("|") or second_part.startswith("\t"):
                second_part = second_part[1:].strip()
                
            second_part_lower = second_part.lower()
            sec_matches = []
            for ext in exts:
                pos = second_part_lower.find(ext)
                if pos != -1:
                    sec_matches.append((pos, pos + len(ext)))
            sec_matches.sort()
            if sec_matches:
                second_img = second_part[:sec_matches[0][1]].strip()
                remainder = second_part[sec_matches[0][1]:].strip()
                if remainder.startswith(",") or remainder.startswith(";") or remainder.startswith("|") or remainder.startswith("\t"):
                    remainder = remainder[1:].strip()
                prompt = remainder
            else:
                second_img = second_part
        elif len(matches) == 1:
            first_img = line[:matches[0][1]].strip()
            remainder = line[matches[0][1]:].strip()
            if remainder.startswith(",") or remainder.startswith(";") or remainder.startswith("|") or remainder.startswith("\t"):
                remainder = remainder[1:].strip()
            for delim in ["|", ",", ";", "\t"]:
                if delim in remainder:
                    parts = remainder.split(delim, 1)
                    second_img = parts[0].strip()
                    prompt = parts[1].strip()
                    break
            if not second_img:
                second_img = remainder
        else:
            for delim in ["|", ",", ";", "\t"]:
                if delim in line:
                    parts = line.split(delim)
                    first_img = parts[0].strip() if len(parts) > 0 else ""
                    second_img = parts[1].strip() if len(parts) > 1 else ""
                    prompt = parts[2].strip() if len(parts) > 2 else ""
                    break
            if not first_img:
                first_img = line
                
        return first_img, second_img, prompt

    def import_i2v_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file CSV/TXT", "", "Data files (*.csv *.txt)")
        if not file_path:
            return
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            valid_items = []
            for line in lines:
                img_path, prompt = self.parse_line_path_prompt(line)
                if img_path:
                    valid_items.append((img_path, prompt))
            
            if not valid_items:
                return
                
            # Remove placeholder row if it is the only row before inserting imported images
            if self.tbl_i2v.rowCount() == 1:
                item = self.tbl_i2v.item(0, 2)
                if item and item.text() == "Nháy đúp để chọn ảnh...":
                    self.tbl_i2v.setRowCount(0)

            self.tbl_i2v.setUpdatesEnabled(False)
            self.tbl_i2v.setSortingEnabled(False)
            
            start_row = self.tbl_i2v.rowCount()
            self.tbl_i2v.setRowCount(start_row + len(valid_items))
            
            for i, (img_path, prompt) in enumerate(valid_items):
                row = start_row + i
                item_select = QTableWidgetItem()
                item_select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                item_select.setCheckState(Qt.Unchecked)
                self.tbl_i2v.setItem(row, 0, item_select)
                
                self.tbl_i2v.setItem(row, 1, QTableWidgetItem(str(row + 1)))
                self.tbl_i2v.setItem(row, 2, self.make_path_item(img_path))
                
                if not prompt:
                    base = os.path.basename(img_path)
                    name, _ = os.path.splitext(base)
                    prompt = name.replace("_", " ").replace("-", " ")
                    
                self.tbl_i2v.setItem(row, 3, QTableWidgetItem(prompt))
                self.tbl_i2v.setItem(row, 4, QTableWidgetItem("9:16"))
                
                self.tbl_i2v.setItem(row, 5, QTableWidgetItem("Chờ"))
                self.tbl_i2v.setItem(row, 6, QTableWidgetItem(str(uuid.uuid4())))
                
            self.tbl_i2v.setUpdatesEnabled(True)
            QMessageBox.information(self, "Thành công", f"Đã nhập {len(valid_items)} dòng thành công.")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể đọc file: {e}")

    def clear_i2v_table(self):
        self.tbl_i2v.setRowCount(0)

    def import_se_csv(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Chọn file CSV/TXT", "", "Data files (*.csv *.txt)")
        if not file_path:
            return
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            valid_items = []
            for line in lines:
                start_img, end_img, prompt = self.parse_line_start_end_prompt(line)
                if start_img:
                    valid_items.append((start_img, end_img, prompt))
                    
            if not valid_items:
                return
                
            self.tbl_se.setUpdatesEnabled(False)
            self.tbl_se.setSortingEnabled(False)
            
            start_row = self.tbl_se.rowCount()
            self.tbl_se.setRowCount(start_row + len(valid_items))
            
            for i, (start_img, end_img, prompt) in enumerate(valid_items):
                row = start_row + i
                self.tbl_se.setItem(row, 0, QTableWidgetItem(str(row + 1)))
                self.tbl_se.setItem(row, 1, self.make_path_item(start_img))
                self.tbl_se.setItem(row, 2, self.make_path_item(end_img))
                
                if not prompt:
                    base = os.path.basename(start_img)
                    name, _ = os.path.splitext(base)
                    prompt = name.replace("_", " ").replace("-", " ")
                    
                self.tbl_se.setItem(row, 3, QTableWidgetItem(prompt))
                self.tbl_se.setItem(row, 4, QTableWidgetItem("5"))
                self.tbl_se.setItem(row, 5, QTableWidgetItem(""))
                self.tbl_se.setItem(row, 6, QTableWidgetItem(""))
                
                item_up = QTableWidgetItem()
                item_up.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                item_up.setCheckState(Qt.Unchecked)
                self.tbl_se.setItem(row, 7, item_up)
                
                item_silent = QTableWidgetItem()
                item_silent.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                item_silent.setCheckState(Qt.Checked)
                self.tbl_se.setItem(row, 8, item_silent)
                
                self.tbl_se.setItem(row, 9, QTableWidgetItem("Chờ"))
                self.tbl_se.setItem(row, 10, QTableWidgetItem(str(uuid.uuid4())))
                
            self.tbl_se.setUpdatesEnabled(True)
            QMessageBox.information(self, "Thành công", f"Đã nhập {len(valid_items)} dòng thành công.")
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không thể đọc file: {e}")

    def clear_se_table(self):
        self.tbl_se.setRowCount(0)

    # Queue controls
    @Slot(str)
    def _do_append_log(self, log_str):
        self.log_console.appendPlainText(log_str)

    def log(self, text):
        log_str = f"[{time.strftime('%H:%M:%S')}] {text}"
        self.gui_log_signal.emit(log_str)
        if self._log_file:
            try:
                self._log_file.write(log_str + "\n")
            except Exception:
                pass

    def start_queue(self):
        tasks = []
        dur_choice = 8
        if hasattr(self, 'combo_duration'):
            dt = self.combo_duration.currentText()
            if "16" in dt:
                dur_choice = 16
            elif "24" in dt:
                dur_choice = 24
            elif "5" in dt:
                dur_choice = 5
            else:
                dur_choice = 8
        
        self._task_row_cache.clear()
        missing_img_rows = []

        # Parse I2V
        for r in range(self.tbl_i2v.rowCount()):
            item_check = self.tbl_i2v.item(r, 0)
            if item_check and item_check.checkState() == Qt.Checked:
                status = self.tbl_i2v.item(r, 5).text() if self.tbl_i2v.item(r, 5) else ""
                if status != "Hoàn thành":
                    task_id_val = self.tbl_i2v.item(r, 6).text() if self.tbl_i2v.item(r, 6) else str(uuid.uuid4())
                    shopee_meta = item_check.data(Qt.UserRole + 1)
                    if not shopee_meta and task_id_val in self.task_shopee_map:
                        shopee_meta = self.task_shopee_map[task_id_val]

                    is_lazy = False
                    if isinstance(shopee_meta, dict) and shopee_meta.get("is_lazy_shopee"):
                        is_lazy = True

                    start_img = self.get_item_path(self.tbl_i2v.item(r, 2))
                    if not is_lazy:
                        if start_img == "Nháy đúp để chọn ảnh..." or not start_img:
                            continue
                        if not os.path.exists(start_img):
                            # Bỏ qua dòng thiếu ảnh thay vì dừng cả hàng chờ
                            missing_img_rows.append(r + 1)
                            self.tbl_i2v.setItem(r, 5, QTableWidgetItem("Lỗi: Không tìm thấy ảnh nguồn"))
                            continue

                    self._task_row_cache[task_id_val] = (r, "i2v")

                    ar = self.tbl_i2v.item(r, 4).text() if self.tbl_i2v.item(r, 4) else "9:16"
                    strip_logo = True
                    up1080 = False

                    s_id = ""
                    s_mkt = ""
                    s_url = ""
                    s_name = ""
                    if isinstance(shopee_meta, dict):
                        s_id = shopee_meta.get("item_id", "")
                        s_mkt = shopee_meta.get("market", "")
                        s_url = shopee_meta.get("image_url", "")
                        s_name = shopee_meta.get("name", "")
                    elif task_id_val in self.task_shopee_map:
                        s_id = self.task_shopee_map[task_id_val].get("item_id", "")
                        s_mkt = self.task_shopee_map[task_id_val].get("market", "")
                        s_url = self.task_shopee_map[task_id_val].get("image_url", "")
                        s_name = self.task_shopee_map[task_id_val].get("name", "")

                    cur_scene = self.combo_scene.currentText() if hasattr(self, 'combo_scene') else "🎲 Random"
                    cur_style = self.combo_review_style.currentText() if hasattr(self, 'combo_review_style') else "🎲 Random"
                    cur_prompt_mode = self.combo_ai_prompt.currentText() if hasattr(self, 'combo_ai_prompt') else "Template (mặc định)"

                    tasks.append({
                        "mode": "image_to_video",
                        "task_id": task_id_val,
                        "start_image": start_img,
                        "prompt": self.tbl_i2v.item(r, 3).text() if self.tbl_i2v.item(r, 3) else "",
                        "aspect_ratio": ar,
                        "allow_silent": True,
                        "upscale_1080p": up1080,
                        "duration_seconds": dur_choice,
                        "strip_logo": strip_logo,
                        "row_index": r,
                        "tab": "i2v",
                        "is_lazy_shopee": is_lazy,
                        "shopee_item_id": s_id,
                        "shopee_market": s_mkt,
                        "shopee_image_url": s_url,
                        "shopee_name": s_name,
                        "shopee_scene": cur_scene,
                        "shopee_style": cur_style,
                        "shopee_prompt_mode": cur_prompt_mode
                    })
                
        # Parse SE (Disabled)
        pass

        if missing_img_rows:
            preview = ", ".join(str(n) for n in missing_img_rows[:20])
            more = f" ... (+{len(missing_img_rows) - 20})" if len(missing_img_rows) > 20 else ""
            self.log(f"[Hệ thống] Bỏ qua {len(missing_img_rows)} dòng không tìm thấy ảnh nguồn: {preview}{more}")

        if not tasks:
            msg = "Không có tác vụ nào được chọn hoặc cần xử lý!"
            if missing_img_rows:
                msg += f"\n\n{len(missing_img_rows)} dòng đã chọn bị bỏ qua vì không tìm thấy ảnh nguồn (xem log)."
            QMessageBox.information(self, "Thông báo", msg)
            return
            
        # Thư mục lưu video phải dùng được, nếu không mọi video sẽ hỏng khi tải về
        out_dir = self.txt_output.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "Thiếu thư mục lưu", "Vui lòng chọn thư mục lưu video.")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(
                self, "Lỗi thư mục lưu video",
                f"Không thể tạo thư mục lưu video:\n{out_dir}\n\n{e}\n\n"
                f"Hãy bấm nút 'Chọn' để đổi sang thư mục khác."
            )
            return

        # Lưu cài đặt ngay khi bắt đầu chạy, phòng trường hợp app tắt đột ngột
        self.save_all_settings()

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.btn_stop.setText("⏹ Dừng lại")
        self.progress_total.setValue(0)
        self.total_tasks_count = len(tasks)
        self.completed_tasks_count = 0
        self.successful_tasks_count = 0
        self.queue_start_time = time.time()
        self.completed_video_times = []
        self.lbl_avg_speed.setText("Số Video trung bình/phút: --")
        self.metric_timer.start()
        self.progress_total.setFormat(f"Tiến độ tổng: 0% (Thành công: 0/{self.total_tasks_count})")
        
        # Start Thread
        self.worker = WorkerThread(
            self.client, 
            tasks, 
            self.txt_output.text(), 
            self.chk_strip_logo.isChecked(),
            accounts_pool=self.accounts_pool,
            max_workers=self.spin_threads.value(),
            naming_mode=self.combo_naming.currentText(),
            ghep_anh_12s=(self.chk_ghep_anh.isChecked() if hasattr(self, 'chk_ghep_anh') else False),
            del_img=(self.chk_del_img.isChecked() if hasattr(self, 'chk_del_img') else False),
            shopee_client=self.shopee_client
        )
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_task_progress)
        self.worker.task_done_signal.connect(self.handle_task_done)
        self.worker.task_updated_signal.connect(self.handle_task_updated)
        self.worker.finished_signal.connect(self.handle_queue_finished)
        self.worker.account_created_signal.connect(self.update_accounts_label)
        self.worker.task_id_changed_signal.connect(self.handle_task_id_changed)
        self.worker.start()

    def stop_queue(self):
        self.metric_timer.stop()
        if hasattr(self, 'worker') and self.worker:
            self.worker.request_stop()
            self.btn_stop.setText("⏳ Đang đợi hoàn thành...")
            self.btn_stop.setEnabled(False)
            self.log("[Hệ thống] Nhận yêu cầu dừng: Không nhận thêm tác vụ mới, đang hoàn thành nốt các video đang xử lý dở...")



    def update_task_progress(self, task_id, progress, status):
        # Find row in tables
        row, tab = self.find_row_by_task_id(task_id)
        if row != -1:
            tbl = self.tbl_i2v if tab == "i2v" else self.tbl_se
            col = 5 if tab == "i2v" else 9
            it = tbl.item(row, col)
            if it:
                it.setText(f"{status} ({progress}%)")
            else:
                tbl.setItem(row, col, QTableWidgetItem(f"{status} ({progress}%)"))

    @Slot(str, str)
    def handle_task_id_changed(self, old_task_id, new_task_id):
        row, tab = self.find_row_by_task_id(old_task_id)
        if row != -1:
            tbl = self.tbl_i2v if tab == "i2v" else self.tbl_se
            col = 6 if tab == "i2v" else 10
            it = tbl.item(row, col)
            if it:
                it.setText(new_task_id)
            else:
                tbl.setItem(row, col, QTableWidgetItem(new_task_id))

    @Slot(str, str, str)
    def handle_task_updated(self, task_id, image_path, prompt):
        row, tab = self.find_row_by_task_id(task_id)
        if row != -1 and tab == "i2v":
            if image_path and os.path.exists(image_path):
                self.tbl_i2v.setItem(row, 2, self.make_path_item(image_path))
            if prompt:
                self.tbl_i2v.setItem(row, 3, QTableWidgetItem(prompt))

    @Slot(str, str, str)
    def handle_task_done(self, task_id, output_path, result):
        row, tab = self.find_row_by_task_id(task_id)
        if row != -1:
            tbl = self.tbl_i2v if tab == "i2v" else self.tbl_se
            col = 5 if tab == "i2v" else 9
            it = tbl.item(row, col)
            if not it:
                it = QTableWidgetItem(result)
                tbl.setItem(row, col, it)
            else:
                it.setText(result)

            if result == "Hoàn thành":
                it.setForeground(QColor("#00F0FF"))
                self.successful_tasks_count += 1
                self.completed_video_times.append(time.time())
            else:
                it.setForeground(QColor("#FF4D5A"))

        if output_path:
            self.log(f"Đã lưu video thành công: {output_path}")

        self.completed_tasks_count += 1
        pct = int((self.completed_tasks_count / self.total_tasks_count) * 100) if self.total_tasks_count > 0 else 0
        self.progress_total.setValue(pct)
        self.progress_total.setFormat(f"Tiến độ tổng: {pct}% (Thành công: {self.successful_tasks_count}/{self.total_tasks_count})")
        self.update_avg_speed_metric()

    def update_avg_speed_metric(self):
        if not hasattr(self, 'queue_start_time') or self.queue_start_time is None:
            self.lbl_avg_speed.setText("Số Video trung bình/phút: --")
            return
            
        now = time.time()
        elapsed = now - self.queue_start_time
        completed_minutes = int(elapsed // 60)
        
        if completed_minutes < 1:
            self.lbl_avg_speed.setText("Số Video trung bình/phút: --")
        else:
            cutoff_time = self.queue_start_time + completed_minutes * 60
            v_count = sum(1 for t in self.completed_video_times if t < cutoff_time)
            avg = v_count / completed_minutes
            self.lbl_avg_speed.setText(f"Số Video trung bình/phút: {avg:.2f}")

    @Slot()
    def handle_queue_finished(self):
        self.metric_timer.stop()
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText("⏹ Dừng lại")
        self.progress_total.setValue(100)
        self.progress_total.setFormat(f"Tiến độ tổng: 100% (Thành công: {self.successful_tasks_count}/{self.total_tasks_count})")
        
        stopped_by_user = getattr(self.worker, 'stop_requested', False) if hasattr(self, 'worker') and self.worker else False
        if stopped_by_user:
            self.log("[Hệ thống] Đã dừng hàng chờ theo yêu cầu người dùng. Toàn bộ tác vụ đang chạy đã hoàn tất.")
        else:
            self.log("Hoàn thành xử lý hàng chờ.")

        # 1. Automatically delete completed rows ("Hoàn thành") and copyright error rows ("Lỗi Bản Quyền")
        self.del_i2v_success_rows()
        self.del_i2v_copyright_rows()

        # 2. Check if there are remaining rows (failed/pending ones)
        remaining_rows = self.tbl_i2v.rowCount()

        if stopped_by_user:
            return

        if remaining_rows > 0:
            dialog = CountdownMessageBox(self, timeout_seconds=20)
            if dialog.exec() == QDialog.Accepted:
                self.log("Bắt đầu chạy lại các lệnh lỗi/còn lại...")
                self.start_queue()
            else:
                self.log("Người dùng từ chối chạy lại các lệnh lỗi.")
        else:
            QMessageBox.information(self, "Hoàn thành", "Đã xử lý xong hàng chờ! Tất cả video đã tạo thành công.")

    def find_row_by_task_id(self, task_id):
        # Thử vị trí đã biết trước; dòng có thể đã bị xóa/dịch chuyển nên luôn kiểm tra lại Task ID
        cached = self._task_row_cache.get(task_id)
        if cached:
            r, tab = cached
            tbl, col = (self.tbl_i2v, 6) if tab == "i2v" else (self.tbl_se, 10)
            it_tid = tbl.item(r, col)
            if it_tid and it_tid.text() == task_id:
                return r, tab

        # search i2v
        for r in range(self.tbl_i2v.rowCount()):
            it_tid = self.tbl_i2v.item(r, 6)
            if it_tid and it_tid.text() == task_id:
                self._task_row_cache[task_id] = (r, "i2v")
                return r, "i2v"
        # search se
        for r in range(self.tbl_se.rowCount()):
            it_tid = self.tbl_se.item(r, 10)
            if it_tid and it_tid.text() == task_id:
                self._task_row_cache[task_id] = (r, "se")
                return r, "se"
        return -1, ""

    def closeEvent(self, event):
        self.save_all_settings()
        self.save_session()
        # 1. Tự động giải phóng các sản phẩm đang kẹt trên Shopee Database Server.
        # Chạy nền và chờ tối đa 5s để server chậm/mất kết nối không làm treo cửa sổ khi tắt.
        if hasattr(self, 'shopee_client'):
            cid = self.shopee_settings.get("sv_client_id", "XEON-CT2A_822d66")

            def do_release():
                try:
                    rel_cnt = self.shopee_client.release_jobs(client_id=cid)
                    print(f"[Shopee DB] Đã tự động giải phóng {rel_cnt} SP kẹt khi đóng ứng dụng.")
                except Exception as e:
                    print("Lỗi giải phóng SP kẹt khi tắt:", e)

            release_thread = threading.Thread(target=do_release, daemon=True)
            release_thread.start()
            release_thread.join(5)

        # 2. Dừng worker nếu đang chạy (chờ ngắn để QThread không bị hủy khi đang chạy)
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)

        # 3. Dọn dẹp thư mục ảnh Shopee tạm
        try:
            import shutil
            shopee_img_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads", "shopee_images")
            if os.path.isdir(shopee_img_dir):
                shutil.rmtree(shopee_img_dir, ignore_errors=True)
        except Exception:
            pass
        super().closeEvent(event)

    def save_session(self):
        try:
            # Table 1: Image to Video
            i2v_rows = []
            for r in range(self.tbl_i2v.rowCount()):
                def cell_text(col):
                    it = self.tbl_i2v.item(r, col)
                    return it.text() if it else ""

                status = cell_text(5).strip()
                if status in ("Hoàn thành", "Lỗi Bản Quyền"):
                    continue
                img = self.get_item_path(self.tbl_i2v.item(r, 2))
                prompt = cell_text(3)
                ratio = cell_text(4) or "9:16"
                strip_logo = True
                upscale = False
                meta = self.tbl_i2v.item(r, 0).data(Qt.UserRole + 1) if self.tbl_i2v.item(r, 0) else None
                if not isinstance(meta, dict):
                    meta = self.task_shopee_map.get(cell_text(6))
                shopee_item_id = ""
                shopee_market = ""
                shopee_name = ""
                shopee_image_url = ""
                if isinstance(meta, dict):
                    shopee_item_id = meta.get("item_id", "")
                    shopee_market = meta.get("market", "")
                    shopee_name = meta.get("name", "")
                    shopee_image_url = meta.get("image_url", "")

                i2v_rows.append({
                    "start_image": img,
                    "prompt": prompt,
                    "aspect_ratio": ratio,
                    "strip_logo": strip_logo,
                    "upscale_1080p": upscale,
                    "status": status,
                    "shopee_item_id": shopee_item_id,
                    "shopee_market": shopee_market,
                    "shopee_name": shopee_name,
                    "shopee_image_url": shopee_image_url
                })

            # Table 2: Start/End
            se_rows = []

            session_data = {
                "i2v": i2v_rows,
                "se": se_rows,
                # Các tuỳ chọn khác nằm ở shopee_db_settings.json (xem save_all_settings);
                # file này chỉ giữ danh sách hàng chờ và 3 mục gắn liền với phiên làm việc.
                "output_dir": self.txt_output.text(),
                "naming_mode": self.combo_naming.currentText(),
                "duration": self.combo_duration.currentText() if hasattr(self, 'combo_duration') else "8s (Chuẩn 1.5.5)"
            }
            with open("veo3_session.json", "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print("Error saving session:", e)

    def load_session(self):
        if not os.path.exists("veo3_session.json"):
            self.add_i2v_row()
            return
            
        try:
            with open("veo3_session.json", "r", encoding="utf-8") as f:
                session_data = json.load(f)
                
            # 3 mục dưới đây do shopee_db_settings.json quản lý và đã được nạp lúc dựng
            # giao diện. Chỉ lấy từ session khi file cài đặt chưa có key tương ứng
            # (lần đầu sau khi nâng cấp), để không mất lựa chọn cũ của người dùng.
            saved_out = session_data.get("output_dir")
            if saved_out and "seedvis_out_dir" not in self.shopee_settings:
                self.txt_output.setText(saved_out)

            saved_naming = session_data.get("naming_mode")
            if saved_naming and "seedvis_naming" not in self.shopee_settings:
                self.combo_naming.setCurrentText(saved_naming)

            saved_dur = session_data.get("duration")
            if saved_dur and hasattr(self, 'combo_duration') and "seedvis_total_dur" not in self.shopee_settings:
                self.combo_duration.setCurrentText(saved_dur)

            # Các tuỳ chọn Shopee đã được nạp từ shopee_db_settings.json lúc dựng giao diện

            # Load I2V Table: cấp phát đủ số dòng một lần (insertRow từng dòng rất chậm với hàng nghìn dòng)
            i2v_rows = session_data.get("i2v", [])
            self.tbl_i2v.setUpdatesEnabled(False)
            self.tbl_i2v.setSortingEnabled(False)
            self.tbl_i2v.setRowCount(0)
            self.tbl_i2v.setRowCount(len(i2v_rows))
            has_checked = False
            for r, row_data in enumerate(i2v_rows):
                item_select = QTableWidgetItem()
                item_select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                shopee_iid = row_data.get("shopee_item_id")
                start_image = row_data.get("start_image", "")
                task_id_new = str(uuid.uuid4())
                status_str = row_data.get("status", "")
                
                # Mặc định tích chọn các dòng chưa hoàn thành để sẵn sàng chạy tiếp
                is_done = (status_str == "Hoàn thành")
                chk_state = Qt.Unchecked if is_done else Qt.Checked
                item_select.setCheckState(chk_state)
                if chk_state == Qt.Checked:
                    has_checked = True

                if shopee_iid:
                    image_url = row_data.get("shopee_image_url", "")
                    meta = {
                        "item_id": shopee_iid,
                        "market": row_data.get("shopee_market", "PH"),
                        "name": row_data.get("shopee_name", ""),
                        "image_url": image_url,
                        # Chỉ tải ảnh on-demand được khi session có lưu URL ảnh (session bản cũ không lưu)
                        "is_lazy_shopee": bool(image_url)
                    }
                    item_select.setData(Qt.UserRole + 1, meta)
                    self.task_shopee_map[task_id_new] = dict(meta)
                    if not image_url and start_image.startswith("[Shopee]"):
                        status_str = "Lỗi: Thiếu URL ảnh (lấy lại SP từ DB)"

                self.tbl_i2v.setItem(r, 0, item_select)

                self.tbl_i2v.setItem(r, 1, QTableWidgetItem(str(r + 1)))
                self.tbl_i2v.setItem(r, 2, self.make_path_item(start_image))
                self.tbl_i2v.setItem(r, 3, QTableWidgetItem(row_data.get("prompt", "")))
                self.tbl_i2v.setItem(r, 4, QTableWidgetItem(row_data.get("aspect_ratio", "9:16")))

                self.tbl_i2v.setItem(r, 5, QTableWidgetItem(status_str))
                self.tbl_i2v.setItem(r, 6, QTableWidgetItem(task_id_new))
            self.tbl_i2v.setUpdatesEnabled(True)
            if hasattr(self, 'header_checkbox') and has_checked:
                self.header_checkbox.setChecked(True)

            # Load SE Table (Disabled)
            self.tbl_se.setRowCount(0)
                
            if self.tbl_i2v.rowCount() == 0:
                self.add_i2v_row()
        except Exception as e:
            print("Error loading session:", e)
            self.tbl_i2v.setUpdatesEnabled(True)
            self.add_i2v_row()



    def load_accounts_pool(self):
        with _accounts_file_lock:
            if os.path.exists("veo3_accounts.json"):
                try:
                    with open("veo3_accounts.json", "r", encoding="utf-8") as f:
                        self.accounts_pool = json.load(f)
                except Exception as e:
                    print("Error loading accounts pool:", e)
                    if not hasattr(self, 'accounts_pool') or self.accounts_pool is None:
                        self.accounts_pool = []
            else:
                self.accounts_pool = []

        # Đồng bộ hóa cờ Unlimited & slots cho các tài khoản trong pool
        for acc in self.accounts_pool:
            is_un = acc.get("is_unlimited", False) or "unlimited" in str(acc.get("plan", "")).lower() or int(acc.get("veo3_unlimited_threads", 0) or 0) > 0
            if is_un:
                acc["is_unlimited"] = True
                acc["max_slots"] = int(acc.get("max_slots") or acc.get("veo3_unlimited_threads") or 5)
                if not acc.get("plan"):
                    acc["plan"] = "Unlimited 5"
            else:
                acc["is_unlimited"] = False
                acc["max_slots"] = int(acc.get("max_slots") or 1)
            acc["active_slots"] = 0
            acc["in_use"] = False

        self.update_accounts_label()

    def update_accounts_label(self):
        count = len(self.accounts_pool)
        unlimited_count = 0
        total_slots = 0
        for acc in self.accounts_pool:
            is_un = acc.get("is_unlimited", False) or "unlimited" in str(acc.get("plan", "")).lower() or int(acc.get("veo3_unlimited_threads", 0) or 0) > 0 or ("5" in str(acc.get("plan", "")))
            slots = int(acc.get("max_slots") or acc.get("veo3_unlimited_threads") or (5 if is_un else 1))
            if is_un:
                unlimited_count += 1
            if not acc.get("permanent_exhausted"):
                total_slots += slots

        if unlimited_count > 0:
            self.lbl_accounts_count.setText(f"{count} tài khoản ({unlimited_count} Unlimited 5 - Tối đa {total_slots} luồng song song)")
        else:
            self.lbl_accounts_count.setText(f"{count} tài khoản ({total_slots} luồng song song)")

    def set_max_threads_from_pool(self):
        # Tính tổng số luồng song song từ pool (Unlimited 5 có 5 slots/acc, acc thường 1 slot/acc)
        available_accs = [acc for acc in self.accounts_pool if not acc.get("permanent_exhausted")]
        total_threads = sum(int(acc.get("max_slots") or (5 if acc.get("is_unlimited") else 1)) for acc in available_accs)
        if total_threads < 1:
            total_threads = 1
        val = min(100, max(1, total_threads))
        self.spin_threads.setValue(val)
        self.log(f"[Cấu hình] Đã tự động đặt {val} luồng chạy song song ({len(available_accs)} tài khoản, tổng {val} slots trong Pool).")

    def open_account_manager_dialog(self):
        dlg = AccountManagerDialog(self, self.accounts_pool, on_pool_updated=self.on_pool_updated_from_dialog)
        dlg.exec()

    def on_pool_updated_from_dialog(self, new_pool):
        self.accounts_pool = new_pool
        self.update_accounts_label()
        self.log(f"[Pool] Đã cập nhật lại danh sách tài khoản ({len(self.accounts_pool)} tài khoản).")

    def clear_accounts_pool(self):
        reply = QMessageBox.warning(
            self, 
            "Cảnh báo", 
            "Bạn có chắc chắn muốn xóa toàn bộ danh sách tài khoản?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.accounts_pool = []
            if os.path.exists("veo3_accounts.json"):
                try:
                    os.remove("veo3_accounts.json")
                except Exception:
                    pass
            self.update_accounts_label()
            QMessageBox.information(self, "Thành công", "Đã xóa toàn bộ tài khoản.")

if __name__ == "__main__":
    # Các file dữ liệu (veo3_accounts.json, veo3_session.json, logs.txt) dùng đường dẫn tương đối
    os.chdir(APP_DIR)
    app = QApplication(sys.argv)

    creds = get_registry_credentials()

    window = VeoLiteApp(creds)
    _main_window = window
    window.show()

    # Tự động bắt đầu chạy queue sau khi giao diện và session đã dựng xong nếu có cờ --auto-start hoặc --run
    if "--auto-start" in sys.argv or "--run" in sys.argv:
        QTimer.singleShot(2500, window.start_queue)

    sys.exit(app.exec())
