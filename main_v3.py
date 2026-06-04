import sys
import os
import cv2
import time
import pandas as pd
import pyttsx3
import textwrap
import openpyxl
import google.generativeai as genai
from gtts import gTTS
from playsound3 import playsound
from PyQt5.QtWidgets import QFileDialog
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import Qt, QThread
from PyQt5.QtWidgets import QStackedWidget, QListWidgetItem, QMessageBox
from QT_Duong import Ui_MainWindow
import speech_recognition as sr
from playsound3 import playsound  # Thay đổi import ở đây
import gemini
from AppAl_v1 import TextProcessor, main

# Cấu hình API key
GOOGLE_API_KEY = ""
if not GOOGLE_API_KEY:
    print("Lỗi: Vui lòng thiết lập API Key.")
    exit()
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")


def speak_vietnamese_gg(text):
    try:
        tts = gTTS(text=text, lang="vi")
        filename = "temp_speech.mp3"
        tts.save(filename)
        playsound(filename)
        os.remove(filename)
    except Exception as e:
        print(e)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        # xoa trang khi moi khoi dong
        self.ui.tc_nha_truong.clear()  # Reset danh sách câu hỏi
        self.ui.label_cau_hoi_ai.clear()
        self.ui.label_tra_loi_ai.clear()
        self.ui.tra_loi_tc_nha_truong.clear()  # Reset chỗ hiển thị câu trả lời
        # gan su kien
        self.ui.tc_nha_truong.itemClicked.connect(self.on_question_clicked)
        # trang thai ai
        self.ai_dang_chay = False

        # canh giua cho Qlabel
        self.ui.tra_loi_tc_nha_truong.setAlignment(Qt.AlignCenter)
        # Chuc nang nut back
        self.ui.bt_back_tc_nha_truong.clicked.connect(self.home_ui)
        self.ui.bt_back_tc_ai.clicked.connect(self.home_ui)
        self.ui.bt_tc_cap_nhat.clicked.connect(self.load_excel)
        self.ui.bt_tra_cuu.clicked.connect(self.tra_cuu)
        self.ui.btn_bat_dau_ai.clicked.connect(self.toggle_start_ai)
        self.ui.btn_tich_hoi_ai.clicked.connect(self.xac_nhan_cau_hoi_ai)
        self.ui.btn_huy_hoi_ai.clicked.connect(self.huy_cau_hoi_ai)

    def toggle_start_ai(self):
        if not self.ai_dang_chay:
            self.ui.btn_bat_dau_ai.setText("Kết thúc")
            self.ui.label_cau_hoi_ai.clear()
            self.ai_dang_chay = True
            # xu li ai tai day
            # 🎤 Ghi âm và chuyển giọng nói thành văn bản
            r = sr.Recognizer()
            with sr.Microphone() as source:
                # self.ui.label_cau_hoi_ai.setText("🎙 Đang khởi động micro...")
                self.ui.label_lang_nghe.setText("🟢 Tôi đang lắng nghe bạn...")
                QtWidgets.QApplication.processEvents()  # Cập nhật giao diện ngay

                r.adjust_for_ambient_noise(source)
                try:
                    # ⏱ Tăng thời gian ghi tối đa lên 10 giây
                    audio = r.listen(source, timeout=10, phrase_time_limit=10)

                    text = r.recognize_google(audio, language="vi-VN")
                    self.cau_hoi_text = text
                    self.ui.label_cau_hoi_ai.setText(f"🎤 Câu hỏi: {text}")
                    self.ui.label_tra_loi_ai.setText(
                        "✅ Đã ghi âm xong. Nhấn 'Xác nhận' để gửi."
                    )
                except sr.UnknownValueError:
                    self.ui.label_cau_hoi_ai.setText(
                        "❌ Không thể nhận diện được giọng nói.Bạn bấm Hủy để bắt đầu lại nhé "
                    )
                    self.ui.label_tra_loi_ai.setText("")
                except sr.RequestError as e:
                    self.ui.label_cau_hoi_ai.setText(f"❌ Lỗi kết nối: {e}")
                    self.ui.label_tra_loi_ai.setText("")
                except sr.WaitTimeoutError:
                    self.ui.label_cau_hoi_ai.setText(
                        "⌛ Hết thời gian chờ. Bạn chưa nói gì."
                    )
                    self.ui.label_tra_loi_ai.setText("❗ Vui lòng thử lại.")

        else:
            self.ui.btn_bat_dau_ai.setText("Bắt đầu")
            self.ai_dang_chay = False
            self.ui.label_cau_hoi_ai.clear()
            self.ui.label_tra_loi_ai.clear()
            self.ui.label_lang_nghe.setText(
                "🔴🔴 Bạn muốn tra cứu thì hãy bấm bắt đầu nhé !"
            )

    def xac_nhan_cau_hoi_ai(self):
        if not self.cau_hoi_text:
            self.ui.label_tra_loi_ai.setText("⚠️ Chưa có câu hỏi để gửi.")
            return

        self.ui.label_tra_loi_ai.setText("🤖 Đang xử lý câu hỏi... Vui lòng chờ.")
        QtWidgets.QApplication.processEvents()
        self.ui.label_cau_hoi_ai.clear()
        self.ui.label_tra_loi_ai.clear()
        try:

            response = model.generate_content(self.cau_hoi_text)

            if hasattr(response, "text") and response.text:
                tra_loi = response.text.strip()
                self.ui.label_tra_loi_ai.setText(f"💬 Trả lời: {tra_loi}")
                # Chuyển văn bản thành giọng nói
                tts = gTTS(text=response.text, lang="vi")
                tts.save("phan_hoi_v3.mp3")
                playsound("phan_hoi_v3.mp3")
                os.remove("phan_hoi_v3.mp3")
                self.cau_hoi_text = ""

            else:
                self.ui.label_tra_loi_ai.setText("⚠️ Không nhận được phản hồi từ AI.")

        except Exception as e:
            self.ui.label_tra_loi_ai.setText(f"❌ Lỗi khi gửi câu hỏi: {str(e)}")

    def huy_cau_hoi_ai(self):
        self.cau_hoi_text = ""
        self.ui.label_cau_hoi_ai.setText(
            "🔄 Câu hỏi đã bị hủy. Vui lòng nhấn 'Bắt đầu' để thu lại."
        )
        self.ui.label_tra_loi_ai.setText("")
        self.ui.btn_bat_dau_ai.setText("Bắt đầu")
        self.ai_dang_chay = False

    def tra_cuu(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.pape_tra_cuu)

    def home_ui(self):
        self.ui.stackedWidget.setCurrentWidget(self.ui.page_main)

    def load_excel(self):

        try:
            df = pd.read_excel("data_v1.xlsx", header=None, engine="openpyxl")
            df = df.iloc[:, :2]
            df.columns = ["Câu hỏi", "Câu trả lời"]
            df.dropna(how="any", inplace=True)

            self.ui.tc_nha_truong.clear()
            for _, row in df.iterrows():
                item = QListWidgetItem(row["Câu hỏi"])
                item.setData(Qt.UserRole, row["Câu trả lời"])
                item.setTextAlignment(Qt.AlignLeft)  # Canh giữa
                self.ui.tc_nha_truong.addItem(item)
        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Không đọc được file Excel: {str(e)}")

    def on_question_clicked(self):
        item = self.ui.tc_nha_truong.currentItem()
        if item:
            answer = item.data(Qt.UserRole)
            test = answer
            print(test)
            self.ui.tra_loi_tc_nha_truong.setText(test)

            if self.ui.checkBox_giong_noi_2.isChecked():
                self.ui.tra_loi_tc_nha_truong.setText(answer)
                speak_vietnamese_gg(answer)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
