from posthog.test.base import APIBaseTest
from unittest.mock import MagicMock, patch

from parameterized import parameterized

from posthog.cdp.templates.hog_function_template import sync_template_to_db

from products.cdp.backend.api.test.test_hog_function_templates import MOCK_NODE_TEMPLATES
from products.workflows.backend.api.hog_flow import DRAFT_CONTENT_FIELDS
from products.workflows.backend.management.commands.suggest_workflow_optimisations import _shorten_subject
from products.workflows.backend.models.hog_flow.hog_flow import HogFlow
from products.workflows.backend.models.workflow_proposal import WorkflowProposal

webhook_template = MOCK_NODE_TEMPLATES[0]


def _trigger_action() -> dict:
    return {
        "id": "trigger_node",
        "name": "trigger_1",
        "type": "trigger",
        "config": {
            "type": "event",
            "filters": {"events": [{"id": "$pageview", "name": "$pageview", "type": "events", "order": 0}]},
        },
    }


def _webhook_action(action_id: str = "action_1", url: str = "https://example.com") -> dict:
    return {
        "id": action_id,
        "name": action_id,
        "type": "function",
        "config": {"template_id": "template-webhook", "inputs": {"url": {"value": url}}},
    }


@patch("products.workflows.backend.api.hog_flow.posthoganalytics.feature_enabled", return_value=True)
class TestWorkflowProposals(APIBaseTest):
    def setUp(self):
        super().setUp()
        sync_template_to_db(webhook_template)

    def _create_active_flow(self) -> str:
        create = self.client.post(
            f"/api/projects/{self.team.id}/hog_flows",
            {"name": "Proposal Flow", "actions": [_trigger_action(), _webhook_action()]},
        )
        assert create.status_code == 201, create.json()
        flow_id = create.json()["id"]
        activate = self.client.patch(f"/api/projects/{self.team.id}/hog_flows/{flow_id}", {"status": "active"})
        assert activate.status_code == 200, activate.json()
        return flow_id

    def _propose(self, flow_id: str, **overrides) -> dict:
        payload = {
            "title": "Point the webhook somewhere that answers",
            "rationale": "Every call to the current URL failed over the last week.",
            "content": {"actions": [_trigger_action(), _webhook_action(url="https://proposed.example.com")]},
            "evidence": {"metric": "failure rate", "current_value": 1.0, "target_value": 0.0, "window": "-7d"},
            "source_type": "scout",
            **overrides,
        }
        response = self.client.post(
            f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/", payload, format="json"
        )
        assert response.status_code == 201, response.json()
        return response.json()

    def _publish(self, flow_id: str):
        with patch("products.workflows.backend.api.hog_flow.get_hog_flow_in_flight_count") as mock_count:
            mock_count.return_value = MagicMock(
                status_code=200, json=lambda: {"count": 0, "by_action": {}, "position_unknown": 0}
            )
            preview = self.client.post(f"/api/projects/{self.team.id}/hog_flows/{flow_id}/publish", {})
        assert preview.status_code == 200, preview.json()
        response = self.client.post(
            f"/api/projects/{self.team.id}/hog_flows/{flow_id}/publish",
            {"confirm": True, "confirm_token": preview.json()["confirm_token"]},
        )
        assert response.status_code == 200, response.json()
        return response

    def test_approve_stages_a_full_draft_and_leaves_live_alone(self, _mock_flag):
        flow_id = self._create_active_flow()
        proposal = self._propose(flow_id)

        response = self.client.post(
            f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/{proposal['id']}/approve/", {}
        )
        assert response.status_code == 200, response.json()
        assert response.json()["status"] == "approved"

        flow = HogFlow.objects.get(id=flow_id)
        # The live config is untouched: an approval can only ever stage.
        assert flow.actions[1]["config"]["inputs"]["url"]["value"] == "https://example.com"
        assert flow.version == 1
        # The staged draft is a whole-content snapshot (live as the base, the proposal on top), which
        # is what publish's plain copy needs — a partial draft would drop the rest of the workflow.
        assert set(flow.draft.keys()) == set(DRAFT_CONTENT_FIELDS)
        assert flow.draft["actions"][1]["config"]["inputs"]["url"]["value"] == "https://proposed.example.com"

    def test_publish_marks_the_approved_proposal_applied(self, _mock_flag):
        flow_id = self._create_active_flow()
        proposal = self._propose(flow_id)
        self.client.post(f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/{proposal['id']}/approve/", {})

        self._publish(flow_id)

        stored = WorkflowProposal.objects.for_team(self.team.id).get(id=proposal["id"])
        assert stored.status == "applied"
        assert stored.applied_version == HogFlow.objects.get(id=flow_id).version == 2

    def test_provenance_comes_from_the_transport_not_the_payload(self, _mock_flag):
        flow_id = self._create_active_flow()
        response = self.client.post(
            f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/",
            {
                "title": "Self-labelled as a human edit",
                "rationale": "A caller must not be able to pass its own work off as someone else's.",
                "content": {"actions": [_trigger_action(), _webhook_action()]},
                "source_type": "scout",
                "created_via": "web",
            },
            format="json",
            HTTP_X_POSTHOG_CLIENT="mcp",
        )
        assert response.status_code == 201, response.json()
        assert response.json()["created_via"] == "mcp"

    def test_repeat_source_id_returns_the_same_proposal(self, _mock_flag):
        flow_id = self._create_active_flow()
        first = self._propose(flow_id, source_id="run:1:finding:webhook-url")

        again = self.client.post(
            f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/",
            {
                "title": "Retry of the same finding",
                "rationale": "A retried agent run must not queue a second copy for the human.",
                "content": {"actions": [_trigger_action(), _webhook_action()]},
                "source_type": "scout",
                "source_id": "run:1:finding:webhook-url",
            },
            format="json",
        )
        assert again.status_code == 200, again.json()
        assert again.json()["id"] == first["id"]
        assert WorkflowProposal.objects.for_team(self.team.id).filter(hog_flow_id=flow_id).count() == 1

    @parameterized.expand([("approve",), ("reject",)])
    def test_resolving_twice_is_refused(self, _mock_flag, action: str):
        flow_id = self._create_active_flow()
        proposal = self._propose(flow_id)
        url = f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/{proposal['id']}/{action}/"

        assert self.client.post(url, {}).status_code == 200
        second = self.client.post(url, {})
        assert second.status_code == 409, second.json()
        assert second.json()["code"] == "proposal_already_resolved"

    def test_approving_over_a_staged_draft_needs_the_draft_stamp_it_saw(self, _mock_flag):
        flow_id = self._create_active_flow()
        proposal = self._propose(flow_id)
        # A draft staged after the confirmation dialog opened must not be silently overwritten.
        staged = self.client.patch(
            f"/api/projects/{self.team.id}/hog_flows/{flow_id}/graph",
            {"operations": [{"op": "update_action", "id": "action_1", "patch": {"name": "renamed"}}]},
            HTTP_X_POSTHOG_CLIENT="mcp",
        )
        assert staged.status_code == 200, staged.json()

        url = f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/{proposal['id']}/approve/"
        assert self.client.post(url, {}).json()["code"] == "draft_exists"
        stale = self.client.post(url, {"overwrite": True, "expected_draft_updated_at": "2020-01-01T00:00:00Z"})
        assert stale.status_code == 409, stale.json()
        assert WorkflowProposal.objects.for_team(self.team.id).get(id=proposal["id"]).status == "suggested"


@patch("products.workflows.backend.api.hog_flow.posthoganalytics.feature_enabled", return_value=False)
class TestWorkflowProposalsFlagOff(APIBaseTest):
    def setUp(self):
        super().setUp()
        sync_template_to_db(webhook_template)

    def test_the_surface_does_not_exist_without_the_flag(self, _mock_flag):
        create = self.client.post(
            f"/api/projects/{self.team.id}/hog_flows",
            {"name": "Proposal Flow", "actions": [_trigger_action(), _webhook_action()]},
        )
        flow_id = create.json()["id"]

        listed = self.client.get(f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/")
        assert listed.status_code == 404, listed.json()
        created = self.client.post(
            f"/api/projects/{self.team.id}/hog_flows/{flow_id}/proposals/",
            {"title": "x", "rationale": "y", "content": {"actions": []}, "source_type": "scout"},
            format="json",
        )
        assert created.status_code == 404, created.json()


class TestWorkflowProposalModel(APIBaseTest):
    def test_team_is_mirrored_from_the_workflow(self):
        flow = HogFlow.objects.create(team=self.team, name="Scoped flow")
        other_team = self.organization.teams.create(name="Other team")

        proposal = WorkflowProposal(
            hog_flow=flow,
            team=other_team,
            title="Wrong team on the way in",
            rationale="Fail-closed reads filter on this row's team, so it has to match the workflow's.",
            content={"actions": []},
            base_version=1,
            source_type=WorkflowProposal.SourceType.SCOUT,
            created_via=WorkflowProposal.CreatedVia.MCP,
        )
        proposal.save()

        assert proposal.team_id == self.team.id
        assert WorkflowProposal.objects.for_team(other_team.id).filter(id=proposal.id).count() == 0


class TestShortenSubject(APIBaseTest):
    @parameterized.expand(
        [
            ("splits on a colon", "Your weekly summary: everything that happened", "Your weekly summary"),
            ("leaves a short subject alone", "Your weekly summary", "Your weekly summary"),
            ("truncates at a word boundary", "a" * 20 + " " + "b" * 40, "a" * 20),
        ]
    )
    def test_shorten_subject(self, _name: str, subject: str, expected: str):
        assert _shorten_subject(subject) == expected

    def test_never_returns_an_empty_subject(self):
        # Approving a proposal writes this straight into the email step, so an empty result would
        # silently blank a live subject line.
        for subject in [": leading separator", "-", "x" * 200, "   spaced   "]:
            assert _shorten_subject(subject) != ""
