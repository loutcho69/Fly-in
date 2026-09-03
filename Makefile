PYTHON      := python3
MAP         ?= maps/easy_1.map
MYPY_FLAGS  := --warn-return-any --warn-unused-ignores \
               --ignore-missing-imports --disallow-untyped-defs \
               --check-untyped-defs

.PHONY: install run debug clean lint lint-strict

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) main.py $(MAP)

debug:
	$(PYTHON) -m pdb main.py $(MAP)

clean:
	rm -rf .mypy_cache .pytest_cache
	find . -type d -name '__pycache__' -exec rm -rf {} +
	find . -type f -name '*.py[co]' -delete

lint:
	flake8 .
	mypy . $(MYPY_FLAGS)

lint-strict:
	flake8 .
	mypy . --strict
