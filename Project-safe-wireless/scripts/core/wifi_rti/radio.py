"""Presupuesto ilustrativo; no representa propagación interior ni materiales."""
import numpy as np

C_M_S = 299_792_458.0


def fspl_db(distance_m, frequency_mhz):
    d, f = np.asarray(distance_m, dtype=float), np.asarray(frequency_mhz, dtype=float)
    if not np.isfinite(d).all() or not np.isfinite(f).all() or (d <= 0).any() or (f <= 0).any():
        raise ValueError("Distancia y frecuencia deben ser positivas y finitas.")
    return 20 * np.log10(4 * np.pi * d * f * 1e6 / C_M_S)


def noise_floor_dbm(bandwidth_mhz, noise_figure_db=7.0):
    if not np.isfinite([bandwidth_mhz, noise_figure_db]).all() or bandwidth_mhz <= 0:
        raise ValueError("Ancho de banda positivo y parámetros finitos requeridos.")
    return float(-174 + 10*np.log10(bandwidth_mhz*1e6) + noise_figure_db)


def budget_dbm(distances_m, config):
    return (config.tx_power_dbm + config.tx_gain_dbi + config.rx_gain_dbi
            - fspl_db(distances_m, config.carrier_mhz) - config.extra_loss_db)


def reception_threshold_dbm(config):
    return max(config.receiver_sensitivity_dbm,
               noise_floor_dbm(config.bandwidth_mhz, config.noise_figure_db)+config.required_snr_db)

