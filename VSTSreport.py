#!/usr/bin/env python3

import argparse, json, os, sys
from datetime import date, datetime, timedelta
from pprint import pprint

from vstsclient.vstsclient import VstsClient
from vstsclient.constants import StateFilter

# Config
api_address = 'dev.azure.com/heartland-vsts'
api_vers = '4.1'
version = '0.1'
token = '2ci4kut67w6p7dw44v3isia7iejfcvg62v6ptfapmlbthewew3ua'

# CLI Args
parser = argparse.ArgumentParser(description='Generate an audit report of commit user names vs. push user names.')
parser.add_argument('-c', '--check_connection', help='Check connection to the Azure DevOps API and exit.', action='store_true')
parser.add_argument('-e', '--end_date', help='Set an end date for the audit range. Format should be: YYYY-MM-DD. Defaults to today.', type=str)
parser.add_argument('-f', '--from_date', help='Specify a from date (as an integer representing "days ago", ex: 7 for the last week or 30 for the last month). Defaults to 30 days.', type=int, default=30)
#parser.add_argument('-i', '--ignore', help='Specify a file containing a list of projects or repos to be ignored when generating the report (default None).', type=str)
parser.add_argument('-o', '--output', help='Specify an output file (output will be written in csv format). The output file will be appended with a simple time stamp (hour and minute) as well as the .csv file extension. Default commit_report_output_HOUR_MINUTE.csv. WARNING: Existing files by the same name will be overwritten.', type=str, default='output/commit_report_output')
parser.add_argument('-p', '--projects', help='Read a list of projects from a local file (the default is to fetch all projects from the API).', type=str)
parser.add_argument('-s', '--start_date', help='Set a start date for the audit range. Format should be: YYYY-MM-DD. Defaults to 7 days ago.', type=str)
parser.add_argument('-t', '--token', help='Specify a file containing the Azure DevOps API access token. Defaults to \'token\',', type=str, default='token')
parser.add_argument('-v', '--version', help='Display version information and exit.', action='store_true')
args = parser.parse_args()


client = VstsClient(api_address, token)
projects = client.get_projects(StateFilter.WELL_FORMED)
start_date = date.today() - timedelta(days = args.from_date)
end_date = date.today()
str_start_date = '{}/{}/{}+12:00:00+AM'.format(start_date.month, start_date.day, start_date.year)
str_end_date = '{}/{}/{}+11:59:59+PM'.format(end_date.month, end_date.day, end_date.year)


def get_pusher_details(client, url):
	# push detail URLs are like:
	# https://dev.azure.com/heartland-vsts/{PROJECT_ID}/_apis/git/repositories/{REPO_ID}/commits/{COMMIT_HASH}

	parts = url.split('/')
	project_id = parts[4]
	repo_id = parts[8]
	commit_id = parts[10]

	query = 'api-version={}'.format(api_vers)

	request = HTTPRequest()
	request.method = 'GET'
	request.path = '/{}/_apis/git/repositories/{}/commits/{}?{}'.format(project_id, repo_id, commit_id, query)
	request.headers = {'content-type': 'application/json'}

	return client._perform_request(request)

def get_commits_by_user(client, project_name, repo_name, start_date, end_date, username):
#	query = 'searchCriteria.fromDate={}&searchCriteria.toDate={}&$top=1000&api-version={}'.format(start_date, end_date, api_vers);
	query = 'searchCriteria.uthor={}&searchCriteria.fromDate={}&searchCriteria.toDate={}&$top=1000&api-version={}'.format(username, start_date, end_date, api_vers);

# https://dev.azure.com/heartland-vsts/_apis/git/repositories/5af798f1-6953-42dd-9a88-56e81109d586/commits?searchCriteria.author=Gil.Gerassi@globalpay.com&api-version=4.1

	request = HTTPRequest()
	request.method = 'GET'
	request.path = '/{}/_apis/git/repositories/{}/commits?{}'.format(project_name, repo_name, query)
	request.headers = {'content-type': 'application/json'}

	return client._perform_request(request)

def get_commits(client, project_name, repo_name, start_date, end_date):
	query = 'searchCriteria.fromDate={}&searchCriteria.toDate={}&$top=1000&api-version={}'.format(start_date, end_date, api_vers);
#	print ("query = " + query)
	request = HTTPRequest()
	request.method = 'GET'
	request.path = '/{}/_apis/git/repositories/{}/commits?{}'.format(project_name, repo_name, query)
	request.headers = {'content-type': 'application/json'}

	return client._perform_request(request)

class HTTPRequest(object):
	def __init__(self):
		self.host = ''
		self.method = ''
		self.path = ''
		self.query = {}  # list of (name, value)
		self.headers = {}  # list of (header name, header value)
		self.body = ''

def get_repositories(client, project_name):
	query = 'api-version={}'.format(api_vers)

	request = HTTPRequest()
	request.method = 'GET'
	request.path = '/{}/_apis/git/repositories?{}'.format(project_name, query)
	request.headers = {'content-type': 'application/json'}

	return client._perform_request(request)

for project in projects:
	print(project.name)
	repos_raw = get_repositories(client, project.name)
	repos_json = json.dumps(repos_raw)
	repos = json.loads(repos_json)['value']
	print('====================================')	
	print('+ Searching {} repositories in project {}.'.format(str(len(repos)), project.name))
	print('====================================')
	for repo in repos:
		commits_raw = get_commits(client, project.name, repo['name'], str_start_date, str_end_date)
#		commits_raw = get_commits_by_user(client, project.name, repo['name'], str_start_date, str_end_date, 'gil.gerassi@globalpay.com')
		commits_json = json.dumps(commits_raw)
		commits = json.loads(commits_json)['value']
#		print(repo['name'])
#		print(repo['id'])
		for commit in commits:
			push_raw = get_pusher_details(client, commit['url'])
			push_json = json.dumps(push_raw)
			push = json.loads(push_json)
			committer_email = ""
			pushed_by = ""
			if 'email' in push['committer']:
				committer_email = push['committer']['email']
			else:
				committer_email = push['committer']['name']
			if 'uniqueName' in push['push']['pushedBy']:
				pushed_by = push['push']['pushedBy']['uniqueName']
				if committer_email.lower() != pushed_by.lower():
					date_parts = push['push']['date'].split('.')
					pretty_date = date_parts[0].replace('T', ' ')
					print(pretty_date + " "  + project.name + " " + repo['name'] + " " + push['commitId'] + " " + committer_email + " " + pushed_by)
#			report.problems.append(ComplianceEvent(pretty_date, project.name, repo['name'], push['commitId'], committer_email, pushed_by))
#					print(committer_email + " " + pushed_by)
#					if (pushed_by=="gil.gerassi@globalpay.com" or pushed_by=="Gil.Gerassi@globalpay.com" or pushed_by=="Gil Gerassi" or committer_email=="Gil.Gerassi@globalpay.com" or committer_email=="gil.gerassi@globalpay.com"):
#					if pushed_by=="Rahul.Dabi@e-hps.com":
#						print(pretty_date + " "  + project.name + " " + repo['name'] + " " + push['commitId'] + " " + committer_email + " " + pushed_by)

        # GET https://dev.azure.com/heartland-vsts/_apis/git/repositories/1a506981-dab7-49e1-ac7e-0043a0ab58e5/commits?api-version=4.1
        # GET https://dev.azure.com/heartland-vsts/_apis/git/repositories/5af798f1-6953-42dd-9a88-56e81109d586/commits?searchCriteria.author=Gil Gerassi&api-version=4.1

