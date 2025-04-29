import tkinter as tk
from tkinter import messagebox, ttk

import serial.tools.list_ports
import threading
import serial
class UARTApp:
    def __init__(self, master):
        self.master = master
        self.master.title("UART Communication")
        self.master.geometry("1600x900")

        # Serial port configuration
        self.serial_port = None

        # Create widgets
        self.create_widgets()

    def create_widgets(self):
        # Label for COM Port
        self.port_label = tk.Label(self.master, text="Select COM Port:")
        self.port_label.pack(pady=5)

        # Dropdown for COM Port selection
        self.port_combobox = ttk.Combobox(self.master, values=self.get_com_ports())
        self.port_combobox.pack(pady=5)

        # Button to open the serial port
        self.open_button = tk.Button(self.master, text="Open Port", command=self.open_port)
        self.open_button.pack(pady=5)

        # Text area for sending data
        self.send_label = tk.Label(self.master, text="Send Data:")
        self.send_label.pack(pady=5)

        self.send_text = tk.Entry(self.master)
        self.send_text.pack(pady=5)

        self.send_button = tk.Button(self.master, text="Send", command=self.send_data)
        self.send_button.pack(pady=5)

        # Text area for received data
        self.receive_label = tk.Label(self.master, text="Received Data:")
        self.receive_label.pack(pady=5)

        self.receive_text = tk.Text(self.master, height=10, width=40)
        self.receive_text.pack(pady=5)

        # Button to close the serial port
        self.close_button = tk.Button(self.master, text="Close Port", command=self.close_port)
        self.close_button.pack(pady=5)
       
     

    def get_com_ports(self):
        """Get a list of available COM ports."""
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def open_port(self):
        try:
            port = self.port_combobox.get()
            if not port:
                messagebox.showwarning("Warning", "Please select a COM port.")
                return
            
            self.serial_port = serial.Serial(port, baudrate=115200, timeout=1)
            messagebox.showinfo("Info", f"Port {port} opened successfully.")
            self.receive_thread = threading.Thread(target=self.receive_data)
            self.receive_thread.daemon = True
            self.receive_thread.start()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def send_data(self):
        if self.serial_port and self.serial_port.is_open:
            data = self.send_text.get()
            self.serial_port.write(data.encode())
            self.send_text.delete(0, tk.END)  # Clear the entry field
        else:
            messagebox.showwarning("Warning", "Open a port first.")

    def receive_data(self):
        while True:
            if self.serial_port and self.serial_port.is_open:
                data = self.serial_port.readline().decode('utf-8').strip()
                if data:
                    self.receive_text.insert(tk.END, data + "\n")
                    self.receive_text.see(tk.END)  # Scroll to the end

    def close_port(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            messagebox.showinfo("Info", "Port closed.")
        else:
            messagebox.showwarning("Warning", "No port is open.")
    
if __name__ == "__main__":
    root = tk.Tk()
    app = UARTApp(root)
    root.mainloop()