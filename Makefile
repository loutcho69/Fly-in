PYTHON      := python3
VENV        := .venv
VENV_BIN    := $(VENV)/bin
MAP         ?= maps/easy/01_linear_path.txt
MYPY_FLAGS  := --warn-return-any --warn-unused-ignores \
               --ignore-missing-imports --disallow-untyped-defs \
               --check-untyped-defs

.DEFAULT_GOAL := run
.PHONY: install run log debug clean lint lint-strict test

# The simulator itself needs nothing but the standard library, so the
# dependencies are only the two linters. They are installed inside a
# virtual environment: a system-wide pip install is refused by recent
# Python distributions (PEP 668, "externally-managed-environment").
install: $(VENV_BIN)/flake8

$(VENV_BIN)/flake8: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/python -m pip install --quiet --upgrade pip
	$(VENV_BIN)/python -m pip install --quiet -r requirements.txt

# The graphical viewer opens on $(MAP) and lets the user browse every
# other map from its sidebar. The flight log is printed to the terminal
# at the same time, and `make log` gives that log on its own.
run:
	$(PYTHON) main.py $(MAP) --gui

log:
	$(PYTHON) main.py $(MAP)

debug:
	$(PYTHON) -m pdb main.py $(MAP)

test:
	$(PYTHON) check.py

lint: install
	$(VENV_BIN)/flake8 .
	$(VENV_BIN)/mypy . $(MYPY_FLAGS)

lint-strict: install
	$(VENV_BIN)/flake8 .
	$(VENV_BIN)/mypy . --strict

clean:
	rm -rf .mypy_cache .pytest_cache
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete
