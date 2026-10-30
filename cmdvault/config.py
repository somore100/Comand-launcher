"""config -- split out of the former monolithic main.py."""



APP_NAME = "Command Vault"
APP_VERSION = "1.7.0"
GITHUB_REPO = "somore100/Comand-launcher"  # typo in repo name is intentional, cosmetic only

# "Leave Feedback" (see feedback.py). Reports go to the relay when its URL is
# set, otherwise the user's own mail app is opened. The token is a shared
# secret for the relay only -- never put an email password or API key here.
SUPPORT_EMAIL = "support.somore100@gmail.com"
FEEDBACK_RELAY_URL = ""    # paste the Apps Script web-app URL here (examples/feedback_relay.gs)
FEEDBACK_RELAY_TOKEN = ""  # same value as TOKEN in the script
