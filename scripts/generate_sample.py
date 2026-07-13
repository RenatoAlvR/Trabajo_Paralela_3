"""Genera un CSV sintético con el esquema del enunciado (para pruebas locales).

Uso:
    python scripts/generate_sample.py --rows 100000 --out data/ventas.csv
"""
import argparse
import csv
import random
import uuid
from datetime import datetime, timedelta

CANALES = ["POS", "WEB", "APP", "CCT", "APR", "WPR"]
PRODUCTOS = [
    (1095, "EUCERIN SERUM DERMOP.40ML"),
    (2043, "PARACETAMOL 500MG X16"),
    (3310, "IBUPROFENO 400MG X20"),
    (4521, "PROTECTOR SOLAR FPS50 200ML"),
    (5099, "VITAMINA C 1000MG X30"),
    (6712, "SHAMPOO ANTICASPA 400ML"),
]
NOMBRES = ["JUAN", "MARIA", "PEDRO", "ANA", "LUIS", "CARLA", "JOSE", "SOFIA"]
APELLIDOS = ["PÉREZ GÓMEZ", "SOTO DÍAZ", "ROJAS MUÑOZ", "TORRES LEÓN", "VERA PINO"]

HEADERS = [
    "FECHA", "CANAL", "SKU", "PRODUCTO", "UNIDADES", "PORCENTAJE DESCUENTO",
    "MONTO APLICADO", "BOLETA", "LOCAL", "CODIGO CLIENTE", "RUN CLIENTE",
    "NOMBRES", "APELLIDOS", "FECHA NACIMIENTO", "GENERO",
]


def _run_dv(num: int) -> str:
    reversed_digits = [int(d) for d in reversed(str(num))]
    factors = [2, 3, 4, 5, 6, 7]
    total = sum(d * factors[i % 6] for i, d in enumerate(reversed_digits))
    resto = 11 - (total % 11)
    return {10: "K", 11: "0"}.get(resto, str(resto))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=100_000)
    ap.add_argument("--out", default="data/ventas.csv")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    random.seed(args.seed)
    base = datetime(2026, 1, 1)

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADERS)
        for i in range(args.rows):
            sku, prod = random.choice(PRODUCTOS)
            unidades = random.randint(1, 5)
            desc = round(random.choice([0, 0, 0.1, 0.15, 0.2, 0.25]), 2)
            precio = random.choice([2990, 5990, 9990, 12500, 18990, 24990])
            monto = round(precio * unidades * (1 - desc), 1)
            fecha = base + timedelta(seconds=random.randint(0, 180 * 24 * 3600))
            nacimiento = datetime(
                random.randint(1950, 2007), random.randint(1, 12), random.randint(1, 28)
            )
            run_num = random.randint(5_000_000, 25_000_000)
            w.writerow([
                fecha.strftime("%Y-%m-%dT%H:%M:%S"),
                random.choice(CANALES),
                sku,
                prod,
                unidades,
                desc,
                monto,
                100000 + i,
                random.randint(1, 50),
                str(uuid.uuid4()),
                f"{run_num}-{_run_dv(run_num)}",
                random.choice(NOMBRES),
                random.choice(APELLIDOS),
                nacimiento.strftime("%Y-%m-%d"),
                random.choice([1, 2]),
            ])

    print(f"Generadas {args.rows} filas en {args.out}")


if __name__ == "__main__":
    main()
