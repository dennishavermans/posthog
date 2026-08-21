from typing import Any, Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from posthog.api.app_metrics2 import fetch_app_metric_totals
from posthog.dataclasses import frozen
from posthog.models.scoping import team_scope
from posthog.utils import relative_date_parse_with_delta_mapping

from products.workflows.backend.metrics import (
    GUARDRAIL_LABELS,
    GUARDRAIL_METRICS,
    HOG_FLOW_VERSION_APP_SOURCE,
    MIN_EVIDENCE_SAMPLE,
    TARGET_OPEN_METRIC,
    TARGET_SEND_METRIC,
    TARGET_UNTRACKED_METRIC,
    UNAVAILABLE_GUARDRAILS,
)
from products.workflows.backend.models.hog_flow.hog_flow import HogFlow
from products.workflows.backend.models.workflow_proposal import WorkflowProposal

OPEN_RATE_TARGET = 0.2
MIN_SENDS_FOR_EVIDENCE = MIN_EVIDENCE_SAMPLE
SHORT_SUBJECT_CHARS = 45


@frozen
class _SubjectCandidate:
    """An email step whose subject line the stub wants to shorten, and the numbers behind it."""

    action_id: str
    current_subject: str
    proposed_subject: str
    sends: int
    opens: int
    # Sends with open tracking off. They raise `sends` but can never raise `opens`, so the open rate
    # divides by tracked sends rather than all sends — otherwise a tracking change reads as poor copy.
    untracked: int
    # Raw counter-metric counts over the same window, step and version as the target, keyed by
    # app-metric name. Read alongside the target so a suggestion that lifts opens while raising
    # complaints or bounces is visible at review time rather than after it ships.
    guardrail_counts: dict[str, int]
    # True when the step was picked by --force rather than by its own metrics.
    without_evidence: bool

    @property
    def tracked_sends(self) -> int:
        return max(0, self.sends - self.untracked)

    @property
    def open_rate(self) -> Optional[float]:
        return (self.opens / self.tracked_sends) if self.tracked_sends else None

    def guardrails(self) -> list[dict[str, Any]]:
        """The counter-metrics, as rates per send, carrying their own denominator.

        `n` rides on every entry because a rate without its sample size is what lets a loop call
        20 sends an improvement.
        """
        return [
            {
                "metric": GUARDRAIL_LABELS[name],
                "value": (count / self.sends) if self.sends else None,
                "n": self.sends,
            }
            for name, count in self.guardrail_counts.items()
        ]


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
            rate = candidate.open_rate
            self.stdout.write(
                f"  {flow.name} v{flow.version} step {candidate.action_id}: "
                + (
                    "no metrics (forced)"
                    if candidate.without_evidence
                    else f"open rate {rate:.1%} of {candidate.sends} sends"
                )
            )
            self.stdout.write(f"    subject: {candidate.current_subject!r} -> {candidate.proposed_subject!r}")
            if not live_run:
                continue

            with team_scope(team_id):
                proposal = self._build_proposal(flow, candidate, window)
                # Idempotent by source id, so re-running the command re-resolves to the proposal it
                # already made instead of stacking duplicates in someone's queue.
                if WorkflowProposal.objects.filter(hog_flow=flow, source_id=proposal.source_id).exists():
                    self.stdout.write("    already proposed, skipping")
                    continue
                proposal.save()
                written += 1
                self.stdout.write(f"    proposed: {proposal.id}")

        self.stdout.write(f"Done. {written} proposal(s) written.")

    def _pick_candidate(self, flow: HogFlow, after: Any, force: bool) -> Optional[_SubjectCandidate]:
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
                name=[TARGET_SEND_METRIC, TARGET_OPEN_METRIC, TARGET_UNTRACKED_METRIC, *GUARDRAIL_METRICS],
            ).totals
            sent = int(totals.get(TARGET_SEND_METRIC, 0))
            opened = int(totals.get(TARGET_OPEN_METRIC, 0))
            untracked = int(totals.get(TARGET_UNTRACKED_METRIC, 0))
            guardrails = {name: int(totals.get(name, 0)) for name in GUARDRAIL_METRICS}

            # Untracked sends can never record an open, so the open rate and its sample floor read
            # against tracked sends. has_sample is checked first, so tracked is positive at the divide.
            tracked = max(0, sent - untracked)
            has_sample = tracked >= MIN_SENDS_FOR_EVIDENCE
            below_target = has_sample and (opened / tracked) < OPEN_RATE_TARGET
            # --force stands in for a missing sample (demoing against an empty metrics store), so it
            # only relaxes the below-target requirement. A step selected by force still keeps whatever
            # evidence it has — without_evidence means no sample, not "did not clear the target".
            if not below_target and not force:
                continue

            new_subject = _shorten_subject(subject)
            if new_subject == subject:
                self.stdout.write(f"  {flow.name} step {action_id}: subject is already short, nothing to propose")
                continue
            return _SubjectCandidate(
                action_id=str(action_id),
                current_subject=subject,
                proposed_subject=new_subject,
                sends=sent,
                opens=opened,
                untracked=untracked,
                guardrail_counts=guardrails,
                without_evidence=not has_sample,
            )
        return None

    def _build_proposal(
        self,
        flow: HogFlow,
        candidate: _SubjectCandidate,
        window: str,
    ) -> WorkflowProposal:
        actions = []
        for action in flow.actions or []:
            action = dict(action)
            if action.get("id") == candidate.action_id:
                config = dict(action.get("config") or {})
                inputs = dict(config.get("inputs") or {})
                email = dict(inputs.get("email") or {})
                email["value"] = {**dict(email.get("value") or {}), "subject": candidate.proposed_subject}
                inputs["email"] = email
                config["inputs"] = inputs
                action["config"] = config
            actions.append(action)

        rate = candidate.open_rate
        rationale = (
            f"The subject line on this step is long, and shorter subjects tend to get opened more. "
            f"This proposal shortens it to '{candidate.proposed_subject}'. "
        )
        rationale += (
            "No metrics were available for this step, so the change was picked without evidence."
            if candidate.without_evidence
            else f"Over {window} this step was opened {rate:.1%} of the time, against a {OPEN_RATE_TARGET:.0%} target."
        )
        rationale += " Written by a stub generator, not by an agent that read your copy."

        return WorkflowProposal(
            hog_flow=flow,
            title=f"Shorten the subject line on '{_step_name(flow, candidate.action_id)}'",
            rationale=rationale,
            content={"actions": actions},
            base_version=flow.version or 1,
            evidence={
                "metric": "email open rate",
                "current_value": None if candidate.without_evidence else round(rate or 0, 4),
                "target_value": OPEN_RATE_TARGET,
                "window": window,
                # The denominator rides with the rate: a rate on its own is what lets a loop call
                # twenty sends an improvement. Open rate is against tracked sends, so `n` is too.
                "n": candidate.tracked_sends,
                "minimum_n": MIN_SENDS_FOR_EVIDENCE,
                "guardrails": candidate.guardrails(),
                "guardrails_unavailable": list(UNAVAILABLE_GUARDRAILS),
                "sends": candidate.sends,
                "untracked": candidate.untracked,
                "opens": candidate.opens,
                "forced": candidate.without_evidence,
                "app_source_id": f"{flow.id}/{flow.version}",
                "query": (
                    "SELECT metric_name, sum(count) FROM app_metrics WHERE app_source = 'hog_flow_version' "
                    f"AND app_source_id = '{flow.id}/{flow.version}' AND instance_id = '{candidate.action_id}' "
                    "GROUP BY metric_name"
                ),
            },
            source_type=WorkflowProposal.SourceType.STUB,
            # Stable per (flow, version, step, day) so re-running the command is idempotent but a later
            # version can be proposed against again.
            source_id=f"stub:{flow.id}:v{flow.version}:{candidate.action_id}:{timezone.now():%Y-%m-%d}",
            created_via=WorkflowProposal.CreatedVia.API,
            created_by=None,
        )


