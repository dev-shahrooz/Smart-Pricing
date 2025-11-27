"""Models for demand elasticity outputs from ML."""
from dataclasses import dataclass


@dataclass
class ElasticityResult:
    """Captured ML estimation for elasticity and optimal pricing."""

    elasticity: float
    optimal_price: float
    max_profit: float


__all__ = ["ElasticityResult"]
