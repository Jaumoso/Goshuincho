# Contributing

Thanks for your interest in Goshuinchō! Bug reports, ideas and pull requests are welcome.

- **Bugs and ideas:** open an issue using one of the templates.
- **Place data:** if a shrine, temple or station is wrong or missing, the best fix is on [OpenStreetMap](https://www.openstreetmap.org), so every instance benefits on the next import.
- **Code:** for anything bigger than a small fix, open an issue first so we can agree on the approach.

## Development setup

See [Development](README.md#development) in the README. Before opening a pull request, make sure that:

- the backend tests pass: `docker compose -f docker-compose.test.yml run --rm --build tests`,
- new models come with their migration,
- the frontend builds and lints cleanly: `cd frontend && npm run build && npm run lint`,
- new UI text is added to both languages in `frontend/src/i18n.tsx`.

By contributing you agree that your contributions are licensed under the [AGPL-3.0](LICENSE).
