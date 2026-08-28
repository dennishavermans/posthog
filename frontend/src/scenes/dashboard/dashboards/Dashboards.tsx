import { useActions, useValues } from 'kea'
import isEqual from 'lodash/isEqual'
import posthog from 'posthog-js'
import { useEffect, useRef, useState } from 'react'

import * as chartPng from '@posthog/brand/hoggies/png/chart'
import { LemonButton, LemonDialog, LemonInput, LemonTag, lemonToast } from '@posthog/lemon-ui'

import { ApiError } from 'lib/api-error'
import { pngHoggie } from 'lib/brand/hoggies'
import { AccessControlAction } from 'lib/components/AccessControlAction'
import { ObjectTags } from 'lib/components/ObjectTags/ObjectTags'
import { ProductIntroduction } from 'lib/components/ProductIntroduction/ProductIntroduction'
import { Shortcut } from 'lib/components/Shortcuts/Shortcut'
import { keyBinds } from 'lib/components/Shortcuts/shortcuts'
import { LemonField } from 'lib/lemon-ui/LemonField'
import { LemonRadio } from 'lib/lemon-ui/LemonRadio'
import { LemonTab, LemonTabs } from 'lib/lemon-ui/LemonTabs'
import { ProfilePicture } from 'lib/lemon-ui/ProfilePicture'
import { getAccessControlDisabledReason } from 'lib/utils/accessControlUtils'
import { fullName } from 'lib/utils/strings'
import {
    DEFAULT_FILTERS,
    DashboardsFilters,
    DashboardsTab,
    dashboardsLogic,
} from 'scenes/dashboard/dashboards/dashboardsLogic'
import { DashboardTemplateModal } from 'scenes/dashboard/dashboards/templates/DashboardTemplateModal'
import { DashboardTemplatesTable } from 'scenes/dashboard/dashboards/templates/DashboardTemplatesTable'
import { DashboardTemplateEditor } from 'scenes/dashboard/DashboardTemplateEditor'
import { DeleteDashboardModal } from 'scenes/dashboard/DeleteDashboardModal'
import { DuplicateDashboardModal } from 'scenes/dashboard/DuplicateDashboardModal'
import { newDashboardLogic } from 'scenes/dashboard/newDashboardLogic'
import { NewDashboardModal } from 'scenes/dashboard/NewDashboardModal'
import { membersLogic } from 'scenes/organization/membersLogic'
import { sceneConfigurations } from 'scenes/scenes'
import { Scene, SceneExport } from 'scenes/sceneTypes'
import { teamLogic } from 'scenes/teamLogic'
import { userLogic } from 'scenes/userLogic'

import { SceneContent } from '~/layout/scenes/components/SceneContent'
import { SceneTitleSection } from '~/layout/scenes/components/SceneTitleSection'
import { dashboardsModel } from '~/models/dashboardsModel'
import { ProductKey } from '~/queries/schema/schema-general'
import { AccessControlLevel, AccessControlResourceType } from '~/types'

import {
    dashboardSavedViewsCreate,
    dashboardSavedViewsDestroy,
    dashboardSavedViewsList,
    dashboardSavedViewsPartialUpdate,
} from 'products/dashboards/frontend/generated/api'
import type {
    DashboardSavedViewApi,
    PatchedDashboardSavedViewApi,
    DashboardSavedViewWriteApiFilters,
} from 'products/dashboards/frontend/generated/api.schemas'
import { SavedDashboardViewsPicker } from 'products/dashboards/frontend/saved-views/SavedDashboardViewsPicker'

import { DashboardsTableContainer } from './DashboardsTable'
import { ManageDashboardSavedViews } from './ManageDashboardSavedViews'
import { FeaturedTemplatesChooser } from './templates/FeaturedTemplatesChooser'

const HedgehogChart = pngHoggie(chartPng)

const DASHBOARD_DOCS_URL = 'https://posthog.com/docs/product-analytics/dashboards'

