# Name: just another vulnerability viewer - JAVV

## Identity

- web application
- Company/Start-up name: Danube Labs - historical importance to the developer because of birth city
- k8s native, should be able to also deploy standalone via docker compose, docker, etc
- A lot of open source tool like DefectDojo and Dependency Track offer solutions for vulnerability viewing, but they lack the flexibility of a tool such as Kibana when it comes to easy reports generation - a simple click from a lens can give you a .CSV file, they lack in dashboard management when compared to Kibana. At the same time Kibana lacks when it comes tu audit management for Vulnerabilitites since this is what not it was built for. The job of this tool is to combine the best of those 2 worlds. A simple UI, but capable for dashboard building, where you can easily manage vulnerabilitites (at first only docker images) in bulk, audit them, set custom parameters, etc.
- It will use Trivy (will come baked in - research Trivy license and limitations) to scan the images in any k8s cluster
  - also look at Grype. I found that Grype tends to have better scan results
  - Maybe give the user the option to choose the scanner
  - Research Grype license
- Able to filter by tags, applications, teams, organizations - those meta data tags can be added after ingestion
- Will use opensearch for storing the json reports - fast lookup. Will use Postgres for everything else
- Present a per image report
- Generate .csv reports from dashboards, just like Kibana
- Ability to filter by timestamp
- Flow will be something like: Trivy gets deployed in the cluster -> gathers all images per workload and its namespace -> pushes data to the app via an API endpoint
  - ability to select from UI what namespaces to target when scanning 
    - the app will do in cluster namespace discovery for this
- Research openapi? maybe we can use it for rest api calls to our backend
- Have a landing page where data like is shown:
  - top hero - user with the most Vulns solved
  - trends of Vulns per severity
  - other useful stats

## Nice to have

- Drag & drop a .json file - a Trivy report for an image - in the UI and see the vulns.
- Customize dashboards colors
- Jira integration - after alpha implementation
- LDAP/OIDC login

## Tech Stack 

- Python for backend
  - maybe use fastapi?
- Data:
  - Postgres (source of truth)
  - OpenSearch/Elasticsearch (search + aggregations)
- Postgres (source of truth)
  - users
  - RBAC
  - projects
  - integrations
  - scan metadata
  - config
  - audit logs

          ↓ sync/index

- Elasticsearch
  - vulnerability docs
  - image inventory
  - workload relationships
  - aggregations
  - dashboards
  - search
- Frontend:
  - Vue
  - PrimeVue (UI system)
  - vue-echarts (analytics layer)
- It will use Trivy (will come baked in - research Trivy license and limitations) to scan the images in any k8s cluster
  - also look at Grype. I found that Grype tends to have better scan results
  - Maybe give the user the option to choose the scanner
  - Research Grype license

For API endpoint to be able to talk with the app at something like www.javv.com/API_ENDPOINT- look at options, maybe openapi?

We need proper unit testing - research options