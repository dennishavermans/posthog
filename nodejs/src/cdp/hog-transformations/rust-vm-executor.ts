import { DateTime } from 'luxon'
import { Counter, Histogram } from 'prom-client'

import { logger } from '~/common/utils/logger'

import { CyclotronJobInvocationHogFunction, CyclotronJobInvocationResult } from '../types'
import { createAddLogFunction, sanitizeLogMessage } from '../utils'
import { createInvocationResult } from '../utils/invocation-utils'
import { HogvmNodeModule, RUST_MAX_STEPS, isUnsupportedByRustVm, loadHogvmNodeModule } from './rust-vm'

/**
 * Executes transformation invocations on the Rust HogVM (via the `@posthog/hogvm-node` napi
 * addon) as the primary executor, producing the same `CyclotronJobInvocationResult` shape the
 * Node executor does. Programs are registered with the addon once per bytecode version, so the
 * per-event cost is the globals crossing rather than re-marshalling and re-decoding bytecode.
 *
 * Invocations the Rust VM can't run — the addon isn't built, or the program calls a host function
 * the binding doesn't implement — return null so the caller falls back to the Node VM.
 */

export const rustVmExecution = new Counter({
    name: 'hogvm_rust_execution_total',
    help: 'Outcomes of transformation executions where the Rust HogVM is the primary executor',
    labelNames: ['outcome'],
})

export const rustVmExecutionDuration = new Histogram({
    name: 'hogvm_rust_execution_duration_ms',
    help: 'Per-invocation hog execution duration on the Rust HogVM as the primary executor',
    buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 25, 50, 100],
})

export const rustVmProgramRegistrations = new Counter({
    name: 'hogvm_rust_program_registrations_total',
    help: 'Programs registered with the Rust HogVM, by why the cached handle missed',
    labelNames: ['reason'],
})

/**
 * How many decoded programs to keep registered at once. Each entry holds one hog function's
 * decoded token stream, so this bounds registry memory in a process that sees many functions.
 * Well above the number of transformations a single ingestion process realistically cycles
 * through, so steady state is all hits.
 */
export const MAX_REGISTERED_PROGRAMS = 500

export class RustVmExecutor {
    /**
     * Registered-program handles, keyed by hog function id. `updatedAt` is the version guard: a
     * function whose bytecode was edited must not keep executing the handle registered for its
     * previous version. Map iteration order is insertion order, which makes the oldest entry the
     * eviction candidate once the cache is full.
     */
    private handles = new Map<string, { updatedAt: string; handle: number }>()

    constructor(private options: { mmdbPath: string }) {}

    private getModule(): HogvmNodeModule | null {
        return loadHogvmNodeModule({ mmdbPath: this.options.mmdbPath })
    }

    /**
     * The handle for this invocation's program, registering it if this is the first time we've
     * seen the function or its bytecode changed. Releasing the superseded handle (and the evicted
     * one) is what keeps the Rust-side registry bounded rather than growing per edit.
     *
     * Returns null when the function carries no `updated_at` to version the cache by — without
     * one we can't tell an edited program from the one we registered, and serving a stale handle
     * would silently run outdated bytecode. The caller executes those unregistered instead.
     */
    private handleFor(
        module_: HogvmNodeModule,
        hogFunction: { id: string; updated_at?: string; bytecode: unknown[] }
    ): number | null {
        if (!hogFunction.updated_at) {
            return null
        }

        const cached = this.handles.get(hogFunction.id)
        if (cached && cached.updatedAt === hogFunction.updated_at) {
            return cached.handle
        }

        if (cached) {
            module_.releaseProgram(cached.handle)
            this.handles.delete(hogFunction.id)
        }
        rustVmProgramRegistrations.inc({ reason: cached ? 'version_changed' : 'new' })

        if (this.handles.size >= MAX_REGISTERED_PROGRAMS) {
            const [oldestId, oldest] = this.handles.entries().next().value!
            module_.releaseProgram(oldest.handle)
            this.handles.delete(oldestId)
        }

        const handle = module_.registerProgram(hogFunction.bytecode)
        this.handles.set(hogFunction.id, { updatedAt: hogFunction.updated_at, handle })
        return handle
    }

