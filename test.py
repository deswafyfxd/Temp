import os
import requests
import json
import time
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# Configure logging to print to console
logging.basicConfig(level=logging.ERROR, format='%(asctime)s:%(levelname)s:%(message)s')

# Define the projects and their respective owners and workflows
projects = {
    "Weather App - Frontend": "weather-org:build.yml",
    "Weather App - Backend": "weather-org:deploy.yml",
    "Project 2 - Repo 1": "repo-owner-2:workflow2.yml",
    "Project 2 - Repo 2": "repo-owner-3",
    "Project 3 - Repo 1": "repo-owner-4:workflow3.yml",
    "Project 3 - Repo 2": "repo-owner-5",
    "Project 4 - Repo 1": "repo-owner-6:workflow4.yml",
    "Project 4 - Repo 2": "repo-owner-7",
    "Project 5 - Repo 1": "repo-owner-8:workflow5.yml",
    "Project 5 - Repo 2": "repo-owner-9",
    "Project 6 - Repo 1": "repo-owner-10:workflow6.yml",
    "Project 6 - Repo 2": "repo-owner-11",
    "Project 7 - Repo 1": "repo-owner-12:workflow7.yml",
    "Project 7 - Repo 2": "repo-owner-13",
    "Project 8 - Repo 1": "repo-owner-14",
    "Project 8 - Repo 2": "repo-owner-15",
    "Project 9 - Repo 1": "repo-owner-16:workflow9.yml",
    "Project 9 - Repo 2": "repo-owner-17",
    "Project 10 - Repo 1": "repo-owner-18:workflow10.yml",
    "Project 10 - Repo 2": "repo-owner-19",
    "Project 11 - Repo 1": "repo-owner-20:workflow11.yml",
    "Project 11 - Repo 2": "repo-owner-21",
    "Project 12 - Repo 1": "repo-owner-22:workflow12.yml",
    "Project 12 - Repo 2": "repo-owner-23",
    "Project 13 - Repo 1": "repo-owner-24:workflow13.yml",
    "Project 13 - Repo 2": "repo-owner-25",
    "Project 14 - Repo 1": "repo-owner-26:workflow14.yml",
    "Project 14 - Repo 2": "repo-owner-27",
    "Project 15 - Repo 1": "repo-owner-28:workflow15.yml",
    "Project 15 - Repo 2": "repo-owner-29"
}

DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL')

def send_discord_message(message):
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "content": message
    }
    response = requests.post(DISCORD_WEBHOOK_URL, headers=headers, data=json.dumps(data))
    if response.status_code != 204:
        logging.error(f"Failed to send message to Discord: {response.status_code}, {response.text}")

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.exceptions.RequestException))
def make_github_request(url):
    response = requests.get(url)
    response.raise_for_status()
    return response

def check_project(project, details):
    today = datetime.utcnow().strftime("%Y-%m-%d")

    repo_owner, workflow_name = details.split(':') if ':' in details else (details, None)
    repo_name = project.split(' - ')[1]
    custom_name = project.split(' - ')[0]

    try:
        # Check if the repository is accessible
        repo_status = make_github_request(f"https://api.github.com/repos/{repo_owner}/{repo_name}").status_code
        if repo_status != 200:
            message = f"Custom Name: {custom_name} - Project: {repo_name} - Status: repository_not_accessible (status code: {repo_status})"
            send_discord_message(message)
            return

        # Get the first available workflow name if not specified
        if not workflow_name:
            workflows_response = make_github_request(f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows")
            workflows = workflows_response.json().get('workflows', [])
            if not workflows:
                message = f"Custom Name: {custom_name} - Project: {repo_name} - Status: no_workflows_found"
                send_discord_message(message)
                return
            workflow_name = workflows[0]['path']

        # Check if GitHub Actions is enabled for the repository
        actions_status = make_github_request(f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows").json().get('message')
        if actions_status == "Actions are currently disabled for this repository.":
            message = f"Custom Name: {custom_name} - Project: {repo_name} - Status: actions_disabled"
            send_discord_message(message)
            return

        # Check workflow runs
        runs_response = make_github_request(f"https://api.github.com/repos/{repo_owner}/{repo_name}/actions/workflows/{workflow_name}/runs?per_page=100")
        runs = runs_response.json().get('workflow_runs', [])
        runs_today = [run for run in runs if run['created_at'].startswith(today)]

        if not runs_today:
            message = f"Custom Name: {custom_name} - Project: {repo_name} - Workflow: {workflow_name} - Status: not_started"
        elif not any(run['status'] == 'completed' for run in runs_today):
            message = f"Custom Name: {custom_name} - Project: {repo_name} - Workflow: {workflow_name} - Status: not_completed"
        else:
            return

        send_discord_message(message)

    except requests.exceptions.RequestException as e:
        logging.error(f"Error checking project {custom_name} - {repo_name}: {e}")

def check_workflows():
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(check_project, project, details) for project, details in projects.items()]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                logging.error(f"Error processing project: {e}")

if __name__ == "__main__":
    check_workflows()
