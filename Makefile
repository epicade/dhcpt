.PHONY: help install install-dev install-testbed check test lint format testbed-start testbed-stop testbed-status testbed-run testbed-shell man clean

PYTHON ?= python3
SUDO   ?= $(shell if [ "$$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then echo "sudo"; fi)
NS     ?= workstation

help:  ## Show this help message
	@awk 'BEGIN {FS = ":.*?## "} \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } \
		/^[a-zA-Z0-9_-]+:.*?## / { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

##@ Installation

install:  ## Install package globally via pipx for production use
	@echo "==> Installing dhcpt globally via pipx..."
	@if command -v pipx >/dev/null 2>&1; then \
		$(SUDO) pipx install --global .; \
	else \
		$(SUDO) $(PYTHON) -m pip install . || $(SUDO) $(PYTHON) -m pip install --break-system-packages .; \
	fi
	@echo "[OK] dhcpt installed globally into /usr/local/bin/dhcpt!"

install-dev:  ## Set up development environment (lint tools, git hooks, dev dependencies, dev symlinks)
	@echo "==> Checking development system packages and Python dependencies..."
	@PKGS=""; \
	command -v pandoc >/dev/null 2>&1 || PKGS="$$PKGS pandoc"; \
	command -v shellcheck >/dev/null 2>&1 || PKGS="$$PKGS shellcheck"; \
	command -v man >/dev/null 2>&1 || PKGS="$$PKGS man-db groff"; \
	$(PYTHON) -c "import scapy" >/dev/null 2>&1 || PKGS="$$PKGS python3-scapy"; \
	$(PYTHON) -c "import pytest" >/dev/null 2>&1 || PKGS="$$PKGS python3-pytest"; \
	$(PYTHON) -c "import pytest_mock" >/dev/null 2>&1 || PKGS="$$PKGS python3-pytest-mock"; \
	$(PYTHON) -c "import yaml" >/dev/null 2>&1 || PKGS="$$PKGS python3-yaml"; \
	if [ -n "$$PKGS" ]; then \
		if command -v apt-get >/dev/null 2>&1; then \
			echo "Installing missing development dependencies via apt-get:$$PKGS"; \
			DEBIAN_FRONTEND=noninteractive $(SUDO) apt-get update && DEBIAN_FRONTEND=noninteractive $(SUDO) apt-get install -y --no-install-recommends $$PKGS; \
		elif command -v dnf >/dev/null 2>&1; then \
			echo "Installing missing development dependencies via dnf:$$PKGS"; \
			$(SUDO) dnf install -y $$PKGS; \
		elif command -v pacman >/dev/null 2>&1; then \
			echo "Installing missing development dependencies via pacman:$$PKGS"; \
			$(SUDO) pacman -S --needed --noconfirm $$PKGS; \
		fi; \
	fi
	@if ! command -v ruff >/dev/null 2>&1; then \
		echo "Installing ruff linter via pip..."; \
		$(PYTHON) -m pip install ruff 2>/dev/null || $(PYTHON) -m pip install --break-system-packages ruff 2>/dev/null || true; \
	fi
	@echo "==> Configuring Git pre-commit hooks..."
	@git config core.hooksPath .githooks 2>/dev/null || true
	@echo "==> Setting up development symlinks in /usr/local..."
	@$(SUDO) ln -sf "$$(pwd)/src/dhcpt/cli.py" /usr/local/bin/dhcpt 2>/dev/null || true
	@$(SUDO) chmod +x "$$(pwd)/src/dhcpt/cli.py" 2>/dev/null || true
	@$(SUDO) mkdir -p /usr/local/share/man/man1 /usr/local/share/bash-completion/completions /usr/local/share/zsh/site-functions 2>/dev/null || true
	@$(SUDO) ln -sf "$$(pwd)/man/dhcpt.1" /usr/local/share/man/man1/dhcpt.1 2>/dev/null || true
	@$(SUDO) ln -sf "$$(pwd)/completions/bash/dhcpt" /usr/local/share/bash-completion/completions/dhcpt 2>/dev/null || true
	@$(SUDO) ln -sf "$$(pwd)/completions/zsh/_dhcpt" /usr/local/share/zsh/site-functions/_dhcpt 2>/dev/null || true
	@echo "==> Verifying development environment resolution..."
	@ALL_BINS=$$(which -a dhcpt 2>/dev/null || command -v dhcpt 2>/dev/null || true); \
	ACTIVE_BIN=$$(echo "$$ALL_BINS" | head -n1); \
	if [ -n "$$ACTIVE_BIN" ]; then \
		ACTIVE_TARGET=$$(readlink -f "$$ACTIVE_BIN" 2>/dev/null || echo "$$ACTIVE_BIN"); \
		if [ "$$ACTIVE_TARGET" = "$$(pwd)/src/dhcpt/cli.py" ]; then \
			echo "  [OK] Active binary       : $$ACTIVE_BIN -> $$ACTIVE_TARGET"; \
		else \
			echo "  [WARN] Active binary     : $$ACTIVE_BIN does not point to current repository! ($$ACTIVE_TARGET)"; \
		fi; \
		NUM_BINS=$$(echo "$$ALL_BINS" | grep -v '^$$' | wc -l); \
		if [ "$$NUM_BINS" -gt 1 ]; then \
			echo "  [WARN] Multiple 'dhcpt' binaries found in PATH:"; \
			for b in $$ALL_BINS; do \
				if [ "$$b" != "$$ACTIVE_BIN" ]; then \
					echo "         -> Shadowed: $$b ($$(readlink -f "$$b" 2>/dev/null || echo "file"))"; \
				fi; \
			done; \
			echo "         (Consider removing shadowed copies to prevent version drift)"; \
		fi; \
	else \
		echo "  [WARN] Active binary     : 'dhcpt' not found in PATH!"; \
	fi
	@if command -v sudo >/dev/null 2>&1; then \
		SUDO_VER=$$($(SUDO) dhcpt --version 2>&1 || true); \
		if echo "$$SUDO_VER" | grep -q "^dhcpt "; then \
			echo "  [OK] Sudo execution      : $$SUDO_VER ($$($(SUDO) which dhcpt 2>/dev/null))"; \
		else \
			echo "  [WARN] Sudo execution    : 'sudo dhcpt --version' failed! ($$SUDO_VER)"; \
		fi; \
	fi
	@RESOLVED_MAN=$$(man -w dhcpt 2>/dev/null || true); \
	if [ -n "$$RESOLVED_MAN" ]; then \
		MAN_TARGET=$$(readlink -f "$$RESOLVED_MAN" 2>/dev/null || echo "$$RESOLVED_MAN"); \
		if [ "$$MAN_TARGET" = "$$(pwd)/man/dhcpt.1" ]; then \
			echo "  [OK] Manpage resolution  : $$RESOLVED_MAN -> $$MAN_TARGET"; \
		else \
			echo "  [WARN] Manpage resolution: $$RESOLVED_MAN ($$MAN_TARGET) does not link to $$(pwd)/man/dhcpt.1!"; \
		fi; \
	else \
		echo "  [WARN] Manpage resolution: 'dhcpt' not found by 'man -w dhcpt'"; \
	fi
	@if command -v zsh >/dev/null 2>&1; then \
		ZSH_OUT=$$(zsh -i -c 'autoload +X -U _dhcpt 2>/dev/null && whence -v _dhcpt' 2>/dev/null || true); \
		ZSH_FILE=$$(echo "$$ZSH_OUT" | grep -oP '(?<=from )\S+' 2>/dev/null || true); \
		if [ -n "$$ZSH_FILE" ]; then \
			ZSH_TARGET=$$(readlink -f "$$ZSH_FILE" 2>/dev/null || echo "$$ZSH_FILE"); \
			if [ "$$ZSH_TARGET" = "$$(pwd)/completions/zsh/_dhcpt" ]; then \
				echo "  [OK] Zsh completion      : active from $$ZSH_FILE -> $$ZSH_TARGET"; \
			else \
				echo "  [WARN] Zsh completion    : active from $$ZSH_FILE (shadowing $$(pwd)/completions/zsh/_dhcpt)!"; \
			fi; \
		else \
			if zsh -f -c 'fpath=(/usr/local/share/zsh/site-functions $$fpath); autoload +X -U _dhcpt' >/dev/null 2>&1; then \
				echo "  [OK] Zsh completion      : autoloadable via /usr/local/share/zsh/site-functions/_dhcpt"; \
			else \
				echo "  [WARN] Zsh completion    : not found in zsh fpath"; \
			fi; \
		fi; \
	fi
	@BASH_COMP=""; \
	for p in "$$HOME/.local/share/bash-completion/completions/dhcpt" "/usr/local/share/bash-completion/completions/dhcpt" "/etc/bash_completion.d/dhcpt"; do \
		if [ -e "$$p" ]; then BASH_COMP="$$p"; break; fi; \
	done; \
	if [ -n "$$BASH_COMP" ]; then \
		BASH_TARGET=$$(readlink -f "$$BASH_COMP" 2>/dev/null || echo "$$BASH_COMP"); \
		if [ "$$BASH_TARGET" = "$$(pwd)/completions/bash/dhcpt" ]; then \
			echo "  [OK] Bash completion     : $$BASH_COMP -> $$BASH_TARGET"; \
		else \
			echo "  [WARN] Bash completion   : $$BASH_COMP does not point to $$(pwd)/completions/bash/dhcpt!"; \
		fi; \
	else \
		echo "  [WARN] Bash completion   : no completion file found in standard search paths"; \
	fi
	@echo "[OK] Development environment ready! Git hooks active, edits in src/dhcpt/cli.py are live."

install-testbed:  ## Install system packages for live Kea testbed (Kea, Scapy, Jq, Busybox)
	@echo "==> Checking and installing live Kea testbed system packages..."
	@PKGS=""; \
	command -v jq >/dev/null 2>&1 || PKGS="$$PKGS jq"; \
	command -v busybox >/dev/null 2>&1 || PKGS="$$PKGS busybox"; \
	command -v zsh >/dev/null 2>&1 || PKGS="$$PKGS zsh"; \
	if command -v apt-get >/dev/null 2>&1; then \
		dpkg -s kea-dhcp4-server >/dev/null 2>&1 || PKGS="$$PKGS kea-dhcp4-server"; \
		dpkg -s python3-scapy >/dev/null 2>&1 || PKGS="$$PKGS python3-scapy"; \
		if [ -n "$$PKGS" ]; then \
			echo "Installing testbed packages via apt-get:$$PKGS"; \
			DEBIAN_FRONTEND=noninteractive $(SUDO) apt-get update && DEBIAN_FRONTEND=noninteractive $(SUDO) apt-get install -y --no-install-recommends $$PKGS; \
		fi; \
	elif command -v dnf >/dev/null 2>&1; then \
		rpm -q kea >/dev/null 2>&1 || PKGS="$$PKGS kea"; \
		rpm -q python3-scapy >/dev/null 2>&1 || PKGS="$$PKGS python3-scapy"; \
		if [ -n "$$PKGS" ]; then \
			echo "Installing testbed packages via dnf:$$PKGS"; \
			$(SUDO) dnf install -y epel-release 2>/dev/null || true; \
			$(SUDO) dnf install -y $$PKGS; \
		fi; \
	elif command -v pacman >/dev/null 2>&1; then \
		pacman -Qi kea >/dev/null 2>&1 || PKGS="$$PKGS kea"; \
		if [ -n "$$PKGS" ]; then \
			echo "Installing testbed packages via pacman:$$PKGS"; \
			$(SUDO) pacman -S --needed --noconfirm $$PKGS python-scapy; \
		fi; \
	fi
	@echo "[OK] Live testbed system packages ready!"

##@ Verification & Quality

check: lint test  ## Run all linters and the unit test suite (lint + test)

test:  ## Run pytest unit test suite
	PYTHONPATH=src $(PYTHON) -m pytest -v

lint:  ## Run linters (ruff, shellcheck, zsh syntax, manpage, kea configs, version consistency)
	ruff check .
	ruff format --check .
	shellcheck completions/bash/dhcpt
	find tests/e2e -type f -name "*.sh" -exec shellcheck {} +
	bash -o noexec completions/bash/dhcpt
	find tests/e2e -type f -name "*.sh" -exec bash -o noexec {} +
	tests/e2e/testbed.sh check-config
	@echo "Validating YAML configuration and CI workflow syntax..."
	@$(PYTHON) -c "import yaml, glob; files = glob.glob('.github/**/*.yml', recursive=True) + glob.glob('*.yml') + glob.glob('*.yaml'); [yaml.safe_load(open(f, encoding='utf-8')) for f in files]"
	@echo "Validating project version consistency..."
	@$(PYTHON) tests/test_version_consistency.py
	@if command -v zsh >/dev/null 2>&1; then \
		echo "Validating Zsh and Bash completions (syntax & runtime tab-trigger)..."; \
		zsh --noexec completions/zsh/_dhcpt; \
		$(PYTHON) -m pytest -q tests/test_cli.py -k "tab_completion"; \
	fi
	@if command -v man >/dev/null 2>&1; then \
		echo "Validating manpage formatting..."; \
		man -l man/dhcpt.1 >/dev/null; \
	fi
	@if command -v pandoc >/dev/null 2>&1 && command -v man >/dev/null 2>&1; then \
		echo "Validating manpage is up-to-date with Markdown source..."; \
		pandoc man/dhcpt.1.md -s -t man -f markdown-smart -o /tmp/check_dhcpt.1 && \
		MANWIDTH=80 man -l man/dhcpt.1 | col -bx > /tmp/r_committed.txt && \
		MANWIDTH=80 man -l /tmp/check_dhcpt.1 | col -bx > /tmp/r_new.txt && \
		diff -u /tmp/r_committed.txt /tmp/r_new.txt >/dev/null || \
		{ echo "" >&2; \
		  echo "[ERROR] man/dhcpt.1 is out of date with man/dhcpt.1.md! Run 'make man' to recompile." >&2; \
		  diff -u /tmp/r_committed.txt /tmp/r_new.txt >&2 || true; \
		  rm -f /tmp/check_dhcpt.1 /tmp/r_committed.txt /tmp/r_new.txt; exit 1; }; \
		rm -f /tmp/check_dhcpt.1 /tmp/r_committed.txt /tmp/r_new.txt; \
	fi

format:  ## Automatically format code with ruff
	ruff check --fix .
	ruff format .

##@ Live Network Testbed

testbed-run:  ## Run live network test suites against active Kea testbed
	@$(SUDO) tests/e2e/testbed.sh run

testbed-start:  ## Start local Kea DHCP4 testbed with isolated network namespaces
	@$(SUDO) tests/e2e/testbed.sh start

testbed-stop:  ## Stop local Kea DHCP4 testbed and remove network namespaces
	@$(SUDO) tests/e2e/testbed.sh stop

testbed-status:  ## Show status of local Kea DHCP4 testbed
	@$(SUDO) tests/e2e/testbed.sh status

testbed-shell:  ## Open interactive shell in testbed namespace (usage: make testbed-shell NS=workstation)
	@$(SUDO) tests/e2e/testbed.sh shell $(NS)

##@ Build & Housekeeping

man:  ## Compile man/dhcpt.1 from man/dhcpt.1.md using pandoc
	pandoc man/dhcpt.1.md -s -t man -f markdown-smart -o man/dhcpt.1

clean:  ## Remove build artifacts, caches, and testbed runtime files
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache /tmp/dhcpt-kea-*
	find . -type d -name __pycache__ -exec rm -rf {} +
