import logging
import threading
import time
from typing import Optional
import can

# Cấu hình logging hệ thống chuyên dụng
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("Linux_USB_CAN_Driver")


class WaveshareUsbCanLinuxDriver:
    """Lớp điều khiển thiết bị USB-CAN-A Waveshare tối ưu cho môi trường Linux.

    Quản lý luồng Input -> Process -> Output chặt chẽ, ngăn ngừa Undefined Behavior.
    """

    def __init__(self, port: str = "/dev/ttyUSB0", bitrate: int = 500000) -> None:
        self.port: str = port
        self.bitrate: int = bitrate
        self.bus: Optional[can.BusABC] = None
        self._is_running: bool = False
        self._rx_thread: Optional[threading.Thread] = None

    def initialize_bus(self) -> bool:
        """Khởi tạo kết nối tới phần cứng CAN thông qua driver Serial trên Linux.

        Returns:
            bool: Trạng thái trả về True nếu kết nối thành công, False nếu lỗi.
        """
        try:
            # Giao tiếp qua tầng SLCAN/Serial tích hợp của python-can tương thích Linux
            self.bus = can.Bus(
                interface="serial",
                channel=self.port,
                bitrate=self.bitrate,
                timeout=0.1,
            )
            logger.info(
                f"Successfully initialized CAN bus on Linux port {self.port} at {self.bitrate} bps."
            )
            return True
        except (can.CanError, ValueError, FileNotFoundError) as err:
            logger.error(f"Linux CAN bus initialization failed: {str(err)}")
            self.bus = None
            return False

    def start_receive_loop(self) -> None:
        """Kích hoạt luồng nhận dữ liệu không đồng bộ chuyên biệt."""
        if self.bus is None:
            logger.error("Cannot start Rx loop. Bus interface is offline.")
            return

        self._is_running = True
        self._rx_thread = threading.Thread(target=self._receive_handler, daemon=True)
        self._rx_thread.start()
        logger.info("Asynchronous Linux Rx thread spawned.")

    def _receive_handler(self) -> None:
        """Vòng lặp nhận bản tin, cô lập lỗi ngoại lệ tại tầng phần cứng."""
        while self._is_running:
            if self.bus is None:
                break
            try:
                message: Optional[can.Message] = self.bus.recv(timeout=0.5)
                if message is not None:
                    self.process_incoming_frame(message)
            except can.CanError as err:
                logger.error(f"Hardware-level frame reception error: {str(err)}")

    def process_incoming_frame(self, message: can.Message) -> None:
        """Bộ xử lý dữ liệu đầu vào (Input Process)."""
        can_id: int = message.arbitration_id
        data_bytes: bytearray = message.data
        is_extended: bool = message.is_extended_id
        dlc: int = message.dlc

        hex_data: str = " ".join(f"{b:02X}" for b in data_bytes)
        logger.info(
            f"Rx -> ID: 0x{can_id:X} | Ext: {is_extended} | DLC: {dlc} | Data: [{hex_data}]"
        )

    def transmit_frame(
        self, can_id: int, data: list, is_extended: bool = False
    ) -> bool:
        """Truyền bản tin dữ liệu xuống mạng CAN (Output Process).

        Returns:
            bool: Kết quả logic xác nhận việc truyền tin thành công.
        """
        if self.bus is None:
            logger.error("Transmission blocked: Device offline.")
            return False

        if len(data) > 8:
            logger.error("Invalid Frame: CAN 2.0B payload must be <= 8 bytes.")
            return False

        try:
            message = can.Message(
                arbitration_id=can_id,
                data=data,
                is_extended_id=is_extended,
                is_remote_frame=False,
            )
            self.bus.send(message, timeout=0.2)
            logger.info(f"Tx -> ID: 0x{can_id:X} | Data: {data}")
            return True
        except can.CanError as err:
            logger.error(f"Transmission error on frame 0x{can_id:X}: {str(err)}")
            return False

    def shutdown(self) -> None:
        """Giải phóng tài nguyên hệ thống và đóng cổng luồng an toàn."""
        logger.info("Initiating graceful shutdown procedure...")
        self._is_running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)

        if self.bus is not None:
            self.bus.shutdown()
            self.bus = None
        logger.info("Linux CAN driver detached successfully.")


# --- Mock Function / Linux Production Verification ---
if __name__ == "__main__":
    # Cấu hình cổng mặc định cho Linux (Kiểm tra bằng 'ls /dev/ttyUSB*' để xác định chính xác số node)
    LINUX_PORT: str = "/dev/ttyUSB0"
    BITRATE_500K: int = 500000

    can_driver = WaveshareUsbCanLinuxDriver(port=LINUX_PORT, bitrate=BITRATE_500K)

    if can_driver.initialize_bus():
        can_driver.start_receive_loop()

        # Thực thi bản tin kiểm thử (Mock Test)
        # ID: 0x3F4, Data: [0x01, 0x02, 0x03, 0x04]
        mock_payload = [0x01, 0x02, 0x03, 0x04]
        can_driver.transmit_frame(can_id=0x3F4, data=mock_payload, is_extended=False)

        # Duy trì giám sát luồng dữ liệu liên tục trong 5 giây
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            logger.warning("Execution interrupted by operator.")
        finally:
            can_driver.shutdown()
    else:
        logger.critical("Failed to run CAN application on target system.")
