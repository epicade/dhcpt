.PHONY: help install install-dev install-lint install-testbed test lint format check clean man testbed-start testbed-stop testbed-status testbed-workstation testbed-vpn-gw testbed-server testbed-rogue e2e

PYTHON         ?= python3
PANDOC_VERSION ?= 3.7.0.2
SUDO           ?= $(shell if [ "$$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then echo "sudo"; fi)

help:  ## Show this help message
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## Install package globally via pipx for production use
	@echo "==> Installing dhcpt globally via pipx..."
	@if command -v pipx >/dev/null 2>&1; then \
		$(SUDO) pipx install --global .; \
	else \
		$(SUDO) $(PYTHON) -m pip install . || $(SUDO) $(PYTHON) -m pip install --break-system-packages .; \
	fi
	@echo "[OK] dhcpt installed globally into /usr/local/bin/dhcpt!"

install-lint:  ## Install linting dependencies (pinned Pandoc, shellcheck, man-db, python dev dependencies)
	@echo "==> Checking and installing linting tools..."
	@if ! command -v pandoc >/dev/null 2>&1 || [ "$$(pandoc --version 2>/dev/null | head -n1 | awk '{print $$2}')" != "$(PANDOC_VERSION)" ]; then \
		echo "Installing official Pandoc $(PANDOC_VERSION) standalone binary..."; \
		if command -v dpkg >/dev/null 2>&1 && [ "$$(uname -m)" = "x86_64" ]; then \
			curl -sLO "https://github.com/jgm/pandoc/releases/download/$(PANDOC_VERSION)/pandoc-$(PANDOC_VERSION)-1-amd64.deb" && \
			$(SUDO) dpkg -i "pandoc-$(PANDOC_VERSION)-1-amd64.deb" && \
			rm -f "pandoc-$(PANDOC_VERSION)-1-amd64.deb"; \
		else \
			curl -sL "https://github.com/jgm/pandoc/releases/download/$(PANDOC_VERSION)/pandoc-$(PANDOC_VERSION)-linux-$$(uname -m).tar.gz" | \
			$(SUDO) tar -xzf - --strip-components=1 -C /usr/local/ 2>/dev/null || true; \
		fi; \
	else \
		echo "[OK] Pandoc $(PANDOC_VERSION) already present!"; \
	fi
	@PKGS=""; \
	command -v shellcheck >/dev/null 2>&1 || PKGS="$$PKGS shellcheck"; \
	command -v man >/dev/null 2>&1 || PKGS="$$PKGS man-db groff"; \
	if [ -n "$$PKGS" ]; then \
		if command -v apt-get >/dev/null 2>&1; then \
			echo "Installing missing tools via apt-get:$$PKGS"; \
			DEBIAN_FRONTEND=noninteractive $(SUDO) apt-get update && DEBIAN_FRONTEND=noninteractive $(SUDO) apt-get install -y --no-install-recommends $$PKGS; \
		elif command -v dnf >/dev/null 2>&1; then \
			echo "Installing missing tools via dnf:$$PKGS"; \
			$(SUDO) dnf install -y $$PKGS; \
		elif command -v pacman >/dev/null 2>&1; then \
			echo "Installing missing tools via pacman:$$PKGS"; \
			$(SUDO) pacman -S --needed --noconfirm $$PKGS; \
		fi; \
	else \
		echo "[OK] System linting tools (shellcheck, man) already present!"; \
	fi
	@echo "==> Installing Python package and dev dependencies for linting..."
	@$(PYTHON) -m pip install -e .[dev] 2>/dev/null || $(PYTHON) -m pip install --break-system-packages -e .[dev] 2>/dev/null || true
	@echo "[OK] Linting environment ready!"

install-testbed:  ## Install system packages for live Kea testbed (Kea, Scapy, Jq, Busybox)
	@echo "==> Checking and installing live testbed tools (Kea, Scapy, Jq, Busybox)..."
	@PKGS=""; \
	command -v jq >/dev/null 2>&1 || PKGS="$$PKGS jq"; \
	command -v zsh >/dev/null 2>&1 || PKGS="$$PKGS zsh"; \
	command -v pipx >/dev/null 2>&1 || PKGS="$$PKGS pipx"; \
	command -v busybox >/dev/null 2>&1 || PKGS="$$PKGS busybox"; \
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
			$(SUDO) dnf install -y $$PKGS gcc python3-devel; \
		fi; \
	elif command -v pacman >/dev/null 2>&1; then \
		pacman -Qi kea >/dev/null 2>&1 || PKGS="$$PKGS kea"; \
		if [ -n "$$PKGS" ]; then \
			$(SUDO) pacman -S --needed --noconfirm $$PKGS python-scapy python-pipx; \
		fi; \
	fi
	@echo "[OK] Testbed system tools ready!"

install-dev: install-lint install-testbed  ## Install full dev environment (lint, testbed, and live dev symlink)
	@echo "==> Setting up instant live-testing symlink to /usr/local/bin/dhcpt..."
	@$(SUDO) ln -sf "$$(pwd)/src/dhcpt/cli.py" /usr/local/bin/dhcpt 2>/dev/null || true
	@$(SUDO) chmod +x "$$(pwd)/src/dhcpt/cli.py" 2>/dev/null || true
	@echo "==> Symlinking manpage and shell completions for development..."
	@$(SUDO) mkdir -p /usr/local/share/man/man1 /usr/local/share/bash-completion/completions /usr/local/share/zsh/site-functions 2>/dev/null || true
	@$(SUDO) ln -sf "$$(pwd)/man/dhcpt.1" /usr/local/share/man/man1/dhcpt.1 2>/dev/null || true
	@$(SUDO) ln -sf "$$(pwd)/completions/bash/dhcpt" /usr/local/share/bash-completion/completions/dhcpt 2>/dev/null || true
	@$(SUDO) ln -sf "$$(pwd)/completions/zsh/_dhcpt" /usr/local/share/zsh/site-functions/_dhcpt 2>/dev/null || true
	@echo "[OK] Development environment ready! Edits in src/dhcpt/cli.py are immediately executed by 'dhcpt' and 'sudo dhcpt'."

test:  ## Run pytest test suite
	PYTHONPATH=src $(PYTHON) -m pytest -v

lint:  ## Run linters (ruff, shellcheck, zsh syntax, manpage, kea configs, version consistency)
	ruff check .
	ruff format --check .
	shellcheck completions/bash/dhcpt
	find tests/e2e -type f -name "*.sh" -exec shellcheck {} +
	bash -o noexec completions/bash/dhcpt
	find tests/e2e -type f -name "*.sh" -exec bash -o noexec {} +
	tests/e2e/testbed.sh check-config
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

man:  ## Compile man/dhcpt.1 from man/dhcpt.1.md using pandoc
	pandoc man/dhcpt.1.md -s -t man -f markdown-smart -o man/dhcpt.1

testbed-start:  ## Start local Kea DHCP4 testbed with isolated network namespaces
	@sudo tests/e2e/testbed.sh start

testbed-stop:  ## Stop local Kea DHCP4 testbed and remove network namespaces
	@sudo tests/e2e/testbed.sh stop

testbed-status:  ## Show status of local Kea DHCP4 testbed
	@sudo tests/e2e/testbed.sh status

testbed-workstation:  ## Open interactive shell in workstation namespace
	@sudo tests/e2e/testbed.sh shell workstation

testbed-vpn-gw:  ## Open interactive shell in vpn-gw router namespace
	@sudo tests/e2e/testbed.sh shell vpn-gw

testbed-server:  ## Open interactive shell in legitimate DHCP server namespace
	@sudo tests/e2e/testbed.sh shell dhcp-server

testbed-rogue:  ## Open interactive shell in rogue DHCP server namespace
	@sudo tests/e2e/testbed.sh shell dhcp-rogue

e2e:  ## Run end-to-end live network tests against active testbed
	@sudo tests/e2e/testbed.sh run

format:  ## Automatically format code with ruff
	ruff check --fix .
	ruff format .

check: lint test  ## Run all linters and the complete test suite

clean:  ## Remove build artifacts (dist, build, egg-info), Python caches (__pycache__, pytest, ruff), and clean testbed
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache /tmp/dhcpt-kea-*
	find . -type d -name __pycache__ -exec rm -rf {} +
