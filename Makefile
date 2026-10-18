PY := .venv/bin/python
PORT ?= 8000

.PHONY: setup serve stop seed run test test-e2e eval-scripted eval eval-chaos memory demo-gif clean

setup:            ## create the virtualenv, install deps and Chromium
	uv venv --python 3.12 .venv || python3 -m venv .venv
	uv pip install -r requirements.txt || .venv/bin/pip install -r requirements.txt
	.venv/bin/playwright install chromium
	[ -f .env ] || cp .env.example .env
	$(PY) -m company.seed

serve:            ## start the simulated company on http://127.0.0.1:$(PORT)
	PORT=$(PORT) ./scripts/serve.sh

stop:
	-kill $$(cat var/server.pid) 2>/dev/null; rm -f var/server.pid

seed:             ## reset the company to its seeded state
	curl -s -X POST http://127.0.0.1:$(PORT)/admin/api/reset >/dev/null || $(PY) -m company.seed

run:              ## run a task with the LLM brain: make run TASK="..."
	$(PY) -m worker run "$(TASK)"

run-scripted:     ## run a task with the scripted SOP brain (no model needed)
	$(PY) -m worker run "$(TASK)" --brain scripted --human approve-all

test:             ## unit tests (no sandbox, no model)
	$(PY) -m pytest tests -q --ignore=tests/test_e2e_scripted.py

test-e2e:         ## end-to-end runtime tests against the sandbox (make serve first)
	$(PY) -m pytest tests/test_e2e_scripted.py tests/test_e2e_llm_plumbing.py -q

eval-scripted:    ## runtime guarantees under cold + chaos with the scripted brain
	$(PY) -m evals.run_eval --brain scripted --conditions cold chaos --runs 3 --name scripted

eval:             ## the real evaluation with the configured LLM: cold vs learned vs unseen
	$(PY) -m evals.run_eval --brain llm --conditions cold learned unseen --runs 1 --name llm

eval-chaos:
	$(PY) -m evals.run_eval --brain llm --conditions chaos --runs 1 --name llm-chaos

memory:           ## show what the worker has learned
	$(PY) -m worker memory

demo-gif:         ## render the latest run's screenshots into docs/demo.gif
	$(PY) scripts/make_gif.py

clean:
	rm -rf runs/* var/shots