    /**
     * Count and log a fallback so every node-vm handoff is attributable to a function. Returns
     * null for the caller to pass through.
     */
    private fallback(
        outcome: 'fallback_unsupported' | 'fallback_exception',
        invocation: CyclotronJobInvocationHogFunction,
        sensitiveValues: string[],
        error: unknown
    ): null {
        rustVmExecution.inc({ outcome })
        logger.warn('🦀', 'Rust HogVM invocation fell back to the node vm', {
            outcome,
            functionId: invocation.functionId,
            teamId: invocation.teamId,
            // Same redaction as hog print logs: marshalling errors and panic messages can embed
            // values from the invocation globals, which include secret inputs.
            error: error !== undefined ? sanitizeLogMessage([String(error)], sensitiveValues) : undefined,
        })
        return null
    }

    /**
     * Execute one transformation invocation on the Rust VM. Returns null when the Node VM must
     * run it instead.
     *
     * Runs through `executeRegisteredSync` on the JS thread — the same threading model as the
     * Node VM's exec, minus the work. Executions are sub-millisecond and bounded by the step
     * budget, so a libuv thread-hop per invocation would cost more than the execution it
     * offloads; batching many events into one async call is the follow-up if that changes.
     *
     * The program is registered (marshalled, validated, token-decoded) once per bytecode version
     * rather than per event — see `handleFor`.
     */
    public execute(
        invocation: CyclotronJobInvocationHogFunction,
        sensitiveValues: string[]
    ): CyclotronJobInvocationResult<CyclotronJobInvocationHogFunction> | null {
        const module_ = this.getModule()
        if (!module_) {
            // No per-invocation log: a missing addon affects every invocation and the loader
            // already warned once with the load error.
            rustVmExecution.inc({ outcome: 'fallback_unavailable' })
            return null
        }

        let rust
        try {
            const handle = this.handleFor(module_, invocation.hogFunction)
            rust =
                handle === null
                    ? module_.executeSync(invocation.hogFunction.bytecode, invocation.state.globals, {
                          maxSteps: RUST_MAX_STEPS,
                      })
                    : module_.executeRegisteredSync(handle, invocation.state.globals, {
                          maxSteps: RUST_MAX_STEPS,
                      })
        } catch (error) {
            // A throw here is the boundary or the native side, not the program's own error path —
            // marshalling failures (e.g. globals containing NaN or Infinity, which serde_json
            // can't represent), rust panics, addon bugs. Deliberately broad: the node vm can run
            // all of these, so correctness wins and the invocation falls back — while the warn log
            // and the fallback_exception outcome carry the error so native faults stay visible
            // rather than being silently healed.
            return this.fallback('fallback_exception', invocation, sensitiveValues, error)
        }

        if (rust.error && isUnsupportedByRustVm(rust.error)) {
            return this.fallback('fallback_unsupported', invocation, sensitiveValues, rust.error)
        }

        const durationMs = rust.durationUs / 1000
        rustVmExecutionDuration.observe(durationMs)

        const result = createInvocationResult<CyclotronJobInvocationHogFunction>(invocation)
        const addLog = createAddLogFunction(result.logs)
        result.invocation.state.timings.push({ kind: 'hog', duration_ms: durationMs })

        const eventId = invocation.state.globals.event?.uuid || 'Unknown event'

        for (const message of rust.logs ?? []) {
            result.logs.push({
                level: 'info',
                timestamp: DateTime.now(),
                message: sanitizeLogMessage([message], sensitiveValues),
            })
        }
        if (rust.logsTruncated) {
            addLog('warn', `Function exceeded maximum log entries. No more logs will be collected. Event: ${eventId}`)
        }

        if (rust.error) {
            rustVmExecution.inc({ outcome: 'error' })
            addLog('error', `Error executing function on event ${eventId}: ${rust.error}`)
            result.error = rust.error
            return result
        }

        rustVmExecution.inc({ outcome: 'executed' })
        if (rust.result) {
            result.execResult = rust.result
        }
        addLog('debug', `Function completed in ${Number(durationMs.toFixed(2))}ms.`)
        return result
    }
}