def _liquid_balanced(text: str) -> bool:
    """Cheap guard, not a parser: email subjects are Liquid, and shortening only ever drops the tail,
    so a cut through a `{{ }}` or `{% %}` leaves an opener without its closer — a count mismatch here.
    Enough to keep _shorten_subject from proposing a subject that fails Liquid rendering at send time
    (the repo has no Python Liquid parser to validate against). A truncation that stays balanced still
    parses, so it is kept."""
    return text.count("{{") == text.count("}}") and text.count("{%") == text.count("%}")


def _shorten_subject(subject: str) -> str:
    subject = subject.strip()
    for separator in (": ", " - ", ", "):
        head = subject.split(separator)[0]
        # A separator inside a Liquid expression (e.g. the `: ` in `{{ x | default: 'y' }}`) would split
        # mid-tag, so only take a head that leaves every tag closed.
        if 0 < len(head) < len(subject) and _liquid_balanced(head):
            return head
    if len(subject) <= SHORT_SUBJECT_CHARS:
        return subject
    words = subject[:SHORT_SUBJECT_CHARS].rsplit(" ", 1)[0]
    shortened = words or subject[:SHORT_SUBJECT_CHARS]
    # Truncation can cut through a tag too; a subject that still sends beats a shorter one that doesn't.
    return shortened if _liquid_balanced(shortened) else subject


def _step_name(flow: HogFlow, action_id: str) -> str:
    for action in flow.actions or []:
        if isinstance(action, dict) and action.get("id") == action_id:
            return str(action.get("name") or action_id)
    return action_id
