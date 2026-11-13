# BM::Notebook

[![Licenc: AGPL-3.0-or-later](assets/licenc_AGPLv3.svg)](https://www.gnu.org/licenses/agpl-3.0.html)
[![Kettős licenc: AGPLv3+ / Kereskedelmi](assets/licenc_AGPLv3+_kereskedelmi.svg)](LICENSE)

> [English documentation (README.md)](README.md)

Natív asztali, reaktív, **teljesen JS- és böngészőmentes** Jupyter-kompatibilis notebook IDE **Python + Qt6 (PySide6)** alapon.

## Mitől jobb, mint a klasszikus böngészős Jupyter?

1. **Nulla JS / nulla Electron / nulla WebEngine**: Minden felület (kódszerkesztő, szintaxiskiemelés, Markdown előnézet, táblázatok, grafikonok, reaktív DAG gráf) natív C++/Qt6 widgetekkel renderelődik.
2. **Reaktív DAG végrehajtás (nincs rejtett állapot)**:
   - Python AST elemzéssel automatikusan feltérképezi az egyes cellák definícióit (`defs`) és hivatkozásait (`refs`).
   - Egy cella módosításakor azonnal megjelöli (`STALE`) a tőle függő cellákat, futtatáskor pedig **topologikus sorrendben** automatikusan újrafuttatja a teljes érintett láncot.
   - Ha egy cellából törölsz egy változót, a rendszer a kernel névteréből is kitakarítja (`globals().pop(...)`), így nem marad szellemállapot.
   - Automatikusan jelzi a **több cellában definiált névütközéseket** és a **függőségi ciklusokat**.
3. **Git-barát `.bm.md` fájlformátum + `.ipynb` támogatás**:
   - Az alapértelmezett `.bm.md` formátum tiszta Markdown + ```python``` kódblokkokból áll, kimeneti bináris zaj nélkül — olvasható és diffelhető bármilyen VCS-ben.
   - Meglévő `.ipynb` (Jupyter nbformat 4) fájlok közvetlenül megnyithatók és exportálhatók.
4. **Teljes Jupyter kernel kompatibilitás**:
   - `jupyter_client` alapú ZMQ kommunikáció külön háttérszálon (nem akad a UI).
   - Bármely telepített Jupyter kernel kiválasztható.
   - Kernel-alapú `Tab` / `Ctrl+Space` kódkiegészítés, megszakítás (`Ctrl+I`), újraindítás, élő változó-vizsgáló.

## Indítás

```bash
python3 -m bm_notebook examples/reactive_demo.bm.md
```

Vagy telepítve:

```bash
pip install -e . --no-build-isolation
bm-notebook examples/reactive_demo.bm.md
```

## Billentyűparancsok

- `Shift+Enter`: Cella + függő cellák futtatása (reaktív kaszkád) és ugrás a következő cellára
- `Ctrl+Enter`: Cella + függő cellák futtatása helyben maradva
- `Alt+Enter`: Cella futtatása és új kód cella beszúrása alá
- `Tab` / `Ctrl+Space`: Kernel-alapú kódkiegészítés
- `F5` / `Ctrl+R`: Teljes notebook futtatása topologikus sorrendben
- `Ctrl+I`: Futó kernel megszakítása
- `Ctrl+B`: Jobb oldali Reaktív gráf / Változó vizsgáló panel ki/be
- `Ctrl+S` / `Ctrl+O` / `Ctrl+N`: Mentés / Megnyitás / Új notebook
