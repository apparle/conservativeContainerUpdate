#!/usr/bin/env python3

# Copyright 2025 Apoorv Parle
# SPDX-License-Identifier: GPL-3.0-or-later

import requests
import yaml
import jsondiff
import sys
import argparse
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List
from packaging.version import parse as parseVersionString
import requests
from bs4 import BeautifulSoup
import subprocess

####################################################################################
class GotifyNotifier:
    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
    
    def send(self, title: str, message: str):
        payload = {
            "title": title,
            "message": message,
            "priority": 5,
        }

        try:
            response = requests.post(self.url, data=payload, params={"token": self.token})
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            print(f"Gotify notification sent successfully!")
        except requests.exceptions.RequestException as e:
            print(f"Error sending Gotify notification: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while sending Gotify notification: {e}")

notifier = None

####################################################################################

globalLog = ""
def printAndLog(s: str):
    global globalLog
    print(s)
    globalLog = globalLog + s + "\n"

def notifyErrorAndExit(e: int):
    if notifier is not None: notifier.send("❌Error during conservative update", globalLog) 
    exit(e)

def myassert(c: bool, s: str):
    if not c:
        printAndLog(s)
        notifyErrorAndExit(10)

def notifyAndExit(title: str):
    if notifier is not None: notifier.send(title, globalLog)
    exit(0)

####################################################################################

def restartDockerCompose(composeFile: str):
    if not os.path.exists(composeFile):
        printAndLog(f"== Error: File not found at '{composeFile}'")
        notifyErrorAndExit(5)

    workingDir = os.path.dirname(composeFile)
    try:
        printAndLog(f"Running docker compose down for file {composeFile} ...")
        result = subprocess.run(['docker', 'compose', '-f', composeFile, 'down'], capture_output=True, text=True, check=True, cwd=workingDir)
        printAndLog(f"docker compose down successfully. Output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to do docker compose down. Error: {e.stderr.strip()}")
        notifyErrorAndExit(7)

    try:
        printAndLog(f"Running docker compose pull for file {composeFile} ...")
        result = subprocess.run(['docker', 'compose', '-f', composeFile, 'pull'], capture_output=True, text=True, check=True, cwd=workingDir)
        printAndLog(f"docker compose pull successfully. Output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to do docker compose pull. Error: {e.stderr.strip()}")
        notifyErrorAndExit(7)

    try:
        printAndLog(f"Running docker compose up for file {composeFile} ...")
        result = subprocess.run(['docker', 'compose', '-f', composeFile, 'up'], capture_output=True, text=True, check=True, cwd=workingDir)
        printAndLog(f"docker compose up successfully. Output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to do docker compose up. Error: {e.stderr.strip()}")
        notifyErrorAndExit(7)


def restartSystemdUnit(unitName: str):
    try:
        printAndLog("Reloading user systemd daemon...")
        result = subprocess.run(['systemctl', '--user', 'daemon-reload'], capture_output=True, text=True, check=True)
        printAndLog(f"Daemon reload successful. Output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to reload user systemd daemon. Error: {e.stderr.strip()}")
        notifyErrorAndExit(7)

    try:
        printAndLog(f"Restarting user service: {unitName}...")
        result = subprocess.run(['systemctl', '--user', 'restart', unitName], capture_output=True, text=True, check=True)
        printAndLog(f"Service '{unitName}' restarted successfully. Output: {result.stdout.strip()}")
    except subprocess.CalledProcessError as e:
        printAndLog(f"Failed to restart service '{unitName}'. Error: {e.stderr.strip()}")
        notifyErrorAndExit(8)


####################################################################################

