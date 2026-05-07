#!/usr/bin/env bash
# scripts/run_tests.sh

echo "TESTS RUNNER START..."
python tests/test_architecture.py
python tests/test_conf.py
python tests/test_extensions.py
python tests/test_health.py
python tests/test_incremental.py
python tests/test_v10.py
python tests/test_v11.py
python tests/test_v12.py
python tests/test_v13.py
python tests/test_v14.py
python tests/test_v15.py
python tests/test_v16.py
python tests/test_v17.py
echo "TESTS RUNNER END..."
