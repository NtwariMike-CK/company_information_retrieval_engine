#!/usr/bin/env bash
# One command that reproduces ALL automated test evidence on a THROWAWAY stack (it switches the AI config to test providers).
#   cd backend && bash tests/run_all_tests.sh
# Needs: PostgreSQL 16 + pgvector reachable with the DATABASE_URL below, and `pip install -r requirements.txt coverage pytest psutil numpy matplotlib`.
set -u
export DATABASE_URL=${DATABASE_URL:-postgresql://rag_app:change_me_app@localhost:5432/company_rag}
export REGISTER_LIMIT_PER_HOUR=1000
L=../docs/testing/logs; R=../docs/testing/results; mkdir -p $L $R
echo "== 1. unit tests + branch coverage"; python -m pytest tests/test_language.py tests/test_eval_metrics.py tests/test_security_and_pipeline.py -v | tee $L/01_unit_tests_pytest.log | tail -2
coverage run --branch --source=app -m pytest -q tests/test_language.py tests/test_eval_metrics.py tests/test_security_and_pipeline.py >/dev/null 2>&1
coverage report --include="app/rag/lang.py,app/rag/chunking.py,app/rag/clean.py,app/rag/extract.py,app/rag/retrieval.py,app/eval/metrics.py,app/security.py" --show-missing | tee $L/02_unit_coverage_core_modules.log | tail -3
echo "== 2. start the API under coverage"; rm -f .coverage
coverage run --source=app -m uvicorn app.main:app --port 8000 > $L/10_api_server_log.log 2>&1 & API=$!
for i in $(seq 1 40); do curl -sf localhost:8000/health >/dev/null && break; sleep 1; done
echo "== 3. integration suites"
python tests/smoke.py                 | tee $L/03_integration_smoke_core.log | tail -1
python tests/smoke_v11.py             | tee $L/04_integration_smoke_v11.log | tail -1
python tests/smoke_eval.py            | tee $L/05_integration_model_evaluation.log | tail -1
python tests/rest_interface_samples.py | tee $L/09_rest_interface_and_error_tracking.log | grep "REST RESULT"
python tests/data_flow_trace.py       | tee $L/07_data_flow_trace.log | tail -1
python tests/collect_eval_results.py $R/eval_results_test_providers.json
kill -INT $API; sleep 4; wait $API 2>/dev/null
coverage report --include='app/*' | tee $L/06_coverage_api_integration.log | tail -1
echo "== 4. performance (needs the owner DSN for the bulk loader; API must be running again)"
echo "   BENCH_OUT=$R/benchmark_results_sandbox.json DATABASE_URL=<owner dsn> python tests/benchmark.py --part all"
cd .. && python docs/report/build_figures.py
