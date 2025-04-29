import speech_recognition as sr
from gtts import gTTS
from playsound3 import playsound  # Thay đổi import ở đây
import os

def nghe_va_phan_hoi():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        print("Hãy nói gì đó...")
        r.adjust_for_ambient_noise(source) # Điều chỉnh cho tiếng ồn xung quanh
        try:
            audio = r.listen(source)
            text = r.recognize_google(audio, language='vi-VN')
            print(f"Bạn đã nói: {text}")

            # Xử lý câu nói và tạo phản hồi (ví dụ đơn giản)
            if "xin chào" in text.lower():
                phan_hoi = "Xin chào bạn!"
            elif "bạn khỏe không" in text.lower():
                phan_hoi = "Tôi ổn, cảm ơn bạn đã hỏi."
            else:
                phan_hoi = "Tôi chưa hiểu bạn nói gì."

            print(f"Tôi trả lời: {phan_hoi}")

            # Chuyển văn bản phản hồi thành giọng nói và phát
            tts = gTTS(text=phan_hoi, lang='vi')
            tts.save("phan_hoi.mp3")
            playsound("phan_hoi.mp3")  # Sử dụng playsound từ playsound3
            os.remove("phan_hoi.mp3") # Xóa file âm thanh sau khi phát

        except sr.UnknownValueError:
            print("Không thể nhận dạng giọng nói.")
        except sr.RequestError as e:
            print(f"Lỗi dịch vụ nhận dạng giọng nói; {e}")

if __name__ == "__main__":
    nghe_va_phan_hoi()