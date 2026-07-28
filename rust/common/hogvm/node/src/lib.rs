//! Rust HogVM exposed to Node via napi-rs, for executing ingestion transformations.
//!
//! `executeSync` runs one (bytecode, globals) pair synchronously on the calling thread — the
//! primary-execution path, matching the Node VM's synchronous exec with no threadpool round-trip.
//! Executions are sub-millisecond and bounded by the step budget, so blocking the event loop is
//! no worse than the Node VM path it replaces.
//!
//! Transformation host functions (`geoipLookup`, `cleanNullValues`, `isKnownBotUserAgent`,
//! `isKnownBotIp`) mirror `nodejs/src/cdp/hog-transformations/transformation-functions.ts`; call
//! `init` once with the mmdb path and bot lists before executing. A host function this binding
//! can't support fails the execution with an `unsupported_ext_fn:<name>` error so the caller can
//! fall back to the Node VM.

// Workspace-standard allocator (jemalloc): the interpreter's small-allocation churn was a
// measured ~33% of self-time under glibc malloc. Applies to this cdylib's Rust allocations,
// same as every other PostHog Rust service.
common_alloc::used!();

mod exec;
mod ext_fns;
mod geoip;
mod logs;

use napi::Result as NapiResult;
use napi_derive::napi;
use serde_json::Value;

pub use exec::{build_program, run_batch, run_batch_program, HogExecResult};

#[napi(object)]
pub struct InitOptions {
    pub mmdb_path: Option<String>,
    pub known_bot_ua_list: Option<Vec<String>>,
    pub known_bot_ip_list: Option<Vec<String>>,
}

/// Load process-wide state for the transformation host functions. Idempotent; only the first call
/// takes effect.
#[napi]
pub fn init(options: InitOptions) -> NapiResult<()> {
    if let Some(path) = options.mmdb_path {
        geoip::init_geoip(&path).map_err(napi::Error::from_reason)?;
    }
    ext_fns::set_bot_lists(options.known_bot_ua_list, options.known_bot_ip_list);
    Ok(())
}

#[napi(object)]
pub struct ExecuteSyncOptions {
    /// Step budget for the execution (the Rust VM has no wall-clock timeout).
    pub max_steps: Option<u32>,
}

/// Run one Hog program against one event-globals synchronously on the calling thread. This is the
/// primary-execution path for ingestion transformations: it matches the Node VM's synchronous
/// exec, with no threadpool round-trip.
#[napi]
pub fn execute_sync(
    program: Value,
    globals: Value,
    options: Option<ExecuteSyncOptions>,
) -> HogExecResult {
    let tokens = match program {
        Value::Array(tokens) => tokens,
        _ => Vec::new(),
    };
    let max_steps = options.and_then(|o| o.max_steps).map(|m| m as usize);
    run_batch(&tokens, std::slice::from_ref(&globals), max_steps)
        .into_iter()
        .next()
        .expect("run_batch returns one result per event")
}

// Programs registered once by `registerProgram` — validated and token-decoded at registration,
// executed by handle. Skips the per-invocation JS→Rust marshal + copy + decode of the token
// array, so a hogFunction's bytecode is decoded once and reused across every event.
//
// Slots are reused after `releaseProgram`, so a long-lived process that re-registers programs as
// hog functions are edited or evicted doesn't grow the registry without bound. Callers own handle
// lifecycle: a handle must not be executed after it is released (doing so is not unsafe — it
// either errors as unknown or, once the slot is reused, runs the newer program — but it is a
// caller bug).
#[derive(Default)]
struct ProgramRegistry {
    slots: Vec<Option<Result<hogvm::Program, String>>>,
    free: Vec<u32>,
}

static REGISTERED_PROGRAMS: std::sync::RwLock<ProgramRegistry> =
    std::sync::RwLock::new(ProgramRegistry {
        slots: Vec::new(),
        free: Vec::new(),
    });

/// Register a program's bytecode once; returns a handle for `executeRegisteredSync`. Invalid
/// bytecode still gets a handle — executions through it report the validation error.
#[napi]
pub fn register_program(program: Value) -> u32 {
    let tokens = match program {
        Value::Array(tokens) => tokens,
        _ => Vec::new(),
    };
    let built = exec::build_program(tokens);
    let mut registry = REGISTERED_PROGRAMS.write().expect("registry poisoned");
    if let Some(handle) = registry.free.pop() {
        registry.slots[handle as usize] = Some(built);
        return handle;
    }
    registry.slots.push(Some(built));
    (registry.slots.len() - 1) as u32
}

