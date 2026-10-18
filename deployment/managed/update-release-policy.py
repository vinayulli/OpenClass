"""Refresh exact Gateway routes without resetting live release environments."""
import json
from pathlib import Path
import runpy


def main():
    directory = Path(__file__).resolve().parent
    target = directory/'release.auto.tfvars.json'
    values = json.loads(target.read_text())
    outputs = json.loads((directory/'terraform.tfstate').read_text())['outputs']
    environment = values['runtime_environment']
    inventory = {
        'principals': json.loads(environment['OPENCLASS_WORKLOAD_PRINCIPALS']),
        'registered_agents': outputs['registered_agents']['value'],
        'registered_mcp_servers': outputs['registered_mcp_servers']['value'],
        'registered_endpoints': {'coordinator': outputs['registered_coordinator']['value']},
        'coordinator_url': values['coordinator_url'],
        'google_api_context': {'project_number': '159888433965', 'region': environment['GOOGLE_CLOUD_LOCATION'],
            'model': environment['GEMINI_MODEL'], 'armor_template': environment['MODEL_ARMOR_TEMPLATE']},
    }
    module = runpy.run_path(str(directory/'render-policy.py'))
    values['gateway_rules'] = module['compile_policy'](module['render'](inventory))
    target.write_text(json.dumps(values, indent=2)+'\n')
    print('Prepared', len(values['gateway_rules']), 'exact Gateway rules; live environments preserved')


if __name__ == '__main__':
    main()
