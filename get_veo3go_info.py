"""Tool lấy email và license key của Veo3Go đang chạy trên máy này (đọc Registry HKCU).

Chạy:  python get_veo3go_info.py          -> in ra màn hình
       python get_veo3go_info.py --json   -> xuất JSON
       python get_veo3go_info.py --dump   -> liệt kê toàn bộ giá trị Registry của Veo3Go (để debug)
"""
import sys
import json
import winreg

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# (khóa license, tên value key, khóa email, [tên value email])
CANDIDATES = [
    (r"Software\Veo3Go\Veo3 Go\license", "key", r"Software\Veo3Go\Veo3 Go", ["last_email_veo3", "activation/last_email"]),
    (r"Software\Nhungoc\Veo3 Client\license", "key", r"Software\Nhungoc\Veo3 Client\account", ["last_email", "email"]),
    (r"Software\Nhungoc\Nhungoc Video Generator\license", "key", r"Software\Nhungoc\Nhungoc Video Generator", ["last_email_veo3", "last_email"]),
    (r"Software\NhanLyVeo3Gen\NhanLy Veo3Gen\license", "key", r"Software\NhanLyVeo3Gen\NhanLy Veo3Gen", ["last_email_veo3"]),
    (r"Software\GKTech\Veo3HubClient", "api_key", r"Software\GKTech\Veo3HubClient", ["activation_email"]),
]


def _to_str(v):
    if isinstance(v, bytes):
        for enc in ("utf-8", "utf-16-le"):
            try:
                return v.decode(enc).strip("\x00 \r\n")
            except Exception:
                pass
        return v.hex()
    return str(v).strip()


def _read(path, name):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            v, _ = winreg.QueryValueEx(k, name)
            return _to_str(v) if v is not None else ""
    except OSError:
        return ""


def get_all():
    results = []
    for lic_path, lic_name, em_path, em_names in CANDIDATES:
        key = _read(lic_path, lic_name)
        if not key:
            continue
        email = ""
        for n in em_names:
            email = _read(em_path, n)
            if email:
                break
        results.append({"registry": lic_path, "email": email, "key": key})
    return results


def dump(path=r"Software\Veo3Go", depth=0):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            print("  " * depth + "[" + path + "]")
            i = 0
            while True:
                try:
                    n, v, _ = winreg.EnumValue(k, i)
                    print("  " * (depth + 1) + f"{n} = {_to_str(v)}")
                    i += 1
                except OSError:
                    break
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                    dump(path + "\\" + sub, depth + 1)
                    i += 1
                except OSError:
                    break
    except OSError:
        print(f"Không tìm thấy HKCU\\{path}")


def main():
    if "--dump" in sys.argv:
        dump()
        return
    res = get_all()
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    if not res:
        print("Không tìm thấy license Veo3Go trong Registry. Thử: python get_veo3go_info.py --dump")
        return
    for r in res:
        print(f"Nguồn : HKCU\\{r['registry']}")
        print(f"Email : {r['email'] or '(không có)'}")
        print(f"Key   : {r['key']}\n")


if __name__ == "__main__":
    main()
