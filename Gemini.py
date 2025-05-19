import pathlib
import textwrap
import google.generativeai as genai
import os  # For accessing environment variables


def to_markdown(text):
    # Replace bullet points with a more consistent markdown format
    text = text.replace("•", "* ")
    # Indent the entire text block for markdown blockquote style
    return textwrap.indent(text, "> ", predicate=lambda _: True)


# Securely store your API key using an environment variable
GOOGLE_API_KEY = (
    "AIzaSyCxp0wD3-6nZOKaRn_WUkvzwlHOKfw-hJw"  # Replace with your actual API key
)

if not GOOGLE_API_KEY:
    print("Lỗi: Vui lòng thiết lập biến môi trường GEMINI_API_KEY.")
    exit()

genai.configure(api_key=GOOGLE_API_KEY)

try:
    # for m in genai.list_models():
    #      if 'generateContent' in m.supported_generation_methods:
    #          print(m.name)

    model = genai.GenerativeModel("gemini-2.5-flash-preview-04-17-thinking")
    prompt_tieng_viet = "hôm nay là ngày gì"
    response = model.generate_content(prompt_tieng_viet)

    print("Phản hồi:")
    print(to_markdown(response.text))

    if response.prompt_feedback:
        print("\nPhản hồi về prompt:")
        print(response.prompt_feedback)
    else:
        print("\nKhông có phản hồi về prompt.")

except Exception as e:
    print(f"Đã xảy ra lỗi: {e}")
