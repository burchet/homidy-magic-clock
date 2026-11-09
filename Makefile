PY = .venv/bin/python

all: sync

deps:
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements.txt

sync:
	$(PY) goofy.py sync

dump:
	$(PY) goofy.py dump

scan:
	$(PY) scan.py

gatt:
	$(PY) gatt.py

.PHONY: all deps sync dump scan gatt
