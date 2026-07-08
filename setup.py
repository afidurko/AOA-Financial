"""Editable install maps both src/aoa and top-level aoa_financial."""

from setuptools import find_packages, setup

_AOA_FINANCIAL_ROOT = "aoa_financial"


def _aoa_financial_packages() -> list[str]:
    return [_AOA_FINANCIAL_ROOT] + [
        f"{_AOA_FINANCIAL_ROOT}.{name}" for name in find_packages(_AOA_FINANCIAL_ROOT)
    ]


setup(
    package_dir={"": "src", _AOA_FINANCIAL_ROOT: _AOA_FINANCIAL_ROOT},
    packages=find_packages(where="src") + _aoa_financial_packages(),
)
