"""Data access for the DataCo Smart Supply Chain dataset.

Source (public, Kaggle): shashwatwork/dataco-smart-supply-chain-for-big-data-analysis
File: DataCoSupplyChainDataset.csv (latin-1 encoded, ~180k rows, 53 columns).

`load_dataco()` reads the real file if present. `generate_synthetic()` produces a
SCHEMA-FAITHFUL SYNTHETIC sample (same column names/value domains, made-up rows)
so the package runs with no Kaggle credentials. Synthetic rows are tagged
`_synthetic=1` and must never be presented as real results.
"""
from __future__ import annotations
import csv
import random
from pathlib import Path
from typing import Iterable

from .models import Order

# Subset of the real DataCo columns used by this workflow (exact header names).
DATACO_COLUMNS = [
    "Type", "Days for shipping (real)", "Days for shipment (scheduled)",
    "Delivery Status", "Late_delivery_risk", "Category Name", "Customer Id",
    "Customer Segment", "Market", "Order Region", "Order Id", "Order Item Id",
    "order date (DateOrders)", "Order Item Discount Rate", "Order Item Product Price",
    "Order Item Quantity", "Order Item Total", "Order Status", "Product Card Id",
    "Product Name", "Shipping Mode",
]

ORDER_STATUSES = ["COMPLETE", "PENDING", "CLOSED", "PENDING_PAYMENT", "CANCELED",
                  "PROCESSING", "SUSPECTED_FRAUD", "ON_HOLD", "PAYMENT_REVIEW"]
STATUS_WEIGHTS = [33, 11, 11, 22, 2, 12, 2, 5, 2]  # approx. shape of the real data
PAYMENT_TYPES = ["DEBIT", "TRANSFER", "PAYMENT", "CASH"]
SEGMENTS = ["Consumer", "Corporate", "Home Office"]
MARKETS = {"LATAM": ["Central America", "South America", "Caribbean"],
           "Europe": ["Western Europe", "Northern Europe", "Southern Europe"],
           "Pacific Asia": ["Southeast Asia", "Eastern Asia", "Oceania"],
           "USCA": ["US Center", "East of USA", "West of USA"],
           "Africa": ["West Africa", "North Africa"]}
SHIP_MODES = {"Standard Class": 4, "Second Class": 2, "First Class": 1, "Same Day": 0}
PRODUCTS = [  # (card id, generic product name, category, price)
    (1001, "Trail Running Shoe", "Cleats", 59.99),
    (1002, "Performance Polo", "Men's Footwear", 49.98),
    (1003, "Insulated Water Bottle", "Indoor/Outdoor Games", 24.99),
    (1004, "Adjustable Dumbbell Set", "Fitness Accessories", 199.99),
    (1005, "Camping Tent 4P", "Camping & Hiking", 299.98),
    (1006, "Road Bike Helmet", "Cycling", 129.99),
    (1007, "Fishing Rod Combo", "Fishing", 399.98),
    (1008, "Smart Watch", "Electronics", 327.75),
]
OPEN_STATUSES = {"PENDING", "PENDING_PAYMENT", "PROCESSING", "ON_HOLD",
                 "PAYMENT_REVIEW", "SUSPECTED_FRAUD"}


def generate_synthetic(n: int = 200, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        pid, pname, cat, price = rng.choice(PRODUCTS)
        mode = rng.choices(list(SHIP_MODES), weights=[60, 20, 15, 5])[0]
        sched = SHIP_MODES[mode]
        real = max(0, sched + rng.choice([-1, 0, 0, 1, 2, 3]))
        late = int(real > sched)
        status = rng.choices(ORDER_STATUSES, weights=STATUS_WEIGHTS)[0]
        qty = rng.randint(1, 5)
        disc = rng.choice([0.0, 0.04, 0.1, 0.15, 0.18, 0.25])
        total = round(price * qty * (1 - disc), 2)
        if rng.random() < 0.05:  # inject a pricing inconsistency
            total = round(total * 0.8, 2)
        market = rng.choice(list(MARKETS))
        rows.append({
            "Type": rng.choice(PAYMENT_TYPES),
            "Days for shipping (real)": real,
            "Days for shipment (scheduled)": sched,
            "Delivery Status": "Late delivery" if late else "Shipping on time",
            "Late_delivery_risk": late,
            "Category Name": cat,
            "Customer Id": 10000 + rng.randint(0, 60),
            "Customer Segment": rng.choice(SEGMENTS),
            "Market": market,
            "Order Region": rng.choice(MARKETS[market]),
            "Order Id": 50000 + i,
            "Order Item Id": 150000 + i,
            "order date (DateOrders)": f"1/{1 + i % 28}/2018 {i % 24}:00",
            "Order Item Discount Rate": disc,
            "Order Item Product Price": price,
            "Order Item Quantity": qty,
            "Order Item Total": total,
            "Order Status": status,
            "Product Card Id": pid,
            "Product Name": pname,
            "Shipping Mode": mode,
            "_synthetic": 1,
        })
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def read_rows(path: Path, limit: int | None = None) -> list[dict]:
    """Read a DataCo-format CSV. The real Kaggle file is latin-1 encoded."""
    enc = "utf-8"
    try:
        path.open(encoding="utf-8").read(1 << 20)
    except UnicodeDecodeError:
        enc = "latin-1"
    out = []
    with path.open(encoding=enc, newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if limit is not None and i >= limit:
                break
            missing = [c for c in DATACO_COLUMNS if c not in row]
            if missing:
                raise ValueError(f"Not a DataCo-format file; missing columns: {missing}")
            out.append(row)
    return out


def to_order(r: dict) -> Order:
    return Order(
        order_id=int(r["Order Id"]), order_item_id=int(r["Order Item Id"]),
        customer_id=int(r["Customer Id"]), customer_segment=r["Customer Segment"],
        market=r["Market"], order_region=r["Order Region"],
        order_status=r["Order Status"], payment_type=r["Type"],
        shipping_mode=r["Shipping Mode"],
        days_scheduled=int(float(r["Days for shipment (scheduled)"])),
        days_real=int(float(r["Days for shipping (real)"])),
        late_delivery_risk=int(float(r["Late_delivery_risk"])),
        product_card_id=int(r["Product Card Id"]), product_name=r["Product Name"],
        category_name=r["Category Name"],
        unit_price=float(r["Order Item Product Price"]),
        quantity=int(float(r["Order Item Quantity"])),
        discount_rate=float(r["Order Item Discount Rate"]),
        item_total=float(r["Order Item Total"]),
        order_date=r["order date (DateOrders)"],
    )


def load_dataco(path: Path, limit: int | None = None, open_only: bool = True) -> list[Order]:
    orders = [to_order(r) for r in read_rows(path, limit)]
    return [o for o in orders if o.order_status in OPEN_STATUSES] if open_only else orders


def iter_open(orders: Iterable[Order]) -> list[Order]:
    return [o for o in orders if o.order_status in OPEN_STATUSES]
