# Real model testing

The main product now performs a deterministic review first. Use its finding-level “Investigate with AI” button to test the new scoped adapter. It returns an unverified structured draft and checks whether its references resolve. For a bounded five-case evaluation of that same adapter, run `python scripts/evaluate_live_ai.py --live`. Run it without `--live` to validate the fixtures without network calls. Review every saved draft against its rubric; citation existence alone is not an accuracy result. No live evaluation has been completed yet because the local key is absent. The older command below exercises the autonomous agent as a research baseline, not the new product workflow.

The product uses the OpenAI Responses API, with `gpt-4.1-mini` as the configurable default. Create an API key at https://platform.openai.com/api-keys. A chat subscription does not automatically configure this application. See the [OpenAI quickstart](https://developers.openai.com/api/docs/quickstart).

From this repository, run `python scripts/configure_model.py` in an interactive terminal and enter your provider key at the hidden prompt. The helper writes only to the ignored local `.env` and refuses to replace an existing key entry. Never paste credentials into chat or commit them. Environment variables take precedence over `.env`. Restart a running server after configuring it.

Run `python scripts/test_live_model.py` to investigate the bundled fictional 40-transaction case with the real provider. This uses API credits, with at most six agent turns and 2,048 output tokens per turn (input tokens and SDK retries also incur usage). It does not modify a deployed dataset. The model can be overridden with `OPENAI_MODEL` in `.env`.

The ignored `data/live-test-results/latest.json` contains the synthetic trace, expected totals, and completion status. Completion is not an accuracy pass: review whether the final response reports actual 40,780, budget 30,000, variance 10,780 / 35.9%, correctly reconciles the ledger, and cites real returned source IDs without inventing causes. Additional missing-ledger and adversarial-memo evaluations remain necessary before claiming model reliability.

Without a key, the command exits 2 before making any provider call. Deterministic validation is independently reproducible with `python -m pytest -q` and `python scripts/test_synthetic_product.py`.
