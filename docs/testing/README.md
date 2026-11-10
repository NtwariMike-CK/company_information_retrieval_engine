# Test evidence

Everything here was produced by the scripts in `backend/tests/` (reproduce with `bash backend/tests/run_all_tests.sh`). The write-up is [`../TESTING_REPORT.md`](../TESTING_REPORT.md).

| Folder / file | Content |
|---|---|
| `logs/01_unit_tests_pytest.log` | 39 unit tests (pytest) |
| `logs/02_unit_coverage_core_modules.log` | branch coverage of the logic modules (86%) |
| `logs/03-05_integration_*.log` | 51 + 76 + 40 end-to-end checks against the live API and PostgreSQL |
| `logs/06_coverage_api_integration.log` | statement coverage of the API with all suites running (84%) |
| `logs/07_data_flow_trace.log` | one document and three questions traced through every layer, ending with the deletion proof |
| `logs/08_benchmark_run.log` | performance run output |
| `logs/09_rest_interface_and_error_tracking.log` | 32 REST requests (expected vs actual), `error_logs` and `audit_logs` excerpts |
| `logs/10_api_server_log.log` | the API server's own log during that run (shows the logged exception) |
| `logs/11_frontend_build.log` | production build of the 25 front-end pages (types and lint pass) |
| `logs/12_browser_e2e.log` | 29 Chromium checks and throttled-device load profiles |
| `results/benchmark_results_sandbox.json` | latency, throughput, CPU/memory, retrieval scaling (add `benchmark_results_mac.json` from your MacBook) |
| `results/eval_results_test_providers.json` | model-evaluation lab output (test providers; real-Gemini runs are still to do) |
| `results/e2e_browser_results.json` | browser checks, device profiles |
| `screenshots/` | 23 screenshots from the real running app (Chromium + emulated devices); add your own manual-browser and terminal screenshots here |
| `acceptance/` | SUS questionnaire, response template and scoring script (no participant data yet) |

Charts are drawn from the result files by `python docs/report/build_figures.py`.
