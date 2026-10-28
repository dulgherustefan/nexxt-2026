"""Pachetele de reguli. Importul le înregistrează, în ordinea în care motorul le rulează și le raportează."""

from . import pay, dsp, cmp, rec, urm, dp, aml  # noqa: F401

__all__ = ["aml", "cmp", "dp", "dsp", "pay", "rec", "urm"]
