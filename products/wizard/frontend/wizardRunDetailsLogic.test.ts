import { expectLogic } from 'kea-test-utils'

import { projectLogic } from 'scenes/projectLogic'

import { initKeaTests } from '~/test/init'

import { wizardRunsArtifactsList, wizardRunsRetrieve } from './generated/api'
import type { WizardRunApi } from './generated/api.schemas'
import { wizardRunDetailsLogic } from './wizardRunDetailsLogic'

jest.mock('./generated/api', () => ({
    wizardRunsArtifactsList: jest.fn(),
    wizardRunsPartialUpdate: jest.fn(),
    wizardRunsRetrieve: jest.fn(),
}))

const mockWizardRunsArtifactsList = wizardRunsArtifactsList as jest.Mock
const mockWizardRunsRetrieve = wizardRunsRetrieve as jest.Mock

function makeRun(): WizardRunApi {
    return {
        id: 'run-1',
        team_id: 1,
        created_by_id: 1,
        environment: 'cloud',
        workspace: { type: 'git_repository', repository: 'posthog/posthog' },
        program: {
            id: 'posthog-integration',
            name: 'PostHog integration',
            description: 'Set up PostHog',
            wizard_version: '2.6.0',
            command: [],
            tags: [],
            required_programs: [],
            supported_environments: ['local', 'cloud'],
        },
        status: 'running',
        error_code: null,
        error_message: null,
        stage: 'executing_wizard',
        created_at: '2026-08-26T10:00:00Z',
        updated_at: '2026-08-26T10:01:00Z',
        started_at: '2026-08-26T10:00:30Z',
        finished_at: null,
        deadline_at: '2026-08-26T11:00:00Z',
    }
}

describe('wizardRunDetailsLogic', () => {
    let logic: ReturnType<typeof wizardRunDetailsLogic.build>

    beforeEach(async () => {
        initKeaTests()
        mockWizardRunsRetrieve.mockReset()
        mockWizardRunsArtifactsList.mockReset()
        mockWizardRunsRetrieve.mockResolvedValue(makeRun())
        mockWizardRunsArtifactsList.mockResolvedValue([])
        await expectLogic(projectLogic).toMatchValues({ currentProjectId: expect.any(Number) })
        logic = wizardRunDetailsLogic()
        logic.mount()
    })

    afterEach(() => {
        logic.unmount()
    })

    it('loads run details and artifacts through separate endpoints', async () => {
        logic.actions.selectRun(makeRun())

        await expectLogic(logic)
            .toFinishAllListeners()
            .toMatchValues({
                selectedRun: expect.objectContaining({ id: 'run-1' }),
                selectedRunArtifacts: [],
                selectedRunArtifactsInitialLoading: false,
            })

        expect(mockWizardRunsRetrieve).toHaveBeenCalledWith(expect.any(String), 'run-1')
        expect(mockWizardRunsArtifactsList).toHaveBeenCalledWith(expect.any(String), 'run-1')
    })

    it('keeps resolved artifact state visible during a refresh', async () => {
        logic.actions.selectRun(makeRun())
        await expectLogic(logic).toFinishAllListeners()

        mockWizardRunsArtifactsList.mockReturnValue(new Promise(() => {}))
        logic.actions.refreshSelectedRun()

        await expectLogic(logic).toMatchValues({
            runArtifactsLoading: true,
            selectedRunArtifactsInitialLoading: false,
        })
    })
})
