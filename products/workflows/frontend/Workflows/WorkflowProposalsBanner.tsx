import { useActions, useValues } from 'kea'

import { IconBolt } from '@posthog/icons'
import { LemonButton, LemonTag, Tooltip } from '@posthog/lemon-ui'

import { AccessControlAction } from 'lib/components/AccessControlAction'
import { TZLabel } from 'lib/components/TZLabel'
import { LemonCollapse } from 'lib/lemon-ui/LemonCollapse'

import { AccessControlLevel, AccessControlResourceType } from '~/types'

import type { WorkflowProposalApi, WorkflowProposalSourceTypeEnumApi } from '../generated/api.schemas'
import { workflowLogic } from './workflowLogic'
import { workflowProposalsLogic } from './workflowProposalsLogic'

const SOURCE_LABELS: Record<WorkflowProposalSourceTypeEnumApi, string> = {
    scout: 'Suggested by a scout',
    responder: 'Suggested by a responder',
    human: 'Suggested by a person',
    stub: 'Suggested by a stub generator',
}

export function WorkflowProposalsBanner({ id }: { id: string }): JSX.Element | null {
    const logic = workflowProposalsLogic({ id })
    const { pendingProposals, resolvingId } = useValues(logic)
    const { approveProposal, rejectProposal } = useActions(logic)
    const { workflowUserAccessLevel } = useValues(workflowLogic({ id }))

    if (!pendingProposals.length) {
        return null
    }

    return (
        <div className="flex flex-col gap-2">
            {pendingProposals.map((proposal) => (
                <div key={proposal.id} className="border rounded p-3 bg-surface-primary flex flex-col gap-2">
                    <div className="flex items-start gap-2">
                        <IconBolt className="text-lg shrink-0 mt-0.5" />
                        <div className="flex flex-col gap-1 grow">
                            <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold">{proposal.title}</span>
                                <LemonTag type="highlight">{SOURCE_LABELS[proposal.source_type]}</LemonTag>
                                {proposal.is_stale && (
                                    <Tooltip title="The live workflow has changed since this was suggested. Check it still makes sense before you publish.">
                                        <LemonTag type="warning">Out of date</LemonTag>
                                    </Tooltip>
                                )}
                            </div>
                            <p className="mb-0 text-secondary">{proposal.rationale}</p>
                            <EvidenceSummary evidence={proposal.evidence} />
                            <span className="text-xs text-secondary">
                                Suggested <TZLabel time={proposal.created_at} /> against version {proposal.base_version}
                            </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                            <AccessControlAction
                                resourceType={AccessControlResourceType.Workflow}
                                minAccessLevel={AccessControlLevel.Editor}
                                userAccessLevel={workflowUserAccessLevel ?? undefined}
                            >
                                <LemonButton
                                    type="secondary"
                                    size="small"
                                    onClick={() => rejectProposal(proposal.id)}
                                    disabledReason={
                                        resolvingId !== null && resolvingId !== proposal.id
                                            ? 'Another suggestion is being resolved'
                                            : undefined
                                    }
                                >
                                    Reject
                                </LemonButton>
                            </AccessControlAction>
                            <AccessControlAction
                                resourceType={AccessControlResourceType.Workflow}
                                minAccessLevel={AccessControlLevel.Editor}
                                userAccessLevel={workflowUserAccessLevel ?? undefined}
                            >
                                <LemonButton
                                    type="primary"
                                    size="small"
                                    onClick={() => approveProposal(proposal.id)}
                                    loading={resolvingId === proposal.id}
                                    disabledReason={
                                        resolvingId !== null && resolvingId !== proposal.id
                                            ? 'Another suggestion is being resolved'
                                            : undefined
                                    }
                                >
                                    Approve as draft
                                </LemonButton>
                            </AccessControlAction>
                        </div>
                    </div>
                    <LemonCollapse
                        size="small"
                        panels={[
                            {
                                key: 'details',
                                header: 'What it changes and why',
                                content: <ProposalDetails proposal={proposal} />,
                            },
                        ]}
                    />
                </div>
            ))}
        </div>
    )
}

function EvidenceSummary({ evidence }: { evidence: Record<string, unknown> }): JSX.Element | null {
    const metric = typeof evidence.metric === 'string' ? evidence.metric : null
    if (!metric) {
        return null
    }
    const current = formatValue(evidence.current_value)
    const target = formatValue(evidence.target_value)
    const window = typeof evidence.window === 'string' ? evidence.window : null

    return (
        <span className="text-sm">
            {metric}: {current ?? 'no data'}
            {target ? `, target ${target}` : ''}
            {window ? ` over ${window}` : ''}
        </span>
    )
}

function ProposalDetails({ proposal }: { proposal: WorkflowProposalApi }): JSX.Element {
    const changedFields = Object.keys(proposal.content)

    return (
        <div className="flex flex-col gap-2 text-sm">
            <div>
                <span className="font-semibold">Workflow fields it changes: </span>
                {changedFields.length ? changedFields.join(', ') : 'none'}
            </div>
            <div className="flex flex-col gap-1">
                <span className="font-semibold">Evidence</span>
                <pre className="text-xs bg-surface-secondary rounded p-2 overflow-x-auto mb-0">
                    {JSON.stringify(proposal.evidence, null, 2)}
                </pre>
            </div>
            {proposal.source_id && (
                <div>
                    <span className="font-semibold">Source: </span>
                    {proposal.source_id}
                </div>
            )}
        </div>
    )
}

function formatValue(value: unknown): string | null {
    if (typeof value !== 'number') {
        return null
    }
    return value > 0 && value <= 1 ? `${(value * 100).toFixed(1)}%` : String(value)
}
