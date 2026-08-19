# Wizard runs implementation plan

Last updated: 2026-08-19

## Working agreement

- Codex writes one small TDD increment at a time.
- Codex verifies the focused test fails before implementing each behavior.
- Codex runs the focused and affected suites after implementation.
- Every green TDD increment is committed separately for review.
- Production code, tests, and cleanup move together in the same commit.
- Unrelated worktree changes remain untouched.

## Domain vocabulary

| Concept       | Definition                                                                                                              |
| ------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Workspace     | A user-provided project on which the setup agent operates.                                                              |
| Wizard        | The setup agent distributed as an npm package. It owns its harness and skills, and uses the AI gateway for token spend. |
| Wizard run    | One execution of Wizard inside a workspace.                                                                             |
| Environment   | Where a run executes: the user's machine for `local`, or PostHog-provisioned infrastructure for `cloud`.                |
| Wizard Worker | A provisioned cloud sandbox while it is executing a Wizard run.                                                         |
| Run Artifact  | A durable representation of changes produced by a run, such as a Git diff, pull request, or updated archive.            |

### Workspace types

- Local folder
  - V0 metadata: `project_name`.
  - Runs in a local environment.
- Git repository
  - V0 metadata: `repository` in `owner/name` form.
  - Runs in a cloud environment.
- Uploaded archive
  - Future metadata: an object-storage reference, file metadata, and integrity information.
  - Runs in a cloud environment.
  - Archive bytes must not be stored in Postgres or passed through Temporal payloads.

### Supported configurations

| Environment | Workspace        | Delivery |
| ----------- | ---------------- | -------- |
| Local       | Local folder     | V0       |
| Cloud       | Git repository   | V0       |
| Cloud       | Uploaded archive | Future   |

All other environment and workspace combinations are invalid unless explicitly added later.

## Scope

### V0

- Represent local-folder and Git-repository workspaces with typed contracts.
- Create and persist local and cloud Wizard runs.
- Require a team GitHub integration for Git-repository cloud runs.
- Verify that the integration can access the requested repository.
- Execute cloud runs in a Tasks sandbox through a Temporal workflow.
- Pass the Wizard run ID to the npm setup agent.
- Reuse the current Wizard state-update system.
- Persist run lifecycle status and error code.
- Produce a Git diff Run Artifact or a reference to it.
- Preserve the existing Wizard session API during migration.

### Future

- Uploaded-archive workspaces.
- Updated-archive artifacts.
- Pull-request artifacts.
- Append-only state updates owned by individual Wizard runs.
- Multiple execution attempts and an attempt-level audit trail.
- Additional workspace kinds and artifact kinds when a concrete use case requires them.

## Architecture boundaries

```text
presentation
    -> facade/api.py
        -> logic/runs.py
            -> logic/run_domain.py
            -> Wizard models
            -> Tasks facades
            -> Temporal client

Temporal workflow
    -> Wizard activities
        -> Wizard application logic
        -> Tasks Sandbox facade
```

- `products/wizard/backend/facade/api.py` remains Wizard's only public Python interface.
- Public inputs and DTOs live in `products/wizard/backend/facade/contracts.py`.
- Public enums and serialized discriminators live in `products/wizard/backend/facade/enums.py`.
- Public typed errors live in `products/wizard/backend/facade/errors.py`.
- Application orchestration and persistence live in `products/wizard/backend/logic/runs.py`.
- Pure run rules live in `products/wizard/backend/logic/run_domain.py`.
- `WizardSessionRunPhase` belongs to the legacy state stream; `WizardRunStatus` belongs to the persisted run lifecycle.
- Wizard may call `products.tasks.backend.facade.*`, but must not import Tasks models or internal logic.
- Temporal workflows remain deterministic and do not access Django, GitHub, Sandbox, or the network.
- Temporal activities perform database and external operations.
- Secrets are created and consumed inside activities. They must not enter Temporal inputs, results, logs, or persisted workspace metadata.
- Large results are stored by reference. Temporal payloads contain IDs and small typed results only.

## Current state

- [x] Define run statuses: created, running, completed, failed, and canceled.
- [x] Define allowed status transitions.
- [x] Keep terminal statuses final and reject idempotent transitions.
- [x] Allow failed runs to include an optional typed error code.
- [x] Reject transition metadata that does not match the destination status.
- [x] Add `WizardRun`, team scoping, UUID identity, timestamps, and hot-table-safe relationships.
- [x] Add and apply the initial Wizard run migration locally.
- [x] Add `create_run` through the Wizard facade.
- [x] Create local runs in running state.
- [x] Create cloud runs in created state before provisioning a Wizard Worker.
- [x] Check the team GitHub integration and repository access for the current cloud-run input shape.
- [x] Replace the temporary `repository` input shape with workspace contracts.
- [x] Persist workspace metadata.
- [x] Separate facade contracts, enums, errors, application logic, and pure run rules.
- [ ] Add Temporal execution.
- [x] Add Run Artifacts.