export type DashboardListSavedView = Omit<DashboardSavedViewApi, 'filters'> & {
    filters: DashboardsFilters
}

export type DashboardSavedViewScope = NonNullable<DashboardListSavedView['scope']>

function savedViewFilterProperties(filters: DashboardsFilters): Record<string, boolean | number> {
    const tagCount = filters.tags?.length ?? 0
    const hasSearch = Boolean(filters.search)
    const hasFolder = filters.folder != null
    const hasTags = tagCount > 0
    const hasCreator = Array.isArray(filters.createdBy) && filters.createdBy.length > 0
    const isPinned = filters.pinned
    const isShared = filters.shared

    return {
        has_search_filter: hasSearch,
        has_folder_filter: hasFolder,
        has_tag_filter: hasTags,
        tag_count: tagCount,
        has_creator_filter: hasCreator,
        is_pinned: isPinned,
        is_shared: isShared,
        active_filter_count: [hasSearch, hasFolder, hasTags, hasCreator, isPinned, isShared].filter(Boolean).length,
    }
}

async function loadDashboardSavedViews(projectId: string): Promise<DashboardListSavedView[]> {
    const savedViews: DashboardListSavedView[] = []
    const savedViewIds = new Set<string>()
    let cursor: string | undefined

    while (true) {
        const response = await dashboardSavedViewsList(projectId, { limit: 100, cursor })
        for (const view of response.results) {
            if (!savedViewIds.has(view.id)) {
                savedViewIds.add(view.id)
                savedViews.push(view as unknown as DashboardListSavedView)
            }
        }

        if (!response.next || response.results.length === 0) {
            return savedViews
        }

        const nextCursor = new URL(response.next).searchParams.get('cursor')
        if (!nextCursor) {
            return savedViews
        }
        cursor = nextCursor
    }
}

function savedViewFilters(view: DashboardListSavedView): DashboardsFilters {
    return {
        ...DEFAULT_FILTERS,
        ...view.filters,
    }
}

function SavedViewVisibilityPicker({
    initialScope,
    onChange,
}: {
    initialScope: DashboardSavedViewScope
    onChange: (scope: DashboardSavedViewScope) => void
}): JSX.Element {
    const [scope, setScope] = useState<DashboardSavedViewScope>(initialScope)

    const selectScope = (nextScope: DashboardSavedViewScope): void => {
        setScope(nextScope)
        onChange(nextScope)
    }

    return (
        <div className="flex items-center gap-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-secondary">Visibility</div>
            <LemonRadio<DashboardSavedViewScope>
                value={scope}
                onChange={selectScope}
                orientation="horizontal"
                aria-label="View visibility"
                options={[
                    {
                        value: 'private',
                        label: 'Private',
                    },
                    {
                        value: 'team',
                        label: 'Team',
                        disabledReason:
                            getAccessControlDisabledReason(
                                AccessControlResourceType.Dashboard,
                                AccessControlLevel.Editor
                            ) ?? undefined,
                    },
                ]}
            />
        </div>
    )
}

export const scene: SceneExport = {
    component: Dashboards,
    logic: dashboardsLogic,
    productKey: ProductKey.PRODUCT_ANALYTICS,
}

