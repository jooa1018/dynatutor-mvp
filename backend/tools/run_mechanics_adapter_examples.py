from __future__ import annotations

from engine.adapters.sympy_mechanics_adapter import derive_model, list_mechanics_models
from engine.adapters.pydy_adapter import get_pydy_status


def main() -> None:
    print("PyDy status:", get_pydy_status())
    for model in list_mechanics_models():
        name = model["name"]
        derivation = derive_model(name)
        print("\n==", name, "==")
        print("coordinates:", derivation.coordinates)
        print("parameters:", derivation.parameters)
        print("equations:")
        for eq in derivation.equations:
            print("  ", eq)
        print("mass_matrix:", derivation.mass_matrix)
        print("forcing:", derivation.forcing)


if __name__ == "__main__":
    main()
