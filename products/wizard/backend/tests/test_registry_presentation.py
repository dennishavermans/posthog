from posthog.test.base import APIBaseTest
from unittest.mock import patch

from rest_framework import status

from posthog.models import Organization


class TestWizardRegistryViewSet(APIBaseTest):
    def _url(self) -> str:
        return f"/api/projects/{self.team.id}/wizard/registry/"

    def test_list_returns_personalized_unpaginated_registry(self) -> None:
        payload = {
            "version": 1,
            "programs": [
                {
                    "id": "web-analytics-audit",
                    "name": "Web analytics audit",
                    "description": "Audit a project's web analytics setup",
                    "command": ["audit", "web-analytics"],
                    "tags": ["audit", "web-analytics"],
                    "required_programs": ["posthog-integration"],
                    "supported_environments": ["local"],
                }
            ],
        }

        with patch("posthoganalytics.get_feature_flag_payload", return_value=payload) as get_payload:
            response = self.client.get(self._url())

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), payload["programs"])
        get_payload.assert_called_once_with(
            "wizard-program-registry",
            distinct_id=self.user.distinct_id,
            groups={"organization": str(self.team.organization_id)},
            group_properties={"organization": {"id": str(self.team.organization_id)}},
            only_evaluate_locally=False,
            send_feature_flag_events=False,
        )

    def test_list_requires_authentication(self) -> None:
        self.client.logout()

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_rejects_another_organizations_project(self) -> None:
        organization = Organization.objects.create(name="Other organization")
        team = self.create_team_with_organization(organization)

        with patch("posthoganalytics.get_feature_flag_payload") as get_payload:
            response = self.client.get(f"/api/projects/{team.id}/wizard/registry/")

        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        get_payload.assert_not_called()
