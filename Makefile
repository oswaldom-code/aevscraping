# Makefile del proyecto aevscraping.
# Detecta el SO para resolver las rutas del entorno virtual e intérprete.
#   Linux/macOS:  .venv/bin/python
#   Windows:      .venv\Scripts\python.exe
# En Windows requiere GNU make (choco install make / scoop install make).

ifeq ($(OS),Windows_NT)
    PY       := python
    VENV_PY  := .venv\Scripts\python.exe
else
    PY       := python3
    VENV_PY  := .venv/bin/python
endif

# Todos los tests corren en un solo proceso vía scripts/run_tests.py (usa el venv
# porque el consolidador necesita openpyxl).

.DEFAULT_GOAL := help
.PHONY: help venv install install-playwright test \
        scrape-sos scrape-vr backfill-vr consolidate clean

help:
	@echo Targets disponibles:
	@echo   make install            - crea .venv e instala dependencias openpyxl y requests
	@echo   make install-playwright - instala Playwright + Chromium para el scraper terremoto
	@echo   make test               - corre TODOS los tests unitarios scrapers + consolidador
	@echo   make scrape-sos         - corre el scraper de sosvenezuela2026
	@echo   make scrape-vr          - corre venezuelareporta incremental, solo nuevos
	@echo   make backfill-vr        - corre venezuelareporta en modo --full, re-baja todo
	@echo   make consolidate        - corre el consolidador run_consolidacion.py
	@echo   make clean              - borra __pycache__, artefactos _smoke y el .venv

# --- entorno ---
venv:
	$(PY) -m venv .venv

install: venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r consolidator/requirements.txt

install-playwright: install
	$(VENV_PY) -m pip install playwright
	$(VENV_PY) -m playwright install chromium

# --- tests (un solo comando, un solo proceso) ---
test:
	$(VENV_PY) scripts/run_tests.py

# --- scrapers ---
scrape-sos:
	$(PY) scrapers/sosvenezuela2026/scraper.py --output scrapers/sosvenezuela2026/sosvenezuela2026

scrape-vr:
	$(PY) scrapers/venezuelareporta/scraper.py --output scrapers/venezuelareporta/venezuelareporta

backfill-vr:
	$(PY) scrapers/venezuelareporta/scraper.py --full --output scrapers/venezuelareporta/venezuelareporta

# --- consolidador ---
consolidate:
	$(VENV_PY) consolidator/run_consolidacion.py

# --- limpieza (one-liners de Python, portables Linux/Windows) ---
clean:
	$(PY) -c "import shutil,pathlib; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PY) -c "import pathlib; [f.unlink() for f in pathlib.Path('.').rglob('_smoke.*')]"
	$(PY) -c "import shutil,pathlib; shutil.rmtree('.venv') if pathlib.Path('.venv').exists() else None"
