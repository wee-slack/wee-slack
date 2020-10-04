# Contributing

Thank you for considering contributing to `wee-slack`!

## Requirements

* [`git`](https://git-scm.com)
* [`pipenv`](https://github.com/pypa/pipenv)

## Activating the development environment

The development environment contains a few useful tools. Before testing or
working on `wee-slack`, the development environment should be activated. This
will ensure you have access to the necessary development tools.

```
$ cd /path/to/wee-slack
$ pipenv shell

# Install the required development dependencies
$ pipenv install --dev
```

The rest of this document assumes that the development environment has been
activated, and that you have the latest development dependencies installed.

## Testing

Tests are executed with `pytest`. To run the tests, first navigate to the
project root, and then execute:

```
$ pytest
```

## Updating dependencies

It's important to keep our dependencies up-to-date over time. Because we support
multiple versions of Python, we avoid committing the `Pipfile.lock` file (which
is added in `.gitignore`), in addition to avoiding pinning versions of packages.

To update the dependencies installed in your local virtual environment:

```
# Check for upstream updates
$ pipenv update --outdated

# Want to update everything?
$ pipenv update

# Want to update one package at a time?
$ pipenv update <pkg>
```

It's important to [run the tests](#testing) after updating dependencies to
ensure that the updated dependencies have not broken the build.
