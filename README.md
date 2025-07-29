# What is this script for? <br>

This script will update python versions across a SNYK_GROUP
You may also save, and restore old versions

Restore is not currently implemented

## Prerequisites:
- Python 3.9+
- Snyk Token
- Chrome

## Installation instructions:
Clone this repo and run <pre><code>pip3 install -r requirements.txt</pre></code><br>

## How do I use this script?<br>
Edit the Python version at the top of the script.  This will set all orgs to this version at MINIMUM.  If it is already higher, it will leave it higher.

```shell
python3 ./snyk-update-python-version.py
```
#### Script Options:
--help
    will print these help options

--DANGER-UPDATE-ALL
    - default behaviour is to ignore an org with a higher python version than you are setting this to.  This option will FORCE all orgs to the version you set it to.  This is dangerous.  Use at your own risk.

--save
    - will save a backup of orgs for SNYK_GROUP in save_points/<date>.csv

--restore
    - not yet implemented

### *** This script will open a Chrome window and direct you to login Snyk ***

## CSV Example:
