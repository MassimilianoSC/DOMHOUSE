.PHONY: dev bff mock frontend gen-api test

# Starts the BFF (with the built-in mock instance mounted at /mock) and the PWA.
dev:
	$(MAKE) -j2 bff frontend

bff:
	cd bff && [ -f .env ] || cp .env.example .env; cd .. && PORT=8000 uvicorn bff.main:app --host 0.0.0.0 --port 8000 --reload

mock:
	python -m bff.mock_instance --port 8100

frontend:
	cd frontend && yarn install && yarn dev --port 5173

gen-api:
	cd frontend && yarn gen:api

# Full test run: a fresh local BFF per HTTP suite, every suite, totals (see scripts/run_tests.py).
test:
	python scripts/run_tests.py
