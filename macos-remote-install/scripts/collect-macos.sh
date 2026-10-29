#!/bin/sh
# Run on A. Read-only system queries; only a fresh report directory is written.
set -u
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH
if [ "$(uname -s)" != Darwin ]; then
    printf '%s\n' 'Refused: run this collector only on target A in macOS.' >&2
    exit 2
fi
if [ "$#" -ne 1 ]; then
    printf '%s\n' 'Usage: sh collect-macos.sh /absolute/path/to/new-report-directory' >&2
    exit 2
fi
case "$1" in /*) ;; *) printf '%s\n' 'An absolute output path is required.' >&2; exit 2;; esac
umask 077
report=$1
mkdir "$report" || exit 2
failures=0
run() {
    name=$1
    shift
    "$@" > "$report/$name.txt" 2> "$report/$name.stderr.txt"
    result=$?
    printf '%s\t%s\n' "$name" "$result" >> "$report/exit-codes.tsv"
    if [ "$result" -ne 0 ]; then failures=$((failures + 1)); fi
}
date -u '+%Y-%m-%dT%H:%M:%SZ' > "$report/captured_at_utc.txt"
printf '%s\n' 'Private target inventory. Not a shareable report until reviewed and redacted.' > "$report/READ-ME.txt"
run os sw_vers
run kernel uname -a
run cpu sysctl machdep.cpu.brand_string hw.physicalcpu hw.logicalcpu hw.memsize
run disks diskutil list -plist
run physical-disks diskutil list physical
run root-volume diskutil info -plist /
run hardware system_profiler SPHardwareDataType SPDisplaysDataType SPUSBDataType SPNetworkDataType SPBluetoothDataType SPNVMeDataType SPSerialATADataType -detailLevel mini -timeout 120
run network-ports networksetup -listallhardwareports
run network-order networksetup -listnetworkserviceorder
run route route -n get default
run loaded-kexts kmutil showloaded
run power-settings pmset -g custom
run power-assertions pmset -g assertions
run power-schedules pmset -g sched
run boot-args nvram boot-args
run sip csrutil status
# Bound stored power-log output. Capture source status separately from tail status.
pmset -g log > "$report/power-history.tmp" 2> "$report/power-history.stderr.txt"
log_status=$?
tail -n 500 "$report/power-history.tmp" > "$report/power-history.txt"
printf '%s\t%s\n' 'power-history' "$log_status" >> "$report/exit-codes.tsv"
if [ "$log_status" -eq 0 ]; then
    rm "$report/power-history.tmp"
else
    failures=$((failures + 1))
fi
printf 'Report: %s\nQuery failures: %s (see exit-codes.tsv)\n' "$report" "$failures"
if [ "$failures" -gt 0 ]; then exit 2; fi
