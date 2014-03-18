# -*- coding: utf-8 -*-
from pyramid.view import view_config

from bigmax.views.api import TemplateAPI
from bigmax.resources import MaxServer

from pygments import highlight
from pygments.lexers import JsonLexer, HttpLexer
from pygments.formatters import HtmlFormatter

import requests
import urllib
import json


@view_config(context=MaxServer, route_name="endpoints", renderer='bigmax:templates/endpoints.pt', permission='restricted')
def endpoints_view(context, request):
    page_title = "BIG MAX Exception Log"
    api = TemplateAPI(context, request, page_title)

    return dict(api=api,
                url='%s/api' % api.application_url)


@view_config(context=MaxServer, route_name="endpoints_data", renderer='json', permission='restricted')
def endpoints_data(context, request):
    endpoints = context.maxclient.endpoints.get()

    endpoints_by_category = {}

    for route_name, route_info in endpoints.items():
        endpoints_by_category.setdefault(route_info['category'], [])
        endpoints_by_category[route_info['category']].append(route_info)

    sorted_categories = endpoints_by_category.keys()
    sorted_categories.sort()

    categories = []
    for category_name in sorted_categories:

        routes = []
        for route_info in endpoints_by_category[category_name]:
            routes.append({
                'route_id': route_info['id'],
                'route_name': route_info['name'],
                'route_url': route_info['url'],
                'methods': route_info['methods']
            })
        category = {
            'name': category_name,
            'id': category_name.lower().replace(' ', '-'),
            'resources': sorted(routes, key=lambda route: route['route_name'])
        }
        categories.append(category)
    return categories


@view_config(context=MaxServer, route_name="endpoints_request", renderer='json', permission='restricted', request_method='POST')
def endpoints_request(context, request):

    import httplib

    raw = []

    def save_request(data):
        raw.append(data)

    def patch_send():
        old_send = httplib.HTTPConnection.send

        def new_send(self, data):
            save_request(data)
            response = old_send(self, data)
            return response
        httplib.HTTPConnection.send = new_send

    patch_send()

    requests.get("http://www.python.org")

    url = context.max_server + urllib.unquote(request.json['url'])
    for param, value in request.json['url_params'].items():
        url = url.replace(param, value)
    request_method = request.json['method'].lower()
    requester = getattr(requests, request_method)

    params = {
        'headers': request.json['headers'],
        'verify': False,
    }

    if request_method == 'POST':
        params['data'] = request.json['postdata']

    response = requester(url, **params)
    response_headers = '\r\n'.join(['{}: {}'.format(k.capitalize(), v) for k, v in sorted(response.raw.getheaders().items(), key=lambda x: x[0])]) + '\r\n\r\n'
    response_headers = raw[-1].split('\r\n')[0] + '\r\n' + response_headers
    response_headers_html = highlight(response_headers, HttpLexer(), HtmlFormatter(style='friendly'))
    first_line = response_headers_html.find('<span class="nf">GET</span>')
    last_line = response_headers_html.find('<span class="m">1.1</span>') + 26

    response_headers_html = response_headers_html[:first_line] + response_headers_html[last_line:]
    if 'text/html' in response.headers['content-type']:
        response_html = highlight(response.content, HttpLexer(), HtmlFormatter(style='friendly')),
        response_type = 'html'
        response_content = response.content

    elif 'application/json'in response.headers['content-type']:
        pretty_json = json.dumps(json.loads(response.content), indent=4)
        response_html = highlight(pretty_json, JsonLexer(), HtmlFormatter(style='friendly'))
        response_content = response.content
        response_type = 'json'

    elif 'image/'in response.headers['content-type']:
        response_type = 'image'
        encoded_image = response.content.encode("base64").replace("\n", "")
        image_data = 'data:image/png;base64,' + encoded_image
        response_html = '<img alt="" src="{}" />'.format(image_data)
        response_content = "Sorry, can't display binary image data"

    else:
        response_html = response.content
        response_content = response.content

    json_response = {
        # request = highlight(exception_report['request'], HttpLexer(), HtmlFormatter(style='friendly')),
        # response_headers = highlight(exception_report['request'], HttpLexer(), HtmlFormatter(style='friendly')),
        'response_type': response_type,
        'response_html': response_html,
        'response_raw': response_content,
        'request_headers': highlight(raw[-1], HttpLexer(), HtmlFormatter(style='friendly')),
        'response_headers': response_headers_html
    }
    return json_response