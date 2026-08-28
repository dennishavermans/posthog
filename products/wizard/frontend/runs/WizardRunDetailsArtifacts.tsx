import { IconArrowRight, IconExternal, IconGitBranch, IconGithub } from '@posthog/icons'
import { LemonSkeleton, Link } from '@posthog/lemon-ui'

import type { WizardRunApi, WizardRunArtifactApi } from '../generated/api.schemas'
import { formatArtifactSize } from '../wizardRunDisplay'
import { WizardRunDiffStats } from './WizardRunDiffStats'

export function WizardRunDetailsArtifacts({
    run,
    artifacts,
    loading,
}: {
    run: WizardRunApi
    artifacts: WizardRunArtifactApi[]
    loading: boolean
}): JSX.Element {
    if (loading) {
        return <LemonSkeleton repeat={2} className="h-12 w-full" />
    }

    if (artifacts.length === 0) {
        return (
            <p className="m-0 text-sm text-muted">
                {run.status === 'created' || run.status === 'running'
                    ? 'Artifacts will appear here when the Wizard produces them.'
                    : 'This run did not produce any artifacts.'}
            </p>
        )
    }

    const pullRequest = artifacts.find((artifact) => artifact.artifact_type === 'pull_request')
    const gitDiff = artifacts.find((artifact) => artifact.artifact_type === 'git_diff')

    return (
        <div className="flex flex-col gap-2">
            {pullRequest && (
                <Link
                    to={pullRequest.url}
                    target="_blank"
                    targetBlankIcon={false}
                    className="flex flex-col gap-2 rounded border bg-fill-highlight-100 p-3 text-primary hover:text-primary"
                >
                    <span className="flex items-center justify-between">
                        <span className="flex items-center gap-2 font-semibold">
                            <IconGithub />
                            Pull request #{pullRequest.number}
                        </span>
                        <IconExternal />
                    </span>
                    <span className="flex flex-wrap items-center justify-between gap-2">
                        <span className="flex min-w-0 items-center gap-1 text-xs text-muted">
                            <IconGitBranch className="shrink-0" />
                            <span className="truncate">{pullRequest.base_branch}</span>
                            <IconArrowRight className="shrink-0" />
                            <span className="truncate">{pullRequest.head_branch}</span>
                        </span>
                        {gitDiff && <WizardRunDiffStats additions={gitDiff.additions} removals={gitDiff.removals} />}
                    </span>
                </Link>
            )}
            {gitDiff && (
                <div className="flex items-center justify-between rounded border p-3">
                    <span className="flex items-center gap-2 font-semibold">
                        <IconGitBranch /> Git diff
                    </span>
                    <span className="flex items-center gap-3">
                        <WizardRunDiffStats additions={gitDiff.additions} removals={gitDiff.removals} />
                        <span className="text-xs text-muted">{formatArtifactSize(gitDiff.size_bytes)}</span>
                    </span>
                </div>
            )}
        </div>
    )
}
