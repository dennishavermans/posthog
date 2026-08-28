import { FileSystemIconType, ProductItemCategory } from '../../frontend/src/queries/schema/schema-general'
import { ProductManifest } from '../../frontend/src/types'

export const manifest: ProductManifest = {
    name: 'Wizard',
    scenes: {
        Wizard: {
            import: () => import('./frontend/WizardRunsScene'),
            projectBased: true,
            name: 'Wizard',
            layout: 'app-container',
        },
    },
    routes: {
        '/wizard': ['Wizard', 'wizard'],
    },
    redirects: {},
    urls: {
        wizard: (): string => '/wizard',
    },
    fileSystemTypes: {},
    treeItemsNew: [],
    treeItemsProducts: [
        {
            path: 'Wizard',
            intents: [],
            category: ProductItemCategory.ANALYTICS,
            type: 'wizard',
            iconType: 'llm_prompts' as FileSystemIconType,
            href: '/wizard',
            sceneKey: 'Wizard',
        },
    ],
}