The active step is adding persisted lifecycle operations.

## Reconciliation with the workspace specification

This audit covers all Wizard run work completed before the environment and workspace vocabulary was established.

| Existing work                                     | Decision          | Required follow-up                                                                                                       |
| ------------------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `WizardRun` UUID, team, creator, and timestamps   | Keep              | Make `created_by_id` nullable in the DTO because the model uses `SET_NULL`.                                              |
| Run status enum and transition matrix             | Keep              | Move the pure rules to `logic/run_domain.py` after the workspace refactor.                                               |
| Separate outcome and error code                   | Replace           | Run Artifacts represent successful output. Keep error codes for failed runs and remove outcome.                          |
| `WizardRunSurface`                                | Replace           | Use `WizardRunEnvironment` everywhere, including persistence and DTOs.                                                   |
| `LocalWizardRunTarget` and `CloudWizardRunTarget` | Remove            | Replace them with typed local-folder and Git-repository workspaces.                                                      |
| Top-level `repository` on `CreateWizardRunInput`  | Remove            | Read repository metadata only from `GitRepositoryWorkspace`.                                                             |
| `MissingRepositoryError`                          | Remove            | A Git-repository workspace structurally requires its repository field. Presentation validation handles an omitted field. |
| `MissingGithubIntegrationError`                   | Rename            | Use `MissingGitHubIntegrationError`.                                                                                     |
| `RepositoryNotAccessibleError`                    | Keep              | Raise it only for a Git-repository workspace after team integration resolution.                                          |
| Tasks repository-access facade                    | Keep with cleanup | Return or accept facade-owned identifiers so Wizard does not inspect `integration.integration.id`.                       |
| `create_run` facade flow                          | Keep and adapt    | Validate the environment/workspace pair, perform workspace-specific admission, then persist the typed workspace.         |
| Existing local creation test                      | Keep and adapt    | Supply `LocalFolderWorkspace(project_name=...)` and assert the returned workspace.                                       |
| Existing cloud admission tests                    | Keep and adapt    | Supply `GitRepositoryWorkspace(repository=...)` and mock only facade-owned return values.                                |
| Initial `WizardRun` migration                     | Keep              | Add linear follow-up migrations for environment and workspace fields. Inspect SQL before applying.                       |
| Existing Wizard state system                      | Keep for V0       | Correlate updates with the Wizard run ID without introducing state-history models yet.                                   |

### Reconciliation order

1. Finish and test the environment/workspace compatibility rule.
2. Replace temporary target and repository contracts with `WizardWorkspace`.
3. Adapt creation logic and tests to dispatch on the workspace variant.
4. Persist workspace type and metadata, then migrate the database.
5. Clean the Tasks facade so Wizard does not inspect Tasks-owned objects.
6. Re-run the transition and creation suites before starting lifecycle persistence.

## Implementation plan

### 1. Establish environment and workspace rules

- [x] Add `WizardRunEnvironment` with `LOCAL` and `CLOUD`.
- [x] Add `LocalFolderWorkspace` with `project_name`.
- [x] Add `GitRepositoryWorkspace` with `repository`.
- [x] Define the typed `WizardWorkspace` union.
- [x] Add an explicit serialized discriminator for each workspace type.
- [x] Add `InvalidWorkspaceEnvironmentError`.
- [x] Implement the environment and workspace compatibility rule.
- [x] Test every supported and rejected V0 combination with a parameterized matrix.
- [ ] Keep `UploadedArchiveWorkspace` out of executable V0 code until archive delivery begins.

### 2. Move run creation to the new contracts

- [x] Change `CreateWizardRunInput` to accept `environment`.
- [x] Change `CreateWizardRunInput` to accept a typed `workspace`.
- [x] Change `WizardRunDTO` to return `environment`.
- [x] Change `WizardRunDTO` to return a typed `workspace`.
- [x] Update local creation tests to use `LocalFolderWorkspace`.
- [x] Update cloud creation tests to use `GitRepositoryWorkspace`.
- [x] Remove `MissingRepositoryError`; the Git-repository contract structurally requires a repository.
- [x] Rename `MissingGithubIntegrationError` to `MissingGitHubIntegrationError`.
- [x] Remove the temporary target contracts after all callers migrate.
- [x] Remove `WizardRunSurface` after all callers migrate to `WizardRunEnvironment`.
- [x] Ensure local creation never resolves GitHub data.
- [x] Ensure invalid input creates no database row.

### 3. Persist environment and workspace metadata

- [x] Choose the final V0 storage shape after inspecting query requirements.
  - Preferred starting point: queryable `environment` and `workspace_type` fields plus JSON workspace metadata.
  - Store only typed, non-secret metadata.
