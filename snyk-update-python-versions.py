import os
import sys
import snyk
import json
import csv
import requests
import time
import argparse

from tqdm import tqdm
from html.parser import HTMLParser
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from packaging.version import Version

minPythonVersion = f"{3.9:.1f}" #change to .1f for 3.7, 3.8, 3.9 - .2f for 3.10, 3.12, etc
runAllOrgs = "no" #this will run through all orgs without asking for manual intervention, CAREFUL - recommended to only do this on STDIN during runtime
OVERRIDE_ALL= False #this will set the version even if it is higher, CAREFUL - don't change it here, override it on CLI options

class MyHTMLParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        foundVersion = False
        if tag == "input" :
            for attr in attrs:
                if foundVersion == False :
                    if attr[0] == 'id':
                        pythonVersion = attr[1]
                        #print(f"Set python version to : {pythonVersion}")
                if 'pythonVersion' in locals():
                    for attr in attrs:
                        if foundVersion == False :
                            if attr[0] == 'type':
                                if attr[1] == 'radio':
                                    for attr2 in attrs:
                                        if attr2[0] == 'checked':
                                            #print(f"Encountered an input start tag: {tag} with attrs: {attrs}")
                                            #print(f"PYTHON VERSION FOUND: {pythonVersion}")
                                            self.data = pythonVersion
                                            foundVersion = True

    #def handle_endtag(self, tag):
        #print("Encountered an end tag :", tag)

    #def handle_data(self, data):
        #print("Encountered some data  :", data)

def get_org_names():
    snyk_token = os.getenv('SNYK_TOKEN')
    snyk_group = os.getenv('SNYK_GROUP')        

    client = snyk.SnykClient(token=snyk_token, tries=4,
                             delay=1, backoff=4, debug=False)

    print('retrieving list of organizations')
    orgs_resp = client.get("orgs")
    orgs_resp = json.loads(orgs_resp.text)

    orgs = client.organizations.all()
    orgs = [o for o in orgs if o.group ]
    orgs = [o for o in orgs if o.group.id == snyk_group ]

    num_orgs = len(orgs)
    print("\n")
    print(f"Orgs found in Group: {snyk_group}")
    #print(f"ORGS Object in get_org_names: {orgs}")
    for org in tqdm(orgs, desc='Organizations', unit='org', total=num_orgs):
        #org_slug = org_slug
        print(org.slug)
    print("\n")

    return orgs

def write_python_version_csv(lines, filename):
    # Write data to CSV file
    with open(f'{filename}', 'a', newline='\n') as csvfile:
        fieldnames = ['org_id', 'org_slug', 'pyVersion']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        # Write header if file is empty
        csvfile.seek(0, os.SEEK_END)
        if csvfile.tell() == 0:
            writer.writeheader()

            for line in lines:
                writer.writerow({
                    'org_id': line[0],
                    'org_slug': line[1],
                    'pyVersion': line[2]
                })

def get_python_version(driver, org_slug):
    url = f'https://app.snyk.io/org/{org_slug}/manage/languages/python'

    headers = {
        'accept': 'application/json',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': 'https://app.snyk.io',
        'priority': 'u=1, i',
        'referer': f'https://app.snyk.io/registry/org/{org_slug}/manage/languages/python',
        "referrerPolicy": "no-referrer-when-downgrade",
        "method": "GET",
        "mode": "cors",
        "credentials": "include",
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    }
    cookies = driver.get_cookies()
    snyk_cookies = {}
    for cookie in cookies:
        snyk_cookies[cookie['name']] = cookie['value']

    global minPythonVersion
    pythonVersion = minPythonVersion
    try:
        response = requests.get(url, headers=headers, cookies=snyk_cookies)
        response.raise_for_status()
        #print(f"RESPONSE: {response}")

        if response.status_code == 200:
            #print(f"RESPONSE content?: {response.content}")

            parser = MyHTMLParser()
            parser.feed(response.content.decode("utf-8"))
            pythonVersion = parser.data
            
            #print(f"got python data for org {org_slug} - pythonVersion: {pythonVersion}")
        else:
            print(f"Failed to fetch data for org {org_slug}. Status code: {response.status_code}")

    except requests.exceptions.HTTPError as err:
        print(f'HTTP ERROR: {err}')
        raise
    except Exception as e:
        print(f'ERROR: {e}')
        raise

    return pythonVersion