/// Drop a registered program and free its slot for reuse. Releasing an unknown or already-released
/// handle is a no-op, so a caller retrying a cleanup can't corrupt the free list.
#[napi]
pub fn release_program(handle: u32) {
    let mut registry = REGISTERED_PROGRAMS.write().expect("registry poisoned");
    let Some(slot) = registry.slots.get_mut(handle as usize) else {
        return;
    };
    if slot.take().is_some() {
        registry.free.push(handle);
    }
}

// A registered Program clone is two Arc bumps; cloning out keeps the lock scope minimal.
fn get_registered(handle: u32) -> Result<hogvm::Program, String> {
    REGISTERED_PROGRAMS
        .read()
        .expect("registry poisoned")
        .slots
        .get(handle as usize)
        .cloned()
        .flatten()
        .unwrap_or_else(|| Err(format!("unknown program handle {handle}")))
}

fn error_results(error: &str, count: usize) -> Vec<HogExecResult> {
    (0..count)
        .map(|_| HogExecResult {
            result: None,
            error: Some(error.to_string()),
            duration_us: 0.0,
            logs: Vec::new(),
            logs_truncated: false,
        })
        .collect()
}

/// `executeSync` against a program registered with `registerProgram`.
#[napi]
pub fn execute_registered_sync(
    handle: u32,
    globals: Value,
    options: Option<ExecuteSyncOptions>,
) -> HogExecResult {
    let max_steps = options.and_then(|o| o.max_steps).map(|m| m as usize);
    let results = match get_registered(handle) {
        Ok(program) => exec::run_batch_program(&program, std::slice::from_ref(&globals), max_steps),
        Err(e) => error_results(&e, 1),
    };
    results.into_iter().next().expect("one result per event")
}

/// Batch variant: one napi crossing for many events, amortizing the marshalling overhead.
#[napi]
pub fn execute_registered_batch_sync(
    handle: u32,
    events: Vec<Value>,
    options: Option<ExecuteSyncOptions>,
) -> Vec<HogExecResult> {
    let max_steps = options.and_then(|o| o.max_steps).map(|m| m as usize);
    match get_registered(handle) {
        Ok(program) => exec::run_batch_program(&program, &events, max_steps),
        Err(e) => error_results(&e, events.len()),
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    // The registry is process-global, so these tests must not run concurrently with each other:
    // they assert on which slot a registration lands in, and cargo runs tests in parallel threads.
    static REGISTRY_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    fn registry_guard() -> std::sync::MutexGuard<'static, ()> {
        // A panicking test poisons the lock; the registry itself stays consistent, so recover
        // rather than cascading a failure into every other test in this module.
        REGISTRY_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner())
    }

    // "_H" header, version 1, push int 1, RETURN
    fn program(value: i64) -> Value {
        json!(["_H", 1, 33, value, 38])
    }

    #[test]
    fn released_handles_are_reused_so_the_registry_stays_bounded() {
        let _guard = registry_guard();
        // Without slot reuse the registry grows by one entry per re-registration, which for a
        // long-lived process re-registering edited hog functions is an unbounded leak.
        let first = register_program(program(1));
        release_program(first);
        let second = register_program(program(2));
        assert_eq!(first, second);

        // The reused slot must hold the new program, not the released one.
        let result = execute_registered_sync(second, json!({}), None);
        assert_eq!(result.error, None);
        assert_eq!(result.result, Some(json!(2)));
    }

    #[test]
    fn executing_a_released_handle_errors_instead_of_running_a_stale_program() {
        let _guard = registry_guard();
        let handle = register_program(program(1));
        release_program(handle);

        let result = execute_registered_sync(handle, json!({}), None);
        assert!(result.result.is_none());
        assert!(result
            .error
            .as_deref()
            .unwrap()
            .contains("unknown program handle"));
    }

    #[test]
    fn releasing_twice_does_not_hand_the_same_slot_out_to_two_registrations() {
        let _guard = registry_guard();
        // A double release used to be able to push the same handle onto the free list twice, so
        // two live registrations would alias one slot and execute each other's programs.
        let handle = register_program(program(1));
        release_program(handle);
        release_program(handle);

        let a = register_program(program(1));
        let b = register_program(program(2));
        assert_ne!(a, b);

        assert_eq!(
            execute_registered_sync(a, json!({}), None).result,
            Some(json!(1))
        );
        assert_eq!(
            execute_registered_sync(b, json!({}), None).result,
            Some(json!(2))
        );
    }
}
