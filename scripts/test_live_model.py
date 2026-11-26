"""One real-provider synthetic investigation; consumes API credits when configured.

This is a smoke test, not an automatic verdict on model accuracy.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import get_settings
from app.data_loader import DataStore
from app.agent import VarianceAgent


def main():
    os.chdir(ROOT)
    settings = get_settings()
    if not settings.openai_api_key:
        print('No API key configured. Run python scripts/configure_model.py in a terminal.')
        return 2
    settings.max_agent_iterations = 6
    settings.max_tokens_per_turn = 2048
    fixture = ROOT / 'tests/fixtures/synthetic_product/reconciled_40_transactions'
    store = DataStore.from_csv(fixture/'budget.csv', fixture/'transactions.csv', source='synthetic')
    events = []
    agent = None
    try:
        agent = VarianceAgent(store)
        for event in agent.investigate(period='2026-09'):
            events.append(event)
            print('Event:', event['type'])
    except Exception as exc:
        # Do not log provider exception bodies, credentials, or request headers.
        print('Provider call failed:', type(exc).__name__, '(check key, credits and connectivity locally).')
        return 1
    finally:
        if agent is not None:
            agent.client.close()
    finished = any(e['type']=='final' and e.get('markdown') for e in events)
    success = bool(finished and events[-1]['type']=='done' and not any(e['type']=='error' for e in events))
    report = dict(model=settings.openai_model, live_model_tested=True,
                  completed=success, accuracy_review_required=True,
                  expected=dict(actual=40780, budget=30000, variance=10780,
                                variance_percent=35.9333333333, transaction_count=40,
                                reconciliation='matched'), events=events)
    output = ROOT/'data/live-test-results'
    output.mkdir(parents=True, exist_ok=True)
    (output/'latest.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print('Saved local trace to data/live-test-results/latest.json. Review claims and source references against expected values.')
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
