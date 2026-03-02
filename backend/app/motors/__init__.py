"""
app.motors — compat shim.
Os especialistas e SugestaoMotor foram consolidados em app.cerebro.especialistas.
Este módulo re-exporta para não quebrar imports existentes.
"""
from app.cerebro.especialistas import SugestaoMotor  # noqa: F401
from app.cerebro.especialistas import (  # noqa: F401
    alpha as motor_alpha,
    dividendos as motor_dividendos,
    etfs as motor_etfs,
    fiis as motor_fiis,
    momentum as motor_momentum,
    renda_fixa as motor_renda_fixa,
    wheel as motor_wheel,
)
from app.cerebro import gestor as gestor_geral  # noqa: F401

__all__ = [
    "SugestaoMotor",
    "motor_alpha", "motor_dividendos", "motor_etfs", "motor_fiis",
    "motor_momentum", "motor_renda_fixa", "motor_wheel",
    "gestor_geral",
]
