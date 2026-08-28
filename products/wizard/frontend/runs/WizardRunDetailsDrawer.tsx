import { IconCopy, IconPlus, IconRefresh, IconStopFilled } from '@posthog/icons'
import { LemonBanner, LemonButton, LemonDivider, LemonDrawer } from '@posthog/lemon-ui'

import { CopyToClipboardInline } from 'lib/components/CopyToClipboard'
import { TZLabel } from 'lib/components/TZLabel'

import type { WizardRunApi, WizardRunArtifactApi } from '../generated/api.schemas'
import { wizardRunCurrentState, wizardRunIsActive, wizardWorkspaceLabel } from '../wizardRunDisplay'
import { WizardRunDetailsArtifacts } from './WizardRunDetailsArtifacts'
import { WizardRunEnvironmentTag } from './WizardRunEnvironmentTag'
import { WizardRunError } from './WizardRunError'
import { wizardRunErrorDetails } from './wizardRunErrorCatalog'
import { WizardRunProgress } from './WizardRunProgress'
import { WizardRunStatusTag } from './WizardRunStatusTag'

export function WizardRunDetailsDrawer({
    run,
    artifacts,
    artifactsLoading,
    refreshing,
    cancelling,
    onClose,
    onRefresh,
    onCopyRunId,
    onCancel,
    onRunAgain,
}: {
    run: WizardRunApi | null
    artifacts: WizardRunArtifactApi[]
    artifactsLoading: boolean
    refreshing: boolean
    cancelling: boolean
    onClose: () => void
    onRefresh: () => void
    onCopyRunId: (runId: string) => void
    onCancel: (run: WizardRunApi) => void
    onRunAgain: (run: WizardRunApi) => void
}): JSX.Element {
    const pullRequest = artifacts.find((artifact) => artifact.artifact_type === 'pull_request')
    const runError = run?.status === 'failed' ? wizardRunErrorDetails(run.error_code, run.error_message) : null

    return (
        <LemonDrawer
            isOpen={!!run}
            onClose={onClose}
            width={460}
            overlayTransparent
            title={
                run ? (
                    <div className="flex w-full items-center justify-between gap-2 pr-8">
                        <span>{run.program.name}</span>
                        <WizardRunStatusTag status={run.status} />
                    </div>
                ) : (
                    'Wizard run'
                )
            }
            footer={
                run ? (
                    <div className="flex w-full items-center justify-between gap-2">
                        {run.status === 'completed' ? (
                            <LemonButton onClick={() => onRunAgain(run)}>Run again</LemonButton>
                        ) : (
                            <LemonButton icon={<IconCopy />} onClick={() => onCopyRunId(run.id)}>
                                Copy run ID
                            </LemonButton>
                        )}

                        {pullRequest ? (
                            <LemonButton type="primary" icon={<IconPlus />} to={pullRequest.url} targetBlank>
                                Open pull request
                            </LemonButton>
                        ) : wizardRunIsActive(run) ? (
                            <LemonButton
                                status="danger"
                                icon={<IconStopFilled />}
                                onClick={() => onCancel(run)}
                                loading={cancelling}
                            >
                                Cancel run
                            </LemonButton>
                        ) : (
                            <LemonButton type="primary" onClick={() => onRunAgain(run)}>
                                Run again
                            </LemonButton>
                        )}
                    </div>
                ) : null
            }
        >
            {run && (
                <div className="space-y-5">
                    <dl className="space-y-3 text-sm">
                        <div className="grid grid-cols-[120px_1fr] items-center gap-3">
                            <dt className="text-xs font-semibold uppercase text-muted">Workspace</dt>
                            <dd className="m-0 break-all">{wizardWorkspaceLabel(run)}</dd>
                        </div>
                        <div className="grid grid-cols-[120px_1fr] items-center gap-3">
                            <dt className="text-xs font-semibold uppercase text-muted">Environment</dt>
                            <dd className="m-0">
                                <WizardRunEnvironmentTag environment={run.environment} />
                            </dd>
                        </div>
                        <div className="grid grid-cols-[120px_1fr] items-center gap-3">
                            <dt className="text-xs font-semibold uppercase text-muted">Started</dt>
                            <dd className="m-0">
                                {run.started_at ? (
                                    <TZLabel time={run.started_at} />
                                ) : (
                                    <span className="text-muted">Not started</span>
                                )}
                            </dd>
                        </div>
                        <div className="grid grid-cols-[120px_1fr] items-center gap-3">
                            <dt className="text-xs font-semibold uppercase text-muted">Run ID</dt>
                            <dd className="m-0 font-mono text-xs">
                                <CopyToClipboardInline
                                    explicitValue={run.id}
                                >{`${run.id.slice(0, 8)}…`}</CopyToClipboardInline>
                            </dd>
                        </div>
                    </dl>

                    <LemonDivider />

                    <section>
                        <div className="mb-3 flex items-center justify-between">
                            <h4 className="m-0">Artifacts</h4>
                            {wizardRunIsActive(run) && <span className="text-xs text-muted">Pending</span>}
                        </div>
                        <WizardRunDetailsArtifacts run={run} artifacts={artifacts} loading={artifactsLoading} />
                    </section>

                    <LemonDivider />

                    <section>
                        <div className="mb-3 flex items-center justify-between gap-2">
                            <h4 className="m-0">Current state</h4>
                            {wizardRunIsActive(run) && (
                                <span className="flex items-center gap-1 text-xs text-success">
                                    <IconRefresh className="animate-spin" /> Live updates · Just now
                                </span>
                            )}
                        </div>
                        <LemonBanner
                            type={
                                run.status === 'completed'
                                    ? 'success'
                                    : run.status === 'failed'
                                      ? 'error'
                                      : run.status === 'cancelled'
                                        ? 'warning'
                                        : 'info'
                            }
                        >
                            {runError ? (
                                <WizardRunError error={runError} />
                            ) : (
                                <>
                                    <div className="font-semibold">{wizardRunCurrentState(run)}</div>
                                    <div className="text-sm">
                                        {run.status === 'completed'
                                            ? `${artifacts.length} artifact${artifacts.length === 1 ? '' : 's'} produced.`
                                            : wizardRunIsActive(run)
                                              ? 'Updates appear here automatically.'
                                              : 'The run has ended.'}
                                    </div>
                                </>
                            )}
                        </LemonBanner>
                    </section>

                    <section>
                        <h4 className="mb-4">Progress</h4>
                        <WizardRunProgress run={run} />
                        <div className="mt-4 flex items-center justify-between border-t pt-3 text-xs text-muted">
                            <span>
                                {run.status === 'completed' && run.finished_at ? (
                                    <>
                                        Completed <TZLabel time={run.finished_at} />.
                                    </>
                                ) : (
                                    'Updates automatically. Last checked just now.'
                                )}
                            </span>
                            <LemonButton
                                size="small"
                                icon={run.status === 'completed' ? undefined : <IconRefresh />}
                                onClick={() => (run.status === 'completed' ? onRunAgain(run) : onRefresh())}
                                loading={run.status === 'completed' ? false : refreshing}
                            >
                                {run.status === 'completed' ? 'Run again' : 'Refresh'}
                            </LemonButton>
                        </div>
                    </section>
                </div>
            )}
        </LemonDrawer>
    )
}
