import { expectLogic } from 'kea-test-utils'

import { useMocks } from '~/mocks/jest'
import { initKeaTests } from '~/test/init'

import { workflowLogic } from './workflowLogic'
import { workflowProposalsLogic } from './workflowProposalsLogic'

const WORKFLOW_ID = 'wf-proposals-1'
const PROPOSAL_ID = 'proposal-1'
const DRAFT_STAMP = '2026-05-02T00:00:00.000Z'

describe('workflowProposalsLogic', () => {
    let logic: ReturnType<typeof workflowProposalsLogic.build>
    let approveBodies: Record<string, any>[]
    let approveStatus: number

    const proposal = {
        id: PROPOSAL_ID,
        title: 'Shorten the subject line',
        rationale: 'Open rate is under target.',
        content: { actions: [] },
        evidence: { metric: 'email open rate', current_value: 0.11, target_value: 0.2, window: '-7d' },
        base_version: 3,
        is_stale: false,
        status: 'suggested',
        created_via: 'mcp',
        source_type: 'scout',
        source_id: 'run:1:finding:subject',
        created_by: null,
        created_at: '2026-05-01T00:00:00.000Z',
        resolved_at: null,
        resolved_by: null,
        resolution_note: '',
        applied_version: null,
    }

    beforeEach(() => {
        approveBodies = []
        approveStatus = 200
        useMocks({
            get: {
                '/api/environments/:team_id/hog_flows/:id/': {
                    id: WORKFLOW_ID,
                    name: 'Test',
                    version: 3,
                    status: 'active',
                    actions: [],
                    edges: [],
                    draft: { actions: [] },
                    draft_updated_at: DRAFT_STAMP,
                    updated_at: '2026-05-01T00:00:00.000Z',
                },
                '/api/projects/:team_id/hog_flows/:id/proposals/': { count: 1, results: [proposal] },
                '/api/projects/:team_id/hog_function_templates/': { results: [], count: 0 },
            },
            post: {
                '/api/projects/:team_id/hog_flows/:id/proposals/:proposal_id/approve/': async ({ request }) => {
                    approveBodies.push((await request.json()) as Record<string, any>)
                    return [approveStatus, approveStatus === 200 ? proposal : { code: 'stale_update' }]
                },
                '/api/projects/:team_id/hog_flows/:id/proposals/:proposal_id/reject/': {
                    ...proposal,
                    status: 'rejected',
                },
            },
        })
        initKeaTests()
        logic = workflowProposalsLogic({ id: WORKFLOW_ID })
        logic.mount()
    })

    it('loads the pending queue on mount', async () => {
        await expectLogic(logic).toDispatchActions(['loadProposalsSuccess'])
        expect(logic.values.pendingProposals.map((p) => p.id)).toEqual([PROPOSAL_ID])
    })

    // The fence is the whole point: approve must carry the draft stamp the human confirmed against,
    // so a draft staged in another tab meanwhile is rejected by the server instead of overwritten.
    it('approving sends the draft stamp it saw as the overwrite fence', async () => {
        const flowLogic = workflowLogic({ id: WORKFLOW_ID })
        flowLogic.mount()
        await expectLogic(flowLogic).toDispatchActions(['loadWorkflowSuccess'])

        await expectLogic(logic, () => {
            logic.actions.approveProposal(PROPOSAL_ID)
        }).toDispatchActions([flowLogic.actionTypes.loadWorkflow])

        expect(approveBodies).toEqual([{ overwrite: true, expected_draft_updated_at: DRAFT_STAMP }])
        expect(logic.values.resolvingId).toBeNull()
    })

    it('a 409 reloads the workflow and the queue instead of leaving stale state on screen', async () => {
        approveStatus = 409
        const flowLogic = workflowLogic({ id: WORKFLOW_ID })
        flowLogic.mount()
        await expectLogic(flowLogic).toDispatchActions(['loadWorkflowSuccess'])

        await expectLogic(logic, () => {
            logic.actions.confirmApproveProposal(PROPOSAL_ID, DRAFT_STAMP)
        }).toDispatchActions([flowLogic.actionTypes.loadWorkflow, logic.actionTypes.loadProposals])

        expect(logic.values.resolvingId).toBeNull()
    })

    it('ignores a second resolve while one is in flight', async () => {
        await expectLogic(logic).toDispatchActions(['loadProposalsSuccess'])
        logic.actions.setResolvingId(PROPOSAL_ID)

        logic.actions.confirmApproveProposal(PROPOSAL_ID, DRAFT_STAMP)
        logic.actions.confirmRejectProposal(PROPOSAL_ID)
        await expectLogic(logic).toFinishAllListeners()

        expect(approveBodies).toEqual([])
    })
})
