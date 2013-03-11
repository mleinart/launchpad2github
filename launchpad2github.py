#!/usr/bin/env python

import os
import sys
import time
from getpass import getpass
from optparse import OptionParser

from termcolor import colored
from launchpadlib.launchpad import Launchpad
from github3 import login as github_login
from github3 import GitHubError

ACTIVE_STATUSES = [
  "New",
  "Confirmed",
  "Triaged",
  "In Progress"
]

IMPORTED_FIELDS = [
  "owner",
  "web_link",
  "date_created",
  "date_last_updated",
  "tags",
]

def main(args):
  usage = """%s: <lp project> <gh project>\n""" % (sys.argv[0],)

  parser = OptionParser(usage=usage)
  options, args = parser.parse_args(args=args)
  if len(args) != 2:
      parser.print_usage()
      return 1

  lp_project_name = args[0]
  gh_project_name = args[1]

  try:
    gh_owner, gh_repo = gh_project_name.split('/')
  except ValueError:
    print "Unable to parse target Github repo: '%s'" % gh_project_name
    print "Repo should be specified as <owner>/<repo>"

  print "Authenticating with Launchpad"
  launchpad = Launchpad.login_with(os.path.basename(sys.argv[0]), 'production')

  print "Authenticating with Github"
  github_user = raw_input("Github username: ")
  github_pass = getpass("Github password: ")
  try:
    github = github_login(github_user, github_pass)
    github.user()
  except GitHubError:
    raise SystemExit("Invalid Github login or problem contacting server")

  # Validate launchpad project
  try:
    lp_project = launchpad.projects[lp_project_name]
  except KeyError:
    raise SystemExit("Unable to find project named '%s' on Launchpad" % lp_project_name)

  # Validate github project
  if github.repository(gh_owner, gh_repo) is None:
    raise SystemExit("Unable to find Github project %s/%s" % (gh_owner, gh_repo))

  # Begin migration
  open_tasks = lp_project.searchTasks(status=ACTIVE_STATUSES)

  for bug_task in open_tasks:
    for field in IMPORTED_FIELDS:
      print colored(field + ':', 'cyan') + colored(bug_task.bug.__getattr__(field), 'yellow')
    print colored(bug_task.bug.description, 'yellow')
    print

    if confirm_or_exit(colored("Import?", 'cyan')):
      title = bug_task.bug.title
      description = format_description(bug_task.bug)

      issue = github.create_issue(owner=gh_owner, repository=gh_repo, title=title, body=description)
      for i, message in enumerate(bug_task.bug.messages):
        if i == 0: continue  # repeat of description
        time.sleep(0.5)
        comment = format_comment(message)
        issue.create_comment(body=comment)
      issue.add_labels('launchpad_import')
      print colored("Created issue %d: %s" % (issue.number, issue.html_url), 'yellow')

      if confirm_or_exit(colored("Close and update original?", 'cyan')):
        bug_task.bug.newMessage(content="Migrated to Github: %s" % issue.html_url)
        bug_task.status = "Won't Fix"
        bug_task.bug.lp_save()

def format_description(bug):
  output = """#### Imported from %(web_link)s
|||
|----|----|
|Reported by|%(owner)s|
|Date Created|%(date_created)s|
""" % {
   'web_link': bug.web_link,
   'owner': format_user(bug.owner),
   'date_created': bug.date_created.strftime("%b %d, %Y")
 }
  if bug.tags:
    output += "|Tags|%s|" % bug.tags

  output += bug.description.replace("Original description:\n", "")
  return output

def format_user(user):
  return "[%s](%s)" % (user.name, user.web_link)

def format_comment(message):
  output = "#### Comment by %s on %s:\n" % \
      (format_user(message.owner), message.date_created.strftime("%b %d, %Y"))

  output += message.content
  return output

def confirm_or_exit(prompt):
  options = ['y','n','q']
  option_prompt = '/'.join(options)

  choice = None
  while choice not in options:
    choice = raw_input("%s (%s): " % (prompt, option_prompt)).lower()

  if choice == 'y':
    return True
  if choice == 'n':
    return False
  if choice == 'q':
    raise SystemExit(0)


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
