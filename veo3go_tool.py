"""Veo3Go tool: 2 chức năng
  1) info : lấy thông tin đầy đủ của máy đang chạy (email, key, Hardware ID, CPU ID, Mainboard UUID, OS...)
  2) add  : tự động thêm tài khoản (lấy từ máy này) vào veo3_accounts.json của phần mềm

Chạy:
  python veo3go_tool.py info [--json]
  python veo3go_tool.py add  [--file E:\\vanthe_video\\veo3_accounts.json] [--dry-run]
      Ghi đè thủ công nếu cần: --email X --key Y --hwid H --cpu C --mb M
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import winreg

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
DEFAULT_FILE = os.path.join(_BASE_DIR, "veo3_accounts.json")

LICENSE_CANDIDATES = [
    (r"Software\Veo3Go\Veo3 Go\license", "key", r"Software\Veo3Go\Veo3 Go", ["last_email_veo3", "activation/last_email"]),
    (r"Software\Nhungoc\Veo3 Client\license", "key", r"Software\Nhungoc\Veo3 Client\account", ["last_email", "email"]),
    (r"Software\Nhungoc\Nhungoc Video Generator\license", "key", r"Software\Nhungoc\Nhungoc Video Generator", ["last_email_veo3", "last_email"]),
    (r"Software\NhanLyVeo3Gen\NhanLy Veo3Gen\license", "key", r"Software\NhanLyVeo3Gen\NhanLy Veo3Gen", ["last_email_veo3"]),
    (r"Software\GKTech\Veo3HubClient", "api_key", r"Software\GKTech\Veo3HubClient", ["activation_email"]),
]
HW_REG_PATHS = [
    r"Software\ElevenLabs\ElevenLabs TTS Client\system",
    r"Software\Veo3Go\Veo3 Go\system",
    r"Software\Veo3Go\Veo3 Go",
]


# ---------- tiện ích ----------
def _to_str(v):
    if isinstance(v, bytes):
        for enc in ("utf-8", "utf-16-le"):
            try:
                return v.decode(enc).strip("\x00 \r\n")
            except Exception:
                pass
        return v.hex()
    return str(v).strip()


def _reg(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return _to_str(v) if v is not None else ""
    except OSError:
        return ""


def _run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL, timeout=20).strip()
    except Exception:
        return ""


def _wmic_first(query, skip):
    lines = [l.strip() for l in _run(query).splitlines() if l.strip() and skip.lower() not in l.lower()]
    return lines[0] if lines else ""


def _ps(expr):
    return _run(f'powershell -NoProfile -Command "{expr}"')


# ---------- lấy dữ liệu ----------
def get_license():
    """Trả về (email, key, nguồn registry)."""
    for lic_path, lic_name, em_path, em_names in LICENSE_CANDIDATES:
        key = _reg(lic_path, lic_name)
        if key:
            email = next((e for e in (_reg(em_path, n) for n in em_names) if e), "")
            return email, key, lic_path
    return "", "", ""


def get_hardware():
    """Trả về dict hardware_id, cpu_id, mainboard_uuid, nguồn. Ưu tiên cache Registry của Veo3Go."""
    for p in HW_REG_PATHS:
        hw, cpu, mb = _reg(p, "hardware_id"), _reg(p, "cached_cpu_id"), _reg(p, "cached_mainboard_uuid")
        if hw and cpu and mb:
            return {"hardware_id": hw, "cpu_id": cpu, "mainboard_uuid": mb, "source": "registry:" + p}

    cpu = _wmic_first("wmic cpu get ProcessorId", "ProcessorId") or _ps("(Get-CimInstance Win32_Processor).ProcessorId")
    mb = (_wmic_first("wmic csproduct get uuid", "UUID") or _ps("(Get-CimInstance Win32_ComputerSystemProduct).UUID")
          or _wmic_first("wmic baseboard get serialnumber", "SerialNumber"))
    cpu = cpu or "BFEBFBFF000906EA"
    mb = mb or "Default-MB-UUID"
    hw = hashlib.sha256(f"{cpu}|{mb}".encode()).hexdigest()
    return {"hardware_id": hw, "cpu_id": cpu, "mainboard_uuid": mb, "source": "wmi (tính trực tiếp)"}


def get_system_info():
    info = {
        "computer_name": platform.node(),
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "cpu_name": _wmic_first("wmic cpu get Name", "Name") or _ps("(Get-CimInstance Win32_Processor).Name"),
        "bios_serial": _wmic_first("wmic bios get serialnumber", "SerialNumber") or _ps("(Get-CimInstance Win32_BIOS).SerialNumber"),
        "baseboard": (_wmic_first("wmic baseboard get Manufacturer,Product", "Manufacturer")
                      or _ps("$b=Get-CimInstance Win32_BaseBoard; $b.Manufacturer+' '+$b.Product")),
        "ram_gb": "",
        "gpu": _ps("(Get-CimInstance Win32_VideoController | Select -First 1).Name"),
        "mac": _ps("(Get-NetAdapter -Physical | Where Status -eq 'Up' | Select -First 1).MacAddress"),
    }
    ram = _ps("[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)")
    info["ram_gb"] = ram
    return info


def collect():
    email, key, src = get_license()
    hw = get_hardware()
    return {
        "email": email,
        "api_key": key,
        "license_source": "HKCU\\" + src if src else "",
        **hw,
        "system": get_system_info(),
    }


# ---------- chức năng 1 ----------
def cmd_info(args):
    d = collect()
    if args.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return
    print("=== TÀI KHOẢN VEO3GO ===")
    print(f"Email          : {d['email'] or '(không tìm thấy)'}")
    print(f"Key            : {d['api_key'] or '(không tìm thấy)'}")
    print(f"Nguồn license  : {d['license_source'] or '-'}")
    print("\n=== ĐỊNH DANH PHẦN CỨNG ===")
    print(f"Hardware ID    : {d['hardware_id']}")
    print(f"CPU ID         : {d['cpu_id']}")
    print(f"Mainboard UUID : {d['mainboard_uuid']}")
    print(f"Nguồn          : {d['source']}")
    print("\n=== THÔNG TIN MÁY ===")
    for k, v in d["system"].items():
        print(f"{k:<15}: {v or '-'}")


# ---------- chức năng 2 ----------
def _new_entry(email, key, hw, cpu, mb):
    return {
        "email": email, "api_key": key, "device_key": "",
        "hardware_id": hw, "cpu_id": cpu, "mainboard_uuid": mb,
        "is_unlimited": False, "max_slots": 1, "active_slots": 0, "videos_today": 0,
        "plan": "", "status": "Chưa kiểm tra",
        "exhausted": False, "permanent_exhausted": False, "in_use": False,
        "cooldown_until": 0, "last_used_time": 0,
    }


def _app_running():
    out = _run('powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name like \'python%\'\\" | '
               'Where CommandLine -like \'*AutoPromt*\' | Select -ExpandProperty ProcessId"')
    return bool(out.strip())


def _upsert(path, email, key, hw, cpu, mb, dry_run=False):
    """Thêm hoặc cập nhật 1 tài khoản vào file accounts."""
    pool = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                pool = json.load(f)
            if not isinstance(pool, list):
                sys.exit("File accounts không phải danh sách JSON, dừng để tránh hỏng dữ liệu.")
        except json.JSONDecodeError:
            sys.exit(f"{path} bị lỗi JSON, dừng để tránh ghi đè.")

    existing = next((a for a in pool if a.get("email", "").lower() == email.lower() or a.get("api_key") == key), None)
    if existing:
        existing.update({"email": email, "api_key": key, "hardware_id": hw, "cpu_id": cpu, "mainboard_uuid": mb})
        action = "CẬP NHẬT tài khoản đã có"
    else:
        pool.append(_new_entry(email, key, hw, cpu, mb))
        action = "THÊM tài khoản mới"

    print(f"{action}: {email}\n  key={key}\n  hardware_id={hw}\n  cpu_id={cpu}\n  mainboard_uuid={mb}")
    if dry_run:
        print("\n[dry-run] Chưa ghi file.")
        return

    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=4)
    os.replace(tmp, path)
    print(f"\nĐã ghi {path} (backup: {path}.bak). Tổng {len(pool)} tài khoản.")
    if _app_running():
        print("CẢNH BÁO: AutoPromt đang chạy, nó chỉ đọc file lúc khởi động và có thể ghi đè lại. "
              "Hãy tắt rồi mở lại phần mềm để nhận tài khoản mới.")


def cmd_add(args):
    d = collect()
    email = args.email or d["email"]
    key = args.key or d["api_key"]
    if not email or not key:
        sys.exit("Không lấy được email/key. Truyền thủ công bằng --email và --key.")
    _upsert(args.file, email, key, args.hwid or d["hardware_id"], args.cpu or d["cpu_id"],
            args.mb or d["mainboard_uuid"], args.dry_run)


DEFAULT_EXPORT = os.path.join(_BASE_DIR, "veo3_account_export.json")


def cmd_export(args):
    """Xuất tài khoản của máy này ra file để mang sang máy khác."""
    d = collect()
    if not d["email"] or not d["api_key"]:
        sys.exit("Không lấy được email/key trên máy này, không có gì để xuất.")
    data = {
        "email": d["email"], "api_key": d["api_key"],
        "hardware_id": d["hardware_id"], "cpu_id": d["cpu_id"], "mainboard_uuid": d["mainboard_uuid"],
        "computer_name": d["system"]["computer_name"],
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Đã xuất tài khoản {data['email']} ra: {args.out}")
    print("Copy file này sang máy kia rồi chạy: Veo3go-info.exe import <file>")
    print("LƯU Ý: file chứa license key, không chia sẻ công khai.")


def cmd_import(args):
    """Nạp file đã xuất (1 tài khoản hoặc danh sách) vào veo3_accounts.json của máy này."""
    try:
        with open(args.infile, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"Không đọc được {args.infile}: {e}")
    items = data if isinstance(data, list) else [data]
    n = 0
    for it in items:
        email, key = it.get("email", ""), it.get("api_key", "")
        if not email or not key:
            print("Bỏ qua 1 mục thiếu email/api_key.")
            continue
        # Giữ nguyên thông tin phần cứng của máy đã đăng ký tài khoản (lấy từ file)
        _upsert(args.file, email, key, it.get("hardware_id", ""), it.get("cpu_id", ""),
                it.get("mainboard_uuid", ""), args.dry_run)
        n += 1
    print(f"\nXử lý {n} tài khoản.")


def _ask_path(prompt, default):
    s = input(f"{prompt} [{default}]: ").strip().strip('"')
    return s or default


def interactive():
    """Menu cho trường hợp bấm đúp file .exe (không có tham số)."""
    ns = argparse.Namespace(json=False, file=DEFAULT_FILE, dry_run=False, email=None, key=None, hwid=None, cpu=None, mb=None)
    while True:
        print("\n===== VEO3GO INFO =====")
        print("1. Xem thông tin máy + tài khoản")
        print("2. Xuất tài khoản ra file (để mang sang máy khác)")
        print("3. Nạp tài khoản từ file vào veo3_accounts.json")
        print("4. Thêm tài khoản của máy NÀY vào veo3_accounts.json")
        print("0. Thoát")
        c = input("Chọn: ").strip()
        print()
        try:
            if c == "1":
                cmd_info(ns)
            elif c == "2":
                cmd_export(argparse.Namespace(out=_ask_path("File xuất", DEFAULT_EXPORT)))
            elif c == "3":
                cmd_import(argparse.Namespace(infile=_ask_path("File cần nạp", DEFAULT_EXPORT),
                                              file=DEFAULT_FILE, dry_run=False))
            elif c == "4":
                ns.dry_run = False
                cmd_add(ns)
            elif c == "0":
                return
        except SystemExit as e:
            print(e)


def main():
    if len(sys.argv) == 1 and getattr(sys, "frozen", False):
        interactive()
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("info", help="lấy thông tin đầy đủ của máy")
    p1.add_argument("--json", action="store_true")
    p1.set_defaults(fn=cmd_info)
    p2 = sub.add_parser("add", help="thêm tài khoản của máy này vào veo3_accounts.json")
    p2.add_argument("--file", default=DEFAULT_FILE)
    p2.add_argument("--dry-run", action="store_true")
    for n in ("email", "key", "hwid", "cpu", "mb"):
        p2.add_argument("--" + n)
    p2.set_defaults(fn=cmd_add)
    p3 = sub.add_parser("export", help="xuất tài khoản của máy này ra file")
    p3.add_argument("--out", default=DEFAULT_EXPORT)
    p3.set_defaults(fn=cmd_export)
    p4 = sub.add_parser("import", help="nạp file đã xuất vào veo3_accounts.json")
    p4.add_argument("infile", nargs="?", default=DEFAULT_EXPORT)
    p4.add_argument("--file", default=DEFAULT_FILE)
    p4.add_argument("--dry-run", action="store_true")
    p4.set_defaults(fn=cmd_import)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
