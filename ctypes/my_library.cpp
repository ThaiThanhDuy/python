#include <iostream>

extern "C" { // Quan trọng để tương thích với ctypes
    int add(int a, int b) {
        return a + b;
    }

    void print_message(const char* message) {
        std::cout << "Message from C++: " << message << std::endl;
    }

    double multiply(double x, double y){
        return x*y;
    }
}
