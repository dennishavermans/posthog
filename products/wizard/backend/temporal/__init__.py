from products.wizard.backend.temporal.activities.execute_cloud import execute_cloud_run
from products.wizard.backend.temporal.activities.lifecycle import cancel_run, complete_run, fail_run, start_run
from products.wizard.backend.temporal.workflows.execute_run import ExecuteWizardRunWorkflow

WORKFLOWS = [ExecuteWizardRunWorkflow]

ACTIVITIES = [start_run, execute_cloud_run, complete_run, fail_run, cancel_run]
