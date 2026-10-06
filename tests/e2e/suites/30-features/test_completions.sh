#!/usr/bin/env bash
# E2E Test: Interactive Tab-Tab Completion in Bash and Zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
# shellcheck source=tests/e2e/helpers/assert.sh
source "${SCRIPT_DIR}/../../helpers/assert.sh"

# 1. Test Bash Autocompletion Functionality
BASH_SCRIPT="${PROJECT_ROOT}/completions/bash/dhcpt"
if [ -f "$BASH_SCRIPT" ] && command -v bash >/dev/null 2>&1; then
    bash_out=$(bash -c "
source \"$BASH_SCRIPT\"
COMP_WORDS=(dhcpt --)
COMP_CWORD=1
cur='--'
prev='dhcpt'
_dhcpt_bash
echo \"\${COMPREPLY[*]}\"
")
    assert_contains "Bash Tab completion contains --interface" "--interface" "$bash_out"
    assert_contains "Bash Tab completion contains --target-gateway" "--target-gateway" "$bash_out"
    assert_contains "Bash Tab completion contains --dhcp-servers" "--dhcp-servers" "$bash_out"
fi

# 2. Test Zsh Tab-Tab Interactive Completion via PTY
ZSH_SCRIPT="${PROJECT_ROOT}/completions/zsh/_dhcpt"
if [ -f "$ZSH_SCRIPT" ] && command -v zsh >/dev/null 2>&1; then
    zsh_test_py="
import os, pty, select, subprocess, sys

master, slave = pty.openpty()
proc = subprocess.Popen(['zsh', '-f'], stdin=slave, stdout=slave, stderr=slave, close_fds=True)
os.close(slave)

def send(cmd: str) -> None:
    os.write(master, cmd.encode('utf-8') + b'\n')

send('autoload -Uz compinit && compinit -D -u')
send('source \"${ZSH_SCRIPT}\"')
send('compdef _dhcpt dhcpt')
# Simulate pressing Tab on 'dhcpt '
os.write(master, b'dhcpt \t')
send('')
send('exit')

output = b''
while True:
    r, _, _ = select.select([master], [], [], 1.5)
    if not r:
        break
    try:
        data = os.read(master, 1024)
        if not data:
            break
        output += data
    except OSError:
        break

os.close(master)
proc.wait()
out = output.decode('utf-8', errors='replace')

if '_arguments:' in out or 'comparguments:' in out or 'invalid argument' in out:
    print(f'[FAIL] Zsh completion syntax error: {out}', file=sys.stderr)
    sys.exit(1)

sys.exit(0)
"
    set +e
    python3 -c "$zsh_test_py"
    zsh_status=$?
    set -e
    assert_exit_code "Zsh Tab-Tab completion PTY test" 0 "$zsh_status"
fi
