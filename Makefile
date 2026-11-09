PY = .venv/bin/python

all: sync

deps:
	python3 -m venv .venv
	$(PY) -m pip install -q -r requirements.txt

sync:
	$(PY) homidy.py sync

dump:
	$(PY) homidy.py dump

scan:
	$(PY) scan.py

gatt:
	$(PY) gatt.py

.PHONY: all deps sync dump scan gatt
