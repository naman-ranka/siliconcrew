import json
import time
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

project = 'siliconcrew'
region = 'us-central1'
updates = {
    'siliconcrew-backend': 'us-central1-docker.pkg.dev/siliconcrew/siliconcrew/backend@sha256:1b79fc453f5d8754edabf621774fb0eef290288aff13c634938fbdcd6e02e6a3',
    'siliconcrew-frontend': 'us-central1-docker.pkg.dev/siliconcrew/siliconcrew/frontend@sha256:d78cb64ea24ffb7ceada4aca5bf1cb5c27893ac587fac0ab33bbb9320d381a0f',
}

def main():
    creds = service_account.Credentials.from_service_account_file('gcp-key.json', scopes=['https://www.googleapis.com/auth/cloud-platform'])
    sess = AuthorizedSession(creds)

    for svc, new_image in updates.items():
        name = f'projects/{project}/locations/{region}/services/{svc}'
        url = f'https://run.googleapis.com/v2/{name}'
        
        # 1. Fetch current service
        print(f"Retrieving service config for {svc}...")
        r = sess.get(url, timeout=30)
        if r.status_code != 200:
            print(f"Error fetching service: {r.status_code}")
            print(r.text)
            raise SystemExit(1)
            
        service = r.json()
        containers = service['template']['containers']
        old_image = containers[0].get('image')
        
        # Update image
        containers[0]['image'] = new_image
        body = {
            'name': name,
            'template': {
                'containers': containers
            }
        }
        
        # 2. Validate patch
        print(f"Validating change for {svc}...")
        vr = sess.patch(f'{url}?updateMask=template.containers&validateOnly=true', json=body, timeout=60)
        if vr.status_code != 200:
            print(f"Validation failed for {svc}: {vr.status_code}")
            print(vr.text)
            raise SystemExit(2)
            
        # 3. Apply patch
        print(f"Applying change to {svc}...")
        pr = sess.patch(f'{url}?updateMask=template.containers', json=body, timeout=60)
        if pr.status_code not in (200, 201):
            print(f"Patch failed for {svc}: {pr.status_code}")
            print(pr.text)
            raise SystemExit(3)
            
        op = pr.json().get('name')
        print(f"Service {svc} patch submitted. Old image: {old_image} -> New image: {new_image}")
        
        # 4. Poll operation status
        if op:
            op_url = f'https://run.googleapis.com/v2/{op}'
            print(f"Waiting for Cloud Run deployment operation to complete...")
            for i in range(80):
                o = sess.get(op_url, timeout=30).json()
                if o.get('done'):
                    if 'error' in o:
                        print(f"Deployment error on {svc}: {json.dumps(o['error'])}")
                        raise SystemExit(4)
                    print(f"Successfully rolled revision for {svc}!")
                    break
                time.sleep(3)
            else:
                print(f"Timeout waiting for {svc}")
                raise SystemExit(5)
                
        # 5. Verify final status
        final = sess.get(url, timeout=30).json()
        print(f"Latest revision ready: {final.get('latestReadyRevision')}")
        for c in final.get('conditions', []):
            if c.get('type') in ('Ready', 'RoutesReady', 'ConfigurationsReady'):
                print(f"  Condition: {c.get('type')} = {c.get('state')} ({c.get('message', '')})")
        print("-" * 50)

if __name__ == "__main__":
    main()
