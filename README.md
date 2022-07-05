
# About this project

## What it does
This is a series of functions that uses the Google API to move stuff around. It recursively moves all folders and files under a folder into a Shared Drive, since you can't move folders to shared Drives (see below). Some folders needed to be renamed in the move, so a folder map is referenced to rename those as they are moved.

There is also a set of functions to handle a few basic Zendesk actions. 

The drive service and zendesk service classes are written for re-use in the future should the need arise. All custom logic should be in main. 

The benefit of using it is not having to deal with writing code for authentication, pagination, and basic functions that don't exist in the API like moving multiple files around with one function. It also logs and handles common errors. 

## Why the Google API is stupid
"Dear user trying to automate with our API to avoid **MANUALLY** moving 20,000 folders into your shared drive, `"Moving folders into shared drives is not supported.". Details: "[{'domain': 'global', 'reason': 'teamDrivesFolderMoveInNotSupported', 'message': 'Moving folders into shared drives is not supported.'}]">`. @#!$ you." -- Google, apparently

# "Moving" files/folders
Moving files in Google Drive means simply removing one parent and adding another. 

Note: Google Drive API v3 treats files like Linux does: everything is a file. Thus, a folder is a file. Listing "files" also lists folders. 

## Parents
Regarding parent"s": https://developers.google.com/drive/api/v3/ref-single-parent
You used to be able to have more than 1 parent for a file. You can't now. That's why it's counter-intuitively plural.

# Resources
- https://developers.google.com/drive/api/v3/folder
- https://developers.google.com/drive/api/v3/quickstart/python
- ZD ticket comments: https://developer.zendesk.com/api-reference/ticketing/tickets/ticket_comments/
- custom fields: https://developer.zendesk.com/documentation/developer-tools/working-with-the-zendesk-apis/making-requests-to-the-zendesk-api/

## list()
response format: `{'kind': 'drive#fileList', 'nextPageToken': 'whatever', 'incompleteSearch': False, 'files': [{},{}]}`
- the `files` field is a list of the same dicts returned when you call `get()`

code: `response = service.files().list(q=query_string).execute()`

## get()
response format: `{'kind': 'drive#file', 'id': 'an id', 'name': 'file name', 'mimeType': '...'}`
- if it's a folder, the mimeType `application/vnd.google-apps.folder` will indicate this; the "kind" is always `drive#file`

code: `response = service.files().get(fileId='...',fields='..., ...').execute()`

## query strings
https://developers.google.com/drive/api/v3/fields-parameter

## Authenticating

### Note on refresh tokens (important) 
Drive API only gives you a refresh token for refreshing credentials one time: the first time you ever authenticate to it. **Do not ever delete token.json**. The next token.json which the API process creates will not include that token, which means you'll have to open a local server to authenticate every single time, and your app will never be able to run longer than the token lasts because it will never refresh. If you ever accidentally do this, you must do the following: 
1. visit https://myaccount.google.com/permissions and remove your project's access to your account
2. Close the browser completely
3. Run your code again, it will ask you to re-authenticate.

Alternatively, you can add the query parameters `prompt=consent&access_type=offline` to the OAuth redirect (see Google's OAuth 2.0 for Web Server Applications page), which will ask you to re-authenticate and return a refresh token.

See https://stackoverflow.com/a/10857806. 

### Where to get an auth file
1. You have to create a project at https://console.cloud.google.com/
2. Go to "Enable API's and Services" (currently in Dashboard view) and enable Drive
3. Go to the Credentials tab and create OAuth 2.0 creds. Download the file