export function Dashboards(): JSX.Element {
    const { dashboardsLoading } = useValues(dashboardsModel)
    const { setCurrentTab, setFilters, setSearch } = useActions(dashboardsLogic)
    const { dashboards, currentTab, filters, isFiltering } = useValues(dashboardsLogic)
    const { selectableMembers } = useValues(membersLogic)
    const { currentTeamId } = useValues(teamLogic)
    const { user } = useValues(userLogic)
    const { showNewDashboardModal } = useActions(newDashboardLogic)
    const [dashboardSavedViewsEnabled, setDashboardSavedViewsEnabled] = useState(true)
    const [savedViews, setSavedViews] = useState<DashboardListSavedView[]>([])
    const [activeSavedViewId, setActiveSavedViewId] = useState<string | null>(null)
    const [updatingSavedView, setUpdatingSavedView] = useState(false)
    const [savedViewsLoadError, setSavedViewsLoadError] = useState(false)
    const [savedViewsReloadCount, setSavedViewsReloadCount] = useState(0)
    const currentSavedViewsTeamId = useRef<number | null>(currentTeamId)
    const savedViewsRequestVersion = useRef(0)
    currentSavedViewsTeamId.current = currentTeamId
    const activeSavedView = savedViews.find((view) => view.id === activeSavedViewId)
    const activeSavedViewHasUnsavedChanges =
        activeSavedView != null && !isEqual(filters, savedViewFilters(activeSavedView))
    const membersById = Object.fromEntries(selectableMembers().map((member) => [member.user.id, member]))
    const savedViewCreatorName = (view: DashboardListSavedView): string => {
        if (view.created_by == null) {
            return 'Unknown user'
        }
        const user = membersById[view.created_by]?.user
        return user ? fullName(user) || user.email : `User ${view.created_by}`
    }
    const savedFiltersSummary = (viewFilters: DashboardsFilters): JSX.Element => (
        <div>
            <div className="text-sm text-secondary">This view saves:</div>
            <ul className="list-disc space-y-2 pl-5 text-sm">
                {viewFilters.shared && <li>Shared dashboards</li>}
                {viewFilters.pinned && <li>Pinned dashboards</li>}
                {viewFilters.tags && viewFilters.tags.length > 0 && (
                    <li>
                        <div className="flex flex-wrap items-center gap-1">
                            <span>Tags:</span>
                            <ObjectTags tags={viewFilters.tags} staticOnly />
                        </div>
                    </li>
                )}
                {viewFilters.createdBy !== 'All users' && (
                    <li>
                        <div className="flex flex-wrap items-center gap-1">
                            <span>Created by:</span>
                            {viewFilters.createdBy.map((id) => {
                                const member = membersById[id]
                                const name = member ? fullName(member.user) || member.user.email : `User ${id}`

                                return (
                                    <LemonTag
                                        key={id}
                                        size="medium"
                                        icon={<ProfilePicture user={member?.user} name={name} size="sm" />}
                                    >
                                        {name}
                                    </LemonTag>
                                )
                            })}
                        </div>
                    </li>
                )}
                {viewFilters.folder != null && <li>Folder: {viewFilters.folder || 'Project root'}</li>}
                {viewFilters.search && <li>Search: “{viewFilters.search}”</li>}
            </ul>
        </div>
    )
    const savedViewsEditDisabledReason = getAccessControlDisabledReason(
        AccessControlResourceType.Dashboard,
        AccessControlLevel.Editor
    )

    const savedViewsRequestIsCurrent = (teamId: number, requestVersion: number): boolean =>
        currentSavedViewsTeamId.current === teamId && savedViewsRequestVersion.current === requestVersion

    const saveView = (initialScope: DashboardSavedViewScope = 'private'): void => {
        if (!isFiltering) {
            lemonToast.error('Add a filter before saving a view')
            return
        }
        let scope = initialScope
        LemonDialog.openForm({
            title: 'Save dashboard list view',
            initialValues: { name: 'My View' },
            content: (
                <div className="space-y-6">
                    {savedFiltersSummary(filters)}
                    <LemonField name="name">
                        <LemonInput autoFocus placeholder="View name" />
                    </LemonField>
                    <SavedViewVisibilityPicker initialScope={scope} onChange={(value) => (scope = value)} />
                </div>
            ),
            errors: {
                name: (value) => (!value?.trim() ? 'Enter a view name' : undefined),
            },
            showErrorsOnTouch: true,
            onSubmit: async ({ name }) => {
                const trimmedName = name.trim()
                if (currentTeamId == null) {
                    return
                }
                const teamId = currentTeamId
                const requestVersion = savedViewsRequestVersion.current
                if (!savedViewsRequestIsCurrent(teamId, requestVersion)) {
                    return
                }
                try {
                    const savedView = await dashboardSavedViewsCreate(teamId.toString(), {
                        name: trimmedName,
                        filters: filters as unknown as DashboardSavedViewWriteApiFilters,
                        scope,
                    })
                    if (savedViewsRequestIsCurrent(teamId, requestVersion)) {
                        setSavedViews((views) => [...views, savedView as unknown as DashboardListSavedView])
                        setActiveSavedViewId(savedView.id)
                        lemonToast.success(`Saved ${scope} view`)
                    }
                } catch (error) {
                    const detail = error instanceof ApiError && typeof error.detail === 'string' ? error.detail : null
                    lemonToast.error(detail || 'Could not save view')
                    throw error
                }
            },
            primaryButtonProps: {
                children: 'Save view',
            },
            shouldAwaitSubmit: true,
            width: 600,
            zIndex: '1169',
        })
    }

    const deleteSavedView = async (view: DashboardListSavedView): Promise<void> => {
        if (currentTeamId == null) {
            return
        }
        const teamId = currentTeamId
        const requestVersion = savedViewsRequestVersion.current
        if (!savedViewsRequestIsCurrent(teamId, requestVersion)) {
            return
        }
        try {
            await dashboardSavedViewsDestroy(teamId.toString(), view.id)
            if (savedViewsRequestIsCurrent(teamId, requestVersion)) {
                setSavedViews((views) => views.filter((savedView) => savedView.id !== view.id))
                setActiveSavedViewId((activeId) => (activeId === view.id ? null : activeId))
                lemonToast.success('Saved view deleted')
            }
        } catch (error) {
            const detail = error instanceof ApiError && typeof error.detail === 'string' ? error.detail : null
            lemonToast.error(detail || 'Could not delete view')
            throw error
        }
    }

    const updateSavedViewMetadata = async (
        view: DashboardListSavedView,
        update: Pick<PatchedDashboardSavedViewApi, 'name' | 'scope'>
    ): Promise<DashboardListSavedView> => {
        if (currentTeamId == null) {
            throw new Error('No project selected')
        }
        const teamId = currentTeamId
        const requestVersion = savedViewsRequestVersion.current
        if (!savedViewsRequestIsCurrent(teamId, requestVersion)) {
            throw new Error('The project changed before the saved view was updated')
        }

        try {
            const savedView = await dashboardSavedViewsPartialUpdate(teamId.toString(), view.id, update)
            const updatedView = savedView as unknown as DashboardListSavedView
            if (savedViewsRequestIsCurrent(teamId, requestVersion)) {
                setSavedViews((views) =>
                    views.map((savedViewItem) => (savedViewItem.id === view.id ? updatedView : savedViewItem))
                )
                lemonToast.success('Saved view updated')
            }
            return updatedView
        } catch (error) {
            const detail = error instanceof ApiError && typeof error.detail === 'string' ? error.detail : null
            lemonToast.error(detail || 'Could not update view')
            throw error
        }
    }

    const savedFiltersDescription = (viewFilters: DashboardsFilters): string => {
        const descriptions: string[] = []
        if (viewFilters.shared) {
            descriptions.push('Shared dashboards')
        }
        if (viewFilters.pinned) {
            descriptions.push('Pinned dashboards')
        }
        if (viewFilters.tags?.length) {
            descriptions.push(`Tags: ${viewFilters.tags.join(', ')}`)
        }
        const createdBy = viewFilters.createdBy === 'All users' ? [] : viewFilters.createdBy || []
        if (createdBy.length > 0) {
            const creators = createdBy.map((id) => {
                const member = membersById[id]
                return member ? fullName(member.user) || member.user.email : `User ${id}`
            })
            descriptions.push(`Created by: ${creators.join(', ')}`)
        }
        if (viewFilters.folder != null) {
            descriptions.push(`Folder: ${viewFilters.folder || 'Project root'}`)
        }
        if (viewFilters.search) {
            descriptions.push(`Search: “${viewFilters.search}”`)
        }
        return descriptions.length > 0 ? descriptions.join(', ') : 'No filters'
    }

    const manageSavedViews = (): void => {
        LemonDialog.open({
            title: 'Manage saved views',
            content: (
                <ManageDashboardSavedViews
                    views={savedViews}
                    currentUserId={user?.id ?? null}
                    editDisabledReason={savedViewsEditDisabledReason}
                    onUpdate={updateSavedViewMetadata}
                    onDelete={deleteSavedView}
                    renderCreator={(view) => {
                        const creator = view.created_by ? membersById[view.created_by]?.user : null
                        return (
                            <span className="flex items-center gap-2">
                                <ProfilePicture user={creator} name={savedViewCreatorName(view)} size="md" />
                                <span>{savedViewCreatorName(view)}</span>
                            </span>
                        )
                    }}
                    renderFilters={savedFiltersDescription}
                />
            ),
            primaryButton: null,
            secondaryButton: { children: 'Close' },
            width: 1100,
            maxWidth: 'calc(100vw - 2rem)',
            zIndex: '1169',
        })
    }

    const updateSavedView = async (view: DashboardListSavedView): Promise<void> => {
        if (currentTeamId == null || updatingSavedView) {
            return
        }
        const teamId = currentTeamId
        const requestVersion = savedViewsRequestVersion.current
        if (!savedViewsRequestIsCurrent(teamId, requestVersion)) {
            return
        }

        setUpdatingSavedView(true)
        try {
            const savedView = await dashboardSavedViewsPartialUpdate(teamId.toString(), view.id, {
                filters: filters as unknown as DashboardSavedViewWriteApiFilters,
            })
            if (savedViewsRequestIsCurrent(teamId, requestVersion)) {
                setSavedViews((views) =>
                    views.map((savedViewItem) =>
                        savedViewItem.id === view.id ? (savedView as unknown as DashboardListSavedView) : savedViewItem
                    )
                )
                lemonToast.success('Saved view updated')
            }
        } catch (error) {
            const detail = error instanceof ApiError && typeof error.detail === 'string' ? error.detail : null
            lemonToast.error(detail || 'Could not update view')
            throw error
        } finally {
            if (savedViewsRequestIsCurrent(teamId, requestVersion)) {
                setUpdatingSavedView(false)
            }
        }
    }

    useEffect(() => {
        if (currentTeamId == null) {
            setSavedViews([])
            setActiveSavedViewId(null)
            setDashboardSavedViewsEnabled(false)
            setUpdatingSavedView(false)
            return
        }

        const requestVersion = savedViewsRequestVersion.current + 1
        savedViewsRequestVersion.current = requestVersion
        setSavedViews([])
        setActiveSavedViewId(null)
        setUpdatingSavedView(false)
        setDashboardSavedViewsEnabled(true)
        setSavedViewsLoadError(false)
        void loadDashboardSavedViews(currentTeamId.toString())
            .then((views) => {
                if (savedViewsRequestIsCurrent(currentTeamId, requestVersion)) {
                    setSavedViews(views)
                    setDashboardSavedViewsEnabled(true)
                }
            })
            .catch((error) => {
                if (savedViewsRequestIsCurrent(currentTeamId, requestVersion)) {
                    if (!(error instanceof ApiError && error.status === 403)) {
                        posthog.captureException(error)
                        setSavedViewsLoadError(true)
                        return
                    }
                    setSavedViews([])
                    setDashboardSavedViewsEnabled(false)
                }
            })
    }, [currentTeamId, savedViewsReloadCount])

    const enabledTabs: LemonTab<DashboardsTab>[] = [
        {
            key: DashboardsTab.All,
            label: 'All dashboards',
        },
        { key: DashboardsTab.Yours, label: 'My dashboards' },
        {
            key: DashboardsTab.Templates,
            label: 'Templates',
        },
    ]

    return (
        <SceneContent>
            <NewDashboardModal />
            <DuplicateDashboardModal />
            <DeleteDashboardModal />
            <DashboardTemplateEditor />
            <DashboardTemplateModal />

            <SceneTitleSection
                name={sceneConfigurations[Scene.Dashboards].name}
                description={sceneConfigurations[Scene.Dashboards].description}
                resourceType={{
                    type: sceneConfigurations[Scene.Dashboards].iconType || 'default_icon_type',
                }}
                actions={
                    <>
                        <AccessControlAction
                            resourceType={AccessControlResourceType.Dashboard}
                            minAccessLevel={AccessControlLevel.Editor}
                        >
                            <Shortcut
                                name="NewDashboard"
                                keybind={[keyBinds.new]}
                                intent="New dashboard"
                                interaction="click"
                                scope={Scene.Dashboards}
                            >
                                <LemonButton
                                    size="small"
                                    data-attr="new-dashboard"
                                    onClick={showNewDashboardModal}
                                    type="primary"
                                >
                                    New dashboard
                                </LemonButton>
                            </Shortcut>
                        </AccessControlAction>
                    </>
                }
            />
            <LemonTabs
                onChange={(newKey) => {
                    setCurrentTab(newKey)
                }}
                activeKey={currentTab}
                tabs={enabledTabs}
                sceneInset
                rightSlot={
                    dashboardSavedViewsEnabled && currentTab === DashboardsTab.All ? (
                        <SavedDashboardViewsPicker
                            activeSavedView={activeSavedView}
                            activeSavedViewHasUnsavedChanges={activeSavedViewHasUnsavedChanges}
                            isFiltering={isFiltering}
                            savedViews={savedViews}
                            updatingSavedView={updatingSavedView}
                            loadError={savedViewsLoadError}
                            editDisabledReason={savedViewsEditDisabledReason}
                            onSaveAsNewView={saveView}
                            onSaveChanges={(view) => void updateSavedView(view)}
                            onSelectView={(view) => {
                                if (activeSavedViewId === view.id) {
                                    setActiveSavedViewId(null)
                                    return
                                }
                                posthog.capture('dashboard saved view applied', {
                                    scope: view.scope,
                                    ...savedViewFilterProperties(view.filters),
                                })
                                const nextFilters = savedViewFilters(view)
                                setFilters({ ...nextFilters, search: '' })
                                setSearch(nextFilters.search)
                                setActiveSavedViewId(view.id)
                            }}
                            onManageViews={manageSavedViews}
                            onRetryLoad={() => setSavedViewsReloadCount((count) => count + 1)}
                        />
                    ) : null
                }
                rightSlotClassName="!static !justify-start !bg-transparent"
            />

            <div>
                {currentTab === DashboardsTab.Templates ? (
                    <DashboardTemplatesTable />
                ) : dashboardsLoading || dashboards.length > 0 || isFiltering ? (
                    <DashboardsTableContainer />
                ) : (
                    <ProductIntroduction
                        productName="Dashboards"
                        thingName="dashboard"
                        titleOverride="Your home for what you actually care about"
                        description="Keep analytics, session replay, logs, and the rest of your PostHog stack in one place. Below are customer-favorite dashboards to get you started quickly. Or skip them and start blank, up to you."
                        isEmpty={true}
                        docsURL={DASHBOARD_DOCS_URL}
                        customHog={HedgehogChart}
                        hogLayout="responsive"
                        useMainContentContainerQueries={true}
                        contentClassName="max-w-[1000px]"
                        actionElementOverride={<FeaturedTemplatesChooser />}
                        mcpSurfaceKey="dashboards.create"
                    />
                )}
            </div>
        </SceneContent>
    )
}
