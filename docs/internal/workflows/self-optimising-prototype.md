# Self-optimising workflows: proposal spine (prototype)

Status: prototype, behind the `self-optimising-workflows` feature flag.
Scope: the human-in-the-loop half of self-optimising workflows.
Not shipped, not production-hardened, no A/B.

## What this builds

An agent reads a workflow's performance, writes a **proposal** (a named, agent-authored change with evidence), a human approves it, and approval **stages the change into the workflow's draft** so the existing publish-confirm flow takes it live.

```text
metrics ──▶ [Scout / stub generator] ──▶ WorkflowProposal (suggested)
                                              │
                                     human approves / rejects
                                              │ approve
                                              ▼
                              HogFlow.draft  ← staged, live untouched
                                              │
                                     existing publish + confirm
                                              ▼
                                      live version  (proposal → applied)
```

The suggestion engine is **not** built here.
The real brain is a **PostHog Autonomy Scout** (RFC #1141), owned by another team.
This prototype ships the seam it will call plus a labelled stub generator so the loop is demoable end to end.

## What was already true (verified, not rebuilt)

| Fact                                                                                                                 | Where                                                                                                         |
| -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Whole-workflow, append-only content snapshots keyed unique on `(hog_flow, version)`                                  | `products/workflows/backend/models/hog_flow_revision.py`, written by `_append_revisions`                      |
| The stage-then-confirm move: copy a snapshot into `draft`, never touch live                                          | `restore_revision`, `products/workflows/backend/api/hog_flow.py`                                              |
| Draft staging, publish preview + signed confirm token, discard                                                       | `publish` / `discard_draft`, same file                                                                        |
| Per-`(flow, version)` metrics, mirrored under `app_source='hog_flow_version'`, `app_source_id='<flow id>/<version>'` | PR #75100, **merged 2026-08-05**; see `products/workflows/CONTRIBUTING.md`, "Metrics and version attribution" |
| Per-step metrics are keyed by `instance_id` = the action id                                                          | `fetch_app_metric_totals(..., instance_id=...)`, `posthog/api/app_metrics2.py`                                |
| Agent outputs are attributed by transport-derived `created_via`, never self-reported                                 | `get_event_source` / `AGENT_EVENT_SOURCES`, `posthog/event_usage.py`; `ExternalDataSource.CreatedVia`         |
| Scout output rows carry a stable `source_id` (`run:<run_id>:finding:<finding_id>`)                                   | `SignalScoutEmission`, `products/signals/backend/models.py`                                                   |
| No agent can edit a workflow today                                                                                   | `products/workflows/backend/max_tools.py` has only `CreateMessageTemplateTool`                                |
| A/B between revisions does not exist                                                                                 | only `random_cohort_branch`, which splits edges _within_ one revision                                         |

Nothing reads the versioned metric series yet, so the stub generator is its first reader.

## Data model

`products/workflows/backend/models/workflow_proposal.py` — `WorkflowProposal(TeamScopedRootMixin, UUIDTModel)`.

| Field                                           | Why                                                                                                                                        |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `team` FK (`db_constraint=False`)               | Tenant boundary. Mirrored from `hog_flow.team_id` in `save()`, exactly as `HogFlowRevision` does, so fail-closed reads filter on this row. |
| `hog_flow` FK, `related_name="proposals"`       | The workflow the change is for.                                                                                                            |
| `title`, `rationale`                            | What the agent proposes, and why, in prose a human reads.                                                                                  |
| `content` JSON                                  | The proposed change: a **subset** of `DRAFT_CONTENT_FIELDS`. Partial by design (see below).                                                |
| `base_version` int                              | The live version the proposal was authored against. Drives a staleness warning, never a hard block.                                        |
| `evidence` JSON                                 | `{metric, current_value, target_value, window, query, app_source_id}` — the numbers behind the claim, and the query to re-run them.        |
| `status`                                        | `suggested → approved → applied`, or `suggested → rejected`. The whole lifecycle a human resolves.                                         |
| `created_via`                                   | `web` / `api` / `mcp` / `self_driving`, **derived server-side** from `get_event_source(request)`. Not client-settable.                     |
| `source_type`                                   | `scout` / `responder` / `human` / `stub` — which kind of producer. Client-settable: transport cannot tell a Scout from a Responder.        |
| `source_id`                                     | Stable id of the producing run/finding, mirroring the Signals `source_id` convention. Unique per flow when set.                            |
| `created_by` FK User (null)                     | The human, when a human authored it.                                                                                                       |
| `resolved_at`, `resolved_by`, `resolution_note` | Who resolved it and what they said. Global resolution, not per-viewer.                                                                     |
| `applied_version` int (null)                    | The version the approved change went live as.                                                                                              |

Deliberately absent: any UI-state field (`seen`, `dismissed_for_me`, sort order).
The Autonomy Inbox and the workflow page must be able to read the same row and resolve it identically, so nothing on the model may assume who is looking at it.

`(hog_flow, source_id)` is unique when `source_id` is set, so an MCP retry or a re-emitted finding updates nothing and creates nothing rather than stacking duplicate proposals in a human's queue.

### Why `content` is partial

`restore_revision` stages a **full** snapshot because a revision is one.
A proposal is not: an agent changing an email subject should not have to send, or be trusted with, the whole graph.
So `content` holds only the fields it changes, and approve stages `{**snapshot_flow_content(live), **proposal.content}` — a full snapshot, which is what `_write_draft` guarantees and what publish's plain copy requires.
A proposal therefore stays applicable when unrelated parts of the flow have moved on.

Secrets are stripped from `content` on create.
An agent proposal has no business setting secret function inputs, and revision snapshots are secret-free for the same reason.

## API

On `HogFlowViewSet`, so the operations generate as `hog_flows_proposals_*` and become MCP tools from the same OpenAPI spec.

| Endpoint                                              | Does                                                                         |
| ----------------------------------------------------- | ---------------------------------------------------------------------------- |
| `GET  /api/projects/{team}/hog_flows/{id}/proposals/` | List, newest first, optional `?status=`                                      |
| `POST /api/projects/{team}/hog_flows/{id}/proposals/` | **The agent seam.** Create from `(content, evidence, rationale, provenance)` |
| `GET  .../proposals/{proposal_id}/`                   | Detail, with content and evidence                                            |
| `POST .../proposals/{proposal_id}/approve/`           | Stage into `draft`. Live untouched.                                          |
| `POST .../proposals/{proposal_id}/reject/`            | Resolve with an optional note                                                |

The create endpoint takes no in-app-session state: an MCP caller with a personal API key can post a proposal with provenance and nothing else.

Two of these are exposed as MCP tools in `products/workflows/mcp/tools.yaml`, both gated on the same flag: `workflows-propose-change` (create) and `workflows-list-proposals` (so an agent can see what was already rejected before proposing it again).
**Approve and reject are deliberately not MCP tools.** An agent can propose; only a person resolves.

### Approve reuses the restore pattern

Approve is `restore_revision` with an agent-authored snapshot in place of a historical one:

- `select_for_update` on the flow, and on the proposal row so a double-submit cannot resolve it twice.
- Refuses when a draft is already staged unless `overwrite` is passed, and fences the overwrite on `expected_draft_updated_at` — a draft edited since the dialog opened returns 409 rather than being clobbered.
- `draft_encrypted_inputs = None`: the staged content carries no secrets, so publish re-attaches them from the live encrypted column.
- No strict revalidation at stage time. Publish revalidates and recompiles bytecode, exactly as it does for a restored revision.
- A proposal not in `suggested` returns 409. That, plus the button's loading state, is the double-submission guard.

`applied` is set in `publish`, by a single indexed `UPDATE` that flips any `approved` proposal for that flow to `applied` with the published version. It is a no-op for every team that has no proposals, which is why it needs no flag check of its own.

## Feature flag

`self-optimising-workflows`.

- Backend: every proposal endpoint 404s when the flag is off for the team, so the surface does not exist.
- Frontend: `FEATURE_FLAGS.SELF_OPTIMISING_WORKFLOWS` gates the panel; the logic does not load without it.
- The `publish` hook is data-driven rather than flag-gated: no proposals, no effect.

## Stub generator (labelled stub, not the brain)

`python manage.py suggest_workflow_optimisations --team-id N [--workflow-id UUID] [--window -7d] [--live-run] [--force]`

One heuristic, and it is honest about being one:
read the live version's `email_sent` and `email_opened` from the versioned series per email step, and when a step's open rate is under target over enough sends, propose a shorter subject line on that step with the rate as evidence.
When no step qualifies it prints why and exits. Default is a dry run; `--live-run` writes.
`--force` proposes without evidence for demos against an empty metrics store, and records `forced: true` in the evidence so nobody mistakes it for a measured claim.

Its `source_id` is `stub:<flow>:v<version>:<step>:<date>`, so re-running the command on the same day resolves to the proposal it already made, but a newly published version can be proposed against again.

The real replacement is an Autonomy Scout: scheduled, prompted, reasoning over the same metrics, calling the same create endpoint over MCP.

Reading the versioned series turned up a live bug in the shared helper: `fetch_app_metric_totals` rendered its `instance_id` / `name` / `kind` placeholders into the SQL but never bound them, so every caller that passed one got a `KeyError` (a 500 on `GET .../metrics/totals?name=…` for hog functions and hog flows alike).
Fixed here, with a regression case in `posthog/api/test/test_app_metrics2.py`.

## Where A/B is stubbed

Out of scope, deliberately.
Approve stages a draft and stops; a human publishes.
The transition where A/B would begin is the moment a proposal is approved — instead of staging straight into `draft`, a future version would enrol the proposed revision as a variant against the live one, split traffic, and only stage the winner.
Nothing in this model forecloses that: the proposal already names a base version and carries the proposed content, which is what a variant needs.
Auto-apply of a winner without human approval stays out.

## Forward-compatibility with Autonomy

An Autonomy Scout can drive this without a schema change:

- provenance is a `created_via` + `source_type` + `source_id` triple, matching the Inbox convention, not an "agent vs human" boolean;
- a `WorkflowProposal` is Autonomy's "a change you should review" output type, with a status lifecycle a human resolves — it can sit beside "a change to merge" and "a report needing judgment" without special-casing;
- creation is a plain authenticated POST, which is how Autonomy agents act (public MCP server);
- resolution is global and IDs are stable, so the Inbox can render and resolve the same row the workflow page does.

The Inbox integration itself is not built here.

## Open questions

- **Evidence shape.** Free-form JSON in the prototype. A Scout writing arbitrary claims into it is only as trustworthy as the Scout; a typed shape (metric id, window, query, computed-at) would let the UI re-run the number instead of believing it.
- **Who owns the threshold.** The stub hardcodes one. A real Scout gets it from its prompt, which means the "why now" is unauditable unless the evidence records it.
- **Staleness policy.** `base_version` drives a warning today. A proposal authored against a version that has since been replaced twice may be nonsense, and nothing expires it.
- **Multiple pending proposals.** Allowed, and they can conflict: approving two in a row means the second overwrites the first's staged draft. Fencing catches the clobber, but nothing sequences the queue.
- **Metric read is a rate over a window, not a comparison.** Until a proposal has actually run, there is no counterfactual, which is exactly the gap A/B fills.
- **Per-version reads have no endpoint.** The generator queries `app_metrics2` directly. A versioned filter on `/metrics` is the natural next step (noted as such in CONTRIBUTING.md).
