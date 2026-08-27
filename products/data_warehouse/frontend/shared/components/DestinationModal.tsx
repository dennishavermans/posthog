import { useActions, useValues } from 'kea'
import { Form } from 'kea-forms'

import { LemonButton, LemonInput, LemonModal, LemonSelect } from '@posthog/lemon-ui'

import { LemonField } from 'lib/lemon-ui/LemonField'
import { PostgreSQLSetupModal } from 'scenes/integrations/postgresql/PostgreSQLSetupModal'

import {
    DestinationModalLogicProps,
    destinationModalLogic,
} from 'products/data_warehouse/frontend/shared/logics/destinationModalLogic'

import { DestinationIcon } from './DestinationIcon'

export function DestinationModal(props: DestinationModalLogicProps): JSX.Element {
    const logic = destinationModalLogic(props)
    const { isOpen, editing, postgresIntegrations, isDestinationFormSubmitting, showConnectionSetup } = useValues(logic)
    const { closeModal, submitDestinationForm, setDestinationFormValue, setConnectionSetupOpen } = useActions(logic)

    return (
        <>
            <LemonModal
                isOpen={isOpen && !showConnectionSetup}
                onClose={closeModal}
                title={
                    <div className="flex gap-2 items-center">
                        <DestinationIcon type="Postgres" />
                        <span>{editing ? 'Edit destination' : 'New destination'}</span>
                    </div>
                }
                footer={
                    <>
                        <LemonButton type="secondary" onClick={closeModal}>
                            Cancel
                        </LemonButton>
                        <LemonButton
                            type="primary"
                            onClick={submitDestinationForm}
                            loading={isDestinationFormSubmitting}
                            data-attr="warehouse-destination-save"
                        >
                            {editing ? 'Save' : 'Add destination'}
                        </LemonButton>
                    </>
                }
            >
                <Form
                    logic={destinationModalLogic}
                    props={props}
                    formKey="destinationForm"
                    className="deprecated-space-y-4"
                >
                    <LemonField name="name" label="Name">
                        <LemonInput placeholder="Customer Postgres" data-attr="warehouse-destination-name" />
                    </LemonField>

                    <LemonField
                        name="integrationId"
                        label="Connection"
                        info="Credentials live on the connection, so one connection can back several destinations and batch exports."
                    >
                        {({ value, onChange }) => (
                            <div className="flex gap-2 items-center">
                                <LemonSelect
                                    className="flex-1"
                                    value={value}
                                    onChange={onChange}
                                    placeholder="Pick a connection"
                                    options={postgresIntegrations.map((integration) => ({
                                        value: integration.id,
                                        label: integration.display_name || `Connection ${integration.id}`,
                                    }))}
                                />
                                <LemonButton
                                    type="secondary"
                                    onClick={() => setConnectionSetupOpen(true)}
                                    data-attr="warehouse-destination-new-connection"
                                >
                                    New connection
                                </LemonButton>
                            </div>
                        )}
                    </LemonField>

                    <div className="flex gap-2">
                        <LemonField name="database" label="Database" className="flex-1">
                            <LemonInput data-attr="warehouse-destination-database" />
                        </LemonField>
                        <LemonField name="schema" label="Schema" className="flex-1">
                            <LemonInput data-attr="warehouse-destination-schema" />
                        </LemonField>
                    </div>
                </Form>
            </LemonModal>

            <PostgreSQLSetupModal
                isOpen={showConnectionSetup}
                onComplete={(integrationId?: number) => {
                    if (integrationId) {
                        setDestinationFormValue('integrationId', integrationId)
                    }
                    setConnectionSetupOpen(false)
                }}
            />
        </>
    )
}
