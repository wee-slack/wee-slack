# Contributing

Thank you for considering contributing to `wee-slack`!

## Requirements

* [`git`](https://git-scm.com)
* [`uv`](https://docs.astral.sh/uv/)

## Installing dependencies

The main dependencies are installed automatically when running `uv` commands,
but to install the dependencies required by the `extract_token_from_browser.py`
script, first navigate to the project root, and then execute:

```
$ uv sync --all-extras
```

## Formatting and linting

The code is formatted and linted with [`ruff`](https://docs.astral.sh/ruff/).
To format all the files, first navigate to the project root, and then execute:

```
$ uv run ruff format
```

To lint all the files, first navigate to the project root, and then execute:

```
$ uv run ruff check
```

## Testing

Tests are executed with [`pytest`](https://pytest.org/). To run the tests,
first navigate to the project root, and then execute:

```
$ uv run pytest
```

## Updating dependencies

It's important to keep our dependencies up-to-date over time. To update the
dependencies installed in your local virtual environment:

```
# Check for upstream updates
$ uv tree --depth 1 --outdated

# Want to update everything?
$ uv lock --upgrade

# Want to update one package at a time?
$ uv lock --upgrade-package <pkg>
```

It's important to [run the tests](#testing) after updating dependencies to
ensure that the updated dependencies have not broken the build.
