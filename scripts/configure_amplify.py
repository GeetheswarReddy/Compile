"""Preview or apply the existing Amplify app's repository build configuration."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-id', required=True)
    parser.add_argument('--api-url', required=True)
    parser.add_argument('--region', default='ap-southeast-2')
    parser.add_argument('--apply', action='store_true', help='Update the app; without this flag only print planned settings')
    args = parser.parse_args()
    if not args.api_url.startswith('https://'):
        parser.error('--api-url must use HTTPS')
    specification = (Path(__file__).resolve().parents[1] / 'amplify.yml').read_text()
    planned = {'AMPLIFY_MONOREPO_APP_ROOT': 'frontend', 'VITE_API_BASE_URL': args.api_url.rstrip('/'), 'VITE_DEMO_TRACE': 'true'}
    print('App:', args.app_id)
    print('Build specification: repository root amplify.yml')
    print('SPA rewrite: /<*> -> /index.html (404-200)')
    for key, value in planned.items():
        print(f'{key}={value}')
    if not args.apply:
        print('Preview only. Use --apply after approving this configuration.')
        return
    import boto3
    client = boto3.client('amplify', region_name=args.region)
    current = client.get_app(appId=args.app_id)['app']
    environment = {**current.get('environmentVariables', {}), **planned}
    environment.pop('API_BASE_URL', None)
    environment.pop('DEMO_TRACE', None)
    client.update_app(appId=args.app_id, environmentVariables=environment, buildSpec=specification,
                      customRules=[{'source': '/<*>', 'target': '/index.html', 'status': '404-200'}])
    print('Amplify configuration updated. No build was started and no Git push was performed.')


if __name__ == '__main__':
    main()