def set_org_python_versions(driver, csrf_token, orgs):
    create_save_point(driver, orgs)

    print('running through list of organizations')

    global runAllOrgs
    global minPythonVersion
    global OVERRIDE_ALL

    if OVERRIDE_ALL:
        print(f"***WARNING*** Currently in override mode - this will set ALL orgs to {minPythonVersion} even if they are currently set higher - ctrl-c to abort!")

    print("\n") #set a newline before starting

    for org in tqdm(orgs, desc='Organizations', unit='org', total=len(orgs)):
        org_slug = org.slug

        print(f"Getting python version for {org_slug}")
        currentPythonVersion = get_python_version(driver, org_slug)

        print(f"{org_slug} current python version: {currentPythonVersion}")

        if OVERRIDE_ALL or Version(minPythonVersion) > Version(currentPythonVersion) :
            if runAllOrgs != "ALL":
                print(f'Press ENTER to SET "{org_slug}" TO python version: {minPythonVersion} - to skip this manual check type ALL to run through ALL orgs (please be sure you have right group/orgs!)')
                runAllOrgs = input('>_ ')

            set_python_version(driver, org_slug, minPythonVersion, csrf_token)
            print(f"Current org {org_slug} set to: {minPythonVersion}")
        else :
            print(f"Nothing to be done - {org_slug} remains at {currentPythonVersion}")
        print("\n") #set a newline between orgs

def set_python_version(driver, orgSlug, python_version, csrf_token):
    url = f'https://app.snyk.io/registry/org/{orgSlug}/manage/languages/python' 

    data = {
        "_csrf": csrf_token,
        "packageManager": "pip",
        "pythonVersion": f"{python_version}",
    }

    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9',
        'content-type': 'application/json',
        'origin': 'https://app.snyk.io',
        'priority': 'u=1, i',
        "x-requested-with": "XMLHttpRequest",
        "x-csrf-token": csrf_token,
        'referer': f'https://app.snyk.io/registry/org/{orgSlug}/manage/languages/python',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    }

    cookies = driver.get_cookies()
    snyk_cookies = {}
    for cookie in cookies:
        snyk_cookies[cookie['name']] = cookie['value']

    try:
        print(f"Setting org {orgSlug} to: {python_version}") 
        response = requests.post(url, headers=headers, cookies=snyk_cookies, json=data)
        response.raise_for_status()

        if response.status_code == 200:
            try:
                data = response.json()
                #print(f"DATA: {data}")
            except:
                print("couldn't decode json")
            print(f"RESPONSE: {response}")
            print(f"RESPONSE CONTENT: {response.content}")
        else:
            print(
                f"Failed to fetch data for page {orgSlug}. Status code: {response.status_code}")
    except requests.exceptions.HTTPError as err:
        print(f'HTTP ERROR: {err}')
        raise
    except Exception as e:
        print(f'ERROR: {e}')
        raise

    return data

def create_save_point(driver, orgs):
    #print(f"SAVE POINT ORGS: {orgs}")
    os.makedirs('save_points', exist_ok=True)
    timestr = time.strftime("%Y%m%d-%H%M%S")
    filename=f"save_points/orgPythonVersions.{timestr}.csv"
    print(f"creating savepoint in {filename}")

    lines = []
    for org in tqdm(orgs, desc='Organizations', unit='org', total=len(orgs)):
        #print(f"ORG IN SAVE POINT {org}")
        org_slug = org.slug
        org_id = org.id
        pythonVersion = get_python_version(driver, org_slug)
        lines.append([org_id, org_slug, pythonVersion])

    write_python_version_csv(lines, filename)

    print(f"\nsavepoint created in {filename} - press enter to continue")
    input('>_ ')

