import sys

# Library GUI
from PyQt5.QtWidgets import QApplication,QMainWindow
from test_1 import Ui_MainWindow 

class MainApp(QMainWindow,Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self) 
        self.setupSingal()
    
    # Button event 
    def setupSingal(self):
        self.bt_diem_danh.clicked.connect(self.show_diem_danh)
        self.bt_back_diem_danh.clicked.connect(self.back_diem_danh)
        self.bt_setup.clicked.connect(self.show_setup)
        self.bt_back_setup.clicked.connect(self.back_setup)
        self.bt_thoat.clicked.connect(self.close) 
        self.bt_thu_phong.clicked.connect(self.toggleFullScreen)
        self.bt_thu_nho.clicked.connect(self.showMinimized)



    # Funtion Page
    
    #Page_diem_danh
    def show_diem_danh(self):
        self.stackedWidget.setCurrentWidget(self.page_diem_danh)
    def back_diem_danh(self):
        self.stackedWidget.setCurrentWidget(self.page_main)
   #Page_Setup
    def show_setup(self):
        self.stackedWidget.setCurrentWidget(self.page_setup)
    def back_setup(self):
        self.stackedWidget.setCurrentWidget(self.page_main)
    
    # Funtion event 
    def toggleFullScreen(self):
        """ Bật hoặc tắt chế độ toàn màn hình """
        if self.isFullScreen():
            self.showNormal()  # Thoát toàn màn hình
        else:
            self.showFullScreen()  # Bật toàn màn hình

    
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainApp()
    window.show()
    sys.exit(app.exec_())