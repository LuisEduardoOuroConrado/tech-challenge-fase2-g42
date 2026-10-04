"""python -m medroute.data.cli  -> gera as instâncias padrão em data/instances/."""
from __future__ import annotations

from pathlib import Path

from .generator import generate_instance
from .loader import load_fleet, save_instance, validate_instance

INSTANCIAS = {"sp_15": (15, 4), "sp_40": (40, 10), "sp_80": (80, 10)}


def main(out: str = "data/instances", seed: int = 42) -> None:
    fleet = load_fleet()
    Path(out).mkdir(parents=True, exist_ok=True)
    for nome, (n, n_real) in INSTANCIAS.items():
        inst = generate_instance(nome, n, n_real, fleet, seed=seed)
        validate_instance(inst, fleet)
        save_instance(inst, Path(out) / f"{nome}.json")
        print(f"{nome}: {len(inst.deliveries)} entregas ({n_real} reais) -> {out}/{nome}.json")


if __name__ == "__main__":
    main()
