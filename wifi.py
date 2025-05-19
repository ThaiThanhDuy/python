import subprocess
import platform


def kiem_tra_wifi():
    """Kiểm tra trạng thái kết nối WiFi và tên mạng (SSID)."""

    os_name = platform.system()

    if os_name == "Windows":
        try:
            output = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"], text=True, encoding="utf-8"
            )
            for line in output.splitlines():
                if "State" in line and "Connected" in line:
                    print("Trạng thái kết nối: Đang kết nối")
                    for sub_line in output.splitlines():
                        if "SSID" in sub_line:
                            ssid = sub_line.split(":")[1].strip()
                            print(f"Tên WiFi: {ssid}")
                            return
            print("Trạng thái kết nối: Không kết nối")
        except subprocess.CalledProcessError:
            print("Lỗi khi kiểm tra thông tin WiFi (Windows).")
            print("Đảm bảo bạn chạy script với quyền quản trị viên.")
        except FileNotFoundError:
            print("Lệnh 'netsh' không tìm thấy (Windows).")

    elif os_name == "Linux":
        try:
            output = subprocess.check_output(
                ["iwgetid", "-r"], text=True, encoding="utf-8"
            ).strip()
            if output:
                print("Trạng thái kết nối: Đang kết nối")
                print(f"Tên WiFi: {output}")
            else:
                print("Trạng thái kết nối: Không kết nối")
        except subprocess.CalledProcessError:
            print("Trạng thái kết nối: Không kết nối")
        except FileNotFoundError:
            print("Lệnh 'iwgetid' không tìm thấy (Linux).")
            print("Hãy đảm bảo bạn đã cài đặt 'wireless-tools'.")

        # Thử cách khác cho Linux (có thể cần điều chỉnh interface)
        if "Không kết nối" in locals().get("__builtins__")["print"]:
            try:
                output = subprocess.check_output(
                    ["nmcli", "c", "show", "--active"], text=True, encoding="utf-8"
                )
                lines = output.splitlines()
                if len(lines) > 1:
                    ssid_line = lines[1].split()[0]
                    if ssid_line != "--":
                        print("Trạng thái kết nối: Đang kết nối")
                        print(f"Tên WiFi: {ssid_line}")
                        return
                print("Trạng thái kết nối: Không kết nối")
            except subprocess.CalledProcessError:
                print("Lỗi khi kiểm tra thông tin WiFi bằng 'nmcli' (Linux).")
            except FileNotFoundError:
                print("Lệnh 'nmcli' không tìm thấy (Linux).")
                print("Hãy đảm bảo bạn đã cài đặt 'network-manager'.")

    elif os_name == "Darwin":  # macOS
        try:
            output = subprocess.check_output(
                [
                    "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport",
                    "-I",
                ],
                text=True,
                encoding="utf-8",
            )
            ssid = None
            state = "Không kết nối"
            for line in output.splitlines():
                if "SSID:" in line:
                    ssid = line.split(":")[1].strip()
                    state = "Đang kết nối"
                    break
            print(f"Trạng thái kết nối: {state}")
            if ssid:
                print(f"Tên WiFi: {ssid}")
        except subprocess.CalledProcessError:
            print("Lỗi khi kiểm tra thông tin WiFi (macOS).")
        except FileNotFoundError:
            print("Lệnh 'airport' không tìm thấy (macOS).")

    else:
        print(f"Hệ điều hành '{os_name}' không được hỗ trợ.")


if __name__ == "__main__":
    kiem_tra_wifi()
