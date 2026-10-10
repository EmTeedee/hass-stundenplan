# Contributing

Thanks for helping! Pull requests are welcome.

## Contributor agreement (MIT)

This project is released under the [MIT License](LICENSE). By signing this agreement you
confirm for all your contributions to this project that:

1. You wrote the contribution yourself, or you have the right to submit it.
2. Your contribution is licensed to the project and to everyone who receives it
   under the MIT License (same terms as `LICENSE`), and you grant the maintainer
   the right to release it under the MIT License.
3. You keep the copyright to your contribution.

**You sign once per author, not per pull request.** On your first pull request the CLA bot
comments with instructions: reply with exactly

> I have read the CLA Document and I hereby sign the CLA

Your GitHub username is then recorded in the `cla-signatures` branch (`signatures/cla.json`)
and all your later pull requests pass the `CLAAssistant` check automatically. Comment
`recheck` to re-run the check. The maintainer and bots (Dependabot) are exempt.

## Development

* Pure logic lives in `custom_components/stundenplan/schedule.py` and is covered by
  `python -m pytest tests`.
* CI runs the tests, Hassfest and the HACS validation on every pull request.
