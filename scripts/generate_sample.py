"""Regenerate the committed SYNTHETIC DataCo-schema sample (deterministic)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oea.data import generate_synthetic, write_csv  # noqa: E402

out = Path(__file__).resolve().parents[1] / "data" / "sample" / "dataco_synthetic_sample.csv"
write_csv(generate_synthetic(n=200, seed=42), out)
print(f"wrote {out}")
