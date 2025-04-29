import ctypes

# Load thư viện C++
#my_library = ctypes.CDLL('./my_library.so')  # Linux/macOS
#my_library = ctypes.CDLL('./my_library.dll') # Windows
my_library = ctypes.CDLL(r'F:\Workspace\Python\ctypes\my_library.dll')
# Gọi hàm add
result_add = my_library.add(5, 3)
print(f"Result of add(5, 3): {result_add}")

# Gọi hàm print_message
message = "Hello from Python!"
my_library.print_message(message.encode('utf-8')) # encode string sang bytes

# Gọi hàm multiply
x = 2.5
y = 4.0

my_library.multiply.restype = ctypes.c_double # chỉ định kiểu trả về của hàm multiply
result_multiply = my_library.multiply(ctypes.c_double(x), ctypes.c_double(y)) # chỉ định kiểu dữ liệu đầu vào.
print(f"Result of multiply(2.5, 4.0): {result_multiply}")