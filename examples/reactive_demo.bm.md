---
title: Reaktív notebook demó
kernel: python3
reactive: true
---

# BM Notebook — natív, reaktív, js-mentes demó

Ez a notebook `.bm.md` formátumban tárolódik: **tiszta Markdown + kódblokkok**, nincs zajos JSON vagy base64 kimenet a Git diffekben.

Próbáld ki: módosítsd a `freq` vagy `amp` értékét az első cellában, majd nyomj `Shift+Enter`-t — az összes függő cella (az adatgenerálás, statisztika és a grafikon is) **automatikusan újrafut** topologikus sorrendben!

```python id="c-params"
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

freq = 2.5
amp = 1.4
n_points = 300
```

```python id="c-signal"
t = np.linspace(0, 2 * np.pi, n_points)
signal = amp * np.sin(freq * t) + 0.25 * np.cos(3 * freq * t)
```

```python id="c-table"
summary = pd.DataFrame(
    {
        "metric": ["min", "max", "mean", "std"],
        "value": [
            float(np.min(signal)),
            float(np.max(signal)),
            float(np.mean(signal)),
            float(np.std(signal)),
        ],
    }
)
summary
```

```python id="c-plot"
fig, ax = plt.subplots(figsize=(7.5, 3.2), dpi=120)
ax.plot(t, signal, color="#5B8AF5", linewidth=2.0, label=f"freq={freq}, amp={amp}")
ax.axhline(0, color="#737D94", linestyle="--", linewidth=0.8)
ax.set_title("Reaktív jel-vizualizáció (Qt6 QPixmap)")
ax.set_xlabel("t (rad)")
ax.set_ylabel("Amplitúdó")
ax.legend()
ax.grid(alpha=0.25)
fig.tight_layout()
plt.show()
```
