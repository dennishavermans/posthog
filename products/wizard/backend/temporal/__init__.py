from products.wizard.backend.temporal.activities.execution import execute_wizard
from products.wizard.backend.temporal.activities.handoff import create_run_artifacts
from products.wizard.backend.temporal.activities.lifecycle import cancel_run, complete_run, fail_run, start_run
from products.wizard.backend.temporal.activities.workspace import clone_repository, destroy_worker, provision_worker
from products.wizard.backend.temporal.workflows.execute_run import ExecuteWizardRunWorkflow

WORKFLOWS = [ExecuteWizardRunWorkflow]

ACTIVITIES = [
    start_run,
    provision_worker,
    clone_repository,
    execute_wizard,
    create_run_artifacts,
    destroy_worker,
    complete_run,
    fail_run,
    cancel_run,
]
