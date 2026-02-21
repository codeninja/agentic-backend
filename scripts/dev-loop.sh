#!/usr/bin/env bash
# =============================================================================
# NinjaStack Autonomous Development Loop (Concurrent)
# =============================================================================
# Entry point — sources modular components and runs main loop.
#
# Usage:     ./scripts/dev-loop.sh
# Stop:      touch stop.txt      (immediate — kills everything)
# Shutdown:  touch shutdown.txt   (graceful — stops loops, waits for agents)
# =============================================================================
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Source all components (order matters: config → board → helpers → worktree → agents → loops)
source "$SCRIPT_DIR/dev-loop/config.sh"
source "$SCRIPT_DIR/dev-loop/board.sh"
source "$SCRIPT_DIR/dev-loop/helpers.sh"
source "$SCRIPT_DIR/dev-loop/worktree.sh"
for f in "$SCRIPT_DIR"/dev-loop/agents/*.sh; do source "$f"; done
for f in "$SCRIPT_DIR"/dev-loop/loops/*.sh; do source "$f"; done

main() {
    log "============================================"
    log "🥷 NinjaStack Dev Loop Starting (concurrent)"
    log "  Project: $REPO (board #$PROJECT_NUM)"
    log "  Loops: sync(120s) triage(60s) planning(60s) implement(60s)"
    log "         promote(90s) review(60s) audit(300s) status(60s)"
    log "  Max agents: triage=$MAX_TRIAGE_AGENTS planning=$MAX_PLANNING_AGENTS"
    log "              implement=$MAX_IMPLEMENT_AGENTS review=$MAX_REVIEW_AGENTS"
    log "  Worktrees: $WORKTREE_BASE"
    log "  Logs: $LOG_DIR"
    log "  Stop: touch $PROJECT_ROOT/stop.txt"
    log "  Shutdown: touch $PROJECT_ROOT/shutdown.txt"
    log "============================================"

    : > "$LOOP_PIDS_FILE"

    # Pull latest main once at startup
    (cd "$PROJECT_ROOT" && git pull --rebase origin main 2>/dev/null || true)

    # Initial board sync
    $NINJA_BOARD sync 2>/dev/null || log "⚠️  Initial board sync failed"

    # Trap signals
    trap 'log "Signal received — shutting down"; kill_all_loops; kill_all_agents; cleanup; exit 0' INT TERM

    # Launch all loops with slight stagger
    launch_loop "sync"      loop_sync;      sleep 1
    launch_loop "triage"    loop_triage;    sleep 1
    launch_loop "planning"  loop_planning;  sleep 1
    launch_loop "implement" loop_implement; sleep 1
    launch_loop "promote"   loop_promote;   sleep 1
    launch_loop "review"    loop_review;    sleep 1
    launch_loop "audit"     loop_audit;     sleep 1
    launch_loop "status"    loop_status

    # Monitor loop
    while true; do
        sleep 10

        if [[ -f "$PROJECT_ROOT/stop.txt" ]]; then
            log "🛑 stop.txt — killing everything"
            kill_all_loops; kill_all_agents
            rm -f "$PROJECT_ROOT/stop.txt"
            cleanup; exit 0
        fi

        if [[ -f "$PROJECT_ROOT/shutdown.txt" ]]; then
            log "🔻 shutdown.txt — stopping loops, waiting for agents..."
            kill_all_loops
            local wait_count=0
            while any_agents_running_global; do
                log "  ⏳ Agents still running... (${wait_count}s)"
                sleep 15
                wait_count=$(( wait_count + 15 ))
                if (( wait_count > 900 )); then
                    log "  ⚠️  Agents still running after 15min — force killing"
                    kill_all_agents; break
                fi
            done
            rm -f "$PROJECT_ROOT/shutdown.txt"
            cleanup
            log "🛑 Graceful shutdown complete."
            exit 0
        fi

        # Check for needed board sync
        if $NINJA_BOARD needs-sync 2>/dev/null; then
            $NINJA_BOARD sync 2>/dev/null &
        fi

        check_and_restart_loops
    done
}

main "$@"