def immich_changelogBreakingChanges(baseVersionStr, newVersionStr):
    url = "https://github.com/immich-app/immich/discussions?discussions_q=label%3Achangelog%3Abreaking-change+sort%3Adate_created"

    try:
        baseVersion = parseVersionString(baseVersionStr.lstrip('v'))
        newVersion = parseVersionString(newVersionStr.lstrip('v'))
    except Exception as e:
        printAndLog(f"== Error parsing version strings: {e}. Ensure format like 'v1.132.0'.")
        return True

    myassert(baseVersion < newVersion, "Base version must be older than the new version. No check performed.")

    breakingChangesFound = []

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Updated selector: Look for h4 tags within a specific structure,
        # or a more general link within a discussion item.
        # GitHub often uses `h4` for discussion titles within list items or articles.
        # This is not necessarily most reliable pattern
        discussionLinks = soup.select('a[data-hovercard-type="discussion"]')
        if not discussionLinks:
            printAndLog("== Could not find discussion links on the page. HTML structure might have changed.")
            printAndLog("== Please inspect the GitHub discussions page manually to verify the correct selector.")
            return True

        versionPattern = re.compile(r'v?(\d+\.\d+\.\d+)')

        foundLowerVersion = False
        for link in discussionLinks:
            title = link.get_text(strip=True)
            href = link.get('href')
            fullUrl = f"https://github.com{href}" if href and href.startswith('/') else href

            match = versionPattern.search(title)
            if match:
                discussionVersionStr = match.group(1)
                try:
                    discussionVersion = parseVersionString(discussionVersionStr)
                    if discussionVersion < baseVersion:
                        foundLowerVersion = True
                    if baseVersion < discussionVersion <= newVersion:
                        breakingChangesFound.append({
                            'title': title,
                            'version': f"v{discussionVersion}",
                            'url': fullUrl
                        })
                except Exception as e:
                    printAndLog(f"== Warning: Could not parse version '{discussionVersionStr}' from title '{title}': {e}")
                    return True

        if not foundLowerVersion:
            printAndLog(f"== Warning: No parsed version lower than base version found. There *may* be breaking versions of page-2 that aren't scraped. Check manually.")
            return True

    except requests.exceptions.RequestException as e:
        printAndLog(f"== Error fetching URL: {e}")
        return True
    except Exception as e:
        printAndLog(f"== An unexpected error occurred: {e}")
        return True

    if breakingChangesFound:
        printAndLog(f"== Breaking change(s) found between {baseVersionStr} and {newVersionStr}:")

        for bc in breakingChangesFound:
            printAndLog(f"== - {bc['title']} (Version: {bc['version']})")
            printAndLog(f"==   Link: {bc['url']}")
            
        return True
    else:
        printAndLog(f"== No breaking changes found between {baseVersionStr} and {newVersionStr}.")
        return False

####################################################################################

# Global app list
app_metadata = {
    'immich' : {
        'templateUrl' : 'https://github.com/immich-app/immich/releases/download/<VERSION>/docker-compose.yml',
        'owner' : 'immich-app',
        'repo' : 'immich',
        'tag2version' : lambda s: s,
        'validateVersion' : lambda s: re.fullmatch(r'^v\d+\.\d+\.\d+$', s) is not None,
        'versionEnvVariable' : 'IMMICH_VERSION',
        'changelogBreakingChanges' : immich_changelogBreakingChanges,
    },
    'authentik' : {
        'templateUrl' : 'https://raw.githubusercontent.com/goauthentik/authentik/refs/tags/version/<VERSION>/docker-compose.yml',
        'owner' : 'goauthentik',
        'repo' : 'authentik',
        'tag2version' : lambda s: s.split('/')[1],
        'validateVersion' : lambda s: re.fullmatch(r'^202\d\.\d+\.\d+$', s) is not None,
        'versionEnvVariable' : 'AUTHENTIK_TAG',
        'changelogBreakingChanges' : lambda b, n: (False, []),
    }
}

