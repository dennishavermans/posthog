from products.wizard.backend.facade.temporal import ACTIVITIES, WORKFLOWS
from products.wizard.backend.temporal.activities.execute_cloud import execute_cloud_run
from products.wizard.backend.temporal.activities.lifecycle import cancel_run, complete_run, fail_run, start_run
from products.wizard.backend.temporal.workflows.execute_run import ExecuteWizardRunWorkflow


def test_wizard_temporal_registry_exposes_cloud_run_components() -> None:
    assert WORKFLOWS == [ExecuteWizardRunWorkflow]
    assert ACTIVITIES == [start_run, execute_cloud_run, complete_run, fail_run, cancel_run]
