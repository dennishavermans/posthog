from prometheus_client import Counter, Histogram

from products.wizard.backend.facade.contracts import WizardRunDTO

WIZARD_RUNS_CREATED_TOTAL = Counter(
    "posthog_wizard_runs_created_total",
    "Wizard runs created",
    labelnames=["environment"],
)

WIZARD_RUNS_FINISHED_TOTAL = Counter(
    "posthog_wizard_runs_finished_total",
    "Wizard runs that reached a terminal status",
    labelnames=["environment", "status", "error_code"],
)

WIZARD_RUN_DURATION_SECONDS = Histogram(
    "posthog_wizard_run_duration_seconds",
    "Wizard run duration",
    labelnames=["environment", "status"],
    buckets=(30, 60, 120, 300, 600, 1200, 1800, 3600, 7200, float("inf")),
)


def report_run_created(run: WizardRunDTO) -> None:
    WIZARD_RUNS_CREATED_TOTAL.labels(environment=run.environment.value).inc()


def report_run_finished(run: WizardRunDTO) -> None:
    WIZARD_RUNS_FINISHED_TOTAL.labels(
        environment=run.environment.value,
        status=run.status.value,
        error_code=run.error_code.value if run.error_code is not None else "none",
    ).inc()
    if run.started_at is None or run.finished_at is None:
        return
    duration = (run.finished_at - run.started_at).total_seconds()
    if duration >= 0:
        WIZARD_RUN_DURATION_SECONDS.labels(environment=run.environment.value, status=run.status.value).observe(duration)
