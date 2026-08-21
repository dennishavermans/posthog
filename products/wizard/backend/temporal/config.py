from datetime import timedelta

from temporalio.common import RetryPolicy

FINALIZATION_TIMEOUT = timedelta(minutes=1)
PROVISION_TIMEOUT = timedelta(minutes=5)
PREPARATION_TIMEOUT = timedelta(minutes=10)
EXECUTION_TIMEOUT = timedelta(minutes=50)
HANDOFF_TIMEOUT = timedelta(minutes=5)
CLEANUP_TIMEOUT = timedelta(minutes=5)
FINALIZATION_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
WORKER_RETRY_POLICY = RetryPolicy(maximum_attempts=1)
CLEANUP_RETRY_POLICY = RetryPolicy(maximum_attempts=3)
