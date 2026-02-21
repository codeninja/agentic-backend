#!/usr/bin/env bash
# =============================================================================
# Status loop — periodic board summary
# =============================================================================

loop_status() {
    while check_loop_stop; do
        wait_for_rate_limit "status" || return
        local rl_remaining
        rl_remaining=$(get_graphql_rate_limit)
        log ""
        log "📊 Board Status (GraphQL rate limit: ${rl_remaining}/5000):"
        $NINJA_BOARD summary 2>/dev/null | while IFS= read -r line; do
            log "  $line"
        done
        # Active agents summary
        for t in triage planning implement review audit; do
            local c
            c=$(count_active_agents "$t")
            if (( c > 0 )); then
                log "  🤖 Active $t agents: $c"
            fi
        done
        sleep 60
    done
}
