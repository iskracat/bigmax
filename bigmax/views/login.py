# -*- coding: utf-8 -*-
from pyramid.httpexceptions import HTTPFound

from pyramid.view import view_config
from pyramid.url import resource_url
from pyramid.view import forbidden_view_config

from pyramid.security import remember, forget
from pyramid.settings import asbool

from pyramid_ldap import get_ldap_connector
from bigmax.views.api import TemplateAPI
from bigmax.utils import normalize_userdn
import requests
import json
import logging
import re


def real_request_url(request):
    request_scheme = re.search(r'(https?)://', request.url).groups()[0]
    if request.get('HTTP_X_VIRTUAL_HOST_URI'):
        real_scheme = re.search(r'(https?)://', request.get('HTTP_X_VIRTUAL_HOST_URI')).groups()[0]
        return request.url.replace(request_scheme, real_scheme)
    else:
        return request.url


@view_config(name='login', renderer='bigmax:templates/login.pt')
@forbidden_view_config(renderer='bigmax:templates/login.pt')
def login(context, request):
    """ The login view - pyramid_ldap enabled with the forbidden view logic.
    """
    page_title = "BIG MAX Login"
    api = TemplateAPI(context, request, page_title)
    enable_ldap = asbool(request.registry.settings.get('enable_ldap'))
    max_settings = request.registry.max_settings
    logger = logging.getLogger('bigmax')

    login_url = api.application_url + '/login'
    referrer = real_request_url(request)
    if referrer.endswith('login'):
        referrer = api.application_url  # never use the login form itself as came_from

    came_from = request.params.get('came_from', referrer)
    message = ''
    login = ''
    password = ''

    if request.params.get('form.submitted', None) is not None:
        # identify
        login = request.POST.get('login')
        password = request.POST.get('password')

        if login is u'' or password is u'':
            return dict(
                    message='You need to suply an username and a password.',
                    url=api.application_url+'/login',
                    came_from=came_from,
                    login=login,
                    password=password,
                    api=api
                    )

        if enable_ldap:
            connector = get_ldap_connector(request)
            data = connector.authenticate(login, password)
            if data:
                dn = data[0]
                headers = remember(request, dn)
                auth_user = normalize_userdn(dn)
            # if not successful, try again
            else:
                return dict(
                        message='Login failed. Please try again.',
                        url=api.application_url+'/login',
                        came_from=came_from,
                        login=login,
                        password=password,
                        api=api
                        )
        else:
            # Harcoded developer user
            # Try to suck less here in the future...
            auth_user = login
            headers = remember(request, auth_user)

        # Access the MAX API to look for the auth user
        requser = requests.post('%s/people/%s' % (max_settings.get('max_server'), auth_user), auth=(max_settings.get('max_ops_username'), max_settings.get('max_ops_password')), verify=False)

        if requser.status_code == 201:
            logger.info("User %s created successfully in MAX server." % auth_user)
        elif requser.status_code == 200:
            logger.info("User %s logged in." % auth_user)
        else:
            logger.error("Something wrong happened while accessing MAX server and authenticating %s user." % auth_user)

        subs_payload = {"object": {"url": max_settings.get('max_server'), "objectType": "context"}}

        # Subscribe automatically the logged in user to the default context
        reqsubs = requests.post('%s/people/%s/subscriptions' % (max_settings.get('max_server'), auth_user), data=json.dumps(subs_payload), auth=(max_settings.get('max_ops_username'), max_settings.get('max_ops_password')), verify=False)

        if reqsubs.status_code == 201:
            logger.info("User %s subscribed successfully in default MAX context." % auth_user)
        elif requser.status_code == 400:
            logger.info("User %s already subscribed to default context." % auth_user)
        else:
            logger.error("Something wrong happened while accessing MAX server and subcribing %s user to default context." % auth_user)

        # Request token for auth user
        payload = {"grant_type": max_settings.get('max_oauth_grant_type'),
                   "client_id": max_settings.get('max_oauth_clientid'),
                   "scope": max_settings.get('max_oauth_scope'),
                   "username": auth_user,
                   "password": password
                   }

        req = requests.post(max_settings.get('max_oauth_token_endpoint'), data=payload, verify=False)
        response = json.loads(req.text)
        oauth_token = response.get("oauth_token")

        # Store the user's oauth token in the current session
        request.session['oauth_token'] = oauth_token

        # Finally, return the authenticated view
        return HTTPFound(headers=headers, location=came_from)

    return dict(
            message=message,
            url=api.application_url+'/login',
            came_from=came_from,
            login=login,
            password=password,
            api=api
            )


@view_config(name='logout')
def logout(request):
    headers = forget(request)
    return HTTPFound(location=request.headers.get('X-Virtual-Host-Uri', '/'),  headers=headers)
