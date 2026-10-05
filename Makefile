.PHONY: help install test lint format check clean man

PYTHON ?= python3

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install:  ## Install package in editable mode with development dependencies
	$(PYTHON) -m pip install -e .[dev]

test:  ## Run pytest test suite
	PYTHONPATH=src $(PYTHON) -m pytest -v

lint:  ## Run linters (ruff, shellcheck, zsh syntax, manpage)
	ruff check .
	ruff format --check .
	shellcheck completions/bash/dhcpt
	bash -o noexec completions/bash/dhcpt
	@if command -v zsh >/dev/null 2>&1; then \
		echo "Validating Zsh completions..."; \
		zsh --noexec completions/zsh/_dhcpt; \
		zsh -f -c 'autoload -Uz compinit && compinit -D -u && source completions/zsh/_dhcpt'; \
	fi
	@if command -v man >/dev/null 2>&1; then \
		echo "Validating manpage formatting..."; \
		man -l man/dhcpt.1 >/dev/null; \
	fi
	@if command -v pandoc >/dev/null 2>&1; then \
		echo "Validating manpage is up-to-date with Markdown source..."; \
		pandoc man/dhcpt.1.md -s -t man -f markdown-smart -o /tmp/check_dhcpt.1 && cmp man/dhcpt.1 /tmp/check_dhcpt.1 && rm -f /tmp/check_dhcpt.1; \
	fi

man:  ## Compile man/dhcpt.1 from man/dhcpt.1.md using pandoc
	pandoc man/dhcpt.1.md -s -t man -f markdown-smart -o man/dhcpt.1

format:  ## Automatically format code with ruff
	ruff check --fix .
	ruff format .

check: lint test  ## Run all linters and the complete test suite

clean:  ## Clean temporary build, cache, and test artifacts
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
