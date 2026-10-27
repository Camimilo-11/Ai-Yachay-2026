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
