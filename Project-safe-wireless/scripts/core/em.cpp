// EM para dos gaussianas de media cero. C++17, solo biblioteca estandar.
// Compilar: g++ -std=c++17 -O2 -static em.cpp -o build/em.exe
#include <algorithm>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

struct FitResult {
    double p, sigma1, sigma2;
    int iterations;
    bool converged;
};

// BEGIN EM CORE
// Paso E: probabilidad posterior de la componente estrecha, en logaritmos.
double responsibility(double x, double p, double s1, double s2) {
    const double v1 = std::max(s1 * s1, 1e-8), v2 = std::max(s2 * s2, 1e-8);
    const double pi = std::acos(-1.0);
    const double a = std::log(std::max(p, 1e-12)) - 0.5 * std::log(2 * pi * v1) - x * x / (2 * v1);
    const double b = std::log(std::max(1 - p, 1e-12)) - 0.5 * std::log(2 * pi * v2) - x * x / (2 * v2);
    const double largest = std::max(a, b);
    const double ea = std::exp(a - largest), eb = std::exp(b - largest);
    return ea / std::max(ea + eb, 1e-300);
}

// Entradas: residuos finitos, limite/tolerancia, inicios y piso de sigma.
// Un inicio sigma NaN solicita el valor automatico basado en std poblacional.
// Salida: p, sigma1, sigma2, iteraciones y cumplimiento de la tolerancia.
FitResult fit_em(const std::vector<double>& x, int max_iterations, double tolerance,
                 double p, double s1, double s2, double sigma_floor) {
    const double n = static_cast<double>(x.size());
    if (x.empty()) throw std::invalid_argument("Se requiere al menos un residuo.");
    const double mean = std::accumulate(x.begin(), x.end(), 0.0) / n;
    double sum_deviations = 0;
    for (double value : x) sum_deviations += (value - mean) * (value - mean);
    const double spread = std::max(std::sqrt(sum_deviations / n), 1e-3);
    p = std::clamp(p, 1e-4, 1.0 - 1e-4);
    s1 = std::max(std::isnan(s1) ? spread * 0.55 : s1, sigma_floor);
    s2 = std::max(std::isnan(s2) ? spread * 1.8 : s2, s1 * 1.05);
    std::vector<double> tau(x.size());  // O(N) memoria de responsabilidades.

    for (int iteration = 1; iteration <= max_iterations; ++iteration) {
        const double old_p = p, old_s1 = s1, old_s2 = s2;
        // E: cada residuo recibe una pertenencia suave entre cero y uno.
        for (std::size_t i = 0; i < x.size(); ++i)
            tau[i] = responsibility(x[i], p, s1, s2);
        const double mass1 = std::max(std::accumulate(tau.begin(), tau.end(), 0.0), 1e-8);
        const double mass2 = std::max(n - mass1, 1e-8);
        // M: actualiza peso y segundos momentos ponderados; medias fijas cero.
        p = std::clamp(mass1 / n, 1e-4, 1.0 - 1e-4);
        double square_sum1 = 0, square_sum2 = 0;
        for (std::size_t i = 0; i < x.size(); ++i) {
            const double square = x[i] * x[i];
            square_sum1 += tau[i] * square;
            square_sum2 += (1 - tau[i]) * square;
        }
        s1 = std::max(std::sqrt(std::max(square_sum1 / mass1, 0.0)), sigma_floor);
        s2 = std::max(std::sqrt(std::max(square_sum2 / mass2, 0.0)), sigma_floor);
        if (s1 > s2) { std::swap(s1, s2); p = 1 - p; }
        const double change = std::max({
            std::abs(p - old_p) / std::max(std::abs(old_p), 1e-8),
            std::abs(s1 - old_s1) / std::max(std::abs(old_s1), 1e-8),
            std::abs(s2 - old_s2) / std::max(std::abs(old_s2), 1e-8)});
        if (change < tolerance) return {p, s1, s2, iteration, true};
    }
    return {p, s1, s2, max_iterations, false};
}
// END EM CORE

double read_number() {
    std::string token;
    if (!(std::cin >> token)) throw std::invalid_argument("Entrada numerica incompleta.");
    std::size_t consumed = 0;
    const double number = std::stod(token, &consumed);
    if (consumed != token.size()) throw std::invalid_argument("Numero no valido.");
    return number;
}

void demo() {
    const std::vector<double> x{-3, -1, 1, 3};
    std::cout << "UNA iteracion E/M, medias fijas cero. Datos: [-3,-1,1,3]\n";
    std::cout << "Iniciales: p=0.5, sigma1=1, sigma2=3\n";
    std::cout << std::fixed << std::setprecision(6);
    for (double value : x)
        std::cout << "ruido " << value << ": responsabilidad=" << responsibility(value, 0.5, 1, 3) << '\n';
    const auto result = fit_em(x, 1, 1e-7, 0.5, 1, 3, 0.15);
    std::cout << "p=" << result.p << "; sigma1=" << result.sigma1 << "; sigma2=" << result.sigma2 << '\n';
    std::cout << "Una iteracion no demuestra convergencia ni valida un modelo con cuatro datos.\n";
}

int main(int argc, char* argv[]) {
    try {
        if (argc == 2 && std::string(argv[1]) == "--demo") { demo(); return 0; }
        if (argc != 2 || std::string(argv[1]) != "--fit") {
            std::cerr << "Uso: em.exe --demo | --fit\n"
                      << "stdin --fit: N maxiter tol p0 s10 s20 floor, luego N residuos.\n"
                      << "Usar nan para sigma inicial automatica.\n";
            return 2;
        }
        std::size_t n;
        int max_iterations;
        if (!(std::cin >> n >> max_iterations)) throw std::invalid_argument("Faltan N e iteraciones.");
        const double tolerance = read_number(), p = read_number();
        const double s1 = read_number(), s2 = read_number(), floor = read_number();
        if (max_iterations < 1 || !(tolerance > 0) || !(floor > 0) || !std::isfinite(p)
            || !std::isfinite(tolerance) || !std::isfinite(floor)
            || std::isinf(s1) || std::isinf(s2)) throw std::invalid_argument("Parametros no validos.");
        std::vector<double> x;
        for (std::size_t i = 0; i < n; ++i) {
            const double value = read_number();
            if (std::isfinite(value)) x.push_back(value);
        }
        if (x.size() < 20) throw std::invalid_argument("Se requieren al menos 20 residuos finitos para --fit.");
        const auto result = fit_em(x, max_iterations, tolerance, p, s1, s2, floor);
        std::cout << std::setprecision(17) << result.p << ' ' << result.sigma1 << ' '
                  << result.sigma2 << ' ' << result.iterations << ' ' << result.converged << '\n';
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
}
