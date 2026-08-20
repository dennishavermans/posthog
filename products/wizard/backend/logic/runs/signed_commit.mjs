import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'
import { existsSync } from 'node:fs'

const [repositoryPath, branch, message] = process.argv.slice(1)
const serverPath = '/scripts/node_modules/@posthog/agent/dist/adapters/codex-app-server/local-tools-mcp-server.js'
if (!existsSync(serverPath)) {
    throw new Error('The signed-commit tool is unavailable in this Wizard Worker.')
}

const context = Buffer.from(
    JSON.stringify({
        cwd: repositoryPath,
        token: process.env.GITHUB_TOKEN,
    })
).toString('base64')
const transport = new StdioClientTransport({
    command: 'node',
    args: [serverPath],
    env: {
        ...process.env,
        POSTHOG_LOCAL_TOOLS_CTX: context,
        POSTHOG_LOCAL_TOOLS_ENABLED: 'git_signed_commit',
    },
})
const client = new Client({ name: 'wizard-worker', version: '1.0.0' })

try {
    await client.connect(transport)
    const result = await client.callTool({
        name: 'git_signed_commit',
        arguments: { branch, message },
    })
    const detail = result.content
        .filter((content) => content.type === 'text')
        .map((content) => content.text)
        .join('\n')
    if (result.isError) {
        throw new Error(detail || 'The signed-commit tool failed.')
    }
} finally {
    await client.close()
}