def readEnvFile(filePath: str, app: str):
    if not os.path.exists(filePath):
        printAndLog(f"== Error: File not found at '{filePath}'")
        notifyErrorAndExit(5)

    with open(filePath, 'r') as f:
        lines = f.readlines()
    
    for line in lines:
        match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*?)\s*=\s*(.*?)\s*$', line)
        if match and match.group(1) == app_metadata[app]['versionEnvVariable']:
            version = match.group(2)

    return version, lines

def updateEnvFile(filePath: str, lines: List[str], updatesDict: dict):
    if not os.path.exists(filePath):
        printAndLog(f"== Error: File not found at '{filePath}' but it should exist already")
        notifyErrorAndExit(5)

    updatedLines = []
    numChanges = 0
    for line in lines:
        match = re.match(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$', line)
        if match:
            key = match.group(1)
            if key in updatesDict:
                line = "{}={}\n".format(key, updatesDict[key])
                printAndLog(f"== Updated line: {line}")
                numChanges += 1
        updatedLines.append(line)

    myassert(numChanges == len(updatesDict), "Expected {} updates but only matched {} for file {}".format(len(updatesDict), numChanges, filePath))

    try:
        with open(filePath, 'w') as f:
            f.writelines(updatedLines)
        printAndLog(f"== Successfully updated '{filePath}' with provided values.")
    except IOError as e:
        printAndLog(f"== Error writing to file '{filePath}': {e}")
        notifyErrorAndExit(5)

####################################################################################

def GetLatestGitHubReleaseTag(owner, repo):
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        releaseData = response.json()
        print(f"== Tried URL : {url}")
        print(f"== Got tag: " + releaseData.get('tag_name'))
        print(f"== Released At: " + releaseData.get('published_at'))
        #return releaseData.get('tag_name')
        return releaseData.get('tag_name'), releaseData.get('published_at')
    except requests.exceptions.RequestException as e:
        printAndLog(f"== ERROR: Failed to fetch latest release for {owner}/{repo}: {e}", file=sys.stderr)
        notifyErrorAndExit(1) # Exit if we can't get the latest tag
    except json.JSONDecodeError as e:
        printAndLog(f"== ERROR: Failed to parse JSON response from GitHub API for {owner}/{repo}: {e}", file=sys.stderr)
        notifyErrorAndExit(2)

def DownloadAndParseComposeFile(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return yaml.safe_load(response.text)
    except requests.exceptions.RequestException as e:
        printAndLog(f"== ERROR: Failed to download {url}: {e}", file=sys.stderr)
        notifyErrorAndExit(1) # Exit with code 1 for download failure
    except yaml.YAMLError as e:
        printAndLog(f"== ERROR: Failed to parse YAML from {url}: {e}", file=sys.stderr)
        notifyErrorAndExit(2) # Exit with code 2 for YAML parsing failure

def RemoveImageTags(composeData):
    extractedImages = {}
    if isinstance(composeData, dict) and 'services' in composeData:
        for serviceName, serviceConfig in composeData['services'].items():
            if isinstance(serviceConfig, dict):
                if 'image' in serviceConfig:
                    extractedImages[serviceName] = serviceConfig.pop('image')
    return extractedImages

def CompareDockerCompose(templateUrl, version1, version2):
    url1 = templateUrl.replace("<VERSION>", version1)
    url2 = templateUrl.replace("<VERSION>", version2)

    printAndLog(f"== Processing docker-compose.yml for {version1} from: {url1}")
    composeData1 = DownloadAndParseComposeFile(url1)

    printAndLog(f"== Processing docker-compose.yml for {version2} from: {url2}")
    composeData2 = DownloadAndParseComposeFile(url2)

    # Extract and remove image tags from both datasets directly
    extractedImages1 = RemoveImageTags(composeData1)
    extractedImages2 = RemoveImageTags(composeData2)

    # Now, compare the entire compose files except the image tags
    #nonImageDiff = DeepDiff(composeData1, composeData2, ignore_order=True, view='tree')
    nonImageDiff = jsondiff.diff(composeData1, composeData2, syntax='symmetric')

    if nonImageDiff:
        printAndLog("== ## BREAKING CHANGE DETECTED: Structural or non-image related differences")
        printAndLog("== ---")
        printAndLog("== Differences found (excluding 'image' tags):")
        #printAndLog(nonImageDiff.pretty())
        printAndLog(yaml.dump(nonImageDiff, indent=2, default_flow_style=False))
        # Optionally, print image changes too if there are breaking changes
        printAndLog("== ### Image changes (if any, alongside breaking changes)")
        imageChangesFound = False
        allServiceNames = sorted(list(set(extractedImages1.keys()).union(set(extractedImages2.keys()))))
        for serviceName in allServiceNames:
            image1 = extractedImages1.get(serviceName)
            image2 = extractedImages2.get(serviceName)
            if image1 != image2:
                printAndLog(f"==   Service: {serviceName} \n    Old Image: {image1}\n    New Image: {image2}")
                imageChangesFound = True
        if not imageChangesFound:
            printAndLog("==   No image changes detected.")
        return True, None 

    else:
        # If no non-image differences, check if images themselves changed
        imageChangesFound = False
        allServiceNames = sorted(list(set(extractedImages1.keys()).union(set(extractedImages2.keys()))))

        printAndLog("== ## Summary of Image Changes (if any)")
        printAndLog("== ---")
        for serviceName in allServiceNames:
            image1 = extractedImages1.get(serviceName)
            image2 = extractedImages2.get(serviceName)
            if image1 != image2:
                printAndLog(f"==   Service: {serviceName} \n    Old Image: {image1}\n    New Image: {image2}")
                imageChangesFound = True

        if imageChangesFound:
            printAndLog("== Only `image` tags were changed across all services. No structural or other changes detected.")
        else:
            printAndLog("== No changes detected between the two Docker Compose files.")
        return False, extractedImages2

####################################################################################

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Compare Docker Compose files for two release versions.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-f',
        "--file",
        help="environment file to read input version and update contents"
    )
    parser.add_argument('-bv',
        "--base-version",
        help=argparse.SUPPRESS
    )
    parser.add_argument('-nv',
        "--new-version",
        default='latest',
        help="The second release version (e.g., v1.135.3)"
    )
    parser.add_argument('-m',
        "--min-hours-since-latest",
        default=36,
        type=int,
        help="The minimum time since the latest release. If this is not met, latest release is canceled."
    )
    parser.add_argument('-a',
        "--app",
        choices=app_metadata.keys(),
        help="The app to select URL for"
    )
    parser.add_argument('-no',
        "--notify",
        action="store_true",
        help="Send notification"
    )
    parser.add_argument('-d',
        "--dry-run",
        action="store_true",
        help="Dry Run"
    )
    parser.add_argument('-r',
        "--restart-systemd-unit",
        help="Systemd unit (service or target) to restart on update"
    )
    parser.add_argument('-rd',
        "--restart-compose-file",
        help="Docker Compose fie to restart on an update"
    )
    parser.add_argument('-gu',
        "--gotify-url",
        help="Gotify URL to send notification"
    )
    parser.add_argument('-gt',
        "--gotify-token",
        help="Gotify Token to send notification"
    )

    args = parser.parse_args()

    if args.gotify_url and args.gotify_token:
        notifier = GotifyNotifier(args.gotify_url, args.gotify_token)
        

    app = args.app
    templateUrl = app_metadata[app]['templateUrl']

    envFileLines=None
    if args.file:
        args.base_version, envFileLines = readEnvFile(args.file, app)
        print(f"Extracted base version {args.base_version}")
        myassert(app_metadata[app]['validateVersion'](args.base_version), f"Version string not valid: {args.base_version}")
        myassert(args.base_version != "release" and args.base_version != "latest", "Base version can't be \"release\" or \"latest\"")

    if args.new_version.lower() == 'latest':
        owner = app_metadata[app]['owner']
        repo = app_metadata[app]['repo']
        print(f"Resolving 'latest' for {owner}/{repo} as new version ...")
        resolvedVersion, resolvedTime = GetLatestGitHubReleaseTag(owner, repo)
        resolvedTimeAgo = datetime.now(timezone.utc) - datetime.fromisoformat(resolvedTime)
        if not resolvedVersion or not resolvedTime:
            printAndLog(f"Couldn't resolve latest version or it's release time.")
            notifyErrorAndExit(1) # Exit if 'latest' couldn't be resolved
        elif resolvedTimeAgo < timedelta(hours=args.min_hours_since_latest):
            printAndLog(f"Resolved 'latest' for {owner}/{repo} as {args.new_version} released at {resolvedTime} i.e. {resolvedTimeAgo} ago, less than {args.min_hours_since_latest} hrs. Exiting")
            notifyAndExit(f"ⓘ {app} conservative update: latest version is too now.")
        args.new_version = app_metadata[app]['tag2version'](resolvedVersion)
        print(f"Resolved 'latest' for {owner}/{repo} as {args.new_version} released {resolvedTimeAgo} ago...")
        myassert(app_metadata[app]['validateVersion'](args.new_version), f"Version string not valid: {args.new_version}")
    
    myassert(args.base_version is not None, "base_version unspecified")
    myassert(args.new_version is not None, "new_version unspecified")

    if args.base_version == args.new_version:
        printAndLog(f"Same version {args.base_version} and {args.new_version}, no update to be done.")
        notifyAndExit(f"ⓘ {app} conservative update: no version change")

    printAndLog(f"Comparing {app} versions: {args.base_version} vs {args.new_version}")

    changelogBreakingChanges = immich_changelogBreakingChanges(args.base_version, args.new_version)
    if changelogBreakingChanges:
        printAndLog(f"Detected breaking changes in changelog for between {app} versions: {args.base_version} vs {args.new_version}. Stop")
    else:
        printAndLog(f"No breaking changes detected in changelog for between {app} versions: {args.base_version} vs {args.new_version}.")
        
    composeBreakingChanges, updatedImages = CompareDockerCompose(templateUrl, args.base_version, args.new_version)
    if composeBreakingChanges:
        printAndLog(f"Detected breaking changes in compose file for between {app} versions: {args.base_version} vs {args.new_version}. Stop")
    else:
        printAndLog(f"No breaking changes detected in compose file for between {app} versions: {args.base_version} vs {args.new_version}.")

    if changelogBreakingChanges or composeBreakingChanges: 
        notifyAndExit(f"⚠️ {app} conservative update: breaking change")
    elif args.file:
        printAndLog(f"Attempting to update {app} from {args.base_version} to {args.new_version}.")
        updatedVars = {}
        updatedVars[app_metadata[app]['versionEnvVariable']] = args.new_version
        for k in updatedImages.keys():
            # Skip all images where the value is already VERSION based.
            if app_metadata[app]['versionEnvVariable'] in updatedImages[k]: 
                continue
            elif '$' in updatedImages[k]:
                printAndLog(f"The image for {k} container in {app} contains a variable. Unexpected, treating as a breaking change.")
                notifyAndExit(f"⚠️ {app} conservative update: breaking change")
            else:
                envVar = "{}_{}_IMAGE".format(app.upper(), k.upper())
                updatedVars[envVar] = updatedImages[k]
        if not args.dry_run:
            updateEnvFile(args.file, envFileLines, updatedVars)
            printAndLog(f"Environment file {args.file} updated with version {args.new_version} and tags")
            if args.restart_systemd_unit:
                restartSystemdUnit(args.restart_systemd_unit)
            elif args.restart_compose_file:
                restartDockerCompose(args.restart_compose_file)
        notifyAndExit(f"✅{app} conservative update: Done")
    else:
        printAndLog(f"No breaking changes found. Nothing to do.")
        notifyAndExit(f"✅{app} conservative update: Done")

