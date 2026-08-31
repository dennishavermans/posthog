from posthog.schema import DataVisualizationNode, HogQLQuery, NodeKind

from ee.hogai.eval.scorers import PlanAndQueryOutput, QueryKindSelection


def test_query_kind_selection_uses_the_source_kind_for_sql_visualizations() -> None:
    result = QueryKindSelection(expected=NodeKind.HOG_QL_QUERY)._run_eval_sync(
        PlanAndQueryOutput(query=DataVisualizationNode(source=HogQLQuery(query="SELECT 1")))
    )

    assert result.score == 1
