import sys
import serial
import serial.tools.list_ports
import math
from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QGroupBox, QComboBox
from PySide6.QtWidgets import QWidget, QPushButton, QVBoxLayout, QFrame, QHBoxLayout
from PySide6.QtWidgets import QProgressBar, QSlider, QLineEdit, QMessageBox
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QIcon, QBrush, QLinearGradient, QIntValidator

# Thiết lập mã hóa UTF-8 cho đầu ra
sys.stdout.reconfigure(encoding='utf-8')

# Tạo lớp cho giao diện mới
class NewWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Khai báo các biến toàn cục
        self.L1 = 150
        self.L2 = 150
        self.L3 = 160
        self.L4 = 120
        
        # Biến để kiểm tra xem đã hiện thông báo hay chưa
        self.warning_connect = False  # False = chưa có cảnh báo
        self.is_connected = False  # Ban đầu chưa kết nối
        
        # Định nghĩa hàm create_label
        def create_label(text, x, y, width, height, font_size, parent):
            label = QLabel(text, parent)
            label.setGeometry(x, y, width, height)
            label.setStyleSheet(f"""
                font-size: {font_size}px;
                font-family: Times New Roman;
                font-weight: bold;
                color: black;
            """)
            return label
        
        def create_group_box(title, x, y, width, height, parent):
            group_box = QGroupBox(title, parent)
            group_box.setGeometry(x, y, width, height)
            group_box.setStyleSheet("""
                font-size: 24px; 
                font-family: Times New Roman; 
                font-weight: bold;
            """)
            return group_box
        
        self.setWindowTitle("GIAO DIỆN ĐIỀU KHIỂN")
        self.resize(1200, 800)
        
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        central_widget.setStyleSheet("background-color: white;") 
        
        # Tạo GroupBox trống
        create_group_box(            "CONECT",  20,  10, 300, 150, central_widget)
        create_group_box("FORWARD KINEMATICS", 330,  10, 380, 460, central_widget)
        create_group_box(  "CURRENT POSITION",  20, 170, 300, 300, central_widget)
        create_group_box("INVERSE KINEMATICS", 720,  10, 420, 350, central_widget)
        create_group_box(          "FUNCTION", 720, 370, 420, 100, central_widget)
        
        # ============ Thành phần trong GroupBox connect ==============
        create_label('PORT NAME:', 35, 50, 100, 12, 16, central_widget)
        
        # Tạo QComboBox cho danh sách Port Name
        self.combo_box_port = QComboBox(central_widget)  # Đảm bảo combo_box_port đã được khởi tạo
        self.combo_box_port.setGeometry(140, 48, 80, 20)
        self.update_ports()  # Gọi hàm cập nhật danh sách cổng COM sau khi đã khởi tạo combo_box_port
        
        # Tạo QLabel cho Baud Rate
        create_label('BAUD RATE:', 35, 88, 100, 12, 16, central_widget)
        
        # Tạo QComboBox cho danh sách Baud Rate
        self.combo_box_baud = QComboBox(central_widget)
        self.combo_box_baud.setGeometry(140, 86, 80, 20)
        self.combo_box_baud.addItems(["9600", "19200", "38400", "57600", "115200"])  # Thêm danh sách Baud Rate
        
        # Tạo ProgressBar
        self.progress_bar = QProgressBar(central_widget)
        self.progress_bar.setGeometry(43, 120, 250, 25)
        self.progress_bar.setValue(0)  # Bắt đầu với giá trị 0
        self.progress_bar.setTextVisible(False)
        
        # Tạo nút để connect vs reset
        self.connect_button = self.create_button('CONNECT', 226, 40, 85, 30, '#4fff4f', '#00dd00', self.start_progress, central_widget)
        self.connect_button.clicked.connect(self.connect_to_arduino)
        self.serial_connection = None  # Biến để lưu đối tượng serial connection
        self.reset_button = self.create_button('RESET', 226, 80, 85, 30, '#ff8080', '#df0000', self.start_progress, central_widget)
        self.reset_button.clicked.connect(self.disconnect_from_arduino)
        
        # Tạo QTimer để cập nhật thanh ProgressBar
        self.timer = QTimer(self)
        
        # ============= Thành phần trong GroupBox Forward Kinematic ===============
        self.theta_sliders = []
        self.theta_value_inputs = []
        self.theta_labels = ['Theta 1:', 'Theta 2:', 'Theta 3:', 'Theta 4:']
        
        # Tạo các slider và ô nhập cho theta
        for i, label_text in enumerate(self.theta_labels):
            self.create_theta_control(central_widget, label_text, i)

        # Tạo QLabel cho Theta và ô hiển thị giá trị
        create_label('Theta:', 350, 290, 250, 20, 20, central_widget)
        self.total_theta_input = self.create_QLineEdit('0', 640, 290, 50, 20, central_widget)
        
        # Tạo nút nhấn gửi góc FK cho arduino
        self.sendFK_button = self.create_button('SEND FK', 400, 325, 85, 30, '#4fff4f', '#00dd00', self.send_FK, central_widget)
        
        # Tạo nút home reset các góc
        self.home_button = self.create_button('HOME', 555, 325, 85, 30, '#4fff4f', '#00dd00', self.home, central_widget)
        
        create_label('POSITION', 470, 365, 100, 20, 20, central_widget)
        # Tạo QLineEdit để hiển thị Px, Py, Pz
        self.Px_FK_label = self.create_QLineEdit( '430', 345, 430, 60, 20, central_widget)
        self.Py_FK_label = self.create_QLineEdit(   '0', 440, 430, 60, 20, central_widget)
        self.Pz_FK_label = self.create_QLineEdit( '150', 535, 430, 60, 20, central_widget)
        self.t_FK_label  = self.create_QLineEdit(   '0', 630, 430, 60, 20, central_widget)
        
        # Sử dụng hàm để tạo các QLabel
        create_label('Px', 365, 400, 50, 20, 20, central_widget)
        create_label('Py', 460, 400, 50, 20, 20, central_widget)
        create_label('Pz', 555, 400, 50, 20, 20, central_widget)
        create_label('Theta', 635, 400, 50, 20, 20, central_widget)
        
        # ================ Thành phần trong GroupBox Current Position ===============
        # Tạo QLabel cho các góc và vị trí hiện tại
        create_label( 'ANGLES', 125, 220, 80, 20, 20, central_widget)
        create_label('Theta 1',  25, 260, 65, 20, 20, central_widget)
        create_label('Theta 2', 100, 260, 65, 20, 20, central_widget)
        create_label('Theta 3', 175, 260, 65, 20, 20, central_widget)
        create_label('Theta 4', 250, 260, 65, 20, 20, central_widget)
        create_label('POSITION', 120, 350, 100, 20, 20, central_widget)
        create_label('Px', 70, 390, 50, 20, 20, central_widget)
        create_label('Py', 155, 390, 50, 20, 20, central_widget)
        create_label('Pz', 240, 390, 50, 20, 20, central_widget)
        
        # Tạo QLineEdit cho các góc và vị trí hiện tại
        self.t1_CURRENT = self.create_QLineEdit(  '0',  30, 300, 50, 20, central_widget)
        self.t2_CURRENT = self.create_QLineEdit(  '0', 105, 300, 50, 20, central_widget)
        self.t3_CURRENT = self.create_QLineEdit(  '0', 180, 300, 50, 20, central_widget)
        self.t4_CURRENT = self.create_QLineEdit(  '0', 255, 300, 50, 20, central_widget)
        self.Px_CURRENT = self.create_QLineEdit('430',  55, 420, 50, 20, central_widget)
        self.Py_CURRENT = self.create_QLineEdit(  '0', 140, 420, 50, 20, central_widget)
        self.Pz_CURRENT = self.create_QLineEdit('150', 225, 420, 50, 20, central_widget)

        # ============ Thành phần trong GroupBox Inverse Kinematics ==============
        # Tạo QLabel cho các góc và vị trí mong muốn
        create_label('POSITION',  870,  50, 120, 20, 20, central_widget)
        create_label(      'Px',  780,  80,  25, 20, 20, central_widget)
        create_label(      'Py',  870,  80,  25, 20, 20, central_widget)
        create_label(      'Pz',  960,  80,  50, 20, 20, central_widget)
        create_label(   'Theta', 1035,  80,  65, 20, 20, central_widget)
        create_label(  'ANGLES',  880, 160, 100, 20, 20, central_widget)
        create_label( 'Theta 1',  760, 190,  65, 20, 20, central_widget)
        create_label( 'Theta 2',  850, 190,  65, 20, 20, central_widget)
        create_label( 'Theta 3',  940, 190,  65, 20, 20, central_widget)
        create_label( 'Theta 4', 1030, 190,  65, 20, 20, central_widget)
        
        # Tạo QLineEdit cho các góc và vị trí mong muốn
        self.Px_IK_label = self.create_QLineEdit(  '0',  760, 110, 60, 20, central_widget)
        self.Py_IK_label = self.create_QLineEdit(  '0',  850, 110, 60, 20, central_widget)
        self.Pz_IK_label = self.create_QLineEdit(  '0',  940, 110, 60, 20, central_widget)
        self.t_IK_label  = self.create_QLineEdit(  '0', 1030, 110, 60, 20, central_widget)
        self.t1_IK_label = self.create_QLineEdit('430',  766, 220, 50, 20, central_widget)
        self.t2_IK_label = self.create_QLineEdit(  '0',  856, 220, 50, 20, central_widget)
        self.t3_IK_label = self.create_QLineEdit('150',  946, 220, 50, 20, central_widget)
        self.t4_IK_label = self.create_QLineEdit(  '0', 1036, 220, 50, 20, central_widget)
        
        # Tạo nút nhấn tính động học nghịch
        self.IK_button = self.create_button( 'CAL IK', 830, 310, 85, 30, '#4fff4f', '#00dd00', self.calculate_angles, central_widget)
        self.IK_button = self.create_button('SEND IK', 940, 310, 85, 30, '#4fff4f', '#00dd00', self.calculate_angles, central_widget)
        
        # Tạo QComboBox cho 2 bộ nghiệm
        self.combo_box_angles = QComboBox(central_widget)
        self.combo_box_angles.setGeometry(900, 265, 60, 20)
        self.combo_box_angles.addItems(["BN1", "BN2"])
        
        # Kết nối sự kiện thay đổi giá trị của QComboBox
        self.combo_box_angles.currentIndexChanged.connect(self.update_angles_display)
        
        # =============== Thành phần trong GroupBox Function ===============
        # Tạo 2 nút nhấn chuyển sao chép
        self.coppy_button = self.create_button('COPPY', 760, 420, 85, 30, '#4fff4f', '#00dd00', self.coppy_value, central_widget)
        self.suck_button = self.create_button( 'SUCK', 885, 420, 85, 30, '#4fff4f', '#00dd00', self.suck, central_widget)
        self.drop_button = self.create_button( 'DROP', 1010, 420, 85, 30, '#4fff4f', '#00dd00', self.drop, central_widget)
        
    def update_ports(self):
        """Cập nhật danh sách cổng COM có sẵn vào combo box"""
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]  # Lấy tên cổng
        self.combo_box_port.clear()  # Xóa danh sách hiện tại
        self.combo_box_port.addItems(port_list)  # Thêm cổng mới

    def create_theta_control(self, parent, label_text, index):
        # Tạo QLabel
        label = QLabel(label_text, parent)
        label.setGeometry(350, 45 + index * 60, 70, 20)
        label.setStyleSheet("""
            font-size: 20px;        
            font-family: Times New Roman;     
            font-weight: bold;      
            color: black;           
        """)
        
        # Tạo slider
        slider = QSlider(Qt.Horizontal, parent)
        slider.setGeometry(430, 45 + index * 60, 200, 20)
        slider.setRange(-90, 90)
        slider.setValue(0)
        slider.setTickInterval(10)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.valueChanged.connect(lambda value: self.update_value_input(value, index))
        
        # Tạo QLineEdit
        value_input = QLineEdit('0', parent)
        value_input.setGeometry(640, 45 + index * 60, 50, 20)
        value_input.setStyleSheet("""
            font-size: 20px;
            font-family: Times New Roman;
            font-weight: bold;
            color: black;
        """)
        value_input.setAlignment(Qt.AlignCenter) # căn giữa
        value_input.setValidator(QIntValidator(-90, 90, self))
        value_input.textChanged.connect(lambda text: self.update_slider_value(text, index))
        
        self.theta_sliders.append(slider)
        self.theta_value_inputs.append(value_input)
        
        self.display_ticks(parent, 45 + index * 60)

    def display_ticks(self, parent, y_position):
        for i in range(-90, 91, 30):
            label = QLabel(f'{i}°', parent)
            label.setStyleSheet("""
                font-size: 12px;
                font-family: Times New Roman;
                color: black;
            """)
            if(i < 0):  
                x_pos = 434 + int((i + 82) / 190 * 200)
            elif(i == 0):
                x_pos = 527
            elif(i > 0):
                x_pos = 429 + int((i + 92) / 192 * 200)
            label.setGeometry(x_pos, y_position + 20, 30, 20)

    def update_value_input(self, value, index):
        self.theta_value_inputs[index].setText(f'{value}')
        self.update_total_theta()

    def update_slider_value(self, text, index):
        if text:
            value = int(text)
            self.theta_sliders[index].setValue(value)
            self.update_total_theta()

    def update_total_theta(self):
        theta1 = int(self.theta_value_inputs[0].text())
        theta2 = int(self.theta_value_inputs[1].text())
        theta3 = int(self.theta_value_inputs[2].text())
        theta4 = int(self.theta_value_inputs[3].text())
        total = theta2 + theta3 + theta4
        self.total_theta_input.setText(str(total))
        
        t1 = math.radians(theta1)
        t2 = math.radians(theta2)
        t3 = math.radians(theta3)
        t4 = math.radians(theta4)
        
        t_FK  = t2+ t3 + t4
        self.Px_FK = math.cos(t1)*(self.L4*math.cos(t_FK) + self.L3*math.cos(t2+t3) + self.L2*math.cos(t2))
        self.Py_FK = math.sin(t1)*(self.L4*math.cos(t_FK) + self.L3*math.cos(t2+t3) + self.L2*math.cos(t2))
        self.Pz_FK = self.L4*math.sin(t_FK) + self.L3*math.sin(t2+t3) + self.L2*math.sin(t2) + self.L1
        self.t_FK  = round(math.degrees(t_FK))
        
        self.Px_FK_label.setText(f"{round(self.Px_FK, 2):.2f}")
        self.Py_FK_label.setText(f"{round(self.Py_FK, 2):.2f}")
        self.Pz_FK_label.setText(f"{round(self.Pz_FK, 2):.2f}")
        self.t_FK_label.setText(f"{round(self.t_FK, 2):.2f}")
        
    def connect_to_arduino(self):
        """Kết nối với Arduino qua cổng COM và Baud Rate đã chọn"""
        port_name = self.combo_box_port.currentText()
        baud_rate = int(self.combo_box_baud.currentText())
        self.timer.timeout.connect(self.update_progress_green)
        
        # Kiểm tra nếu thiếu thông tin thì hiển thị thông báo và không cho ProgressBar chạy
        if not port_name or not baud_rate:
            self.show_warning_message("Hãy chọn cổng COM và Baud Rate hợp lệ.")
            self.warning_displayed = True  # Đã hiện bảng cảnh báo
        
        if port_name and baud_rate:
            try:
                # Kiểm tra nếu đã có kết nối thì không kết nối lại
                if self.serial_connection is None or not self.serial_connection.is_open:
                    self.serial_connection = serial.Serial(port_name, int(baud_rate))
                    print(f"Đã kết nối thành công với Arduino qua {port_name} ở Baud Rate {baud_rate}")
                    self.is_connected = True  # Đánh dấu đã kết nối
                    self.warning_displayed = False  # Không có cảnh báo, tiếp tục chạy ProgressBar
                    self.start_progress()  # Chỉ bắt đầu tiến trình nếu kết nối thành công
                else:
                    print("Đã có kết nối với Arduino. Hãy ngắt kết nối trước.")
            except serial.SerialException as e:
                print(f"Lỗi khi kết nối: {e}")
            
    # Phương thức để bắt đầu tiến trình
    def start_progress(self):
        if not self.warning_connect:  # Chỉ khi không có cảnh báo
            self.progress_value = 0
            self.progress_bar.setValue(0)
            self.timer.start(10)  # Cập nhật mỗi 100ms
    
    # Phương thức cập nhật thanh ProgressBar và thay đổi màu sắc
    def update_progress_green(self):
        if self.is_connected:  # Chỉ cho phép cập nhật nếu đã kết nối
            self.progress_value += 5
            self.progress_bar.setValue(self.progress_value)

            # Cập nhật màu sắc bằng CSS
            self.progress_bar.setStyleSheet(f"""
                QProgressBar::chunk {{
                    background-color: #64ff64;
                }}
            """)

            if self.progress_value >= 100:
                self.timer.stop()  # Dừng khi đạt giá trị 100
        else:
            print("Chưa kết nối với cổng COM. Không thể thay đổi màu sắc.")
            
    # Phương thức cập nhật thanh ProgressBar và thay đổi màu sắc
    def update_progress_red(self):
        if self.is_connected:  # Chỉ cho phép cập nhật nếu đã kết nối
            self.progress_value += 5
            self.progress_bar.setValue(self.progress_value)

            # Cập nhật màu sắc bằng CSS
            self.progress_bar.setStyleSheet(f"""
                QProgressBar::chunk {{
                    background-color: #ff6464;
                }}
            """)

            if self.progress_value >= 100:
                self.timer.stop()  # Dừng khi đạt giá trị 100
        else:
            print("Chưa kết nối với cổng COM. Không thể thay đổi màu sắc.")
            
    def create_QLineEdit(self, text, x, y, weight, high, parent):
        line_edit = QLineEdit(text, parent)
        line_edit.setGeometry(x, y, weight, high)
        line_edit.setStyleSheet("""
            font-size: 20px;
            font-family: Times New Roman;
            font-weight: bold;
            color: black;
        """)
        line_edit.setAlignment(Qt.AlignCenter)
        line_edit.setReadOnly(True)
        return line_edit
    
    def coppy_value(self):
        self.Px_IK = self.Px_FK
        self.Py_IK = self.Py_FK
        self.Pz_IK = self.Pz_FK
        self.t_IK = self.t_FK
        
        self.Px_IK_label.setText(f"{round(self.Px_IK, 2):.2f}")
        self.Py_IK_label.setText(f"{round(self.Py_IK, 2):.2f}")
        self.Pz_IK_label.setText(f"{round(self.Pz_IK, 2):.2f}")
        self.t_IK_label.setText(f"{round(self.t_IK, 2):.2f}")
        
    def calculate_angles(self):
        px = self.Px_IK
        py = self.Py_IK
        pz = self.Pz_IK
        t_IK_rad = math.radians(self.t_IK)
        
        k = math.sqrt(px*px + py*py)
        if(k == 0):
            t1_IK_rad = 0
        else:
            t1_IK_rad = math.atan2(py/k, px/k)  
            
        self.t1_IK = round(math.degrees(t1_IK_rad))
        if(self.t1_IK < -180):
            self.t1_IK = self.t1_IK + 360
        if(self.t1_IK >= 180):
            self.t1_IK = self.t1_IK - 360
        
        E = round(px*math.cos(t1_IK_rad) + py*math.sin(t1_IK_rad) - self.L4*math.cos(t_IK_rad), 6)
        F = round(pz - self.L1 - self.L4*math.sin(t_IK_rad), 6)
        a = round(-2*self.L2*F, 6)
        b = round(-2*self.L2*E, 6)
        d = round(self.L3*self.L3 - E*E - F*F - self.L2*self.L2, 6)
        f = math.sqrt(a*a + b*b)
        alpha_rad = math.atan2(a/f, b/f)
        alpha = round(math.degrees(math.atan2(a/f, b/f)))
        
        t2_1_IK_rad = math.atan2(math.sqrt(1-d*d/(f*f)), d/f)  + alpha_rad
        self.t2_1_IK = round(math.degrees(t2_1_IK_rad))
        if(self.t2_1_IK < -180):
            self.t2_1_IK = self.t2_1_IK + 360
        if(self.t2_1_IK >= 180):
            self.t2_1_IK = self.t2_1_IK - 360
            
        t2_2_IK_rad = math.atan2(-math.sqrt(1-d*d/(f*f)), d/f)  + alpha_rad
        self.t2_2_IK = round(math.degrees(t2_2_IK_rad))
        if(self.t2_2_IK < -180):
            self.t2_2_IK = self.t2_2_IK + 360
        if(self.t2_2_IK >= 180):
            self.t2_2_IK = self.t2_2_IK - 360
            
        C23_1 = (px*math.cos(t1_IK_rad) + py*math.sin(t1_IK_rad) - self.L2*math.cos(t2_1_IK_rad) - self.L4*math.cos(t_IK_rad))/self.L3
        S23_1 = (pz - self.L1 - self.L2*math.sin(t2_1_IK_rad) - self.L4*math.sin(t_IK_rad))/self.L3
        t3_1_IK_rad = math.atan2(S23_1, C23_1) - t2_1_IK_rad
        self.t3_1_IK = round(math.degrees(t3_1_IK_rad))
        if(self.t3_1_IK < -180):
            self.t3_1_IK = self.t3_1_IK + 360
        if(self.t3_1_IK >= 180):
            self.t3_1_IK = self.t3_1_IK - 360
            
        C23_2 = (px*math.cos(t1_IK_rad) + py*math.sin(t1_IK_rad) - self.L2*math.cos(t2_2_IK_rad) - self.L4*math.cos(t_IK_rad))/self.L3
        S23_2 = (pz - self.L1 - self.L2*math.sin(t2_2_IK_rad) - self.L4*math.sin(t_IK_rad))/self.L3
        t3_2_IK_rad = math.atan2(S23_2, C23_2) - t2_2_IK_rad
        self.t3_2_IK = round(math.degrees(t3_2_IK_rad))
        if(self.t3_2_IK < -180):
            self.t3_2_IK = self.t3_2_IK + 360
        if(self.t3_2_IK >= 180):
            self.t3_2_IK = self.t3_2_IK - 360
            
        self.t4_1_IK = self.t_IK - self.t2_1_IK - self.t3_1_IK
        self.t4_2_IK = self.t_IK - self.t2_2_IK - self.t3_2_IK
        
        self.t1_IK_label.setText(str(self.t1_IK))
        self.t2_IK_label.setText(str(self.t2_1_IK))
        self.t3_IK_label.setText(str(self.t3_1_IK))
        self.t4_IK_label.setText(str(self.t4_1_IK))
        
    def update_angles_display(self):
        if self.combo_box_angles.currentText() == "BN1":
            # Hiển thị bộ nghiệm 1
            self.t1_IK_label.setText(str(self.t1_IK))
            self.t2_IK_label.setText(str(self.t2_1_IK))
            self.t3_IK_label.setText(str(self.t3_1_IK))
            self.t4_IK_label.setText(str(self.t4_1_IK))
        elif self.combo_box_angles.currentText() == "BN2":
            # Hiển thị bộ nghiệm 2
            self.t1_IK_label.setText(str(self.t1_IK))
            self.t2_IK_label.setText(str(self.t2_2_IK))
            self.t3_IK_label.setText(str(self.t3_2_IK))
            self.t4_IK_label.setText(str(self.t4_2_IK))
            
    def create_button(self, text, x, y, width, height, color, hover_color, callback, parent):
        button = QPushButton(text, parent)
        button.setGeometry(x, y, width, height)
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};  /* Màu nền của nút */
                color: white;               /* Màu chữ của nút */
                font-size: 16px;            /* Cỡ chữ */
                font-weight: bold;          /* Độ dày của chữ */
                border-radius: 10px;        /* Bo tròn các góc của nút */
            }}
            QPushButton:hover {{
                background-color: {hover_color};  /* Màu nền khi rê chuột qua */
            }}
        """)
        button.clicked.connect(callback)
        return button
    
    def off_progress(self):
        a = 1
        
    def send_FK(self):
        b = 1
        
    def home(self):
        # Reset tất cả các QLineEdit về 0
        for value_input in self.theta_value_inputs:
            value_input.setText('0')
    
        # Đồng thời, reset các slider về 0
        for slider in self.theta_sliders:
            slider.setValue(0)
            
    def drop(self):
        c =1
        
    def suck(self):
        d = 1

    def disconnect_from_arduino(self):
        """Ngắt kết nối với Arduino"""
        self.progress_value = 0  # Giá trị bắt đầu của ProgressBar
        self.timer.timeout.connect(self.update_progress_red)

        if self.serial_connection is not None and self.serial_connection.is_open:
            try:
                self.serial_connection.close()  # Đóng kết nối với Arduino
                print("Đã ngắt kết nối thành công.")
            except serial.SerialException as e:
                print(f"Lỗi khi ngắt kết nối: {e}")
        else:
            print("Không có kết nối để ngắt.")
            
    def show_warning_message(self, message):
        """Hiển thị một bảng thông báo cảnh báo"""
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Warning)  # Thiết lập biểu tượng cảnh báo
        msg_box.setWindowTitle("Cảnh báo")  # Tiêu đề của bảng thông báo
        msg_box.setText(message)  # Nội dung thông báo
        msg_box.setStandardButtons(QMessageBox.Ok)  # Nút OK để đóng thông báo
        msg_box.exec_()  # Hiển thị bảng thông báo
            
# Khởi tạo ứng dụng
app = QApplication(sys.argv)

# Tạo cửa sổ chính từ MainWindow
window = NewWindow()
window.show()

# Thoát ứng dụng khi đóng cửa sổ
sys.exit(app.exec_())