- [x] Serialize typed workspaces into model fields in one private mapper.
- [x] Deserialize model fields into typed facade contracts in `_to_dto`.
- [x] Add workspace fields to the branch-only initial migration without modifying migrations on `master`.
- [x] Keep foreign keys to Team and User free of database constraints.
- [x] Inspect `sqlmigrate` output before applying the migration.
- [x] Apply the migration locally with orphan checking skipped only if the existing branch-switching issue recurs.
- [x] Test local and cloud persistence through `facade/api.py`.
- [ ] Test malformed persisted workspace data as an explicit typed failure if it can occur in production.

### 4. Complete Git-repository admission

- [x] Keep repository checks in the Wizard application service, outside pure domain rules.
- [x] Resolve only team-owned GitHub integrations through the Tasks facade.
- [x] Reject a cloud Git-repository run when the team has no GitHub integration.
- [x] Reject repositories the resolved integration cannot access.
- [ ] Treat missing and inaccessible repositories as the same external result to avoid revealing private repository existence.
- [x] Validate the `owner/name` shape before calling GitHub-backed services.
- [ ] Recheck integration and repository access when cloud execution starts because access can change after creation.
- [ ] Confirm that all required GitHub and token operations are available through public facades.
- [x] Add a Tasks facade method that returns the selected integration ID without leaking a Tasks-owned object.

### 5. Add persisted lifecycle operations

- [x] Add an internal, team-scoped run lookup.
- [x] Add a typed run-not-found error that does not disclose another team's run.
- [x] Lock the run row with `select_for_update` during lifecycle changes.
- [x] Persist created to running through the existing transition rules.
- [x] Persist successful completion. Run Artifacts represent any produced changes.
- [x] Persist failure with an optional typed error code.
- [x] Persist cancellation without terminal metadata.
- [x] Leave the stored row unchanged when a transition fails validation.
- [x] Make repeated or concurrent terminal updates deterministic.
- [x] Keep generic transition persistence private. Public operations express intent or are driven by execution.
- [ ] Expose cancellation through HTTP only when a user-facing cancellation flow is added.

### 6. Define Run Artifacts

- [x] Add `WizardRunArtifactType` with the V0 `GIT_DIFF` type.
- [x] Decide whether metadata belongs in a separate team-scoped artifact model or an object-storage manifest.
- [x] Store large diffs in object storage and persist a reference.
- [ ] Never return large diff contents through a Temporal activity result.
- [x] Associate every artifact with one run and team.
- [x] Return typed artifact metadata through the Wizard facade.
- [x] Define the no-changes result without creating an empty artifact.
- [x] Reserve pull-request and updated-archive artifact types for their implementation phases.

### 7. Add Temporal contracts and registration

- [ ] Create `products/wizard/backend/temporal/contracts.py`.
- [ ] Define a small workflow input containing `team_id` and `run_id`.
- [ ] Create `products/wizard/backend/temporal/workflows/execute_run.py`.
- [ ] Create `products/wizard/backend/temporal/activities/lifecycle.py`.
- [ ] Create `products/wizard/backend/temporal/activities/execute_cloud.py`.
- [ ] Create `products/wizard/backend/temporal/client.py`.
- [ ] Register workflows and activities in `products/wizard/backend/temporal/__init__.py`.
- [ ] Confirm how the shared Temporal worker discovers product-owned registrations.
- [ ] Add a registration test.
- [ ] Use a deterministic workflow ID derived from the Wizard run UUID.
- [ ] Pass IDs through Temporal rather than serialized model or workspace contents.

### 8. Implement the cloud workflow

- [ ] Mark the run as running in a lifecycle activity.
- [ ] Load and validate the Git-repository workspace in the execution activity.
- [ ] Resolve the current GitHub integration and authorize the repository again.
- [ ] Create short-lived GitHub and Wizard credentials inside the execution activity.
- [ ] Provision a sandbox through `products.tasks.backend.facade.sandbox`.
- [ ] Clone the repository into a stable sandbox workspace path.
- [ ] Run the npm Wizard in headless mode with the Wizard run ID.
- [ ] Apply explicit execution, heartbeat, and sandbox TTL timeouts.
- [ ] Clean up the sandbox in `finally` for success, failure, timeout, and cancellation.
- [ ] Collect a Git diff and persist a Run Artifact reference.
- [ ] Complete the run and associate any produced Run Artifacts.
- [ ] Map sandbox or activity timeout to the timeout error code.
- [ ] Map other execution failures to a typed error code before enabling broad retries.
- [ ] Mark canceled executions as canceled.
- [ ] Avoid retrying irreversible side effects without an idempotency strategy.

### 9. Dispatch cloud runs

