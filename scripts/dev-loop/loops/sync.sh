#!/usr/bin/env bash
# =============================================================================
# Sync loop — periodic board sync + orphan fix
# =============================================================================

loop_sync() {
    while check_loop_stop; do
        wait_for_rate_limit "sync" || return

        # Full board sync via $NINJA_BOARD
        $NINJA_BOARD sync 2>/dev/null

        # Fix orphans (items with no status)
        local orphans
        orphans=$($NINJA_BOARD issues-by-status "No Status" 2>/dev/null)
        if [[ -n "$orphans" ]]; then
            while read -r issue_num; do
                [[ -z "$issue_num" ]] && continue
                $NINJA_BOARD set-status "$issue_num" "Triage" 2>/dev/null
                log "[sync] 🔄 #$issue_num → Triage (had no status)"
            done <<< "$orphans"
        fi

        sleep 120
    done
}
