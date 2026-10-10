# Contributing

Thanks for helping! Pull requests are welcome.

## Contributor agreement (MIT)

This project is released under the [MIT License](LICENSE). By submitting a pull
request you agree that:

1. You wrote the contribution yourself, or you have the right to submit it.
2. Your contribution is licensed to the project and to everyone who receives it
   under the MIT License (same terms as `LICENSE`), and you grant the maintainer
   the right to release it under the MIT License.
3. You keep the copyright to your contribution.

You confirm this by ticking the agreement checkbox in the pull request
template. A pull request without the ticked checkbox cannot be merged
(enforced by the `Contributor agreement` check).

## Development

* Pure logic lives in `custom_components/stundenplan/schedule.py` and is covered by
  `python -m pytest tests`.
* CI runs the tests, `hassfest` and the HACS validation on every pull request.
