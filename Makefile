.PHONY: run stream validate sample test

run:
	python -m logs_simulator.cli generate --config config.example.yaml --out-dir ./logs_out --duration-sec 60 --events-per-sec 120 --seed 42

stream:
	python -m logs_simulator.cli stream --config config.example.yaml --out-dir ./logs_out --events-per-sec 120 --seed 42

validate:
	python -m logs_simulator.cli validate-config --config config.example.yaml

sample:
	python make_sample_dataset.py --config config.example.yaml --out-dir ./sample_dataset --duration-sec 90 --events-per-sec 90 --seed 7

test:
	pytest