- [ ] Start the Temporal workflow only after the run row commits.
- [ ] Use `transaction.on_commit` for workflow dispatch.
- [ ] Keep local run creation free of Temporal dispatch.
- [ ] Handle duplicate workflow starts idempotently.
- [ ] Decide what happens when workflow dispatch fails after the run commits.
- [ ] Add an observable dispatch-failed state if operational recovery requires it.
- [ ] Test dispatch through the facade while mocking only the Temporal client boundary.

### 10. Reuse V0 state synchronization

- [ ] Document the current state-update endpoint and payload used by the npm Wizard.
- [ ] Pass the existing Wizard run ID to both local and cloud executions.
- [ ] Ensure a local setup agent creates its run before sending updates.
- [ ] Ensure a Wizard Worker receives the pre-created run ID.
- [ ] Bind updates to both `team_id` and `run_id`.
- [ ] Preserve the existing Wizard session API and frontend stream behavior.
- [ ] Add a compatibility test for the existing state-update path.
- [ ] Keep V1 append-only run state updates out of the V0 migration.

### 11. Add presentation and API support

- [x] Add discriminated workspace serializers under `products/wizard/backend/presentation/runs.py`.
- [x] Validate missing and unknown workspace discriminators without database access.
- [ ] Add one database-backed endpoint test as a serializer wiring guard.
- [ ] Add request and response schema annotations.
- [ ] Add create, retrieve, and any required status endpoints through `routes.py`.
- [ ] Enforce team scoping from request context.
- [ ] Return typed errors with actionable public messages.
- [ ] Regenerate OpenAPI and product frontend types after serializer changes.
- [ ] Update relevant public documentation in the same PR when the API becomes user-facing.

### 12. Tests and verification

- [ ] Keep transition and compatibility matrices at the pure-function level.
- [ ] Keep persistence tests at the Django level through `facade/api.py`.
- [ ] Test Temporal orchestration with mocked activities.
- [ ] Test activities with Django and mocked Tasks, GitHub, AI gateway, and Sandbox boundaries.
- [ ] Do not use a real network, live GitHub repository, or arbitrary sleeps in automated tests.
- [ ] Test tenant isolation for run reads, writes, updates, and artifacts.
- [ ] Test sandbox cleanup after every terminal path.
- [ ] Run the focused Wizard run suite after every increment.
- [ ] Run Wizard product tests before each commit that completes a phase.
- [ ] Run formatting and lint checks on changed Python files.
- [ ] Run migration checks and inspect generated SQL for schema changes.
- [ ] Run `hogli ci:preflight --fix` before the first push.

### 13. Focused cleanup before review

- [x] Extract pure transition and environment/workspace rules to `logic/run_domain.py`.
- [x] Keep `logic/runs.py` as the application service.
- [ ] Remove temporary compatibility names after all call sites migrate.
- [ ] Review the purpose of untracked manual files `backend/test.py` and `backend/test2.py`; do not delete them without explicit confirmation.
- [ ] Remove comments that restate code and retain comments that explain a non-obvious constraint.
- [x] Confirm DTO nullability matches model nullability, including `created_by_id`.
- [ ] Confirm all cross-product imports point to facades.
- [ ] Update this tracker with final decisions and deferred work.

## Future archive phase

- [ ] Define `UploadedArchiveWorkspace` with an object-storage key and safe file metadata.
- [ ] Add authenticated upload initiation and completion endpoints.
- [ ] Enforce compressed and expanded size limits.
- [ ] Reject path traversal, symlink escape, archive bombs, and unsupported formats.
- [ ] Verify integrity before extraction.
- [ ] Materialize the archive only inside a sandbox.
- [ ] Produce a diff and optionally an updated archive.
- [ ] Store the updated archive in object storage with a bounded retention period.
- [ ] Return a short-lived download mechanism through a typed Run Artifact.
- [ ] Delete expired source and result archives according to the retention policy.

## Future state-history phase

- [ ] Define an append-only `WizardRunStateUpdate` owned by a team and run.
- [ ] Include ordering, timestamp, phase, progress, and a typed payload.
- [ ] Make duplicate client updates idempotent.
- [ ] Support reconnect and replay from a sequence cursor.
- [ ] Migrate local and cloud setup agents from the V0 state system.
- [ ] Remove the compatibility path only after all supported clients have migrated.

## Commands

Run commands from the repository root through Flox:

```bash
.codex/with-flox pytest -s products/wizard/backend/tests/runs
.codex/with-flox env DEBUG=1 ./manage.py makemigrations wizard -n <migration_name>
.codex/with-flox env DEBUG=1 ./manage.py sqlmigrate wizard <migration_name>
.codex/with-flox env DEBUG=1 ./manage.py migrate wizard --skip-orphan-check
```

Use `--skip-orphan-check` only for the known local database state caused by switching branches. Do not delete migration records manually.
