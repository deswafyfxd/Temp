import os
import requests
import json
import time
import logging
import yaml
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# Configure logging to print to console
logging.basicConfig(level=logging.ERROR, format='%(asctime)s:%(levelname)s:%(message)s')

# Load projects from YAML file
with open('projects.yml', 'r') as file:
    config = yaml.safe_load(file)
    projects = config['projects']

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

def send_discord_message(Account_Number_and_ID, custom_name, repo_name, repo_owner, status, workflow_file=None, details=None):
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "content": f"Account Number and ID: {Account_Number_and_ID}\n"
                   f"Email and Repo No: {custom_name}\n"
                   f"Repository: {repo_name}\n"
                   f"GitHub Username: {repo_owner}\n"
                   f"Status: {status}\n"
                   f"Workflow: {workflow_file or 'N/A'}\n"
                   f"Details: {details or 'No additional details'}\n"
                   f"Checked At: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    }
    response = requests.post(DISCORD_WEBHOOK_URL, headers=headers, data=json.dumps(data))
    if response.status_code != 204:
        logging.error(f"Failed to send message to Discord: {response.status_code}, {response.text}")

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.exceptions.RequestException))
def make_github_request(url):
    response = requests.get(url)
    response.raise_for_status()
    return response

def check_repo(repo):
    today = datetime.utcnow().strftime("%Y-%m-%d")

    repo_owner = repo['repo_owner']
    repo_name = repo['repo_name']
    workflow_file = repo.get('workflow_file')
    custom_name = repo['Email_and_Repo_Number']
    Account_Number_and_ID = repo['custom_project_name']

    try:
        # Check if the repository is accessible
        repo_status = make_github_request(f"https://api.github.com/repos/{repo_owner}/{repo_name}").status_code
        if repo_status != 200:
            send_discord_message(Account_Number_and_ID, custom_name, repo_name, repo_owner, "repository_not_accessible", details=f"Status code: {repo_status}")
            return

        # Get the first available workflow name if not specified
        if not workflow_file:
            workflows_response = make_github_request(f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows")
            workflows = workflows_response.json().get('workflows', [])
            if not workflows:
                send_discord_message(Account_Number_and_ID, custom_name, repo_name, repo_owner, "no_workflows_found")
                return
            workflow_file = workflows[0]['path']

        # Check if GitHub Actions is enabled for the repository
        actions_status = make_github_request(f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows").json().get('message')
        if actions_status == "Actions are currently disabled for this repository.":
            send_discord_message(Account_Number_and_ID, custom_name, repo_name, repo_owner, "actions_disabled")
            return

        # Check workflow runs
        runs_response = make_github_request(f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows/{workflow_file}/runs?per_page=100")
        runs = runs_response.json().get('workflow_runs', [])
        runs_today = [run for run in runs if run['created_at'].startswith(today)]

        if not runs_today:
            send_discord_message(Account_Number_and_ID, custom_name, repo_name, repo_owner, "not_started", workflow_file=workflow_file)
        elif not any(run['status'] == 'completed' for run in runs_today):
            send_discord_message(Account_Number_and_ID, custom_name, repo_name, repo_owner, "not_completed", workflow_file=workflow_file)
        else:
            return

    except requests.exceptions.RequestException as e:
        logging.error(f"Error checking project {custom_name} - {repo_name}: {e}")

def check_account(account):
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(check_repo, repo) for repo in account['repos']]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Error processing repo: {e}")

def check_project(project):
    for account in project['accounts']:
        check_account(account)

def check_workflows():
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(check_project, project) for project in projects]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Error processing project: {e}")

if __name__ == "__main__":
    check_workflows()
