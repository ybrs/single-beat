# Contributing

Install the pre-commit hook after cloning:

```sh
git config core.hooksPath .githooks
```

The hook runs the unit and end-to-end tests on every commit using Docker Compose. Before creating a pull request, run the hook and ensure all tests pass:

```sh
.githooks/pre-commit
```

Docker and the Compose plugin must be available and running. To remove the test containers afterward, run `docker compose -f compose.test.yaml down`.
