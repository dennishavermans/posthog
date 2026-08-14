import asyncio
from dataclasses import asdict
from datetime import timedelta

from django.conf import settings

import structlog
from temporalio.common import RetryPolicy, WorkflowIDConflictPolicy, WorkflowIDReusePolicy

from posthog.temporal.common.client import sync_connect
from posthog.temporal.data_modeling.workflows.materialize_view import MaterializeViewWorkflowInputs

from products.data_modeling.backend.logic.node_suspension import resume_nodes
from products.data_modeling.backend.models import Node
from products.data_modeling.backend.models.datawarehouse_saved_query import DataWarehouseSavedQuery
from products.data_modeling.backend.schedule import get_v2_saved_query_ids

logger = structlog.get_logger(__name__)


def start_node_materialization(node: Node) -> None:
    """Start a one-off materialization workflow for a single node.

    Shared by node `materialize` and saved-query `run`.
    """
    # An explicit run is a request to try again, so it gets a fresh failure window.
    resume_nodes([node], by="manual_run")
    inputs = MaterializeViewWorkflowInputs(
        team_id=node.team_id,
        dag_id=str(node.dag_id),
        node_id=str(node.id),
    )

    temporal = sync_connect()
    asyncio.run(
        temporal.start_workflow(
            "data-modeling-materialize-view",
            asdict(inputs),
            id=f"materialize-view-{node.id}",
            task_queue=str(settings.DATA_MODELING_TASK_QUEUE),
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=10),
                maximum_interval=timedelta(seconds=60),
                maximum_attempts=3,
                non_retryable_error_types=["NondeterminismError", "CancelledError"],
            ),
        )
    )


def is_saved_query_on_v2_schedule(saved_query: DataWarehouseSavedQuery) -> bool:
    """Whether the saved query's DAG already runs on a v2 schedule.

    Keys on the Temporal source of truth (get_v2_saved_query_ids), not the feature flag, since a
    team can be schedule-migrated without being flagged.
    """
    return saved_query.id in get_v2_saved_query_ids([saved_query.id])


def materialize_saved_query(saved_query: DataWarehouseSavedQuery) -> None:
    """Materialize the saved query's backing node via the v2 workflow.

    Fire a single materialization — don't fan out over duplicate-DAG nodes, or two workers race to
    write the same backing table.
    """
    node = Node.objects.filter(saved_query_id=saved_query.id).first()
    if node is None:
        # v2 was already confirmed, so a node should exist; a missing one is a data inconsistency.
        # Skip rather than fall back to the v1 schedule, which no longer exists on a v2 team.
        logger.warning("materialize_saved_query_missing_node", saved_query_id=str(saved_query.id))
        return
    start_node_materialization(node)
