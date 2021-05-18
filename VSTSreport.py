#!/usr/bin/env python3

import argparse, json, os, sys
from datetime import date, datetime, timedelta
from pprint import pprint

from vstsclient.vstsclient import VstsClient
from vstsclient.constants import StateFilter

'''
This script makes use of a simple REST client for azure devops/vsts:
https://github.com/rcoenmans/vsts-client
Not all of the necessary queries are implemented in that client.
To take care of this, some functions create their own HTTPRequest object and makes use of the client's
"_perform_request" function.

For additional API documentation see:
https://docs.microsoft.com/en-us/rest/api/azure/devops/git/?view=azure-devops-rest-4.1
'''

# Config
api_address = 'dev.azure.com/heartland-vsts'
api_vers = '4.1'
version = '0.1'

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

class HTTPRequest(object):
	def __init__(self):
		self.host = ''
		self.method = ''
		self.path = ''
		self.query = {}  # list of (name, value)
		self.headers = {}  # list of (header name, header value)
		self.body = ''


class ComplianceEvent(object):
	def __init__(self, date, project_name, repo_name, id, committer_email, pushed_by):
		self.date = date
		self.project_name = project_name
		self.repo_name = repo_name
		self.id = id
		self.committer_email = committer_email
		self.pushed_by = pushed_by

	def csv(self):
		return '{},{},{},{},{},{}'.format(self.date, self.project_name, self.repo_name, self.id, self.committer_email, self.pushed_by)

class ProjectReport(object):
	def __init__(self, name):
		self.name = name
		self.problems  = []


def get_repositories(client, project_name):
	query = 'api-version={}'.format(api_vers)

	request = HTTPRequest()
	request.method = 'GET'
	request.path = '/{}/_apis/git/repositories?{}'.format(project_name, query)
	request.headers = {'content-type': 'application/json'}

	return client._perform_request(request)


def get_commits(client, project_name, repo_name, start_date, end_date):
	'''
	API Documentation including a full explanation of searchCriteria query options:
	https://docs.microsoft.com/en-us/rest/api/azure/devops/git/commits/get%20commits?view=azure-devops-rest-4.1
	
	For a date specific example:
	https://docs.microsoft.com/en-us/rest/api/azure/devops/git/commits/get%20commits?view=azure-devops-rest-4.1#examples
	
	The relevent section/formatting:
	&searchCriteria.fromDate=6/14/2018+12:00:00+AM
	'''

	query = 'searchCriteria.fromDate={}&searchCriteria.toDate={}&$top=1000&api-version={}'.format(start_date, end_date, api_vers);

	request = HTTPRequest()
	request.method = 'GET'
	request.path = '/{}/_apis/git/repositories/{}/commits?{}'.format(project_name, repo_name, query)
	request.headers = {'content-type': 'application/json'}

	return client._perform_request(request)


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


if args.version:
	print()
	print('version: {}'.format(version))
	print()
	sys.exit(0)

# Read token from token_file.
token_file = args.token

if not os.path.exists(token_file):
	print()
	print('Error - Could not find token file.  See report.py --help for additional details.')
	print()
	sys.exit(1)

token_file_handle = open(token_file, 'r')
token = str(token_file_handle.readlines()[0]).strip()
token_file_handle.close()

if args.check_connection:
	print()
	print('Checking connection to Azure DevOps API...')

	client = VstsClient(api_address, token)
	projects = client.get_projects(StateFilter.WELL_FORMED)

	if 0 < len(projects):
		print(' + SUCCESS (found {} projects).'.format(len(projects)))
		print()
		sys.exit(0)
	else:
		print(' x FAILED (Could not connect to API, or retreived 0 projects.')
		print('   See vsts-client.log for additional information.')
		print()
		sys.exit(1)

client = VstsClient(api_address, token)
projects = []

if args.projects:
	print()
	print('+ Reading projects from file {}.'.format(args.projects))
	
	project_file = args.projects
	project_file_handle = open(project_file, 'r')
	project_list = project_file_handle.readlines()
	
	for project in project_list:
		if '' != project.strip():
			projects.append(type('', (object,),{'name': project.strip()})())
else:
	projects = client.get_projects(StateFilter.WELL_FORMED)

start_date = date.today() - timedelta(days = args.from_date)
end_date = date.today()

if args.start_date:
	start_date = datetime.fromisoformat(args.start_date)

if args.end_date:
	end_date = datetime.fromisoformat(args.end_date)

# Replace spaces with the '+' sign for url encoding. '6/14/2018 12:00:00 AM' becomes '6/14/2018+12:00:00+AM'.
from_date = '{}/{}/{}+12:00:00+AM'.format(start_date.month, start_date.day, start_date.year)

str_start_date = '{}/{}/{}+12:00:00+AM'.format(start_date.month, start_date.day, start_date.year)
str_end_date = '{}/{}/{}+11:59:59+PM'.format(end_date.month, end_date.day, end_date.year)

print()
print('+ Starting commit audit on range {} to {}.'.format(str_start_date, str_end_date))

#problems = []
reports = []

now = datetime.now().time()

if not os.path.exists('output'):
	os.mkdir('output')

output_template = '{}_{}_{}'.format(args.output, now.strftime('%H'), now.strftime('%M'))
header = 'Commit Date, Project, Repository, Commit Id, Commit Author, Pushed By\n'

# Workloop
for project in projects:
	repos_raw = get_repositories(client, project.name)
	repos_json = json.dumps(repos_raw)
	repos = json.loads(repos_json)['value']

	print('+ Searching {} repositories in project {}.'.format(str(len(repos)), project.name))

	report = ProjectReport(project.name)

	for repo in repos:
		commits_raw = get_commits(client, project.name, repo['name'], str_start_date, str_end_date)
		commits_json = json.dumps(commits_raw)
		commits = json.loads(commits_json)['value']

		print(' + Checking {}/{} ({} commits).'.format(project.name, repo['name'], json.loads(commits_json)['count']))

		for commit in commits:
			push_raw = get_pusher_details(client, commit['url'])
			push_json = json.dumps(push_raw)
			push = json.loads(push_json)

			committer_email = ""
			pushed_by = ""

			#print(push)

			if 'email' in push['committer']:
				committer_email = push['committer']['email']
			else:
				committer_email = push['committer']['name']

			if 'uniqueName' in push['push']['pushedBy']:
				pushed_by = push['push']['pushedBy']['uniqueName']

			if committer_email.lower() != pushed_by.lower():
				date_parts = push['push']['date'].split('.')
				pretty_date = date_parts[0].replace('T', ' ')
				report.problems.append(ComplianceEvent(pretty_date, project.name, repo['name'], push['commitId'], committer_email, pushed_by))

	reports.append(report)

	output_file = '{}_{}.csv'.format(output_template, report.name)
	print('+ Found {} problems. Writing to file {}.'.format(len(report.problems), output_file))

	file = open(output_file, 'w')
	file.write(header)
	
	for p in report.problems:
		file.write('{}\n'.format(p.csv()))

	file.close()
# End Workloop

print()
print('+ Done.')
print()
