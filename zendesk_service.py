import ast
import json
import os
import requests
import variables
from requests.auth import HTTPBasicAuth

HEADERS = {'content-type': 'application/json'}
TICKETS_EP = f'{variables.zendesk_url}/{variables.zendesk_tickets_ep}'
USERS_EP = f'{variables.zendesk_url}/{variables.zendesk_users_ep}'
AUTH = HTTPBasicAuth(variables.zendesk_user, variables.zendesk_token)


def cache_ticket_fields():
    if not os.path.exists('zd_ticket_fields'):
        fields_raw = get_ticket_fields()
        fields_json = json.loads(fields_raw)
        fields = {item.get('title'): item.get('id') for item in fields_json.get('ticket_fields')}
        with open('zd_ticket_fields', 'w') as outf:
            outf.write(str(fields))


def get_ticket(ticket_id: str):
    url = f'{TICKETS_EP}/{ticket_id}.json'
    return requests.get(url, auth=AUTH).text


def get_ticket_fields():
    url = f'{variables.zendesk_url}/{variables.zendesk_ticket_fields_ep}'
    return requests.get(url, auth=AUTH).text


def internal_comment_on_ticket(ticket_id: str, comment: str, user_id: str):
    """
    :param ticket_id: ticket id
    :param comment: comment to put
    :param user_id: id of user making the comment
    :return: result
    """
    data = {"ticket": {"comment": {"body": comment, "author_id": user_id, "public": False}}}
    return requests.put(f'{TICKETS_EP}/{ticket_id}.json', auth=AUTH, data=json.dumps(data), headers=HEADERS).text


def find_user(query: str):
    """
    :param query: query, e.g. "aerin"
    :return: result
    """
    return requests.get(f'{USERS_EP}/search', params={'query': query}, auth=AUTH, headers=HEADERS)


def update_custom_field(ticket_id: str, value: str, field_id: str = None, field_name: str = None):
    """
    Update a specific custom field for test ticket. MUST have either an ID or a name; name overrides ID

    :param ticket_id: ticket id
    :param value: value of custom field
    :param field_id: ID of the field, if name not given
    :param field_name: name of the field
    :return:
    """
    if not field_id and not field_name:
        raise Exception('You must provide either a field ID or a field name to update_custom_field!')
    if field_name:
        cache_ticket_fields()
        with open('zd_ticket_fields', 'r') as inf:
            fields = ast.literal_eval(inf.read())
            id_from_name = fields.get(field_name)
        data = {'ticket': {'custom_fields': [{'id': id_from_name, 'value': value}]}}
    else:
        data = {'ticket': {'custom_fields': [{'id': field_id, 'value': value}]}}
    return requests.put(f'{TICKETS_EP}/{ticket_id}.json', auth=AUTH, data=json.dumps(data), headers=HEADERS).text


def update_custom_fields(ticket_id: str, updates: list):
    """
    :param ticket_id: ticket id
    :param updates: a list of dicts in the format  [{'id': 'field_id', 'value': 'your update'},{},...]
    :return: result
    """
    data = {'ticket': {'custom_fields': updates}}
    return requests.put(f'{TICKETS_EP}/{ticket_id}.json', auth=AUTH, data=json.dumps(data), headers=HEADERS).text
