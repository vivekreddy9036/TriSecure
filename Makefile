VENV    := venv
PYTHON  := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip

COVER_PKGS := --cov=models --cov=core --cov=repositories \
              --cov=security --cov=config --cov=backend/crypto

.PHONY: install test coverage coverage-html lint run backup lock clean

install:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip wheel
	$(PIP) install -r requirements.txt

lock:
	$(PIP) freeze > requirements-lock.txt

test:
	$(PYTHON) -m pytest tests/ -q --tb=short

coverage:
	$(PYTHON) -m pytest tests/ $(COVER_PKGS) --cov-report=term-missing -q

coverage-html:
	$(PYTHON) -m pytest tests/ $(COVER_PKGS) --cov-report=html
	@echo "HTML report: htmlcov/index.html"

lint:
	$(VENV)/bin/flake8 . --exclude=venv,data,htmlcov --max-line-length=100
	$(VENV)/bin/mypy . --ignore-missing-imports --exclude venv

run:
	$(PYTHON) app.py

backup:
	@STAMP=$$(date +%Y%m%d_%H%M%S); \
	cp data/trisecure.db data/backup_$$STAMP.db; \
	echo "Backup created: data/backup_$$STAMP.db"

clean:
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage
