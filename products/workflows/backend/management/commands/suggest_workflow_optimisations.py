from typing import Any, Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from posthog.api.app_metrics2 import fetch_app_metric_totals
from posthog.models.scoping import team_scope
from posthog.utils import relative_date_parse_with_delta_mapping

from products.workflows.backend.models.hog_flow.hog_flow import HogFlow
from products.workflows.backend.models.workflow_proposal import WorkflowProposal

HOG_FLOW_VERSION_APP_SOURCE = "hog_flow_version"
OPEN_RATE_TARGET = 0.2
MIN_SENDS_FOR_EVIDENCE = 20
SHORT_SUBJECT_CHARS = 45


class Command(BaseCommand):
    help = (
        "STUB proposal generator for self-optimising workflows. Stands in for a PostHog Autonomy Scout "
        "so the propose/approve/publish loop is demoable end to end. One heuristic: read a workflow's "
        "live-version email metrics per step and, where a step's open rate is under target, propose a "
        "shorter subject line. The real generator is a Scout that reasons over the same metrics and "
        "calls the proposals API over MCP; this command exists only to prove the seam. Default dry-run."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--team-id", type=int, required=True, help="Team whose workflows to look at")
        parser.add_argument("--workflow-id", default=None, help="Limit to one workflow id")
        parser.add_argument("--window", default="-7d", help="Metric window, e.g. -7d (default) or -30d")
        parser.add_argument("--live-run", action="store_true", help="Write proposals (default is dry-run)")
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Propose against the first email step even when there are no metrics for it. For local "
                "demos against an empty metrics store; the evidence records that it was forced."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        team_id: int = options["team_id"]
        window: str = options["window"]
        live_run: bool = options["live_run"]
        force: bool = options["force"]

        queryset = HogFlow.objects.filter(team_id=team_id).exclude(status=HogFlow.State.ARCHIVED)
        if options["workflow_id"]:
            queryset = queryset.filter(id=options["workflow_id"])
        flows = list(queryset)
        if not flows:
            raise CommandError("No workflows found for that team.")

        after, _, _ = relative_date_parse_with_delta_mapping(window, flows[0].team.timezone_info)

        self.stdout.write(f"{'LIVE RUN' if live_run else 'DRY RUN'}: {len(flows)} workflow(s), window {window}")
        written = 0
        for flow in flows:
            candidate = self._pick_candidate(flow, after, force)
            if candidate is None:
                continue
            action_id, subject, new_subject, sent, opened, forced = candidate
            open_rate = (opened / sent) if sent else None
            self.stdout.write(
                f"  {flow.name} v{flow.version} step {action_id}: "
                f"{'no metrics (forced)' if forced else f'open rate {open_rate:.1%} of {sent} sends'}"
            )
            self.stdout.write(f"    subject: {subject!r} -> {new_subject!r}")
            if not live_run:
                continue

            with team_scope(team_id):
                proposal = self._build_proposal(flow, action_id, new_subject, open_rate, sent, opened, window, forced)
                # Idempotent by source id, so re-running the command re-resolves to the proposal it
                # already made instead of stacking duplicates in someone's queue.
                if WorkflowProposal.objects.filter(hog_flow=flow, source_id=proposal.source_id).exists():
                    self.stdout.write("    already proposed, skipping")
                    continue
                proposal.save()
                written += 1
                self.stdout.write(f"    proposed: {proposal.id}")

        self.stdout.write(f"Done. {written} proposal(s) written.")

    def _pick_candidate(self, flow: HogFlow, after: Any, force: bool) -> Optional[tuple[str, str, str, int, int, bool]]:
        for action in flow.actions or []:
            if not isinstance(action, dict) or action.get("type") != "function_email":
                continue
            action_id = action.get("id")
            value = (((action.get("config") or {}).get("inputs") or {}).get("email") or {}).get("value") or {}
            subject = value.get("subject")
            if not action_id or not isinstance(subject, str) or not subject.strip():
                continue

            totals = fetch_app_metric_totals(
                team_id=flow.team_id,
                app_source=HOG_FLOW_VERSION_APP_SOURCE,
                app_source_id=f"{flow.id}/{flow.version}",
                breakdown_by="name",
                after=after,
                instance_id=str(action_id),
                name=["email_sent", "email_opened"],
            ).totals
            sent = int(totals.get("email_sent", 0))
            opened = int(totals.get("email_opened", 0))

            enough_evidence = sent >= MIN_SENDS_FOR_EVIDENCE and (opened / sent) < OPEN_RATE_TARGET
            if not enough_evidence and not force:
                continue

            new_subject = _shorten_subject(subject)
            if new_subject == subject:
                self.stdout.write(f"  {flow.name} step {action_id}: subject is already short, nothing to propose")
                continue
            return str(action_id), subject, new_subject, sent, opened, not enough_evidence
        return None

    def _build_proposal(
        self,
        flow: HogFlow,
        action_id: str,
        new_subject: str,
        open_rate: Optional[float],
        sent: int,
        opened: int,
        window: str,
        forced: bool,
    ) -> WorkflowProposal:
        actions = []
        for action in flow.actions or []:
            action = dict(action)
            if action.get("id") == action_id:
                config = dict(action.get("config") or {})
                inputs = dict(config.get("inputs") or {})
                email = dict(inputs.get("email") or {})
                email["value"] = {**dict(email.get("value") or {}), "subject": new_subject}
                inputs["email"] = email
                config["inputs"] = inputs
                action["config"] = config
            actions.append(action)

        rationale = (
            f"The subject line on this step is long, and shorter subjects tend to get opened more. "
            f"This proposal shortens it to '{new_subject}'. "
        )
        rationale += (
            "No metrics were available for this step, so the change was picked without evidence."
            if forced
            else f"Over {window} this step was opened {open_rate:.1%} of the time, against a {OPEN_RATE_TARGET:.0%} target."
        )
        rationale += " Written by a stub generator, not by an agent that read your copy."

        return WorkflowProposal(
            hog_flow=flow,
            title=f"Shorten the subject line on '{_step_name(flow, action_id)}'",
            rationale=rationale,
            content={"actions": actions},
            base_version=flow.version or 1,
            evidence={
                "metric": "email open rate",
                "current_value": None if forced else round(open_rate or 0, 4),
                "target_value": OPEN_RATE_TARGET,
                "window": window,
                "sends": sent,
                "opens": opened,
                "forced": forced,
                "app_source_id": f"{flow.id}/{flow.version}",
                "query": (
                    "SELECT metric_name, sum(count) FROM app_metrics WHERE app_source = 'hog_flow_version' "
                    f"AND app_source_id = '{flow.id}/{flow.version}' AND instance_id = '{action_id}' "
                    "GROUP BY metric_name"
                ),
            },
            source_type=WorkflowProposal.SourceType.STUB,
            # Stable per (flow, version, step, day) so re-running the command is idempotent but a later
            # version can be proposed against again.
            source_id=f"stub:{flow.id}:v{flow.version}:{action_id}:{timezone.now():%Y-%m-%d}",
            created_via=WorkflowProposal.CreatedVia.API,
            created_by=None,
        )


def _shorten_subject(subject: str) -> str:
    subject = subject.strip()
    for separator in (": ", " - ", ", "):
        head = subject.split(separator)[0]
        if 0 < len(head) < len(subject):
            return head
    if len(subject) <= SHORT_SUBJECT_CHARS:
        return subject
    words = subject[:SHORT_SUBJECT_CHARS].rsplit(" ", 1)[0]
    return words or subject[:SHORT_SUBJECT_CHARS]


def _step_name(flow: HogFlow, action_id: str) -> str:
    for action in flow.actions or []:
        if isinstance(action, dict) and action.get("id") == action_id:
            return str(action.get("name") or action_id)
    return action_id
