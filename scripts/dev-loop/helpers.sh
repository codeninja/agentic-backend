#!/usr/bin/env bash
# =============================================================================
# Helpers — logging, rate limiting, PID tracking, bounce tracking, loop mgmt
# =============================================================================

# ---------------------------------------------------------------------------
# Logging & Stop/Shutdown
# ---------------------------------------------------------------------------
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

check_loop_stop() {
    [[ -f "$PROJECT_ROOT/stop.txt" ]] && return 1
    [[ -f "$PROJECT_ROOT/shutdown.txt" ]] && return 1
    return 0
}

# ---------------------------------------------------------------------------
# GitHub API Rate Limit
# ---------------------------------------------------------------------------
get_graphql_rate_limit() {
    local now mtime=0 remaining=-1
    now=$(date +%s)
    if [[ -f "$RATE_LIMIT_CACHE" ]]; then
        mtime=$(stat -c %Y "$RATE_LIMIT_CACHE" 2>/dev/null || echo 0)
    fi
    if (( now - mtime < RATE_LIMIT_CHECK_INTERVAL )); then
        cat "$RATE_LIMIT_CACHE" 2>/dev/null || echo -1
        return
    fi
    local rate_json
    rate_json=$(gh api rate_limit 2>/dev/null)
    if [[ -n "$rate_json" ]]; then
        remaining=$(echo "$rate_json" | python3 -c "
import json, sys
data = json.load(sys.stdin)
gql = data.get('resources', {}).get('graphql', {})
print(gql.get('remaining', -1))
" 2>/dev/null || echo -1)
        local reset_at
        reset_at=$(echo "$rate_json" | python3 -c "
import json, sys, datetime
data = json.load(sys.stdin)
gql = data.get('resources', {}).get('graphql', {})
ts = gql.get('reset', 0)
print(datetime.datetime.fromtimestamp(ts).strftime('%H:%M:%S') if ts else 'unknown')
" 2>/dev/null || echo "unknown")
        echo "$remaining" > "$RATE_LIMIT_CACHE"
        if (( remaining >= 0 && remaining < RATE_LIMIT_THRESHOLD )); then
            log "[rate-limit] ⚠️  GraphQL: $remaining/$( echo "$rate_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('resources',{}).get('graphql',{}).get('limit',5000))" 2>/dev/null ) remaining (resets $reset_at)"
        fi
    fi
    echo "$remaining"
}

is_rate_limited() {
    local remaining
    remaining=$(get_graphql_rate_limit)
    (( remaining >= 0 && remaining < RATE_LIMIT_THRESHOLD ))
}

wait_for_rate_limit() {
    local loop_name="${1:-}"
    while is_rate_limited; do
        check_loop_stop || return 1
        local remaining
        remaining=$(get_graphql_rate_limit)
        log "[${loop_name}] 🛑 Rate limited — $remaining remaining (threshold: $RATE_LIMIT_THRESHOLD). Sleeping 60s..."
        sleep 60
        rm -f "$RATE_LIMIT_CACHE"
    done
    return 0
}

# ---------------------------------------------------------------------------
# PID Tracking (per agent type)
# ---------------------------------------------------------------------------
track_agent_pid() {
    local agent_type="$1" pid="$2"
    echo "$pid" >> "$AGENT_PIDS_DIR/${agent_type}.pids"
}

clean_agent_pids() {
    local agent_type="$1"
    local pidfile="$AGENT_PIDS_DIR/${agent_type}.pids"
    [[ -f "$pidfile" ]] || return
    local alive=""
    while IFS= read -r pid; do
        [[ -z "$pid" ]] && continue
        if kill -0 "$pid" 2>/dev/null; then
            alive+="$pid"$'\n'
        fi
    done < "$pidfile"
    echo -n "$alive" > "$pidfile"
}

count_active_agents() {
    local agent_type="$1"
    clean_agent_pids "$agent_type"
    local pidfile="$AGENT_PIDS_DIR/${agent_type}.pids"
    [[ -f "$pidfile" ]] || { echo 0; return; }
    local c
    c=$(grep -c . "$pidfile" 2>/dev/null || true)
    echo "${c:-0}"
}

any_agents_running_global() {
    for pidfile in "$AGENT_PIDS_DIR"/*.pids; do
        [[ -f "$pidfile" ]] || continue
        while IFS= read -r pid; do
            [[ -z "$pid" ]] && continue
            if kill -0 "$pid" 2>/dev/null; then
                return 0
            fi
        done < "$pidfile"
    done
    return 1
}

# ---------------------------------------------------------------------------
# Bounce tracking
# ---------------------------------------------------------------------------
get_bounce_count() {
    local issue_num="$1"
    if [[ -f "$BOUNCE_FILE" ]]; then
        grep -c "^${issue_num}$" "$BOUNCE_FILE" 2>/dev/null || echo 0
    else
        echo 0
    fi
}

record_bounce() {
    echo "$1" >> "$BOUNCE_FILE"
}

escalate_to_human() {
    local issue_num="$1" title="$2" bounces="$3"
    log "[review] 🚨 #$issue_num bounced $bounces times — escalating to Need Human"
    set_status "$issue_num" "Need Human"
    openclaw system event --text "🚨 Dev Loop Escalation: Issue #$issue_num ($title) has failed AI review $bounces times and has been moved to Need Human. Please review manually: https://github.com/$REPO/issues/$issue_num" --mode now 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Loop management
# ---------------------------------------------------------------------------
kill_all_loops() {
    if [[ -f "$LOOP_PIDS_FILE" ]]; then
        while read -r name pid; do
            [[ -z "$pid" ]] && continue
            kill "$pid" 2>/dev/null || true
        done < "$LOOP_PIDS_FILE"
    fi
}

kill_all_agents() {
    for pidfile in "$AGENT_PIDS_DIR"/*.pids; do
        [[ -f "$pidfile" ]] || continue
        while IFS= read -r pid; do
            [[ -z "$pid" ]] && continue
            kill "$pid" 2>/dev/null || true
        done < "$pidfile"
    done
}

cleanup() {
    rm -f "$LOOP_PIDS_FILE"
    rm -f "$AGENT_PIDS_DIR"/*.pids
    rm -f "$BOARD_CACHE_FILE" "$BOARD_CACHE_LOCK"
}

launch_loop() {
    local name="$1" func="$2"
    $func &
    local pid=$!
    if [[ -f "$LOOP_PIDS_FILE" ]]; then
        sed -i "/^${name} /d" "$LOOP_PIDS_FILE" 2>/dev/null || true
    fi
    echo "$name $pid" >> "$LOOP_PIDS_FILE"
    log "🚀 Launched $name loop (PID $pid)"
}

check_and_restart_loops() {
    local -A expected_loops=(
        [sync]=loop_sync
        [triage]=loop_triage
        [planning]=loop_planning
        [implement]=loop_implement
        [promote]=loop_promote
        [review]=loop_review
        [audit]=loop_audit
        [status]=loop_status
    )
    for name in "${!expected_loops[@]}"; do
        local pid=""
        if [[ -f "$LOOP_PIDS_FILE" ]]; then
            pid=$(awk -v n="$name" '$1==n {print $2}' "$LOOP_PIDS_FILE" 2>/dev/null)
        fi
        if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
            log "⚠️  $name loop died — restarting"
            launch_loop "$name" "${expected_loops[$name]}"
        fi
    done
}
