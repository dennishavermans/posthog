import { useState } from 'react'

import { IconTrash } from '@posthog/icons'
import { LemonButton, LemonDialog, LemonInput, LemonSelect } from '@posthog/lemon-ui'

import { TZLabel } from 'lib/components/TZLabel'
import { LemonTable, LemonTableColumns } from 'lib/lemon-ui/LemonTable'

import type { DashboardListSavedView, DashboardSavedViewScope } from './Dashboards'

type SavedViewUpdate = Pick<DashboardListSavedView, 'name' | 'scope'>

interface ManageDashboardSavedViewsProps {
    views: DashboardListSavedView[]
    currentUserId: number | null
    editDisabledReason: string | null
    onUpdate: (view: DashboardListSavedView, update: Partial<SavedViewUpdate>) => Promise<DashboardListSavedView>
    onDelete: (view: DashboardListSavedView) => Promise<void>
    renderCreator: (view: DashboardListSavedView) => JSX.Element | string
    renderFilters: (filters: DashboardListSavedView['filters']) => string
}

export function ManageDashboardSavedViews({
    views: initialViews,
    currentUserId,
    editDisabledReason,
    onUpdate,
    onDelete,
    renderCreator,
    renderFilters,
}: ManageDashboardSavedViewsProps): JSX.Element {
    const [views, setViews] = useState(initialViews)
    const [names, setNames] = useState<Record<string, string>>(() =>
        Object.fromEntries(initialViews.map((view) => [view.id, view.name]))
    )
    const [updatingIds, setUpdatingIds] = useState<string[]>([])

    const setUpdating = (id: string, updating: boolean): void => {
        setUpdatingIds((ids) => (updating ? [...ids, id] : ids.filter((updatingId) => updatingId !== id)))
    }

    const replaceView = (updatedView: DashboardListSavedView): void => {
        setViews((currentViews) => currentViews.map((view) => (view.id === updatedView.id ? updatedView : view)))
    }

    const saveName = async (view: DashboardListSavedView): Promise<void> => {
        if (editDisabledReason) {
            return
        }
        const name = names[view.id].trim()
        if (!name) {
            setNames((currentNames) => ({ ...currentNames, [view.id]: view.name }))
            return
        }
        if (name === view.name || updatingIds.includes(view.id)) {
            return
        }

        setUpdating(view.id, true)
        try {
            const updatedView = await onUpdate(view, { name })
            replaceView(updatedView)
        } catch {
            setNames((currentNames) => ({ ...currentNames, [view.id]: view.name }))
        } finally {
            setUpdating(view.id, false)
        }
    }

    const saveScope = async (view: DashboardListSavedView, scope: DashboardSavedViewScope): Promise<void> => {
        if (scope === view.scope || updatingIds.includes(view.id)) {
            return
        }

        setUpdating(view.id, true)
        try {
            const updatedView = await onUpdate(view, { scope })
            replaceView(updatedView)
        } catch {
            return
        } finally {
            setUpdating(view.id, false)
        }
    }

    const deleteView = (view: DashboardListSavedView): void => {
        LemonDialog.open({
            title: `Delete ${view.name}?`,
            description:
                view.scope === 'private'
                    ? 'This removes the saved view only for you.'
                    : 'This removes the saved view for everyone in this project.',
            primaryButton: {
                children: 'Delete view',
                status: 'danger',
                onClick: () => {
                    setViews((currentViews) => currentViews.filter((savedView) => savedView.id !== view.id))
                    void onDelete(view).catch(() => {
                        setViews((currentViews) => [...currentViews, view])
                    })
                },
            },
            secondaryButton: { children: 'Cancel' },
            zIndex: '1169',
        })
    }

    const columns: LemonTableColumns<DashboardListSavedView> = [
        {
            title: 'Name',
            key: 'name',
            width: 240,
            render: function renderName(_, view) {
                if (editDisabledReason) {
                    return <span className="text-secondary">{view.name}</span>
                }
                return (
                    <LemonInput
                        value={names[view.id]}
                        onChange={(name) => setNames((currentNames) => ({ ...currentNames, [view.id]: name }))}
                        onBlur={() => void saveName(view)}
                        onPressEnter={() => void saveName(view)}
                        disabled={updatingIds.includes(view.id)}
                    />
                )
            },
        },
        {
            title: 'Visibility',
            key: 'scope',
            width: 150,
            render: function renderScope(_, view) {
                const visibilityLocked = view.scope === 'team' && view.created_by !== currentUserId
                if (editDisabledReason || visibilityLocked) {
                    return <span className="text-secondary">{view.scope === 'private' ? 'Private' : 'Team'}</span>
                }
                return (
                    <LemonSelect<DashboardSavedViewScope>
                        size="small"
                        value={view.scope ?? 'team'}
                        options={[
                            { value: 'private', label: 'Private' },
                            { value: 'team', label: 'Team' },
                        ]}
                        onChange={(scope) => void saveScope(view, scope)}
                        disabled={updatingIds.includes(view.id)}
                    />
                )
            },
        },
        {
            title: 'Created by',
            key: 'created_by',
            width: 160,
            render: function renderCreatorColumn(_, view) {
                return renderCreator(view)
            },
        },
        {
            title: 'Created',
            key: 'created_at',
            width: 130,
            render: function renderCreated(_, view) {
                return <TZLabel time={view.created_at} />
            },
        },
        {
            title: 'Last updated',
            key: 'updated_at',
            width: 130,
            render: function renderUpdated(_, view) {
                return <TZLabel time={view.updated_at || view.created_at} />
            },
        },
        {
            title: 'Saved filters',
            key: 'filters',
            render: function renderFiltersColumn(_, view) {
                return <span className="text-secondary">{renderFilters(view.filters)}</span>
            },
        },
    ]
    const sortedViews = [...views].sort((left, right) => {
        const scopeOrder = (view: DashboardListSavedView): number => (view.scope === 'private' ? 0 : 1)
        return scopeOrder(left) - scopeOrder(right) || left.name.localeCompare(right.name)
    })

    return (
        <LemonTable
            columns={columns}
            dataSource={sortedViews}
            rowKey="id"
            size="small"
            className="max-w-full"
            rowActions={(view) => (
                <LemonButton
                    size="xsmall"
                    type="tertiary"
                    status="danger"
                    icon={<IconTrash />}
                    tooltip={`Delete ${view.name}`}
                    aria-label={`Delete ${view.name}`}
                    disabledReason={editDisabledReason}
                    onClick={() => deleteView(view)}
                />
            )}
        />
    )
}