def restore_save_point(driver, filename):
    print(f"Attempting to restore previous save point {filename} - will back up first")

    #get orgs from file
    with open(filename, newline='') as csvfile:
        Lines = list(csv.reader(csvfile))

    orgs = []
    count=0
    for line in Lines:
        print(f"Line: {line}")
        if count != 0:
            next_org = {
                'id':line[0],
                'slug':line[1],
            }
            orgs.append(next_org)
        count+=1
    csvfile.close()

    print("\nPress enter after verifying above")
    input('>_ ')

    #back up orgs from file
    print(f"press enter to create save point for the orgs in backup file: {orgs}")
    input('>_ ')

    #creates a save point for current version of all the orgs we're about to restore
    create_save_point(driver, orgs)

    #loop through file and set to previous version
    with open(filename, newline='') as csvfile:
        Lines = list(csv.reader(csvfile))

    orgs = []
    for line in Lines:
        print(f"Line: {line}")
    csvfile.close()

    exit

def main():
    if "SNYK_TOKEN" not in os.environ or 'SNYK_GROUP' not in os.environ:
        print(f'Make sure to set ENV SNYK_TOKEN and SNYK_GROUP before running this script:')
        print(f'export SNYK_TOKEN=<TOKEN> (needs to have wide access, probably org admin)')
        print(f'export SNYK_GROUP=<GROUP_ID>')
        print("")
        sys.exit()

    # Variables for the type of deps you want
    parser = argparse.ArgumentParser("update python versions")
    parser.add_argument("--DANGER-UPDATE-ALL", help="This will OVERRIDE existing Python versions, be careful",action='store_true', default=False)
    parser.add_argument("--save", help="This will save all python versions currently in SNYK_GROUP",action='store_true', default=False)
    parser.add_argument("--restore", help="This will restore an old version, it will create another backup first",action='store')
    args = parser.parse_args()

    if args.DANGER_UPDATE_ALL:
        global OVERRIDE_ALL
        OVERRIDE_ALL=True
        print("OVERRIDE ALL SET")

    # Set up Selenium
    driverPath = ChromeDriverManager().install()
    service = Service(executable_path=driverPath)
    driver = webdriver.Chrome(service=service)

    loginURL = 'https://app.snyk.io'

    print('Loading Snyk login page....')
    driver.get(loginURL)

    if 'app.snyk.io/login' in driver.current_url:
        print('Please Login to Snyk')
        WebDriverWait(driver, timeout=120).until(
            EC.url_contains('app.snyk.io/org/'))
        
        driver.minimize_window()

        #save org settings and exit
        if args.save:
            orgs = get_org_names()
            print(f'Press ENTER to create savepoint: ')
            input('>_ ')
            create_save_point(driver, orgs)
            sys.exit()

        #restoring old org settings - will create backup first 
        if args.restore:
            filename = args.restore
            restore_save_point(driver, filename)
            sys.exit()

        print(f'\n***VERIFY*** Will attempt to set orgs to {minPythonVersion} - please change at top of script if you would like a different version\n')
        print(f'Press ENTER to get Snyk orgs: ')
        input('>_ ')
        orgs = get_org_names()

        time.sleep(1)
        csrf_token_element = driver.find_element(By.NAME, '_csrf')
        csrf_token = csrf_token_element.get_attribute('value')

        print(f'Press ENTER to SET each org python version to: {minPythonVersion}')
        if OVERRIDE_ALL == True:
            print(f'OVERRIDE is on, this will OVERRIDE the current version even if it is higher')
        else:
            print(f'OVERRIDE is off, if the current version is the same or higher, nothing will be changed')

        input('>_ ')

        set_org_python_versions(driver, csrf_token, orgs)

if __name__ == "__main__":
    main()
